"""
Tests for Events and Stats API (Phase 3).

Uses a fake Redis client to test stream queries, pagination, and stats aggregation.
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ── Helpers to build fake Redis stream entries ──

def _make_stream_entry(
    stream_id: str,
    device_id: str,
    event_type: str,
    server_ts: str,
    extra: dict | None = None,
) -> tuple[str, dict]:
    """Build a (stream_id, data) tuple like redis.xrange returns."""
    data = {
        "eventId": f"evt-{stream_id}",
        "deviceId": device_id,
        "type": event_type,
        "serverReceivedTs": server_ts,
        "payload": json.dumps({"test": True}),
    }
    if extra:
        data.update(extra)
    return (stream_id, data)


DEVICE_ID = "test-device-evt-001"
BASE_TS = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)

# Build a batch of sample events
SAMPLE_ENTRIES = [
    _make_stream_entry(
        f"1706788800000-{i}",
        DEVICE_ID,
        "knock_result",
        (BASE_TS + timedelta(seconds=i * 10)).isoformat(),
        extra={"matched": "true" if i % 2 == 0 else "false", "score": str(0.8 + i * 0.01)},
    )
    for i in range(20)
] + [
    _make_stream_entry(
        f"1706788800000-{20 + i}",
        DEVICE_ID,
        "telemetry",
        (BASE_TS + timedelta(seconds=(20 + i) * 10)).isoformat(),
    )
    for i in range(5)
]


# ──────────────────── Events Tests ────────────────────


class TestEventsAPI:
    """Tests for /api/v1/devices/{deviceId}/events endpoints."""

    @pytest.mark.asyncio
    async def test_latest_returns_correct_count(self, client: TestClient):
        """GET /events/latest returns up to limit items for given deviceId."""
        fake_redis = AsyncMock()
        fake_redis.xrevrange = AsyncMock(return_value=list(reversed(SAMPLE_ENTRIES)))

        with patch("app.api.events.get_redis", return_value=fake_redis):
            response = client.get(
                f"/api/v1/devices/{DEVICE_ID}/events/latest?limit=5"
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) == 5
            # All items belong to our device
            for item in body["items"]:
                assert item["deviceId"] == DEVICE_ID

    @pytest.mark.asyncio
    async def test_events_pagination_returns_next_cursor(self, client: TestClient):
        """GET /events with limit < total returns nextCursor."""
        fake_redis = AsyncMock()
        fake_redis.xrange = AsyncMock(return_value=SAMPLE_ENTRIES)

        with patch("app.api.events.get_redis", return_value=fake_redis):
            response = client.get(
                f"/api/v1/devices/{DEVICE_ID}/events?limit=5"
            )
            assert response.status_code == 200
            body = response.json()
            assert len(body["items"]) == 5
            assert body["nextCursor"] is not None, "Expected a nextCursor when more items exist"

    @pytest.mark.asyncio
    async def test_events_type_filter(self, client: TestClient):
        """GET /events?type=telemetry filters to only telemetry events."""
        fake_redis = AsyncMock()
        fake_redis.xrange = AsyncMock(return_value=SAMPLE_ENTRIES)

        with patch("app.api.events.get_redis", return_value=fake_redis):
            response = client.get(
                f"/api/v1/devices/{DEVICE_ID}/events?type=telemetry&limit=50"
            )
            assert response.status_code == 200
            body = response.json()
            for item in body["items"]:
                assert item["type"] == "telemetry"
            assert len(body["items"]) == 5  # we have exactly 5 telemetry events

    @pytest.mark.asyncio
    async def test_events_matched_filter(self, client: TestClient):
        """GET /events?type=knock_result&matched=true filters to matched only."""
        fake_redis = AsyncMock()
        fake_redis.xrange = AsyncMock(return_value=SAMPLE_ENTRIES)

        with patch("app.api.events.get_redis", return_value=fake_redis):
            response = client.get(
                f"/api/v1/devices/{DEVICE_ID}/events?matched=true&limit=50"
            )
            assert response.status_code == 200
            body = response.json()
            for item in body["items"]:
                assert item["type"] == "knock_result"
                assert item["matched"] is True
            # Even indices (0,2,4,...18) -> 10 matched events
            assert len(body["items"]) == 10


# ──────────────────── Stats Tests ────────────────────


class TestStatsAPI:
    """Tests for /api/v1/stats/knocks endpoint."""

    @pytest.mark.asyncio
    async def test_knock_stats_aggregation(self, client: TestClient):
        """GET /stats/knocks aggregates knock_result events into buckets."""
        fake_redis = AsyncMock()
        fake_redis.xrange = AsyncMock(return_value=SAMPLE_ENTRIES)

        with patch("app.api.stats.get_redis", return_value=fake_redis):
            response = client.get(
                f"/api/v1/stats/knocks?deviceId={DEVICE_ID}&bucket=1m"
            )
            assert response.status_code == 200
            body = response.json()
            assert body["deviceId"] == DEVICE_ID
            assert body["bucket"] == "1m"

            series = body["series"]
            assert len(series) > 0

            # Sum all totals across buckets – should equal 20 knock_result events
            total = sum(p["total"] for p in series)
            assert total == 20

            # Sum matched across buckets – should equal 10 (even indices)
            matched = sum(p["matched"] for p in series)
            assert matched == 10

            # Sum failed across buckets – should equal 10 (odd indices)
            failed = sum(p["failed"] for p in series)
            assert failed == 10

    @pytest.mark.asyncio
    async def test_knock_stats_empty(self, client: TestClient):
        """GET /stats/knocks returns empty series when no events."""
        fake_redis = AsyncMock()
        fake_redis.xrange = AsyncMock(return_value=[])

        with patch("app.api.stats.get_redis", return_value=fake_redis):
            response = client.get(
                f"/api/v1/stats/knocks?deviceId=no-such-device&bucket=5m"
            )
            assert response.status_code == 200
            body = response.json()
            assert body["series"] == []

    @pytest.mark.asyncio
    async def test_knock_stats_bucket_sizes(self, client: TestClient):
        """All supported bucket sizes are accepted."""
        fake_redis = AsyncMock()
        fake_redis.xrange = AsyncMock(return_value=[])

        for bucket in ["10s", "1m", "5m", "15m", "1h", "1d"]:
            with patch("app.api.stats.get_redis", return_value=fake_redis):
                response = client.get(
                    f"/api/v1/stats/knocks?deviceId={DEVICE_ID}&bucket={bucket}"
                )
                assert response.status_code == 200, f"Failed for bucket={bucket}"
