import json
from typing import Any, Optional

import redis.asyncio as redis

from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)

# Global Redis client instance
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """
    - Get the Redis client instance.
    - Creates a new connection if one doesn't exist.
    Returns: Redis client instance
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        logger.info(f"Connecting to Redis at {settings.REDIS_URL}")
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        # Test connection
        await _redis_client.ping()
        logger.info("Redis connection established")
    return _redis_client


async def close_redis() -> None:
    """Close the Redis conn"""
    global _redis_client
    if _redis_client is not None:
        logger.info("Closing Redis connection")
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


async def json_set(key: str, obj: Any, ex: Optional[int] = None) -> bool:
    """
    Store
    Args:
        key: Redis key
        obj: JSON-serializable object
    Returns: True if successful
    """
    client = await get_redis()
    serialized = json.dumps(obj, default=str)
    result = await client.set(key, serialized, ex=ex)
    logger.debug(f"json_set: {key} = {serialized[:100]}...")
    return result is True


async def json_get(key: str) -> Optional[Any]:
    """
    Retrieve
    Args:
        key: Redis key
    Returns:
        Deserialized object or None if key doesn't exist
    """
    client = await get_redis()
    value = await client.get(key)
    if value is None:
        return None
    result = json.loads(value)
    logger.debug(f"json_get: {key} = {str(result)[:100]}...")
    return result


async def stream_add(
    stream_key: str,
    data: dict[str, Any],
    maxlen: Optional[int] = 10000,
) -> str:
    """
    Add an entry to a Redis stream.

    Args:
        stream_key: Redis stream key
        data: Dictionary of field-value pairs
        maxlen: Maximum stream length (approximate trimming)

    Returns:
        The entry ID
    """
    client = await get_redis()
    # Serialize complex values to JSON strings
    serialized_data = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in data.items()}
    entry_id = await client.xadd(stream_key, serialized_data, maxlen=maxlen)
    logger.debug(f"stream_add: {stream_key} -> {entry_id}")
    return entry_id


async def health_check() -> bool:
    """
    Check Redis connectivity.

    Returns:
        True if Redis is reachable
    """
    try:
        client = await get_redis()
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False
