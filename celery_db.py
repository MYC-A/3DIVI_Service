from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/raw_data"

sync_engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()
sync_session = sessionmaker(sync_engine, expire_on_commit=False)

def connect():
    with sync_engine.connect() as connection:
        connection.begin()
    print("Успешное подключение к базе данных для Celery")

def disconnect():
    sync_engine.dispose()
    print("Соединение с базой данных для Celery закрыто")


