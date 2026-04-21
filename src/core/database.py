from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator
from src.core.supabase import supabase_client

engine = None
AsyncSessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Direct SQL sessions are disabled; the app runs in Supabase REST mode."""
    raise RuntimeError("Direct database sessions are disabled. This app runs against Supabase REST only.")
    yield  # pragma: no cover


async def get_db_optional() -> AsyncGenerator[AsyncSession | None, None]:
    """Yield None because direct SQL mode is intentionally disabled."""
    yield None


async def init_db():
    """Verify Supabase REST connectivity without mutating schema."""
    if not supabase_client.configured:
        raise RuntimeError(
            "Supabase REST is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
    await supabase_client.health_check()
