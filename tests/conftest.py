import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from redis.asyncio import Redis

from src.main import app
from src.core.database import get_db
from src.core.redis import get_redis_client
from src.models.base import Base


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/notifications"
TEST_REDIS_URL = "redis://localhost:6379/1"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session using existing database."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # DON'T create/drop tables - use existing database schema
    # Tables already exist from migrations

    # Create session
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        # Clean up will be handled by test teardown if needed
        await session.close()

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncGenerator[Redis, None]:
    """Create test Redis client."""
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    # Flush before test to ensure clean state
    await client.flushdb()
    yield client
    # Flush after test for cleanup
    await client.flushdb()
    await client.close()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession, redis_client: Redis) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        return redis_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def mock_api_key():
    """Mock API key for testing."""
    return "test-api-key-12345"


@pytest_asyncio.fixture(autouse=True)
async def mock_embedding_service(monkeypatch, redis_client):
    """Mock embedding service to avoid PyTorch/Windows issues."""
    def mock_generate_embedding(*args, **kwargs):
        # Return dummy 384-dimensional vector (all-MiniLM-L6-v2 dimension)
        # This is now synchronous because it's called via asyncio.to_thread()
        return [0.0] * 384

    # Mock the generate_embedding method
    monkeypatch.setattr(
        "src.services.embedding_service.EmbeddingService.generate_embedding",
        mock_generate_embedding
    )

    # Also mock get_redis_client to return the test Redis client
    async def mock_get_redis_client():
        return redis_client

    monkeypatch.setattr(
        "src.services.orchestration_agent.get_redis_client",
        mock_get_redis_client
    )
