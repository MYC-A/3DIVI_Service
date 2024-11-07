import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import connect, disconnect
from api.endpoints import upload

app = FastAPI()
# Lifespan для старта и остановки приложения
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect()
        print("Подключение к базе данных успешно!")
        yield
    finally:
        await disconnect()
        print("Отключение от базы данных.")

app = FastAPI(lifespan=lifespan)
app.include_router(upload.router)
if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)