import asyncio
import base64
import logging
import aiohttp
import aiofiles
from celery import Celery
from sqlalchemy.ext.asyncio import AsyncSession

from core.utils import save_detection, get_next_image_by_task_id
from database import async_session
from models import DetectionData
from dotenv import load_dotenv
import os

# Инициализация объекта Celery
celery_app = Celery("tasks", broker="pyamqp://guest:guest@localhost//")
# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# Настройка RabbitMQ
@celery_app.task
def process_image_task(img_id, img_path, img_additional_data, api_url: str):
    """
    Задача Celery для обработки изображений.
    """
    # Получаем event loop для выполнения асинхронного кода
    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_image(img_id=img_id, img_path=img_path, img_additional_data=img_additional_data, api_url=api_url))


async def summon_images_task(task_id: int):
    """
    Метод API для запуска задачи обработки изображений.
    """

    load_dotenv()
    api_url = os.getenv('image_api_detection_url')

    async with async_session() as session:
        processed_images_count = 0
        last_processed_id = None

        while True:
            # Извлекаем следующее изображение
            image = await get_next_image_by_task_id(session, task_id, last_processed_id)

            if image is None:
                # Если изображений больше нет, завершаем цикл
                break

            # Выполнение обработки изображения
            img_id = image.id
            img_path = image.image_path
            img_additional_data = image.additional_data
            process_image_task.apply_async(args=[img_id, img_path, img_additional_data, api_url])

            # Обновляем последний обработанный ID
            last_processed_id = image.id
            processed_images_count += 1

    return {"message": f"Processing task started for task_id: {task_id}"}


async def process_image(img_id, img_path, img_additional_data, api_url):
    async with async_session() as session:
        try:
            logger.info("Начата обработка изображения с ID: %s", img_id)

            logger.info(img_path)
            # Чтение изображения
            async with aiofiles.open(img_path, "rb") as file:
                img = await file.read()

            # Преобразование изображения в base64
            image_data = base64.b64encode(img).decode("utf-8")
            logger.info("Base64-кодирование изображения завершено.")

            # Проверка на наличие данных
            if not image_data:
                logger.error("Base64-данные изображения не были сформированы.")
                raise ValueError("Base64-данные изображения не были сформированы.")
            logger.info(img_additional_data)
            if not img_additional_data:
                logger.info("Запрос с картинкой")

                # Формирование данных для запроса
                payload = {
                    "image": {  # Обратите внимание на корректность ключа
                        "blob": image_data,
                        "format": "IMAGE",
                    },
                    "objects": [{}],  # Добавьте или удалите в зависимости от требований API
                }
            else:
                logger.info("Запрос с данными и картинкой")

                payload = {
                    "image": {  # Обратите внимание на корректность ключа
                        "blob": image_data,
                        "format": "IMAGE",
                    },
                    "objects": img_additional_data,  # Добавьте или удалите в зависимости от требований API
                }

            if not payload.get("image"):
                logger.info("Base64-данные изображения не были сформированы.")

                raise ValueError("Отсутствуют данные изображения для отправки в API")

            headers = {
                "Content-Type": "application/json",
                # Добавьте токен авторизации, если требуется
                # "Authorization": f"Bearer {api_key}",
            }
            if not payload.get("image"):
                logger.error("Payload для отправки: %s", payload)
                raise ValueError("Отсутствуют данные изображения для отправки в API")

            # Отправка данных в API
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as http_session:
                async with http_session.post(api_url, json=payload, headers=headers) as response:
                    response_text = await response.text()
                    if response.status != 200:
                        logger.info("Ошибка API: %s", response_text)
                        raise ValueError(f"API вернул ошибку: {response.status}, {response_text}")

                    api_result = await response.json()
                    logger.info("Ответ API успешно получен: %s")

            # Сохранение данных в базу
            detection_data = api_result.get("objects", [])
            template_data = api_result.get("template", None)

            detection_entry = DetectionData(
                image_id=img_id,
                detection=detection_data,
                template=template_data,
            )
            session.add(detection_entry)
            await session.commit()
            logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

        except Exception as e:
            logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
            await session.rollback()
            raise

    return f"Изображение {img_id} обработано успешно"
