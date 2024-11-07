import base64
import os
from uuid import uuid4
from core.config import UPLOAD_DIR
from sqlalchemy.ext.asyncio import AsyncSession
from models import Task, ImageData
from sqlalchemy.future import select
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
