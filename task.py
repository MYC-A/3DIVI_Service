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

# Инициализация объекта Celery
celery_app = Celery("tasks", broker="pyamqp://guest:guest@localhost//")
# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Настройка RabbitMQ


@celery_app.task
def process_image_task(task_id: int):
    """
    Задача Celery для обработки изображений.
    """
    # Получаем event loop для выполнения асинхронного кода
    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_images_celery(task_id))

async def process_images_celery(task_id: int):
    """
    Асинхронная часть задачи Celery.
    """
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
            await process_image(image,session,"https://demo.3divi.ai/face-detector-face-fitter/v2/process/sample")

            # Обновляем последний обработанный ID
            last_processed_id = image.id
            processed_images_count += 1

        print(f"Celery task completed: Processed {processed_images_count} images for task_id {task_id}")


async def process_image(image, session: AsyncSession, api_url: str):
    try:
        logger.info("Начата обработка изображения с ID: %s", image.id)

        logger.info(image.image_path)
        # Чтение изображения
        async with aiofiles.open(image.image_path, "rb") as file:
            img = await file.read()

        # Преобразование изображения в base64
        image_data = base64.b64encode(img).decode("utf-8")
        logger.info("Base64-кодирование изображения завершено.")

        # Проверка на наличие данных
        if not image_data:
            logger.error("Base64-данные изображения не были сформированы.")
            raise ValueError("Base64-данные изображения не были сформированы.")
        logger.info(image.additional_data)
        if not image.additional_data:

            logger.info("Запрос с картинкой")

            # Формирование данных для запроса
            payload = {
                "image": {  # Обратите внимание на корректность ключа
                    "blob": image_data,
                    "format": "IMAGE",
                },
                "objects": [{}],  # Добавьте или удалите в зависимости от требований API
            }
        if image.additional_data:
            logger.info("Запрос с данными и картинкой")

            payload = {
                "image": {  # Обратите внимание на корректность ключа
                    "blob": image_data,
                    "format": "IMAGE",
                },
                "objects": image.additional_data,  # Добавьте или удалите в зависимости от требований API
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
            image_id=image.id,
            detection=detection_data,
            template=template_data,
        )
        session.add(detection_entry)
        await session.commit()
        logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", image.id)

    except Exception as e:
        logger.error("Ошибка при обработке изображения с ID %s: %s", image.id, str(e))
        await session.rollback()
        raise

    return f"Изображение {image.id} обработано успешно"

