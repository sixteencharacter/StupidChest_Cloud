"""
Redis storage helpers for event streaming.

Handles appending events to Redis Streams.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.storage.redis import get_redis

logger = get_logger(__name__)


async def append_event(
    event_type: str,
    device_id: str,
    payload: dict[str, Any],
    event_id: Optional[str] = None,
    device_ts: Optional[datetime] = None,
    extra_fields: Optional[dict[str, Any]] = None,
) -> str:
    """
    Append an event to the Redis event stream.

    Args:
        event_type: Type of event (telemetry, knock_live, knock_result, logs, command_ack)
        device_id: Device identifier
        payload: Original payload dict
        event_id: Event ID (generated if not provided)
        device_ts: Timestamp from device
        extra_fields: Additional fields to store (e.g., matched, score, patternId)

    Returns:
        The Redis stream entry ID
    """
    settings = get_settings()
    client = await get_redis()

    # Generate event ID if not provided
    if not event_id:
        event_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)

    # Build event data
    event_data = {
        "eventId": event_id,
        "deviceId": device_id,
        "type": event_type,
        "deviceTs": device_ts.isoformat() if device_ts else None,
        "serverReceivedTs": now.isoformat(),
        "payload": json.dumps(payload, default=str),
    }

    # Add extra fields if provided
    if extra_fields:
        for key, value in extra_fields.items():
            if value is not None:
                event_data[key] = json.dumps(value) if isinstance(value, (dict, list)) else str(value)

    # Filter out None values
    event_data = {k: v for k, v in event_data.items() if v is not None}

    # Add to stream with approximate max length
    entry_id = await client.xadd(
        settings.EVENT_STREAM_KEY,
        event_data,
        maxlen=settings.STREAM_MAXLEN,
        approximate=True,
    )

    logger.debug(f"Event appended: stream={settings.EVENT_STREAM_KEY}, id={entry_id}, type={event_type}")
    return entry_id


async def get_recent_events(
    count: int = 100,
    event_type: Optional[str] = None,
    device_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Get recent events from the stream.

    Args:
        count: Maximum number of events to return
        event_type: Filter by event type
        device_id: Filter by device ID

    Returns:
        List of event dictionaries
    """
    settings = get_settings()
    client = await get_redis()

    # Read from stream (newest first using XREVRANGE)
    entries = await client.xrevrange(settings.EVENT_STREAM_KEY, count=count)

    events = []
    for entry_id, data in entries:
        event = {"streamId": entry_id, **data}

        # Parse JSON payload back
        if "payload" in event:
            try:
                event["payload"] = json.loads(event["payload"])
            except json.JSONDecodeError:
                pass

        # Apply filters
        if event_type and event.get("type") != event_type:
            continue
        if device_id and event.get("deviceId") != device_id:
            continue

        events.append(event)

    return events
