import os
import json
import base64
import logging
import requests
import psycopg2
from celery.bin.control import status
from psycopg2 import pool
from celery import Celery
from kombu import Connection
from dotenv import load_dotenv
from sqlalchemy.sql import text

from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from sqlalchemy import update, and_

from celery_db import sync_session
from core.utils import sync_get_next_image_by_task_id
from models import Task, ImageData

# Инициализация объекта Celery
celery_app = Celery("tasks", broker="pyamqp://guest:guest@localhost//")
# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

load_dotenv()

# берем данные БД из .env файлика

username=os.getenv('db_username')
password=os.getenv('db_password')
host=os.getenv('db_host')
db_port=os.getenv('db_port')
db_name=os.getenv('db_name')
port=os.getenv('db_port')

# Вместо работы с пулом подключений - работаем с сессиями
@celery_app.task(name='task.controller.controller')
def controller():
    task_id, task_status = get_oldest_requested_task()

    if not task_status:
        return 0

    logger.info(f'task_id : {task_id} | {type(task_id)}')

    if not task_id:
        logger.info('Controller waiting for requests')
        return 'Waiting for requests'

    logger.info('Current status of requested task: ' + task_status)

    task_count = 0
    for queue in ['queue_detection', 'queue_template', 'queue_quality']:
        task_count += check_queue_task_count(queue)

    logger.info(f'task count, {task_count}, {type(task_count)}')
    if task_count != 0:
        logger.info('Controller waiting for empty queue')
        return 'Controller waiting for empty queue'

    if task_status == 'pending':

        update_task_status(task_id, 'image_detection_started')

        task = celery_summon_images_detection_task.apply_async(args=[task_id], queue='queue_detection')

        logger.info(f'Controller has started a new detection task for task_id {task_id}, celery task id is {task.id}')

    elif task_status == 'image_detection_started':

        update_task_status(task_id, 'template_extraction_started')

        task = celery_summon_template_extraction_task.apply_async(args=[task_id], queue='queue_template')
        logger.info(
            f'Controller has started a new template extraction task for task_id {task_id}, celery task id is {task.id}')

    elif task_status == 'template_extraction_started':

        update_task_status(task_id, 'quality_estimation_started')

        task = celery_summon_quality_estimation_task.apply_async(args=[task_id], queue='queue_quality')
        logger.info(
            f'Controller has started a new quality estimation task for task_id {task_id}, celery task id is {task.id}')

    elif task_status == 'quality_estimation_started':
        logger.info(f'TASK DONE!')
        update_task_status(task_id, 'done')


def summon_images_task(task_id: int, api_stage: str):
    data_stages = os.getenv('stages_of_preparing')

    assert api_stage in data_stages, f'Stage must be from list of possible stages: {data_stages}'

    logger.info(f"Requested summon_images_task with task_id {task_id} and api_stage {api_stage}")

    session = sync_session()
    processed_images_count = 0
    last_processed_id = None

    try:
        while True:
            # Извлекаем следующее изображение через ORM
            image = session.query(ImageData).filter(
                ImageData.task_id == task_id,
                ImageData.id > (last_processed_id or 0)
            ).order_by(ImageData.id).first()  # Получаем следующее изображение

            if image is None:
                # Если изображений больше нет, завершаем цикл
                break

            img_id = image.id
            img_path = image.image_path
            img_additional_data = image.additional_data

            logger.info(f"Retrieved next image of task {task_id}; {processed_images_count if processed_images_count else 0}")
            logger.info(f"img_id: {img_id}\nimg_additional_data: {type(img_additional_data), len(str(img_additional_data))}")

            # В зависимости от стадии, выбираем соответствующий API
            if api_stage == 'detection':
                api_url = os.getenv('image_api_detection_url')
                process_image_detection_task.apply_async(args=[img_id, img_path, img_additional_data, api_url],
                                                         queue='queue_detection')
            elif api_stage == 'template':
                api_url = os.getenv('image_api_template_url')
                process_template_extraction_task.apply_async(
                    args=[img_id, img_path, img_additional_data, api_url], queue='queue_template')
            elif api_stage == 'quality':
                api_url = os.getenv('image_api_quality_url')
                process_quality_estimation_task.apply_async(
                    args=[img_id, img_path, img_additional_data, api_url], queue='queue_quality')

            # Обновляем последний обработанный ID
            last_processed_id = img_id
            processed_images_count += 1

        return {"message": f"Processing task on stage {api_stage} started for task_id: {task_id}"}
    except Exception as ex:
        logger.error(f"Error in summon_images_task: {ex}")
        return {"error": str(ex)}
    finally:
        session.close()


