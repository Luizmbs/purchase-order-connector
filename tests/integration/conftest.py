import os
import subprocess
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from infrastructure.database import get_redis, get_session
from main import app

TEST_DB_NAME = "v360_test"
_PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
_REDIS_HOST = os.getenv("REDIS_HOST", "redis")
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)

TEST_DATABASE_URL = f"postgresql+asyncpg://postgres:postgres@{_PG_HOST}:5432/{TEST_DB_NAME}"
TEST_REDIS_URL = f"redis://{_REDIS_HOST}:6379/1"

# NullPool: each request opens and closes its own connection; prevents reuse of
# corrupted connections between tests.
_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
_SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def _override_get_session():
    async with _SessionFactory() as session:
        yield session


async def _override_get_redis():
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


# Aplica overrides para toda a sessão de testes
app.dependency_overrides[get_session] = _override_get_session
app.dependency_overrides[get_redis] = _override_get_redis


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Cria v360_test se não existir e aplica as migrações."""
    # Conecta ao banco de manutenção para criar o banco de testes
    conn = await asyncpg.connect(
        f"postgresql://postgres:postgres@{_PG_HOST}:5432/postgres"
    )
    exists = await conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
    )
    if not exists:
        # CREATE DATABASE não pode rodar dentro de transação; asyncpg executa
        # comandos DDL fora de bloco transacional automaticamente.
        await conn.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    await conn.close()

    # Roda alembic upgrade head contra v360_test
    env = {
        **os.environ,
        "DATABASE_URL": f"postgresql+asyncpg://postgres:postgres@{_PG_HOST}:5432/{TEST_DB_NAME}",
    }
    result = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic falhou no banco de teste:\n{result.stderr}")


@pytest_asyncio.fixture(autouse=True)
async def clean_db(setup_test_db):
    """Limpa dados de negócio antes de cada teste. Preserva users e clients (seeded)."""
    async with _SessionFactory() as session:
        await session.execute(text("TRUNCATE purchase_orders CASCADE"))
        await session.commit()
    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await redis.flushdb()
    await redis.aclose()
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
