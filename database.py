from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/Raw_data"

async_engine = create_async_engine(DATABASE_URL, echo=True)
Base = declarative_base()
async_session = sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

async def connect():
    async with async_engine.connect() as connection:
        await connection.begin()
    print("Успешное подключение к базе данных")

async def disconnect():
    await async_engine.dispose()
    print("Соединение с базой данных закрыто")