@celery_app.task(name='tasks.detection.process_detection', acks_late=True)
def process_image_detection_task(img_id, img_path, img_additional_data, api_url: str):
    session = sync_session()
    try:
        logger.info("Начато получение детекции изображения с ID: %s", img_id)
        logger.info("Запрос на api_url %s", api_url)
        logger.info("Путь к изображению: %s", img_path)

        with open(img_path, "rb") as file:
            img = file.read()

        image_data = base64.b64encode(img).decode("utf-8")

        if not image_data:
            logger.error("Base64-данные изображения не были сформированы.")
            raise ValueError("Base64-данные изображения не были сформированы.")

        #logger.info("Дополнительные данные изображения: %s", img_additional_data)

        payload = {
            "image": {
                "blob": image_data,
                "format": "IMAGE",
            },
            "objects": img_additional_data if img_additional_data else [{}],
        }

        headers = {
            "Content-Type": "application/json",
        }

        response = requests.post(api_url, json=payload, headers=headers, verify=False)
        if response.status_code != 200:
            logger.error("Ошибка API: %s", response.text)
            raise ValueError(f"API вернул ошибку: {response.status_code}, {response.text}")

        api_result = response.json()
        logger.info("Ответ API успешно получен")

        detection_data = api_result.get("objects", [])
        image = session.query(ImageData).filter_by(id=img_id).first()

        image.additional_data = detection_data
        session.commit()

        logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

    except Exception as e:
        logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
        session.rollback()
    finally:
        session.close()

    return f"Детекция изображения {img_id} получена успешно"


def update_task_status(task_id: int, task_status: str):
    allowed_statuses = [
        'not_requested', 'pending', 'image_detection_started',
        'template_extraction_started', 'quality_estimation_started', 'done'
    ]

    if task_status not in allowed_statuses:
        raise ValueError(f"Invalid status: {task_status}, allowed ones are {allowed_statuses}")

    session = sync_session()

    try:
        # ORM-based update
        stmt = update(Task).where(Task.id == task_id).values(status=task_status)
        session.execute(stmt)
        session.commit()
        logger.debug(f'Successfully updated task id={task_id} to status={task_status}')
    except Exception as ex:
        logger.debug(f'Exception in update_task_status: {ex}')
        session.rollback()
    finally:
        session.close()


@celery_app.task(name='tasks.template.process_template', acks_late=True)
def process_template_extraction_task(img_id, img_path, img_additional_data, api_url: str):
    session = sync_session()
    try:
        logger.info("Начата обработка изображения с ID: %s", img_id)
        logger.info("Запрос на api_url %s", api_url)
        logger.info("Путь к изображению: %s", img_path)

        with open(img_path, "rb") as file:
            img = file.read()

        image_data = base64.b64encode(img).decode("utf-8")

        if not image_data:
            logger.error("Base64-данные изображения не были сформированы.")
            raise ValueError("Base64-данные изображения не были сформированы.")

        #logger.info("Дополнительные данные изображения: %s", img_additional_data)

        payload = {
            "image": {
                "blob": image_data,
                "format": "IMAGE",
            },
            "objects": img_additional_data,
        }

        headers = {
            "Content-Type": "application/json",
        }

        response = requests.post(api_url, json=payload, headers=headers, verify=False)
        if response.status_code != 200:
            logger.error("Ошибка API: %s", response.text)
            raise ValueError(f"API вернул ошибку: {response.status_code}, {response.text}")

        api_result = response.json()
        logger.info("Ответ API успешно получен: %s", api_result)

        detection_data = api_result.get("objects", [])
        template_data = api_result.get("template", None)

        # Сохраняем результат в БД
        image = session.query(ImageData).filter(ImageData.id == img_id).first()
        if image:
            image.additional_data = json.dumps(detection_data)
            session.commit()

        logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

    except Exception as e:
        logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
        session.rollback()
    finally:
        session.close()

    return f"Детекция изображения {img_id} получена успешно"


