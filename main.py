import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from starlette.middleware.cors import CORSMiddleware

from database import connect, disconnect, init_db
from api.endpoints import upload

app = FastAPI()
# Lifespan для старта и остановки приложения
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect()
        await init_db()  # Проверка и создание таблиц при старте приложения
        print("Подключение к базе данных успешно!")
        yield
    finally:
        await disconnect()
        print("Отключение от базы данных.")


app = FastAPI(lifespan=lifespan)
app.include_router(upload.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешает запросы от всех источников
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)