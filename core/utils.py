import base64
import os
from typing import Optional

from fastapi import Request, Response
from uuid import uuid4
from core.config import UPLOAD_DIR
from sqlalchemy.ext.asyncio import AsyncSession
from models import Task, ImageData
from sqlalchemy.future import select
from typing import List, Optional, Dict, Any

import aiofiles

async def save_file(file):
    file_name = f"{uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    async with aiofiles.open(file_path, "wb") as buffer:
        content = await file.read()
        await buffer.write(content)
    return file_path

async def save_base64_image(base64_data: str):
    mime_type = base64_data.split(';')[0].split('/')[-1] if "data:image" in base64_data else "png"
    base64_str = base64_data.split(",")[1] if "," in base64_data else base64_data
    image_data = base64.b64decode(base64_str)
    file_name = f"{uuid4()}.{mime_type}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    async with aiofiles.open(file_path, "wb") as file:
        await file.write(image_data)

    return file_path

async def get_or_create_task(session: AsyncSession, task_id: int = None):
    if task_id is None:
        result = await session.execute(select(Task.id).order_by(Task.id.desc()))
        last_task_id = result.scalars().first() or 0
        task_id = last_task_id + 1

    result = await session.execute(select(Task).filter(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        task = Task(id=task_id)
        session.add(task)
        await session.commit()
    return task_id

async def save_image_to_db(session: AsyncSession, task_id: int, image_path: str):
    new_image = ImageData(task_id=task_id, image_path=image_path)
    session.add(new_image)
    await session.commit()


async def save_image_to_db_v1(session: AsyncSession, task_id: int, file_path: str, additional_data: dict):
    new_image = ImageData(
        task_id=task_id,
        image_path=file_path,
        additional_data=additional_data
    )
    session.add(new_image)
    await session.commit()


async def find_first_free_task_id(session: AsyncSession) -> int:
    # Извлекаем все существующие task_id из таблицы
    result = await session.execute(select(Task.id))
    task_ids = sorted([row[0] for row in result.fetchall()])

    # Находим первый пропущенный идентификатор
    free_task_id = 1  # Стартовое значение
    for task_id in task_ids:
        if task_id == free_task_id:
            free_task_id += 1
        else:
            break

    return free_task_id

async def find_free_task_id(session: AsyncSession) -> int:
    # Извлекаем все существующие task_id из таблицы
    result = await session.execute(select(Task.id))
    task_ids = sorted([row[0] for row in result.fetchall()])

    # Находим первый пропущенный идентификатор
    free_task_id = task_ids[-1]

    return free_task_id+1

# Функция для извлечения task_id из cookies
def get_task_id_from_cookies(request: Request) -> Optional[int]:
    task_id = request.cookies.get("task_id")
    if task_id:
        return int(task_id)
    return None

# Функция для сохранения task_id в cookies
def set_task_id_in_cookies(response: Response, task_id: int):
    response.set_cookie(key="task_id", value=str(task_id), httponly=True)


async def get_next_image_by_task_id(session: AsyncSession, task_id: int, last_processed_id: int = None):
    """
    Получает следующее изображение с данным task_id, которое идет после last_processed_id.
    """
    query = select(ImageData).filter(ImageData.task_id == task_id)

    if last_processed_id is not None:
        # Фильтруем по id, чтобы получать изображения с id, большим чем last_processed_id
        query = query.filter(ImageData.id > last_processed_id)

    query = query.order_by(ImageData.id).limit(1)  # Извлекаем по одному изображению

    result = await session.execute(query)
    return result.scalar_one_or_none()  # Возвращаем одно изображение или None, если изображений больше нет