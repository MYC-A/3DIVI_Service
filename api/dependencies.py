from database import async_session
from sqlalchemy.ext.asyncio import AsyncSession

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session

async def get_async_session() -> AsyncSession:
    async with async_session() as session:
        return session