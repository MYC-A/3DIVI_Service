from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/raw_data"

async_engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()
async_session = sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

async def connect():
    async with async_engine.connect() as connection:
        await connection.begin()
    print("Успешное подключение к базе данных")

async def disconnect():
    await async_engine.dispose()
    print("Соединение с базой данных закрыто")

async def init_db():
    """Создает таблицы, если они еще не существуют."""
    async with async_engine.begin() as conn:  # async_engine.begin() для использования транзакций
        await conn.run_sync(Base.metadata.create_all)  # выполняет create_all в асинхронном контексте
    print("Таблицы созданы")
