from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.utils import save_file, save_base64_image, get_or_create_task, save_image_to_db
from schemas import ImageBase64Schema
from api.dependencies import get_session

router = APIRouter()

@router.post("/upload_image")
async def upload_image(task_id: int = None, file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    task_id = await get_or_create_task(session, task_id)
    file_path = await save_file(file)
    await save_image_to_db(session, task_id, file_path)
    return {"message": "Image uploaded successfully", "file_path": file_path}

@router.post("/upload_images")
async def upload_images(task_id: int = None, files: list[UploadFile] = File(...), session: AsyncSession = Depends(get_session)):
    task_id = await get_or_create_task(session, task_id)
    for file in files:
        file_path = await save_file(file)
        await save_image_to_db(session, task_id, file_path)
    return {"message": "Images uploaded successfully"}

@router.post("/upload_images_base64")
async def upload_images_base64(data: ImageBase64Schema, session: AsyncSession = Depends(get_session)):
    task_id = await get_or_create_task(session, data.task_id)
    for base64_image in data.images:
        file_path = await save_base64_image(base64_image)
        await save_image_to_db(session, task_id, file_path)
    return {"message": "Images uploaded successfully", "task_id": task_id}
