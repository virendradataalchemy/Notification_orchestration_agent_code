import asyncio
from src.core.redis import init_redis, get_redis_client

async def flush():
    await init_redis()
    redis = await get_redis_client()
    await redis.flushdb()
    print('Redis flushed successfully')

if __name__ == "__main__":
    asyncio.run(flush())
