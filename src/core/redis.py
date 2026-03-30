from redis.asyncio import Redis, ConnectionPool
from typing import Optional
from src.config import settings

# Global Redis client
redis_client: Optional[Redis] = None
connection_pool: Optional[ConnectionPool] = None


async def init_redis():
    """Initialize Redis connection."""
    global redis_client, connection_pool

    connection_pool = ConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
    )

    redis_client = Redis(connection_pool=connection_pool)
    return redis_client


async def get_redis_client() -> Redis:
    """Get Redis client instance."""
    global redis_client

    if redis_client is None:
        redis_client = await init_redis()

    return redis_client


async def close_redis():
    """Close Redis connection."""
    global redis_client, connection_pool

    if redis_client:
        await redis_client.close()
        redis_client = None

    if connection_pool:
        await connection_pool.disconnect()
        connection_pool = None
