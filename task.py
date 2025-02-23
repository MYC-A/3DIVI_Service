import os
import json
import base64
import logging
import requests
import numpy as np
import networkx as nx
from io import BytesIO
from minio import Minio
from celery import Celery
from kombu import Connection
from sqlalchemy import update
from bitstring import BitArray
from dotenv import load_dotenv
from celery_db import sync_session
from models import Task, ImageData
from contextlib import contextmanager
# from face_sdk_3divi import FacerecService
from sklearn.preprocessing import normalize
from sklearn.metrics import pairwise_distances

# Инициализация объекта Celery
celery_app = Celery("tasks", broker="pyamqp://guest:guest@localhost//")
# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

load_dotenv()

minio_client = Minio(
    os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=False
)

bucket_name = os.getenv("MINIO_BUCKET_NAME")
if not minio_client.bucket_exists(bucket_name):
    minio_client.make_bucket(bucket_name)


def get_base64_from_path(img_path):
    response = minio_client.get_object(bucket_name, img_path)
    data = response.read()
    return base64.b64encode(data).decode("utf-8")

@contextmanager
def get_session():
    session = sync_session()
    try:
        yield session
    finally:
        session.close()

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

        update_task_status(task_id, 'clustering_started')

        task = celery_summon_clustering_task.apply_async(args=[task_id], queue='queue_quality')
        logger.info(
            f'Controller has started a new clustering task for task_id {task_id}, celery task id is {task.id}')


    elif task_status == 'clustering_started':
        logger.info(f'TASK DONE!')
        update_task_status(task_id, 'done')


