"""
Redis storage helpers for Knock Patterns.

Key layout:
  knocklock:pattern:{patternId}          → JSON (PatternRecord)
  knocklock:patterns:index               → Redis Set of all patternIds
  knocklock:device_active_pattern:{devId} → patternId string
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.pattern import PatternRecord
from app.storage.redis import get_redis

logger = get_logger(__name__)


# ──────────────────── Key helpers ────────────────────


def _pattern_key(pattern_id: str) -> str:
    settings = get_settings()
    return f"{settings.PATTERN_KEY_PREFIX}{pattern_id}"


def _active_pattern_key(device_id: str) -> str:
    settings = get_settings()
    return f"{settings.DEVICE_ACTIVE_PATTERN_KEY_PREFIX}{device_id}"


def _index_key() -> str:
    settings = get_settings()
    return settings.PATTERN_INDEX_KEY


# ──────────────────── CRUD ────────────────────


async def save_pattern(record: PatternRecord) -> bool:
    """
    Persist a PatternRecord to Redis and add its ID to the index.

    Args:
        record: PatternRecord to save

    Returns:
        True if saved successfully
    """
    client = await get_redis()
    key = _pattern_key(record.patternId)

    serialized = json.dumps(record.model_dump(mode="json"), default=str)
    ok = await client.set(key, serialized)

    # Add to global index
    await client.sadd(_index_key(), record.patternId)

    logger.info(f"Pattern saved: id={record.patternId}, version={record.version}")
    return ok is True


async def get_pattern(pattern_id: str) -> Optional[PatternRecord]:
    """
    Retrieve a PatternRecord from Redis by ID.

    Args:
        pattern_id: Pattern identifier

    Returns:
        PatternRecord or None if not found
    """
    client = await get_redis()
    key = _pattern_key(pattern_id)

    raw = await client.get(key)
    if raw is None:
        return None

    data = json.loads(raw)
    return PatternRecord.model_validate(data)


async def list_patterns(active_only: bool = False) -> list[PatternRecord]:
    """
    List all patterns from Redis.

    Args:
        active_only: If True, return only patterns with isActive=True

    Returns:
        List of PatternRecord objects sorted by createdAt desc
    """
    client = await get_redis()
    index_key = _index_key()

    # Get all IDs from index
    pattern_ids = await client.smembers(index_key)
    if not pattern_ids:
        return []

    records: list[PatternRecord] = []
    for pid in pattern_ids:
        record = await get_pattern(pid)
        if record is None:
            # Stale index entry — clean up
            await client.srem(index_key, pid)
            continue
        if active_only and not record.isActive:
            continue
        records.append(record)

    # Sort by createdAt descending
    records.sort(key=lambda r: r.createdAt, reverse=True)
    return records


async def delete_pattern(pattern_id: str) -> bool:
    """
    Delete a pattern from Redis and remove it from the index.

    Args:
        pattern_id: Pattern identifier

    Returns:
        True if the pattern existed and was deleted
    """
    client = await get_redis()
    key = _pattern_key(pattern_id)

    deleted = await client.delete(key)
    await client.srem(_index_key(), pattern_id)

    logger.info(f"Pattern deleted: id={pattern_id}, existed={deleted > 0}")
    return deleted > 0


async def set_active_pattern(device_id: str, pattern_id: str) -> bool:
    """
    Record which pattern is active for a device.

    Args:
        device_id: Device identifier
        pattern_id: Pattern to activate

    Returns:
        True if stored successfully
    """
    client = await get_redis()
    key = _active_pattern_key(device_id)
    ok = await client.set(key, pattern_id)
    logger.info(f"Active pattern set: device={device_id}, pattern={pattern_id}")
    return ok is True


async def get_active_pattern_id(device_id: str) -> Optional[str]:
    """
    Get the currently active pattern ID for a device.

    Args:
        device_id: Device identifier

    Returns:
        patternId string or None
    """
    client = await get_redis()
    key = _active_pattern_key(device_id)
    value = await client.get(key)
    return value  # already a string since decode_responses=True


def new_pattern_id() -> str:
    """Generate a URL-safe unique pattern ID, e.g. 'pat-a1b2c3d4'."""
    short = uuid.uuid4().hex[:8]
    return f"pat-{short}"


def now_utc() -> datetime:
    """Return timezone-aware current UTC time."""
    return datetime.now(timezone.utc)
