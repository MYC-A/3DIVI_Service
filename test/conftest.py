import os
import sys
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv('.env.test')
os.environ["TESTING"] = "true"

from main import app
from api.dependencies import get_session

# DATABASE_URL = os.getenv("DATABASE_URL")
# if not DATABASE_URL:
#     raise ValueError("DATABASE_URL must be set in .env.test")
#
# if "+asyncpg" in DATABASE_URL:
#     sync_url = DATABASE_URL.replace("+asyncpg", "")
# else:
#     sync_url = DATABASE_URL
#
# sync_engine = create_engine(sync_url, echo=False, future=True)
# SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as client:
        yield client

# @pytest.fixture(scope="function")
# def db_session():
#     session = SyncSessionLocal()
#     try:
#         yield session
#     finally:
#         session.rollback()
#         session.close()

# Опции командной строки для медленных тестов, пути к JSON и номера теста
def pytest_addoption(parser):
    parser.addoption(
        "--run-slow", action="store_true", default=False, help="run slow tests"
    )
    parser.addoption(
        "--clusters-json",
        action="store",
        default="expected_clusters.json",
        help="Path to expected clusters JSON file"
    )
    parser.addoption(
        "--test-number",
        action="store",
        default="1",
        help="Test number (folder name in test/images/test_[number])"
    )

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")

def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="need --run-slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
