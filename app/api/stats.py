"""
Stats API endpoints.

GET /api/v1/stats/knocks?deviceId=&from=&to=&bucket=
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.api import BucketSize, KnockBucketPoint, KnockStats
from app.storage.redis import get_redis

logger = get_logger(__name__)

router = APIRouter(prefix="/stats", tags=["Stats"])

# Bucket duration in seconds
_BUCKET_SECONDS = {
    BucketSize.TEN_SEC: 10,
    BucketSize.ONE_MIN: 60,
    BucketSize.FIVE_MIN: 300,
    BucketSize.FIFTEEN_MIN: 900,
    BucketSize.ONE_HOUR: 3600,
    BucketSize.ONE_DAY: 86400,
}


def _bucket_start(ts: datetime, bucket_seconds: int) -> datetime:
    """Truncate a timestamp to the start of its bucket."""
    epoch = int(ts.timestamp())
    truncated = (epoch // bucket_seconds) * bucket_seconds
    return datetime.fromtimestamp(truncated, tz=timezone.utc)


@router.get(
    "/knocks",
    response_model=KnockStats,
    summary="Aggregate knock statistics",
    description=(
        "Reads knock_result events from the Redis Stream and bucketizes "
        "totals/matched/failed counts."
    ),
)
async def get_knock_stats(
    deviceId: str = Query(..., description="Device ID (required)"),
    bucket: BucketSize = Query(BucketSize.ONE_MIN, description="Bucket size"),
    from_ts: Optional[datetime] = Query(None, alias="from", description="Start of window (ISO 8601)"),
    to_ts: Optional[datetime] = Query(None, alias="to", description="End of window (ISO 8601)"),
) -> KnockStats:
    settings = get_settings()
    client = await get_redis()

    bucket_seconds = _BUCKET_SECONDS[bucket]

    # Read all knock_result events (scan the stream)
    entries = await client.xrange(settings.EVENT_STREAM_KEY, min="-", max="+")

    # Aggregate per bucket
    buckets: dict[str, dict] = defaultdict(lambda: {"total": 0, "matched": 0, "failed": 0})

    for _stream_id, data in entries:
        if data.get("type") != "knock_result":
            continue
        if data.get("deviceId") != deviceId:
            continue

        # Parse timestamp
        ts_str = data.get("serverReceivedTs") or data.get("deviceTs")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        # Time window filter
        if from_ts and ts < from_ts:
            continue
        if to_ts and ts > to_ts:
            continue

        b_start = _bucket_start(ts, bucket_seconds)
        key = b_start.isoformat()
        buckets[key]["total"] += 1

        matched_raw = data.get("matched")
        is_matched = matched_raw in ("True", "true", "1", True)
        if is_matched:
            buckets[key]["matched"] += 1
        else:
            buckets[key]["failed"] += 1

    # Sort buckets chronologically
    series = [
        KnockBucketPoint(t=k, **v) for k, v in sorted(buckets.items())
    ]

    return KnockStats(
        deviceId=deviceId,
        bucket=bucket.value,
        series=series,
    )

@router.get("/{dev_id}/snapshot",description=("return latest snapshot of the specified device"))
async def return_dev_snapshot(dev_id : str) :
    client = await get_redis()
    raw_data = await client.get("knocklock:device_state:{}".format(dev_id))
    return json.loads(raw_data)
