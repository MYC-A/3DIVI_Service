from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.utils import (save_file, save_base64_image, get_or_create_task, save_image_to_db,
                        find_free_task_id, save_image_to_db_v1, find_first_free_task_id, get_all_images_by_task_id,
                        get_task_status, get_clusters)
from schemas import ImageBase64Schema
from api.dependencies import get_session, get_async_session
from task import update_task_status
from uuid import uuid4
from dotenv import load_dotenv
import os
import aiofiles
from minio import Minio
from models import ImageData
import json
from jinja2 import Environment
import mimetypes

router = APIRouter()

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


async def save_uploaded_file(upload_file: UploadFile, destination: str):
    # временное сохранение файла
    async with aiofiles.open(destination, "wb") as out_file:
        while content := await upload_file.read(1024):
            await out_file.write(content)


@router.post("/upload_images")
async def upload_images(task_id: int = None, files: list[UploadFile] = File(...),
                        session: AsyncSession = Depends(get_session)):
    task_id = await get_or_create_task(session, task_id)

    for file in files:
        file_name = f"{uuid4()}_{file.filename}"
        temp_path = os.path.join("/tmp", file_name)
        await save_uploaded_file(file, temp_path)
        await save_image_to_db(session, task_id, temp_path, minio_client, bucket_name)
        os.remove(temp_path)

    return {"message": "Images uploaded successfully"}


@router.post("/upload_images_base64")
async def upload_images_base64(data: ImageBase64Schema, session: AsyncSession = Depends(get_session)):
    task_id = await get_or_create_task(session, data.task_id)

    for image_data in data.images:
        base64_image = image_data.get("base64")
        if not base64_image:
            raise HTTPException(status_code=400, detail="Image base64 data is missing")

        # Сохраняем изображение и получаем путь
        file_path = await save_base64_image(base64_image)

        # Собираем дополнительные данные, кроме base64
        additional_data = {k: v for k, v in image_data.items() if k != "base64"}

        # Сохраняем изображение и дополнительные данные в базе данных
        await save_image_to_db(session, task_id, file_path, minio_client, bucket_name)

    return {"message": "Images uploaded successfully", "task_id": task_id}


@router.get("/first_free_task_id")
async def get_first_free_task_id(session: AsyncSession = Depends(get_session)):
    free_task_id = await find_first_free_task_id(session)
    return {"first_free_task_id": free_task_id}


@router.get("/free_task_id")
async def get_first_free_task_id(session: AsyncSession = Depends(get_session)):
    free_task_id = await find_free_task_id(session)
    return {"free_task_id": free_task_id}


@router.get("/get_task_status_by_id")
async def get_task_status_by_id(task_id: int, session: AsyncSession = Depends(get_session)):
    task_status = await get_task_status(task_id, session)
    return {"task_status": task_status}

@router.get("/get_clusters_by_task_id")
async def get_clusters_by_task_id(task_id: int, session: AsyncSession = Depends(get_session)):
    clusters = await get_clusters(task_id, session)
    return {"clusters": clusters}


@router.post("/process_images")
async def process_images(task_id: int):
    """
    Метод API для запуска задачи обработки изображений.
    """

    # Запуск задач Celery
    update_task_status(task_id, 'pending')
    # task = celery_summon_images_detection_task.apply_async(args=[task_id])
    return {"message": f"Processing task started for task_id: {task_id}"}  # , "celery_task_id": task.id}


def generate_html(clusters, output_file="clusters.html"):
    """
    Генерирует HTML-файл с кластерами и фотографиями.

    clusters: dict - Словарь вида {номер_кластера: [список_путей_к_фотографиям]}.
    output_file: str - Путь к выходному HTML-файлу.
    """
    if not clusters or not isinstance(clusters, dict):
        raise ValueError("clusters должен быть непустым словарём вида {номер_кластера: [пути_к_файлам]}")

    for cluster_id, photos in clusters.items():
        if not isinstance(cluster_id, int):
            raise ValueError(f"Ключи кластеров должны быть целыми числами, получено: {type(cluster_id)}")
        if not photos or not isinstance(photos, list):
            raise ValueError(f"Значение для кластера {cluster_id} должно быть непустым списком путей к файлам")
        # for photo in photos:
        #     if not os.path.isfile(photo):
        #         raise FileNotFoundError(f"Файл {photo} не существует")

    template_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Clusters</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 0; }
            h1 { margin: 20px; text-align: left; padding-left: 20px; }
            .cluster { margin: 20px; padding: 20px; border: 1px solid #ccc; border-radius: 8px; }
            .cluster h2 { margin-top: 0; }
            .photos { display: flex; flex-wrap: wrap; gap: 10px; }
            .photo { width: 150px; height: 150px; overflow: hidden; border: 1px solid #ddd; border-radius: 4px; display: flex; flex-direction: column; align-items: center; }
            .photo img { width: 100%; height: 100%; object-fit: cover; }
            .photo p { margin: 5px 0 0; font-size: 12px; text-align: center; word-wrap: break-word; }
        </style>
    </head>
    <body>
        <h1>Кластеризация фото</h1>
        {% for cluster_id, photos in clusters.items() %}
        <div class="cluster">
            <h2>Кластер {{ cluster_id }}</h2>
            <div class="photos">
                {% for photo in photos %}
                <div class="photo">
                    <img src="{{ photo }}" alt="Photo {{ loop.index }}">
                    <p>{{ photo }}</p>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </body>
    </html>
    """

    env = Environment()
    template = env.from_string(template_content)

    try:
        html_content = template.render(clusters=clusters)

        # with open(output_file, "w", encoding="utf-8") as f:
        #     f.write(html_content)

        # print(f"HTML файл сгенерирован: {output_file}")
        return template
    except Exception as e:
        print(f"Ошибка при генерации HTML: {e}")


minio_client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False
)


@router.get("/proxy/minio/{bucket_name}/{object_name}")
async def proxy_minio(bucket_name: str, object_name: str):
    try:
        response = minio_client.get_object(bucket_name, object_name)

        mime_type, _ = mimetypes.guess_type(object_name)
        if mime_type is None:
            mime_type = "application/octet-stream"

        return StreamingResponse(
            response.stream(32 * 1024),
            media_type=mime_type
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="File not found")


# Эндпоинт
@router.get("/get_cluster_view", response_class=HTMLResponse)
async def get_service_page(task_id: int = Query(..., description="Номер кластера...")):
    """
    Эндпоинт для вьюшки.
    """
    session = await get_async_session()
    images = await get_all_images_by_task_id(session, task_id)

    clusters = {}

    for record in images:
        if record.additional_data is None:
            continue

        image_path = record.image_path
        # Обработка additional_data
        if isinstance(record.additional_data, str):
            try:
                additional_data = json.loads(record.additional_data)
            except json.JSONDecodeError as e:
                continue
        elif isinstance(record.additional_data, list):
            additional_data = record.additional_data
        else:
            continue

        if not isinstance(additional_data, list):
            continue

        pref = r'http://127.0.0.1:8080/proxy/minio/images/'

        for item in additional_data:
            if "cluster" in item:
                cluster = int(item[1])
                if cluster in clusters.keys():
                    clusters[cluster].append(pref + image_path)
                else:
                    clusters[cluster] = [pref + image_path]

    html_content = generate_html(clusters)
    html_content = html_content.render(clusters=clusters)
    return HTMLResponse(content=html_content, status_code=200)
