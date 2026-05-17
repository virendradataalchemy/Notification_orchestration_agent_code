import uuid
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
from src.config import settings
from src.models.base import Base

engine_kwargs = {
    "echo": settings.sql_echo,
    "connect_args": {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
}

# Supabase pooler / pgbouncer needs NullPool and unique prepared statement names.
if "pooler.supabase.com" in settings.database_url:
    engine_kwargs["poolclass"] = NullPool
    engine_kwargs["connect_args"]["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid.uuid4().hex}__"
else:
    engine_kwargs["pool_size"] = settings.db_pool_size
    engine_kwargs["max_overflow"] = settings.db_max_overflow

# Create async engine
engine = create_async_engine(
    settings.database_url,
    **engine_kwargs,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Alias for convenience and backward compatibility
async_session_maker = AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
