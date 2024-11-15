import base64
import logging
import requests
import aiofiles
from celery import Celery
from core.utils import save_detection
import aiohttp

# Инициализация объекта Celery
celery_app = Celery("tasks", broker="pyamqp://guest:guest@localhost//")
# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Настройка RabbitMQ


@celery_app.task
def process_image_task(image_id: int):
    logger.info("Задача начата для изображения с ID: %d", image_id)

    # Здесь бы выполнялась обработка изображения
    logger.info("Изображение %d обработано успешно", image_id)

    return f"Image {image_id} processed successfully"




@celery_app.task(acks_late=True)
async def process_detection_task(image_id : int, image_url : str, image_api_url: str): #
    logger.info("Задача детекции начата для изображения с ID: %s", image_url)

    async with aiohttp.ClientSession() as session:
        with open(image_url, "rb") as file:
            files = {"image": file}

        async with session.post(image_api_url, data=files) as response:
            if response.status == 200:
                json_response = await response.json()
                await save_detection(image_id, json_response)
                logger.info("Изображение %d обработано успешно", image_id)
            else:

                logger.error(f"Ошибка на этапе детекции, image_id {image_id}, \
                             response_status {response.status}, {response.text}")

                print(f"Error while detection stage, image_id {image_id}: {response.status}, {await response.text()}")

    return f"Image {image_url} processed successfully"


# template for future developing
# переделаем под получение шаблона
# надо переделать под шаблон
@celery_app.task(acks_late=True)
async def process_template_task(image_id : int, image_url : str, additional_data, image_api_url: str): #
    logger.info("Задача шаблона начата для изображения с ID: %s", image_url)

    async with aiofiles.open(image_url, "rb") as file:
        img = await file.read()
    # get base64
    image_data = base64.b64encode(img)
    detection = requests.post(image_api_url, image_data)         #  надо переделать отправку
    await save_detection(image_id=image_id, detection=detection)


    logger.info("Изображение %d обработано успешно", image_url)

    return f"Image {image_url} processed successfully"
