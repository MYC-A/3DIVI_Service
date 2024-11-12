import logging
from celery import Celery


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