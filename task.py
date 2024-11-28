import os
import json
import base64
import logging
import requests
import psycopg2
from psycopg2 import pool
from celery import Celery
from kombu import Connection
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from core.utils import sync_get_next_image_by_task_id

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

# создаем пул подключений
connection_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=20,
    host=host,
    port=port,
    database=db_name,
    user=username,
    password=password
)


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
        logger.info(
            f'TASK DONE!')
        update_task_status(task_id, 'done')


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


def get_oldest_requested_task():
    connection = connection_pool.getconn()
    cursor = connection.cursor()

    query = """
        SELECT id, status
        FROM tasks
        WHERE status != 'not_requested' AND status != 'done'
        ORDER BY timestamp_of_request
        LIMIT 1
    """

    cursor.execute(query)
    try:
        result = cursor.fetchone()

        logger.debug(f'res {result} {type(result)}')
        if result:
            task_id, task_status = result
        else:
            task_id, task_status = None, None
        return task_id, task_status
    except Exception as ex:
        logger.debug(f'Exception in get_oldest_requested_tasl : {ex}')
        return None, None
    finally:
        if connection:
            connection_pool.putconn(connection)

def update_task_status(task_id: int, task_status: str):
    allowed_statuses = ['not_requested', 'pending', 'image_detection_started',
                        'template_extraction_started', 'quality_estimation_started', 'done']

    if task_status not in allowed_statuses:
        raise ValueError(f"Invalid status: {task_status}, allowed ones are {allowed_statuses}")

    connection = connection_pool.getconn()
    cursor = connection.cursor()

    try:
        query = """
            UPDATE tasks
            SET status = %s
            WHERE id = %s
        """
        cursor.execute(query, (task_status, task_id))
        connection.commit()
    except Exception as ex:
        logger.debug(f'Exception in update_task_status : {ex}')
        if connection:
            connection.rollback()
    finally:
        if connection:
            connection_pool.putconn(connection)

@celery_app.task(name='tasks.quality.summon_quality', acks_late=True)
def celery_summon_quality_estimation_task(task_id: int):
    summon_images_task(task_id, 'quality')

@celery_app.task(name='tasks.template.summon_template', acks_late=True)
def celery_summon_template_extraction_task(task_id: int):
    summon_images_task(task_id, 'template')

@celery_app.task(name='tasks.detection.summon_detection', acks_late=True)
def celery_summon_images_detection_task(task_id: int):
    summon_images_task(task_id, 'detection')


def summon_images_task(task_id: int, api_stage: str):
    data_stages = os.getenv('stages_of_preparing')

    assert api_stage in data_stages, f'Stage must be from list of possible stages: {data_stages}'

    logger.info(f"Requsted summon_images_task with tak_id {task_id} and api_stage {api_stage}")

    connection = connection_pool.getconn()

    processed_images_count = 0
    last_processed_id = None

    while True:
        # Извлекаем следующее изображение
        image = sync_get_next_image_by_task_id(connection, task_id, last_processed_id)

        if image is None:
            # Если изображений больше нет, завершаем цикл
            break

        # Выполнение обработки изображения
        img_id, img_path, img_additional_data = image

        logger.info(
            f"Retrieved next image of task {task_id}; {processed_images_count if processed_images_count else 0}")
        logger.info(
            f"img_id : {img_id}\n"
            f"img_additional_data : {type(img_additional_data), len(str(img_additional_data))}")

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

    if connection:
        connection_pool.putconn(connection)

    return {"message": f"Processing task on stage {api_stage} started for task_id: {task_id}"}

@celery_app.task(name='tasks.detection.process_detection', acks_late=True)
def process_image_detection_task(img_id, img_path, img_additional_data, api_url: str):
    connection = connection_pool.getconn()
    cursor = connection.cursor()
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

        logger.info("Дополнительные данные изображения: %s", img_additional_data)

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
        logger.info("Ответ API успешно получен: %s", api_result)

        detection_data = api_result.get("objects", [])
        template_data = api_result.get("template", None)
        query = sql.SQL("""
            UPDATE images
            SET additional_data = %s
            WHERE id = %s
        """)
        cursor.execute(query, [json.dumps(detection_data), img_id])
        connection.commit()

        logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

    except Exception as e:
        logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
        if connection:
            connection.rollback()
    finally:
        if connection:
            connection_pool.putconn(connection)

    return f"Детекция изображения {img_id} получена успешно"


@celery_app.task(name='tasks.template.process_template', acks_late=True)
def process_template_extraction_task(img_id, img_path, img_additional_data, api_url: str):
    connection = connection_pool.getconn()
    cursor = connection.cursor()
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

        logger.info("Дополнительные данные изображения: %s", img_additional_data)

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
        connection = connection_pool.getconn()
        query = sql.SQL("""
            UPDATE images
            SET additional_data = %s
            WHERE id = %s
        """)
        cursor.execute(query, [json.dumps(detection_data), img_id])
        connection.commit()

        logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

    except Exception as e:
        logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
        if connection:
            connection.rollback()
        raise
    finally:
        if connection:
            connection_pool.putconn(connection)

    return f"Детекция изображения {img_id} получена успешно"

@celery_app.task(name='tasks.quality.process_quality', acks_late=True)
def process_quality_estimation_task(img_id, img_path, img_additional_data, api_url: str):
    connection = connection_pool.getconn()
    cursor = connection.cursor()
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

        logger.info("Дополнительные данные изображения: %s", img_additional_data)

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
        connection = connection_pool.getconn()
        query = sql.SQL("""
            UPDATE images
            SET additional_data = %s
            WHERE id = %s
        """)
        cursor.execute(query, [json.dumps(detection_data), img_id])
        connection.commit()

        logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

    except Exception as e:
        logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
        if connection:
            connection.rollback()
        raise
    finally:
        if connection:
            connection_pool.putconn(connection)

    return f"Детекция изображения {img_id} получена успешно"