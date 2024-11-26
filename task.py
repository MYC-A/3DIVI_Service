import asyncio
import base64
import logging
import aiohttp
import aiofiles
from celery import Celery
from sqlalchemy.ext.asyncio import AsyncSession
from celery import shared_task
from database import get_async_session
from kombu import Connection
from core.utils import get_next_image_by_task_id
from database import async_session
from models import ImageData
from dotenv import load_dotenv
import os
from sqlalchemy.future import select
from sqlalchemy import update
from models import Task

# Инициализация объекта Celery
celery_app = Celery("tasks", broker="pyamqp://guest:guest@localhost//")
# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@celery_app.task(name='task.controller')
def controller():

    loop = asyncio.get_event_loop()
    task_id, task_status = loop.run_until_complete(get_oldest_requested_task())

    if not task_status:
        return 0

    if not task_id:
        logger.info('Controller waiting for requests')
        return 'Waiting for requests'

    logger.info('Current status of requested task: ' + task_status)
    task_count = check_queue_task_count()
    logger.info(f'task count, {task_count}, {type(task_count)}')
    if task_count != 0:
        logger.info('Controller waiting for empty queue')
        return 'Controller waiting for empty queue'

    if task_status == 'pending':

        loop = asyncio.get_event_loop()
        loop.run_until_complete(update_task_status(task_id, 'image_detection_started'))

        task = celery_summon_images_detection_task.apply_async(args=[task_id])

        logger.info(f'Controller has started a new detection task for task_id {task_id}, celery task id is {task.id}')

    elif task_status == 'image_detection_started':

        loop = asyncio.get_event_loop()
        loop.run_until_complete(update_task_status(task_id, 'template_extraction_started'))

        task = celery_summon_template_extraction_task.apply_async(args=[task_id])
        logger.info(f'Controller has started a new template extraction task for task_id {task_id}, celery task id is {task.id}')

    elif task_status == 'template_extraction_started':

        loop = asyncio.get_event_loop()
        loop.run_until_complete(update_task_status(task_id, 'quality_estimation_started'))

        task = celery_summon_quality_estimation_task.apply_async(args=[task_id])
        logger.info(f'Controller has started a new quality estimation task for task_id {task_id}, celery task id is {task.id}')

    elif task_status == 'quality_estimation_started':
        logger.info(
            f'TASK DONE!')
        loop = asyncio.get_event_loop()
        loop.run_until_complete(update_task_status(task_id, 'done'))

def check_queue_task_count():
    rabbitmq_url = "pyamqp://guest:guest@localhost//" # потом надо поменять на os.getenv('rabbit_mq_url')
    queue_name = 'celery' # потом надо поменять на os.getenv('queue_name')

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

async def get_oldest_requested_task():
    session = await get_async_session()
    try:
        result = await session.execute(
            select(Task.id, Task.status)
            .filter((Task.status != 'not_requested') & (Task.status != 'done'))
            .order_by(Task.timestamp_of_request)
            .limit(1)
        )
        result = result.one_or_none()
        print('res', result, type(result))
        if result:
            task_id, task_status = result
        else:
            task_id, task_status = None, None
        return task_id, task_status
    except Exception as ex:
        print('Error while extracting task', ex)
        return None, None
    finally:
        await session.close()


async def update_task_status(task_id: int, task_status: str):
    allowed_statuses = ['not_requested', 'pending', 'image_detection_started',
                        'template_extraction_started', 'quality_estimation_started', 'done']

    if task_status not in allowed_statuses:
        raise ValueError(f"Invalid status: {task_status}, allowed ones are {allowed_statuses}")

    session = await get_async_session()
    try:
        result = await session.execute(select(Task).filter(Task.id == task_id))
        task = result.scalar_one_or_none()

        if task:
            task.status = task_status
            await session.commit()
            return task
        else:
            raise ValueError(f"Task id {task_id} not found")
    except Exception as ex:
        print('Error while updating task status', ex)
    finally:
        await session.close()




# Настройка RabbitMQ
@celery_app.task
def process_image_detection_task(img_id, img_path, img_additional_data, api_url: str):
    """
    Задача Celery для обработки изображений.
    """
    # Получаем event loop для выполнения асинхронного кода
    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_image_detections(img_id=img_id, img_path=img_path, img_additional_data=img_additional_data, api_url=api_url))

@celery_app.task
def process_template_extraction_or_quality_estimation_task(img_id, img_path, img_additional_data, api_url: str):
    """
    Задача Celery для обработки изображений.
    """
    # Получаем event loop для выполнения асинхронного кода
    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_template_extraction_or_quality_estimation(img_id=img_id, img_path=img_path, img_additional_data=img_additional_data, api_url=api_url))

# @celery_app.task
# def process_quality_estimation_task(img_id, img_path, img_additional_data, api_url: str):
#     """
#     Задача Celery для обработки изображений.
#     """
#     # Получаем event loop для выполнения асинхронного кода
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(process_quality_estimation(img_id=img_id, img_path=img_path, img_additional_data=img_additional_data, api_url=api_url))


@celery_app.task(acks_late=True)
def celery_summon_quality_estimation_task(task_id: int):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(summon_images_task(task_id, 'quality'))

@celery_app.task(acks_late=True)
def celery_summon_template_extraction_task(task_id: int):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(summon_images_task(task_id, 'template'))

