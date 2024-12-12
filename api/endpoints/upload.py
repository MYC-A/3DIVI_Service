from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.utils import (save_file, save_base64_image, get_or_create_task, save_image_to_db,
                        find_free_task_id, save_image_to_db_v1, find_first_free_task_id)
from schemas import ImageBase64Schema
from api.dependencies import get_session
from task import update_task_status
from uuid import uuid4
from dotenv import load_dotenv
import os
import aiofiles
from minio import Minio
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
async def upload_images(task_id: int = None, files: list[UploadFile] = File(...), session: AsyncSession = Depends(get_session)):
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
        base64_image = image_data.get("base64")  # Доступ через словарь
        if not base64_image:
            raise HTTPException(status_code=400, detail="Image base64 data is missing")

        # Сохраняем изображение и получаем путь
        file_path = await save_base64_image(base64_image)

        # Собираем дополнительные данные, кроме base64
        additional_data = {k: v for k, v in image_data.items() if k != "base64"}

        # Сохраняем изображение и дополнительные данные в базе данных
        await save_image_to_db_v1(session, task_id, file_path, additional_data)

    return {"message": "Images uploaded successfully", "task_id": task_id}


@router.get("/first_free_task_id")
async def get_first_free_task_id(session: AsyncSession = Depends(get_session)):
    free_task_id = await find_first_free_task_id(session)
    return {"first_free_task_id": free_task_id}

@router.get("/free_task_id")
async def get_first_free_task_id(session: AsyncSession = Depends(get_session)):
    free_task_id = await find_free_task_id(session)
    return {"free_task_id": free_task_id}


@router.post("/process_images")
async def process_images(task_id: int):
    """
    Метод API для запуска задачи обработки изображений.
    """

    # Запуск задач Celery
    update_task_status(task_id, 'pending')
    # task = celery_summon_images_detection_task.apply_async(args=[task_id])
    return {"message": f"Processing task started for task_id: {task_id}"} #, "celery_task_id": task.id}


