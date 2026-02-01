"""
Redis storage helpers for device state.

Handles storing and retrieving device state snapshots.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.state import DeviceState, DeviceStatus
from app.storage.redis import json_get, json_set

logger = get_logger(__name__)


def _get_state_key(device_id: str) -> str:
    """Get Redis key for device state."""
    settings = get_settings()
    return f"{settings.DEVICE_STATE_KEY_PREFIX}{device_id}"


def compute_status(last_seen: Optional[datetime], ttl_seconds: int) -> DeviceStatus:
    """
    Compute device status based on last seen time.

    Args:
        last_seen: Last time device was seen
        ttl_seconds: Seconds after which device is considered offline

    Returns:
        DeviceStatus enum value
    """
    if last_seen is None:
        return DeviceStatus.UNKNOWN

    now = datetime.now(timezone.utc)

    # Ensure last_seen is timezone-aware
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)

    elapsed = (now - last_seen).total_seconds()

    if elapsed <= ttl_seconds:
        return DeviceStatus.ONLINE
    return DeviceStatus.OFFLINE


async def get_state(device_id: str) -> Optional[DeviceState]:
    """
    Get device state from Redis.

    Args:
        device_id: Device identifier

    Returns:
        DeviceState or None if not found
    """
    key = _get_state_key(device_id)
    data = await json_get(key)

    if data is None:
        return None

    # Compute current status based on lastSeen
    settings = get_settings()
    state = DeviceState.model_validate(data)

    # Update status dynamically based on lastSeen
    state.status = compute_status(state.lastSeen, settings.ONLINE_TTL_SEC)

    return state


async def upsert_state(device_id: str, updates: dict[str, Any]) -> DeviceState:
    """
    Update device state, creating if not exists.

    Args:
        device_id: Device identifier
        updates: Fields to update

    Returns:
        Updated DeviceState
    """
    key = _get_state_key(device_id)
    now = datetime.now(timezone.utc)

    # Get existing state or create new
    existing = await json_get(key)

    if existing:
        state_dict = existing
    else:
        state_dict = {"deviceId": device_id}

    # Apply updates
    for field, value in updates.items():
        if value is not None:
            # Handle nested objects (convert Pydantic models to dict)
            if hasattr(value, "model_dump"):
                state_dict[field] = value.model_dump(mode="json")
            elif isinstance(value, datetime):
                state_dict[field] = value.isoformat()
            else:
                state_dict[field] = value

    # Always update lastSeen and updatedAt
    state_dict["lastSeen"] = now.isoformat()
    state_dict["updatedAt"] = now.isoformat()

    # Save to Redis
    await json_set(key, state_dict)

    # Return validated state
    settings = get_settings()
    state = DeviceState.model_validate(state_dict)
    state.status = compute_status(state.lastSeen, settings.ONLINE_TTL_SEC)

    logger.debug(f"State updated: device={device_id}, status={state.status}")
    return state


async def update_telemetry(device_id: str, telemetry_data: dict[str, Any], ts: datetime) -> DeviceState:
    """
    Update device state with new telemetry.

    Args:
        device_id: Device identifier
        telemetry_data: Telemetry data dict
        ts: Timestamp from device

    Returns:
        Updated DeviceState
    """
    telemetry_snapshot = {**telemetry_data, "ts": ts.isoformat()}
    return await upsert_state(device_id, {"telemetry": telemetry_snapshot})


async def update_knock_result(
    device_id: str,
    matched: bool,
    ts: datetime,
    pattern_id: Optional[str] = None,
    score: Optional[float] = None,
    threshold: Optional[float] = None,
    action: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> DeviceState:
    """
    Update device state with knock result.

    Args:
        device_id: Device identifier
        matched: Whether pattern matched
        ts: Timestamp from device
        pattern_id: Matched pattern ID
        score: Match score
        threshold: Match threshold
        action: Action taken
        latency_ms: Processing latency

    Returns:
        Updated DeviceState
    """
    knock_result = {
        "matched": matched,
        "patternId": pattern_id,
        "score": score,
        "threshold": threshold,
        "action": action,
        "latencyMs": latency_ms,
        "ts": ts.isoformat(),
    }
    # Remove None values
    knock_result = {k: v for k, v in knock_result.items() if v is not None}
    knock_result["matched"] = matched  # Always include matched
    knock_result["ts"] = ts.isoformat()  # Always include ts

    return await upsert_state(device_id, {"lastKnockResult": knock_result})


async def update_last_log(device_id: str, log_data: dict[str, Any]) -> DeviceState:
    """
    Update device state with last log entry.

    Args:
        device_id: Device identifier
        log_data: Log data dict

    Returns:
        Updated DeviceState
    """
    return await upsert_state(device_id, {"lastLog": log_data})