@celery_app.task(acks_late=True)
def celery_summon_images_detection_task(task_id: int):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(summon_images_task(task_id, 'detection'))

async def summon_images_task(task_id: int, api_stage: str):

    load_dotenv()
    data_stages = os.getenv('stages_of_preparing')

    assert api_stage in data_stages, f'Stage must be from list of possible stages: {data_stages}'

    logger.info(f"Requsted summon_images_task with tak_id {task_id} and api_stage {api_stage}")

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

            logger.info(
                f"Retrieved next image of task {task_id}; {processed_images_count if processed_images_count else 0}")
            logger.info(
                f"img_id : {img_id}\n"
                f"img_additional_data : {type(img_additional_data), len(str(img_additional_data))}")

            if api_stage == 'detection':
                api_url = os.getenv('image_api_detection_url')
                process_image_detection_task.apply_async(args=[img_id, img_path, img_additional_data, api_url])
            elif api_stage == 'template':
                api_url = os.getenv('image_api_template_url')
                process_template_extraction_or_quality_estimation_task.apply_async(args=[img_id, img_path, img_additional_data, api_url])
            elif api_stage == 'quality':
                api_url = os.getenv('image_api_quality_url')
                process_template_extraction_or_quality_estimation_task.apply_async(args=[img_id, img_path, img_additional_data, api_url])

            # Обновляем последний обработанный ID
            last_processed_id = image.id
            processed_images_count += 1

    return {"message": f"Processing task on stage {api_stage} started for task_id: {task_id}"}

async def process_image_detections(img_id, img_path, img_additional_data, api_url):
    async with async_session() as session:
        try:
            logger.info("Начато получение детекции изображения с ID: %s", img_id)
            logger.info("Запрос на api_url " + api_url)
            logger.info(img_path)
            # Чтение изображения
            async with aiofiles.open(img_path, "rb") as file:
                img = await file.read()

            # Преобразование изображения в base64
            image_data = base64.b64encode(img).decode("utf-8")
            # logger.info("Base64-кодирование изображения завершено.")

            # Проверка на наличие данных
            if not image_data:
                logger.error("Base64-данные изображения не были сформированы.")
                raise ValueError("Base64-данные изображения не были сформированы.")

            logger.info(img_additional_data)

            if not img_additional_data:
                #logger.info("Запрос с картинкой")

                # Формирование данных для запроса
                payload = {
                    "image": {
                        "blob": image_data,
                        "format": "IMAGE",
                    },
                    "objects": [{}],
                }
            else:
                #logger.info("Запрос с данными и картинкой")

                payload = {
                    "image": {
                        "blob": image_data,
                        "format": "IMAGE",
                    },
                    "objects": img_additional_data,
                }

            if not payload.get("image"):
                #logger.info("Base64-данные изображения не были сформированы.")

                raise ValueError("Отсутствуют данные изображения для отправки в API")

            headers = {
                "Content-Type": "application/json",
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

            # detection_entry = DetectionData(
            #     image_id=img_id,
            #     detection=detection_data,
            #     template=template_data,
            # )
            # session.add(detection_entry)
            # await session.commit()

            await session.execute(
                update(ImageData)
                .where(ImageData.id == img_id)
                .values(additional_data=detection_data)
            )

            await session.commit()

            logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

        except Exception as e:
            logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
            await session.rollback()
            raise

    return f"Детекция изображения {img_id} получена успешно"

async def process_template_extraction_or_quality_estimation(img_id, img_path, img_additional_data, api_url):
    async with async_session() as session:
        try:
            logger.info("Начата обработка изображения с ID: %s", img_id)
            logger.info("Запрос на api_url " + api_url)
            logger.info(img_path)
            # Чтение изображения
            async with aiofiles.open(img_path, "rb") as file:
                img = await file.read()

            # Преобразование изображения в base64
            image_data = base64.b64encode(img).decode("utf-8")
            # logger.info("Base64-кодирование изображения завершено.")

            # Проверка на наличие данных
            if not image_data:
                # logger.error("Base64-данные изображения не были сформированы.")
                raise ValueError("Base64-данные изображения не были сформированы.")
            # logger.info(img_additional_data)
            # logger.info("Запрос с данными и картинкой")

            payload = {
                "image": {
                    "blob": image_data,
                    "format": "IMAGE",
                },
                "objects": img_additional_data,
            }

            # logger.info(f'payload {payload.keys()}, {payload["objects"]}')

            if not payload.get("image"):
                logger.info("Base64-данные изображения не были сформированы.")

                raise ValueError("Отсутствуют данные изображения для отправки в API")

            headers = {
                "Content-Type": "application/json",
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

            # detection_entry = DetectionData(
            #     image_id=img_id,
            #     detection=detection_data,
            #     template=template_data,
            # )
            # session.add(detection_entry)
            # await session.commit()

            await session.execute(
                update(ImageData)
                .where(ImageData.id == img_id)
                .values(additional_data=detection_data)
            )

            await session.commit()


            logger.info("Обработка изображения с ID %s завершена. Результат сохранен.", img_id)

        except Exception as e:
            logger.error("Ошибка при обработке изображения с ID %s: %s", img_id, str(e))
            await session.rollback()
            raise

    return f"Шаблон изображения {img_id} получен успешно"

# async def process_quality_estimation(img_id, img_path, img_additional_data, api_url):
#     return f"Детекция изображения {img_id} получена успешно"