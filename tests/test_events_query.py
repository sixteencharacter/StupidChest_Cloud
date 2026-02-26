"""
Tests for Events query API.

GET /api/v1/devices/{deviceId}/events        -> PagedEvents (cursor-based)
GET /api/v1/devices/{deviceId}/events/latest -> PagedEvents (most recent)

Uses FastAPI TestClient with mocked Redis — no real Redis or MQTT needed.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

DEVICE_ID = "test-device-001"
OTHER_DEVICE = "other-device-999"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings():
    s = MagicMock()
    s.EVENT_STREAM_KEY = "knocklock:events"
    return s


def _entry(stream_id: str, device_id: str, event_type: str, extra: dict | None = None) -> tuple:
    """Build a fake Redis stream entry tuple."""
    data = {
        "eventId": f"evt-{stream_id}",
        "deviceId": device_id,
        "type": event_type,
        "deviceTs": "2026-02-01T10:10:00",
        "serverReceivedTs": "2026-02-01T10:10:00+00:00",
        "payload": json.dumps({"data": "stub"}),
    }
    if extra:
        data.update(extra)
    return (stream_id, data)


def _mock_redis(xrange_entries=None, xrevrange_entries=None):
    """Return a mock Redis client with configurable stream results."""
    client = AsyncMock()
    client.xrange = AsyncMock(return_value=xrange_entries or [])
    client.xrevrange = AsyncMock(return_value=xrevrange_entries or [])
    return AsyncMock(return_value=client), client


# ---------------------------------------------------------------------------
# GET /api/v1/devices/{deviceId}/events
# ---------------------------------------------------------------------------


class TestQueryEvents:

    def test_returns_200_empty_when_stream_empty(self):
        get_redis, _ = _mock_redis()
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(f"/api/v1/devices/{DEVICE_ID}/events")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["nextCursor"] is None

    def test_type_logs_returns_only_log_events(self):
        entries = [
            _entry("1-0", DEVICE_ID, "logs",      {"level": "info", "module": "main"}),
            _entry("2-0", DEVICE_ID, "telemetry"),          # different type — filtered out
            _entry("3-0", OTHER_DEVICE, "logs"),             # different device — filtered out
            _entry("4-0", DEVICE_ID, "logs",      {"level": "error", "module": "wifi"}),
        ]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(f"/api/v1/devices/{DEVICE_ID}/events?type=logs")

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert all(e["type"] == "logs" for e in items)
        assert all(e["deviceId"] == DEVICE_ID for e in items)

    def test_no_type_filter_returns_all_events_for_device(self):
        entries = [
            _entry("1-0", DEVICE_ID, "logs"),
            _entry("2-0", DEVICE_ID, "telemetry"),
            _entry("3-0", OTHER_DEVICE, "logs"),   # should be excluded (wrong device)
        ]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(f"/api/v1/devices/{DEVICE_ID}/events")

        items = resp.json()["items"]
        assert len(items) == 2
        assert {e["type"] for e in items} == {"logs", "telemetry"}

    def test_event_fields_populated_correctly(self):
        """Verify that eventId, deviceId, type, serverReceivedTs, payload are all present."""
        entries = [_entry("10-0", DEVICE_ID, "logs", {"level": "warn", "module": "sensor"})]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(f"/api/v1/devices/{DEVICE_ID}/events?type=logs")

        event = resp.json()["items"][0]
        assert event["eventId"] == "evt-10-0"
        assert event["deviceId"] == DEVICE_ID
        assert event["type"] == "logs"
        assert event["serverReceivedTs"] == "2026-02-01T10:10:00+00:00"
        assert event["payload"] is not None
        assert event["streamId"] == "10-0"

    def test_cursor_param_forwarded_to_xrange(self):
        """Cursor value should be passed to xrange as exclusive start."""
        get_redis, mock_client = _mock_redis()
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            TestClient(app).get(f"/api/v1/devices/{DEVICE_ID}/events?cursor=5-0")

        call_kwargs = mock_client.xrange.call_args
        # Exclusive start should be "(5-0"
        assert call_kwargs.kwargs["min"] == "(5-0"

    def test_next_cursor_set_when_page_full(self):
        """nextCursor should be the last streamId when limit is reached."""
        limit = 3
        entries = [_entry(f"{i}-0", DEVICE_ID, "logs") for i in range(1, limit + 1)]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(
                f"/api/v1/devices/{DEVICE_ID}/events?type=logs&limit={limit}"
            )

        body = resp.json()
        assert len(body["items"]) == limit
        assert body["nextCursor"] == f"{limit}-0"

    def test_next_cursor_none_when_page_not_full(self):
        entries = [_entry("1-0", DEVICE_ID, "logs")]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(
                f"/api/v1/devices/{DEVICE_ID}/events?type=logs&limit=50"
            )

        assert resp.json()["nextCursor"] is None


# ---------------------------------------------------------------------------
# GET /api/v1/devices/{deviceId}/events  — knock_result specific
# ---------------------------------------------------------------------------


class TestQueryKnockResult:

    def _knock_entry(self, stream_id: str, matched: bool, score: float = 0.9) -> tuple:
        return _entry(stream_id, DEVICE_ID, "knock_result", {
            "matched": str(matched),
            "score": str(score),
            "patternId": "pat-abc123",
            "action": "unlock" if matched else "deny",
        })

    def test_type_knock_result_returns_only_knock_result_events(self):
        entries = [
            self._knock_entry("1-0", matched=True),
            _entry("2-0", DEVICE_ID, "logs"),           # filtered out
            _entry("3-0", DEVICE_ID, "telemetry"),       # filtered out
            self._knock_entry("4-0", matched=False),
        ]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(
                f"/api/v1/devices/{DEVICE_ID}/events?type=knock_result"
            )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert all(e["type"] == "knock_result" for e in items)

    def test_matched_true_returns_only_matched(self):
        entries = [
            self._knock_entry("1-0", matched=True,  score=0.95),
            self._knock_entry("2-0", matched=False, score=0.30),
            self._knock_entry("3-0", matched=True,  score=0.88),
        ]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(
                f"/api/v1/devices/{DEVICE_ID}/events?type=knock_result&matched=true"
            )

        items = resp.json()["items"]
        assert len(items) == 2
        assert all(e["matched"] is True for e in items)

    def test_matched_false_returns_only_unmatched(self):
        entries = [
            self._knock_entry("1-0", matched=True),
            self._knock_entry("2-0", matched=False),
        ]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(
                f"/api/v1/devices/{DEVICE_ID}/events?type=knock_result&matched=false"
            )

        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["matched"] is False

    def test_knock_result_fields_score_and_pattern_present(self):
        entries = [self._knock_entry("1-0", matched=True, score=0.95)]
        get_redis, _ = _mock_redis(xrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(
                f"/api/v1/devices/{DEVICE_ID}/events?type=knock_result"
            )

        event = resp.json()["items"][0]
        assert event["matched"] is True
        assert event["score"] == pytest.approx(0.95)
        assert event["pattern"] == "pat-abc123"


# ---------------------------------------------------------------------------
# GET /api/v1/devices/{deviceId}/events/latest
# ---------------------------------------------------------------------------


class TestQueryLatestEvents:

    def test_latest_returns_200(self):
        get_redis, _ = _mock_redis(xrevrange_entries=[])
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(f"/api/v1/devices/{DEVICE_ID}/events/latest")

        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_latest_filters_by_device(self):
        entries = [
            _entry("5-0", DEVICE_ID,  "logs"),
            _entry("4-0", OTHER_DEVICE, "logs"),
            _entry("3-0", DEVICE_ID,  "telemetry"),
        ]
        get_redis, _ = _mock_redis(xrevrange_entries=entries)
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            resp = TestClient(app).get(f"/api/v1/devices/{DEVICE_ID}/events/latest")

        items = resp.json()["items"]
        assert len(items) == 2
        assert all(e["deviceId"] == DEVICE_ID for e in items)

    def test_latest_uses_xrevrange(self):
        """Latest endpoint must use XREVRANGE (newest first)."""
        get_redis, mock_client = _mock_redis()
        with (
            patch("app.api.events.get_redis", get_redis),
            patch("app.api.events.get_settings", return_value=_make_settings()),
        ):
            TestClient(app).get(f"/api/v1/devices/{DEVICE_ID}/events/latest")

        mock_client.xrevrange.assert_called_once()
        mock_client.xrange.assert_not_called()
