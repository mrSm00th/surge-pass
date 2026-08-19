import redis.asyncio as redis

from app.core.config import settings

redis_pool: redis.ConnectionPool | None = None


async def init_redis_pool() -> None:
    global redis_pool
    redis_pool = redis.ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=50,
        decode_responses=True,
    )


async def close_redis_pool() -> None:
    if redis_pool:
        await redis_pool.disconnect()


def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=redis_pool)
