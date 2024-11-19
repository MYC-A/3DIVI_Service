import os

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException,Request,Response
from sqlalchemy.ext.asyncio import AsyncSession
from core.utils import (save_file, save_base64_image, get_or_create_task, save_image_to_db,
                        find_free_task_id, set_task_id_in_cookies, save_image_to_db_v1, find_first_free_task_id,
                        get_next_image_by_task_id, save_detection)
from schemas import ImageBase64Schema
from api.dependencies import get_session
from task import summon_images_task  # process_detection_task

router = APIRouter()

"""@router.post("/upload_image")
async def upload_image(task_id: int = None, file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    task_id = await get_or_create_task(session, task_id)
    file_path = await save_file(file)
    await save_image_to_db(session, task_id, file_path)
    return {"message": "Image uploaded successfully", "file_path": file_path}
"""
@router.post("/upload_images")
async def upload_images(task_id: int = None, files: list[UploadFile] = File(...), session: AsyncSession = Depends(get_session)):
    task_id = await get_or_create_task(session, task_id)
    for file in files:
        file_path = await save_file(file)
        await save_image_to_db(session, task_id, file_path)
    return {"message": "Images uploaded successfully"}

"""@router.post("/upload_images_base64")
async def upload_images_base64(data: ImageBase64Schema, session: AsyncSession = Depends(get_session)):
    task_id = await get_or_create_task(session, data.task_id)
    for base64_image in data.images:
        file_path = await save_base64_image(base64_image)
        await save_image_to_db(session, task_id, file_path)
    return {"message": "Images uploaded successfully", "task_id": task_id}
"""
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


"""
@router.post("/upload_images_base64_0_1")
async def upload_images_base64_0_1(data: ImageBase64Schema, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    task_id = get_task_id_from_cookies(request)  # Получаем task_id из cookies

    # Если task_id нет в cookies и last_part=True, создаем новую задачу
    if not task_id and data.last_part:
        task_id = await get_or_create_task(session)
        set_task_id_in_cookies(response, task_id)  # Сохраняем task_id в cookies

    # Если task_id передан в запросе, используем его
    elif data.task_id:
        task_id = data.task_id
        set_task_id_in_cookies(response, task_id)  # Сохраняем task_id в cookies

    # Если last_part=False, добавляем изображения в текущую задачу
    for base64_image in data.images:
        file_path = await save_base64_image(base64_image)
        await save_image_to_db(session, task_id, file_path)

    # Если last_part=False, начинаем новый цикл
    if not data.last_part:
        task_id = await get_or_create_task(session)
        set_task_id_in_cookies(response, task_id)  # Сохраняем новый task_id в cookies

    return {"message": "Images uploaded successfully", "task_id": task_id}
"""


@router.post("/process_images")
async def process_images(task_id: int):
    """
    Метод API для запуска задачи обработки изображений.
    """

    # Запуск задач Celery
    res = await summon_images_task(task_id)
    return {"message": f"Processing task started for task_id: {task_id}", "result": res['message']}