def summon_images_task(task_id: int, api_stage: str):
    data_stages = os.getenv('stages_of_preparing')

    assert api_stage in data_stages, f'Stage must be from list of possible stages: {data_stages}'

    logger.info(f"Requested summon_images_task with task_id {task_id} and api_stage {api_stage}")

    session = sync_session()
    processed_images_count = 0
    last_processed_id = None
    additional_data_list = [] # ####

    if api_stage == 'clustering':  # Переделать
        # process_clustering_task.apply_async(
        #     args=[task_id], queue='queue_quality')
        return {"clustering_message": f"Processing task on stage {api_stage} started for task_id: {task_id}"}

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

            logger.info(
                f"Retrieved next image of task {task_id}; {processed_images_count if processed_images_count else 0}")
            logger.info(
                f"img_id: {img_id}\nimg_additional_data: {type(img_additional_data), len(str(img_additional_data))}")

            # В зависимости от стадии, выбираем соответствующий API
            if api_stage == 'detection':
                api_url = os.getenv('image_api_detection_url')
                process_image_detection_task.apply_async(args=[img_id, img_path, img_additional_data, api_url],
                                                         queue='queue_detection')
            elif api_stage == 'template':
                if img_additional_data:
                    api_url = os.getenv('image_api_template_url')
                    process_template_extraction_task.apply_async(
                        args=[img_id, img_path, img_additional_data, api_url], queue='queue_template')

            elif api_stage == 'quality':
                if img_additional_data:
                    api_url = os.getenv('image_api_quality_url')
                    process_quality_estimation_task.apply_async(
                        args=[img_id, img_path, img_additional_data, api_url], queue='queue_quality')

            elif api_stage == 'clustering': # Переделать
                pass
                # process_clustering_task.apply_async(
                #     args=[task_id], queue='queue_quality')

            # Обновляем последний обработанный ID
            last_processed_id = img_id
            processed_images_count += 1

        '''
        if api_stage == 'clustering':
            process_clustering_task.apply_async(
                args=[task_id], queue='queue_quality')
        '''


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

        image_data = get_base64_from_path(img_path)

        if not image_data:
            logger.error("Base64-данные изображения не были сформированы.")
            raise ValueError("Base64-данные изображения не были сформированы.")

        # logger.info("Дополнительные данные изображения: %s", img_additional_data)
        logger.info(f"{str(img_additional_data)[:50]}, {type(img_additional_data)}")

        payload = {
            "image": {
                "blob": image_data,
                "format": "IMAGE",
            },
            "objects": [{}],
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

        logger.info(f"{str(api_result)[:50], type(api_result)}, {api_result['objects']}")

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

@celery_app.task(name='tasks.template.process_template', acks_late=True)
def process_template_extraction_task(img_id, img_path, img_additional_data, api_url: str):
    session = sync_session()
    try:
        logger.info("Начата обработка изображения с ID: %s", img_id)
        logger.info("Запрос на api_url %s", api_url)
        logger.info("Путь к изображению: %s", img_path)

        image_data = get_base64_from_path(img_path)

        if not image_data:
            logger.error("Base64-данные изображения не были сформированы.")
            raise ValueError("Base64-данные изображения не были сформированы.")

        # logger.info("Дополнительные данные изображения: %s", img_additional_data)
        logger.info(f"{str(img_additional_data)[:50]}, {type(img_additional_data)}")

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
        # logger.info("Ответ API успешно получен: %s", api_result)

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

        image_data = get_base64_from_path(img_path)

        if not image_data:
            logger.error("Base64-данные изображения не были сформированы.")
            raise ValueError("Base64-данные изображения не были сформированы.")

        if isinstance(img_additional_data, str):
            try:
                img_additional_data = json.loads(img_additional_data)
            except json.JSONDecodeError as e:
                logger.error("Ошибка декодирования JSON для img_additional_data: %s", e)
                raise

        # logger.info("Дополнительные данные изображения: %s", img_additional_data)

        logger.info(f"{str(img_additional_data)[:50]}, {type(img_additional_data)}")

        payload = {
            "_image": {
                "blob": image_data,
                "format": "IMAGE",
            },
            "objects": img_additional_data
        }

        headers = {
            "Content-Type": "application/json",
        }

        response = requests.post(api_url, json=payload, headers=headers, verify=False)
        if response.status_code != 200:
            logger.error("Ошибка API: %s", response.text)
            raise ValueError(f"API вернул ошибку: {response.status_code}, {response.text}")

        api_result = response.json()
        # logger.info("Ответ API успешно получен: %s", api_result)

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

'''
        ВЕРСИЯ БЕЗ ИНДЕКСОВ
        
        
@celery_app.task(name='tasks.quality.clustering', acks_late=True)
def process_clustering_task(task_id):

    def fetch_data_in_batches(task_id):
        with get_session() as session:
            query = (
                session.query(ImageData)
                .filter(ImageData.task_id == task_id)
                .yield_per(100)
            )
            for record in query:
                yield record

    def decode_blob(blob_str):
        """
        Декодирует строку blob в массив numpy.
        """
        blob_bytes = base64.b64decode(blob_str)
        return np.frombuffer(blob_bytes, dtype=np.uint8)

    def filter_group_new_clustering(embeddings, quality_scores):
        """
        Метод фильтрации и кластеризации.
        """
        distances = np.inner(embeddings, embeddings)
        quality_scores_matrix = np.zeros_like(distances)
        for i1 in range(len(embeddings)):
            for i2 in range(len(embeddings)):
                quality_scores_matrix[i1][i2] = min(quality_scores[i1], quality_scores[i2])
        condition = (quality_scores_matrix - distances) > 0.1
        connections = []
        for i1 in range(condition.shape[0]):
            for i2 in range(condition.shape[1]):
                if i1 != i2 and not condition[i1][i2]:
                    connections.append((i1, i2))
        G = nx.Graph(connections)
        communities = nx.algorithms.community.label_propagation_communities(G)
        labels = [-1] * len(embeddings)
        for i, community in enumerate(communities):
            for s_l in community:
                labels[s_l] = i
        return np.array(labels)

    embeddings_list = []
    quality_scores_list = []
    templates = []

    logger.info("МЕТОД ЗАПУЩЕН")
    for record in fetch_data_in_batches(task_id):
        if record.additional_data is None:
            logger.info(f"Дополнительные данные отсутствуют (None) для записи {record.id}")
            continue

       # logger.info(f"Данные {record.additional_data}")

        # Обработка additional_data
        if isinstance(record.additional_data, str):
            try:
                additional_data = json.loads(record.additional_data)
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка декодирования JSON для записи {record.id}: {e}")
                continue
        elif isinstance(record.additional_data, list):
            additional_data = record.additional_data
        else:
            logger.warning(f"Дополнительные данные имеют неожиданный тип: {type(record.additional_data)}")
            continue

        # Убедитесь, что additional_data является списком
        if not isinstance(additional_data, list):
            logger.warning(f"Дополнительные данные не являются списком для записи {record.id}")
            continue

        # Извлечение embeddings и quality_scores
        for item in additional_data:
            if "template" in item:
                # Ищем любой ключ в template, который содержит blob
                blob = None
                for key in item["template"]:
                    if isinstance(item["template"][key], dict) and "blob" in item["template"][key]:
                        blob = item["template"][key]["blob"]
                        logger.info(f"BLOB {blob[:10]}")
                        break

                if blob is None:
                    logger.info(f"Шаблон не найден для записи {record.id}")
                    continue

                # Декодируем blob в embeddings
                embeddings = decode_blob(blob)
                embeddings_list.append(embeddings)

                """
                # Преобразуем blob в in-memory поток и загружаем шаблон
                blob_bytes = base64.b64decode(blob)
                binary_stream = BytesIO(blob_bytes)
                template = recognizer.load_template(binary_stream)
                templates.append(template)
                """
            if "confidence" in item:
                quality_scores_list.append(item["confidence"])
                logger.info(f"Embeddings{embeddings} , confidence {item["confidence"]}")
            else:
                logger.info("confidence не найдено")

    # Преобразуем списки в numpy массивы
    embeddings_array = np.array(embeddings_list)
    quality_scores_array = np.array(quality_scores_list)

    # Применяем метод фильтрации
    if len(embeddings_array) > 0 and len(quality_scores_array) > 0:
        labels = filter_group_new_clustering(embeddings_array, quality_scores_array)
        logger.info(f"Результат кластеризации: {labels}")
    else:
        logger.warning("Нет данных для кластеризации.")
    """
    # Создаем индекс и выполняем поиск
    if templates:
        index = recognizer.create_index(templates, 1)
        search_template = templates[0]  # Пример: используем первый шаблон для поиска
        nearest = recognizer.search([search_template], index, 1)[0][0]
        logger.info(f"Ближайший шаблон: {nearest}")
    else:
        logger.warning("Нет шаблонов для создания индекса и поиска.")
    """

    return f"Запрос обработан успешно"
'''


# @celery_app.task(name='tasks.quality.clustering', acks_late=True)
# def process_clustering_task(task_id):
#
#     default_dll_path = "lib/libfacerec.so"
#     face_sdk_3divi_dir = os.getenv('face_sdk_3divi_dir')
#     service = FacerecService.create_service(
#         os.path.join(face_sdk_3divi_dir, default_dll_path),
#         os.path.join(face_sdk_3divi_dir, "conf/facerec")
#     )
#
#     # face_sdk_3divi_dir = "/home/slonyara/3DiVi_FaceSDK/3_24_2"
#     # default_dll_path = "/home/slonyara/3DiVi_FaceSDK/3_24_2/lib/libfacerec.so"
#     # service = FacerecService.create_service(
#     #     dll_path=default_dll_path,
#     #     facerec_conf_dir="/home/slonyara/3DiVi_FaceSDK/3_24_2/conf/facerec", )
#
#     recognizer = service.create_recognizer("recognizer_latest_v1000.xml", True, False, False)
#
#     # функция для нормализации эмбеддингов
#     def cosine_from_euclidean(embeddings, sq_euc) -> np.ndarray:
#         """
#         Get pairwise cosine distances from euclidean distances
#         embedding: int4 matrix of shape (N, C)
#         sq_euc: matrix of shape (N, N) of precalculated squared euclidean dists
#         """
#         zero_point = 0.5
#         dq_norms = np.linalg.norm(embeddings - zero_point, axis=1)
#         n1 = dq_norms[:, np.newaxis]
#         n2 = dq_norms[np.newaxis, :]
#         return ((n1 ** 2) + (n2 ** 2) - sq_euc) / (2 * n1 * n2)
#
#     def load_template_from_base64(blob_str):
#         """
#         Загружает шаблон из base64 строки.
#         """
#         try:
#             blob_bytes = base64.b64decode(blob_str)
#             binary_stream = BytesIO(blob_bytes)
#             return recognizer.load_template(binary_stream)
#         except Exception as e:
#             logger.error(f"Ошибка при загрузке шаблона: {e}")
#             raise
#
#     def push_clusters_to_additional_data(image_id_to_cluster : dict) -> bool:
#         """
#         Добавляем номер кластера к additional_data катинки в базе данных
#         :param image_id_to_cluster: словарь image_id : image_cluster
#         :return: флаг bool - уалось ли запушить изменения
#         """
#         session = sync_session()
#         try:
#             for img_id, value in image_id_to_cluster.items():
#                 image = session.query(ImageData).filter(ImageData.id == img_id).first()
#                 if image:
#                     image_data = json.loads(image.additional_data)
#
#                     image_data.append(['cluster', str(value)])
#
#                     image.additional_data = json.dumps(image_data)
#
#             session.commit()
#             return True
#         except Exception as ex:
#             print('ОШИБКА ДОБАВЛЕНИЯ В БАЗУ : ', ex)
#             return False
#
#     def build_distance_matrix_with_index(templates):
#         """
#         Строит матрицу расстояний с использованием индекса.
#         """
#         n = len(templates)
#         distances = np.zeros((n, n))  # Инициализируем матрицу расстояний
#
#         # Создаем индекс для всех шаблонов
#         index = recognizer.create_index(templates, 1)
#         # print(n)
#         for i in range(n):
#             # Ищем ближайших соседей для каждого шаблона
#             nearest = recognizer.search([templates[i]], index, k=n)[0]
#             for neighbor in nearest:
#                 distances[i][neighbor.i] = neighbor.match_result.score  # Записываем расстояние
#
#         logger.info(f"Матрица из индекса {distances}")
#         # Матрица расстояний симметрична, поэтому заполняем вторую половину
#         distances = np.minimum(distances, distances.T)
#
#         return distances
#
#     def filter_group_new_clustering(templates, quality_scores):
#         """
#         Метод фильтрации и кластеризации с использованием индекса.
#         """
#         # Строим матрицу расстояний с использованием индекса
#         distances = build_distance_matrix_with_index(templates)
#         # sq_distances = np.power(distances, 2)
#         # distances = cosine_from_euclidean(distances, sq_distances)
#
#         # Создаем матрицу качества
#         quality_scores_matrix = np.minimum.outer(quality_scores, quality_scores)
#
#         # Определяем связи на основе условия
#         condition = (quality_scores_matrix - distances) > 0.1
#         connections = []
#         for i1 in range(condition.shape[0]):
#             for i2 in range(condition.shape[1]):
#                 if i1 != i2 and not condition[i1][i2]:
#                     connections.append((i1, i2))
#
#         # Строим граф
#         G = nx.Graph(connections)
#
#         # Находим сообщества
#
#         # Формируем метки
#         communities = nx.algorithms.community.label_propagation_communities(G)
#         labels = [-1] * len(templates)
#         for i, community in enumerate(communities):
#             for s_l in community:
#                 labels[s_l] = i
#         return np.array(labels)
#
#     def fetch_data_in_batches(task_id):
#         with get_session() as session:
#             query = (
#                 session.query(ImageData)
#                 .filter(ImageData.task_id == task_id)
#                 .yield_per(100)
#             )
#             for record in query:
#                 yield record
#
#     def intra_filtering_graph(embeddings, quality, threshold=0.1, distance_thr=0.4,dists=None):
#         embeddings = np.array(embeddings)
#
#         if dists is None:
#             embeddings = normalize(embeddings)
#             dists = np.inner(embeddings, embeddings)
#
#         qaas = np.minimum.outer(quality, quality)
#         if qaas[0][0] > 2:
#             qaas /= 100
#         conn = (qaas - dists) <= threshold
#
#         N = conn.shape[0]
#         not_equal_mask = ~np.eye(N, dtype=bool)
#         mask = not_equal_mask & conn & (dists > distance_thr)
#         i1_array, i2_array = np.where(mask)
#         connections = [(i, j, {"weight": dists[i, j]}) for i, j in zip(i1_array, i2_array)]
#         G = nx.Graph(connections)
#         communities = nx.algorithms.community.label_propagation_communities(G)
#         group_labels = [-1] * len(embeddings)
#         for i, b in enumerate(communities):
#             for bb in b:
#                 group_labels[bb] = i
#
#         return np.array(group_labels)
#
#     templates = []
#     quality_scores_list = []
#     image_id = []
#
#     logger.info("МЕТОД ЗАПУЩЕН")
#     for record in fetch_data_in_batches(task_id):
#         if record.additional_data is None:
#             logger.info(f"Дополнительные данные отсутствуют (None) для записи {record.id}")
#             continue
#
#         # Обработка additional_data
#         if isinstance(record.additional_data, str):
#             try:
#                 additional_data = json.loads(record.additional_data)
#                 id = record.id
#             except json.JSONDecodeError as e:
#                 logger.error(f"Ошибка декодирования JSON для записи {record.id}: {e}")
#                 continue
#         elif isinstance(record.additional_data, list):
#             additional_data = record.additional_data
#             id = record.id
#         else:
#             logger.warning(f"Дополнительные данные имеют неожиданный тип: {type(record.additional_data)}")
#             continue
#
#         if not isinstance(additional_data, list):
#             logger.warning(f"Дополнительные данные не являются списком для записи {record.id}")
#             continue
#
#         # Извлечение embeddings и quality_scores
#         for item in additional_data:
#             if "template" in item:
#                 # Ищем любой ключ в template, который содержит blob
#                 blob = None
#                 for key in item["template"]:
#                     if isinstance(item["template"][key], dict) and "blob" in item["template"][key]:
#                         blob = item["template"][key]["blob"]
#                         break
#
#                 if blob is None:
#                     logger.info(f"Шаблон не найден для записи {record.id}")
#                     continue
#
#                 # Загружаем шаблон из base64
#                 idx_unpacking = np.arange(512)
#                 idx_unpacking[::2] += 1
#                 idx_unpacking[1::2] -= 1
#
#                 template = load_template_from_base64(blob)
#                 byte_io = BytesIO()
#                 template.save(byte_io)
#                 template_bin = byte_io.getvalue()[4:]
#                 template_bin = BitArray(template_bin)
#                 predict_tensor = [template_bin[i * 4:(i + 1) * 4].int for i in idx_unpacking]
#
#                 # template = np.frombuffer(base64.b64decode(blob), dtype='uint8').reshape(296)
#                 templates.append(predict_tensor)
#                 image_id.append(id)
#
#             if "quality" in item:
#                 quality_scores_list.append(item["quality"]["total_score"])
#                 logger.info(f"Quality: {item["quality"]["total_score"]}")
#
#             # if "confidence" in item:
#             #     quality_scores_list.append(item["confidence"])
#             #     logger.info(f"Confidence: {item['confidence']}")
#             else:
#                 logger.info("confidence не найдено")
#
#     # Преобразуем списки в numpy массивы
#     quality_scores_array = np.array(quality_scores_list)
#     print(quality_scores_array)
#
#     # Применяем метод фильтрации
#     if len(quality_scores_array) == 0:
#         print('QUALITY SCORES НЕ НАЙДЕНЫ')
#         quality_scores_array = np.ones(quality_scores_array.shape)
#
#     if len(templates) > 0 and len(quality_scores_array) > 0:
#         templates = np.array(templates)
#
#         euc = pairwise_distances(templates, templates)
#         sq_euc = np.power(euc, 2)
#         cos_from_euc = cosine_from_euclidean(templates, sq_euc)
#         distances = cos_from_euc
#         labels = intra_filtering_graph(templates, quality_scores_array, dists=distances)
#
#         # labels = filter_group_new_clustering(templates, quality_scores_array)
#         from_image_id_to_cluster = dict(zip(image_id, labels))
#
#         result_of_push = push_clusters_to_additional_data(from_image_id_to_cluster)
#         if result_of_push:
#             logger.info(f"Результат кластеризации: {labels}, кластера добавлены в базу")
#         else:
#             logger.info(f"Результат кластеризации: {labels}, кластера НЕ добавлены в базу")
#     else:
#         logger.warning("Нет данных для кластеризации.")
#
#     return f"Запрос обработан успешно labels {labels}"






@celery_app.task(name='tasks.quality.summon_clustering', acks_late=True)
def celery_summon_clustering_task(task_id: int):
    summon_images_task(task_id, 'clustering')

@celery_app.task(name='tasks.quality.summon_quality', acks_late=True)
def celery_summon_quality_estimation_task(task_id: int):
    summon_images_task(task_id, 'quality')


@celery_app.task(name='tasks.detection.summon_detection', acks_late=True)
def celery_summon_images_detection_task(task_id: int):
    summon_images_task(task_id, 'detection')


@celery_app.task(name='tasks.template.summon_template', acks_late=True)
def celery_summon_template_extraction_task(task_id: int):
    summon_images_task(task_id, 'template')


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
    session = sync_session()
    try:
        # Извлекаем самую старую задачу с состоянием 'pending'
        oldest_task = session.query(Task).filter(Task.status != 'not_requested', Task.status != 'done').order_by(
            Task.timestamp_of_request.asc()).first()

        if oldest_task:
            logger.info(
                f"Найдена самая старая задача: task_id={oldest_task.id}, request_time={oldest_task.timestamp_of_request}")
            id = oldest_task.id
            status = oldest_task.status

        else:
            logger.info("Нет задач со статусом 'pending'")
            id = None
            status = None
        return id, status
    except Exception as e:
        logger.error(f"Ошибка при извлечении самой старой задачи: {str(e)}")
        return None, None
    finally:
        session.close()


def update_task_status(task_id: int, task_status: str):
    allowed_statuses = [
        'not_requested', 'pending', 'image_detection_started',
        'template_extraction_started', 'quality_estimation_started','clustering_started','done'
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
