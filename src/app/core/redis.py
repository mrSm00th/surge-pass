import redis.asyncio as redis

from src.app.core.config import settings

_redis: redis.Redis | None = None


async def init_redis() -> None:
    global _redis
    _redis = redis.from_url(settings.redis_url, decode_responses=True)
    await _redis.ping()


async def close_redis() -> None:
    if _redis is not None:
        await _redis.close()


def get_redis() -> redis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized — did the app startup run?")
    return _redis
