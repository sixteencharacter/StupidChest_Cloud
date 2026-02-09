"""
Events query API endpoints.

GET /api/v1/devices/{deviceId}/events         -> PagedEvents (cursor-based)
GET /api/v1/devices/{deviceId}/events/latest  -> PagedEvents (most recent)
"""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.api import Event, PagedEvents
from app.storage.redis import get_redis

logger = get_logger(__name__)

router = APIRouter(prefix="/devices/{deviceId}/events", tags=["Events"])


def _parse_event(stream_id: str, data: dict) -> Event:
    """Convert a raw Redis stream entry to an Event model."""
    payload = data.get("payload")
    if payload:
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            pass

    matched_raw = data.get("matched")
    matched = None
    if matched_raw is not None:
        matched = matched_raw in ("True", "true", "1", True)

    score_raw = data.get("score")
    score = float(score_raw) if score_raw is not None else None

    return Event(
        eventId=data.get("eventId", stream_id),
        deviceId=data.get("deviceId", ""),
        type=data.get("type", "unknown"),
        ts=data.get("deviceTs"),
        serverReceivedTs=data.get("serverReceivedTs", ""),
        matched=matched,
        score=score,
        pattern=data.get("patternId"),
        payload=payload,
        streamId=stream_id,
    )


def _matches_filters(
    event: Event,
    device_id: str,
    event_type: Optional[str],
    matched: Optional[bool],
    from_ts: Optional[datetime],
    to_ts: Optional[datetime],
) -> bool:
    """Apply in-memory filters. Returns True if event passes all filters."""
    if event.deviceId != device_id:
        return False
    if event_type and event.type != event_type:
        return False
    if matched is not None and event.type == "knock_result":
        if event.matched != matched:
            return False
    if matched is not None and event.type != "knock_result":
        # matched filter only applies to knock_result; skip others
        return False

    # Time window filtering (best-effort using serverReceivedTs)
    if from_ts or to_ts:
        try:
            evt_ts = datetime.fromisoformat(event.serverReceivedTs)
            if from_ts and evt_ts < from_ts:
                return False
            if to_ts and evt_ts > to_ts:
                return False
        except (ValueError, TypeError):
            pass  # skip time filter if ts is unparseable

    return True


@router.get(
    "",
    response_model=PagedEvents,
    summary="Query device events",
    description=(
        "Cursor-based paginated query of device events from Redis Stream. "
        "Supports filtering by type, matched status, and time window."
    ),
)
async def get_events(
    deviceId: str,
    cursor: Optional[str] = Query(None, description="Stream ID to continue from (exclusive)"),
    type: Optional[str] = Query(None, description="Event type filter"),
    matched: Optional[bool] = Query(None, description="Filter knock_result by matched status"),
    limit: int = Query(50, ge=1, le=500, description="Max items to return"),
    from_ts: Optional[datetime] = Query(None, alias="from", description="Start of time window (ISO 8601)"),
    to_ts: Optional[datetime] = Query(None, alias="to", description="End of time window (ISO 8601)"),
) -> PagedEvents:
    settings = get_settings()
    client = await get_redis()

    # Use XRANGE starting after cursor (or from beginning)
    start = f"({cursor}" if cursor else "-"
    end = "+"

    # Read more than `limit` to account for filtering
    read_count = limit * 5

    entries = await client.xrange(settings.EVENT_STREAM_KEY, min=start, max=end, count=read_count)

    items: list[Event] = []
    last_stream_id: Optional[str] = None

    for stream_id, data in entries:
        event = _parse_event(stream_id, data)
        if _matches_filters(event, deviceId, type, matched, from_ts, to_ts):
            items.append(event)
            last_stream_id = stream_id
            if len(items) >= limit:
                break

    # Determine next cursor: if we filled the page, there might be more
    next_cursor = last_stream_id if len(items) >= limit else None

    return PagedEvents(items=items, nextCursor=next_cursor)


@router.get(
    "/latest",
    response_model=PagedEvents,
    summary="Get latest device events",
    description="Returns the most recent events for a device (newest first).",
)
async def get_latest_events(
    deviceId: str,
    limit: int = Query(20, ge=1, le=200, description="Number of recent events"),
) -> PagedEvents:
    settings = get_settings()
    client = await get_redis()

    # XREVRANGE gives newest first; read more to filter by deviceId
    read_count = limit * 5
    entries = await client.xrevrange(settings.EVENT_STREAM_KEY, count=read_count)

    items: list[Event] = []
    for stream_id, data in entries:
        event = _parse_event(stream_id, data)
        if event.deviceId == deviceId:
            items.append(event)
            if len(items) >= limit:
                break

    return PagedEvents(items=items, nextCursor=None)