@celery_app.task(name='tasks.quality.process_quality', acks_late=True)
def process_quality_estimation_task(img_id, img_path, img_additional_data, api_url: str):
    session = sync_session()
    try:
        logger.info("Начата обработка изображения с ID: %s", img_id)
        logger.info("Запрос на api_url %s", api_url)
        logger.info("Путь к изображению: %s", img_path)

        with open(img_path, "rb") as file:
            img = file.read()

        image_data = base64.b64encode(img).decode("utf-8")

        if not image_data:
            logger.error("Base64-данные изображения не были сформированы.")
            raise ValueError("Base64-данные изображения не были сформированы.")

        #logger.info("Дополнительные данные изображения: %s", img_additional_data)

        payload = {
            "_image": {
                "blob": image_data,
                "format": "IMAGE",
            },
            "objects": img_additional_data if isinstance(img_additional_data, list) else [],
        }

        headers = {
            "Content-Type": "application/json",
        }

        response = requests.post(api_url, json=payload, headers=headers, verify=False)
        if response.status_code != 200:
            logger.error("Ошибка API: %s", response.text)
            raise ValueError(f"API вернул ошибку: {response.status_code}, {response.text}")

        api_result = response.json()
        logger.info("Ответ API успешно получен: %s", api_result)

        detection_data = api_result.get("objects", [])
        template_data = api_result.get("template", None)

        # Сохраняем результат в БД
        image = session.query(ImageData).filter(ImageData.id == img_id).first()
        if image:
            image.additional_data = json.dumps(detection_data)
            session.commit()

        logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

    except Exception as e:
        logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
        session.rollback()
    finally:
        session.close()

    return f"Детекция изображения {img_id} получена успешно"


@celery_app.task(name='tasks.quality.summon_quality', acks_late=True)
def celery_summon_quality_estimation_task(task_id: int):
    summon_images_task(task_id, 'quality')

def check_queue_task_count(queue_name):
    rabbitmq_url = "pyamqp://guest:guest@localhost//"  # потом надо поменять на os.getenv('rabbit_mq_url')

    try:
        with Connection(rabbitmq_url) as conn:
            channel = conn.channel()
            queue = channel.queue_declare(queue=queue_name,
                                          passive=True)
            message_count = queue.message_count
            print('MESSAGE COUNT: ', message_count)
            return message_count

    except Exception as e:
        print(f"Ошибка при подключении к RabbitMQ: {e}")
        return 0


@celery_app.task(name='tasks.detection.summon_detection', acks_late=True)
def celery_summon_images_detection_task(task_id: int):
    summon_images_task(task_id, 'detection')


@celery_app.task(name='tasks.template.summon_template', acks_late=True)
def celery_summon_template_extraction_task(task_id: int):
    summon_images_task(task_id, 'template')

def get_oldest_requested_task():
    session = sync_session()
    try:
        # Извлекаем самую старую задачу с состоянием 'pending'
        oldest_task = session.query(Task).filter(Task.status != 'not_requested', Task.status != 'done').order_by(Task.timestamp_of_request.asc()).first()

        if oldest_task:
            logger.info(f"Найдена самая старая задача: task_id={oldest_task.id}, request_time={oldest_task.timestamp_of_request}")
            id = oldest_task.id
            status = oldest_task.status

        else:
            logger.info("Нет задач со статусом 'pending'")
            id =  None
            status = None
        return id,status
    except Exception as e:
        logger.error(f"Ошибка при извлечении самой старой задачи: {str(e)}")
        return None,None
    finally:
        session.close()
