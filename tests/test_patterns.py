"""
Tests for Pattern Registration API.

Covers CRUD operations on /api/v1/patterns and the /activate endpoint.
Uses FastAPI TestClient with mocked Redis and MQTT calls.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.mqtt import KnockLivePayload
from app.models.pattern import PatternAlgo, PatternRecord, PatternRepresentation

# ──────────────────── Fixtures ────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# A minimal valid pattern payload
INTERVALS_PATTERN = {
    "name": "Three Knocks",
    "algo": "intervals",
    "representation": {
        "type": "intervals",
        "intervalsMs": [300, 150, 600],
        "toleranceMs": 80,
    },
}

# A sample PatternRecord for mocking storage returns
MOCK_RECORD = PatternRecord(
    patternId="pat-abc12345",
    name="Three Knocks",
    algo=PatternAlgo.INTERVALS,
    version=1,
    isActive=False,
    representation=PatternRepresentation(
        type="intervals",
        intervalsMs=[300, 150, 600],
        toleranceMs=80,
    ),
    createdAt=datetime(2026, 1, 26, 13, 0, 0, tzinfo=timezone.utc),
    updatedAt=datetime(2026, 1, 26, 13, 0, 0, tzinfo=timezone.utc),
)


# ──────────────────── KnockLive payload schema ────────────────────


class TestKnockLiveNewSchema:
    """Validate the updated KnockLive payload schema."""

    def test_knock_live_v2_fixture_valid(self):
        """New knock.live.v1 spec payload should validate correctly."""
        with open(FIXTURES_DIR / "knock_live_v2_payload.json") as f:
            data = json.load(f)

        payload = KnockLivePayload.model_validate(data)

        assert len(payload.data.knocks) == 3
        assert payload.data.knocks[0].tOffsetMs == 120
        assert payload.data.knocks[0].amp == pytest.approx(0.62)
        assert payload.data.windowMs == 2000
        assert payload.data.features is not None
        assert payload.data.features.intervalsMs == [420, 440]
        assert payload.data.features.energy == pytest.approx(1.81)

    def test_knock_live_minimal_valid(self):
        """Knock live with only required fields should validate."""
        data = {
            "meta": {
                "schema": "knock.live.v1",
                "deviceId": "dev-001",
                "ts": "2026-01-26T13:20:05.120Z",
            },
            "data": {
                "knocks": [
                    {"tOffsetMs": 100, "amp": 0.5},
                ]
            },
        }
        payload = KnockLivePayload.model_validate(data)
        assert len(payload.data.knocks) == 1
        assert payload.data.windowMs is None
        assert payload.data.features is None


# ──────────────────── Patterns CRUD ────────────────────


class TestPatternCreate:
    """POST /api/v1/patterns"""

    def test_create_pattern_returns_201(self):
        with (
            patch("app.api.patterns.save_pattern", new_callable=AsyncMock) as mock_save,
            patch("app.api.patterns.new_pattern_id", return_value="pat-abc12345"),
        ):
            mock_save.return_value = True
            client = TestClient(app)
            response = client.post("/api/v1/patterns/", json=INTERVALS_PATTERN)

        assert response.status_code == 201
        data = response.json()
        assert data["patternId"] == "pat-abc12345"
        assert data["name"] == "Three Knocks"
        assert data["version"] == 1
        assert data["algo"] == "intervals"
        assert data["isActive"] is False
        assert "representation" in data
        assert data["representation"]["intervalsMs"] == [300, 150, 600]

    def test_create_pattern_missing_representation_returns_422(self):
        client = TestClient(app)
        response = client.post("/api/v1/patterns/", json={"name": "Bad", "algo": "intervals"})
        assert response.status_code == 422


class TestPatternList:
    """GET /api/v1/patterns"""

    def test_list_patterns_returns_200(self):
        with patch(
            "app.api.patterns.list_patterns", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = [MOCK_RECORD]
            client = TestClient(app)
            response = client.get("/api/v1/patterns/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["patternId"] == "pat-abc12345"
        # Summary should NOT contain representation
        assert "representation" not in data[0]
        mock_list.assert_called_once_with(active_only=False)

    def test_list_patterns_active_only(self):
        with patch(
            "app.api.patterns.list_patterns", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = []
            client = TestClient(app)
            response = client.get("/api/v1/patterns/?activeOnly=true")

        assert response.status_code == 200
        mock_list.assert_called_once_with(active_only=True)

    def test_list_patterns_empty_returns_empty_list(self):
        with patch(
            "app.api.patterns.list_patterns", new_callable=AsyncMock, return_value=[]
        ):
            client = TestClient(app)
            response = client.get("/api/v1/patterns/")

        assert response.status_code == 200
        assert response.json() == []


class TestPatternGet:
    """GET /api/v1/patterns/{patternId}"""

    def test_get_existing_pattern_returns_detail(self):
        with patch(
            "app.api.patterns.get_pattern", new_callable=AsyncMock, return_value=MOCK_RECORD
        ):
            client = TestClient(app)
            response = client.get("/api/v1/patterns/pat-abc12345")

        assert response.status_code == 200
        data = response.json()
        assert data["patternId"] == "pat-abc12345"
        # Detail SHOULD include representation
        assert "representation" in data
        assert data["representation"]["toleranceMs"] == 80

    def test_get_nonexistent_pattern_returns_404(self):
        with patch(
            "app.api.patterns.get_pattern", new_callable=AsyncMock, return_value=None
        ):
            client = TestClient(app)
            response = client.get("/api/v1/patterns/pat-doesnotexist")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestPatternUpdate:
    """PUT /api/v1/patterns/{patternId}"""

    def test_update_pattern_bumps_version(self):
        updated_body = {
            "name": "Four Knocks",
            "algo": "intervals",
            "representation": {
                "type": "intervals",
                "intervalsMs": [200, 200, 200, 200],
                "toleranceMs": 60,
            },
        }
        with (
            patch(
                "app.api.patterns.get_pattern",
                new_callable=AsyncMock,
                return_value=MOCK_RECORD,
            ),
            patch("app.api.patterns.save_pattern", new_callable=AsyncMock) as mock_save,
        ):
            mock_save.return_value = True
            client = TestClient(app)
            response = client.put("/api/v1/patterns/pat-abc12345", json=updated_body)

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == 2  # bumped
        assert data["name"] == "Four Knocks"
        assert data["representation"]["intervalsMs"] == [200, 200, 200, 200]

    def test_update_nonexistent_pattern_returns_404(self):
        with patch(
            "app.api.patterns.get_pattern", new_callable=AsyncMock, return_value=None
        ):
            client = TestClient(app)
            response = client.put(
                "/api/v1/patterns/pat-ghost",
                json=INTERVALS_PATTERN,
            )
        assert response.status_code == 404


class TestPatternDelete:
    """DELETE /api/v1/patterns/{patternId}"""

    def test_delete_existing_pattern_returns_204(self):
        with patch(
            "app.api.patterns.delete_pattern", new_callable=AsyncMock, return_value=True
        ):
            client = TestClient(app)
            response = client.delete("/api/v1/patterns/pat-abc12345")

        assert response.status_code == 204

    def test_delete_nonexistent_pattern_returns_404(self):
        with patch(
            "app.api.patterns.delete_pattern", new_callable=AsyncMock, return_value=False
        ):
            client = TestClient(app)
            response = client.delete("/api/v1/patterns/pat-ghost")

        assert response.status_code == 404


class TestPatternActivate:
    """POST /api/v1/patterns/{patternId}/activate"""

    def test_activate_pattern_with_mqtt_success(self):
        activate_body = {"deviceId": "pc-001", "syncNow": True}
        with (
            patch(
                "app.api.patterns.get_pattern",
                new_callable=AsyncMock,
                return_value=MOCK_RECORD,
            ),
            patch("app.api.patterns.save_pattern", new_callable=AsyncMock, return_value=True),
            patch("app.api.patterns.set_active_pattern", new_callable=AsyncMock, return_value=True),
            patch(
                "app.api.patterns.publisher.publish_pattern_desired",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_publish,
        ):
            client = TestClient(app)
            response = client.post("/api/v1/patterns/pat-abc12345/activate", json=activate_body)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "ACCEPTED"
        mock_publish.assert_called_once()

    def test_activate_pattern_mqtt_fail_still_returns_202(self):
        """MQTT publish failure should NOT cause 5xx — returns 202 with warning message."""
        activate_body = {"deviceId": "pc-001", "syncNow": True}
        with (
            patch(
                "app.api.patterns.get_pattern",
                new_callable=AsyncMock,
                return_value=MOCK_RECORD,
            ),
            patch("app.api.patterns.save_pattern", new_callable=AsyncMock, return_value=True),
            patch("app.api.patterns.set_active_pattern", new_callable=AsyncMock, return_value=True),
            patch(
                "app.api.patterns.publisher.publish_pattern_desired",
                new_callable=AsyncMock,
                return_value=False,  # MQTT failure
            ),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/patterns/pat-abc12345/activate", json=activate_body)

        assert response.status_code == 202
        assert "MQTT push failed" in response.json()["message"]

    def test_activate_without_sync_skips_mqtt(self):
        """syncNow=false should save to Redis but not call MQTT publish."""
        activate_body = {"deviceId": "pc-001", "syncNow": False}
        with (
            patch(
                "app.api.patterns.get_pattern",
                new_callable=AsyncMock,
                return_value=MOCK_RECORD,
            ),
            patch("app.api.patterns.save_pattern", new_callable=AsyncMock, return_value=True),
            patch("app.api.patterns.set_active_pattern", new_callable=AsyncMock, return_value=True),
            patch(
                "app.api.patterns.publisher.publish_pattern_desired",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            client = TestClient(app)
            response = client.post("/api/v1/patterns/pat-abc12345/activate", json=activate_body)

        assert response.status_code == 202
        mock_publish.assert_not_called()

    def test_activate_nonexistent_pattern_returns_404(self):
        with patch(
            "app.api.patterns.get_pattern", new_callable=AsyncMock, return_value=None
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/patterns/pat-ghost/activate",
                json={"deviceId": "pc-001"},
            )

        assert response.status_code == 404
