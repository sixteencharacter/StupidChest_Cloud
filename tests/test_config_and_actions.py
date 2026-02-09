"""
Tests for Config and Actions REST API (Phase 3).

Tests use mocked Redis and MQTT publisher to verify:
- PUT config stores desired config and triggers MQTT publish
- GET config returns snapshot
- POST actions return commandId and issue MQTT publish
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────── Config Tests ────────────────────


class TestConfigAPI:
    """Tests for /api/v1/devices/{deviceId}/config endpoints."""

    @pytest.mark.asyncio
    async def test_put_then_get_config(self, client: TestClient):
        """PUT desired config, then GET snapshot: verify desired is stored."""
        device_id = "test-device-cfg-001"

        desired_body = {
            "rev": 1,
            "data": {"sensitivity": 0.8, "ledBrightness": 50},
        }

        with (
            patch("app.api.config.json_set", new_callable=AsyncMock) as mock_set,
            patch("app.api.config.json_get", new_callable=AsyncMock) as mock_get,
            patch("app.api.config.publisher.publish", new_callable=AsyncMock, return_value=True) as mock_pub,
        ):
            # GET returns what was set by PUT
            mock_get.return_value = None  # no reported

            # --- PUT ---
            response = client.put(
                f"/api/v1/devices/{device_id}/config",
                json=desired_body,
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["deviceId"] == device_id
            assert data["desired"]["rev"] == 1
            assert data["desired"]["data"]["sensitivity"] == 0.8

            # Verify Redis json_set was called with correct key prefix
            mock_set.assert_called_once()
            call_args = mock_set.call_args
            assert device_id in call_args[0][0]  # key contains deviceId

            # Verify MQTT publish was called with retain=True
            mock_pub.assert_called_once()
            pub_args = mock_pub.call_args
            assert "config/desired" in pub_args[0][0]  # topic
            assert pub_args[1]["retain"] is True

        # --- GET ---
        with patch("app.api.config.json_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                {"rev": 1, "data": {"sensitivity": 0.8, "ledBrightness": 50}},  # desired
                None,  # reported
            ]
            response = client.get(f"/api/v1/devices/{device_id}/config")
            assert response.status_code == 200
            snapshot = response.json()
            assert snapshot["deviceId"] == device_id
            assert snapshot["desired"]["rev"] == 1
            assert snapshot["reported"] is None

    @pytest.mark.asyncio
    async def test_sync_config_issues_command(self, client: TestClient):
        """POST /config/sync issues SYNC_CONFIG command via MQTT."""
        device_id = "test-device-cfg-002"

        with patch(
            "app.api.config.publisher.publish",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_pub:
            response = client.post(f"/api/v1/devices/{device_id}/config/sync")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "ISSUED"
            assert body["type"] == "SYNC_CONFIG"
            assert "commandId" in body

            # Verify MQTT publish called with commands topic
            mock_pub.assert_called_once()
            pub_topic = mock_pub.call_args[0][0]
            assert "/commands" in pub_topic


# ──────────────────── Actions Tests ────────────────────


class TestActionsAPI:
    """Tests for /api/v1/devices/{deviceId}/actions/* endpoints."""

    @pytest.mark.asyncio
    async def test_lock_returns_command_issued(self, client: TestClient):
        """POST /actions/lock returns CommandIssued."""
        device_id = "test-device-act-001"

        with patch(
            "app.api.actions.publisher.publish",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_pub:
            response = client.post(f"/api/v1/devices/{device_id}/actions/lock")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "ISSUED"
            assert body["type"] == "LOCK"
            assert "commandId" in body
            assert "issuedAt" in body

            # Verify MQTT payload contains LOCK type
            mock_pub.assert_called_once()
            payload = mock_pub.call_args[0][1]
            assert payload["data"]["type"] == "LOCK"

    @pytest.mark.asyncio
    async def test_unlock_with_duration(self, client: TestClient):
        """POST /actions/unlock with durationMs param."""
        device_id = "test-device-act-002"

        with patch(
            "app.api.actions.publisher.publish",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_pub:
            response = client.post(
                f"/api/v1/devices/{device_id}/actions/unlock",
                json={"durationMs": 5000},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["type"] == "UNLOCK"

            payload = mock_pub.call_args[0][1]
            assert payload["data"]["type"] == "UNLOCK"
            assert payload["data"]["params"]["durationMs"] == 5000

    @pytest.mark.asyncio
    async def test_learn_start(self, client: TestClient):
        """POST /actions/learn/start returns CommandIssued."""
        device_id = "test-device-act-003"

        with patch(
            "app.api.actions.publisher.publish",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = client.post(
                f"/api/v1/devices/{device_id}/actions/learn/start",
                json={"sessionName": "my-pattern", "maxDurationMs": 10000},
            )
            assert response.status_code == 200
            assert response.json()["type"] == "START_LEARN"

    @pytest.mark.asyncio
    async def test_learn_stop(self, client: TestClient):
        """POST /actions/learn/stop returns CommandIssued."""
        device_id = "test-device-act-004"

        with patch(
            "app.api.actions.publisher.publish",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = client.post(
                f"/api/v1/devices/{device_id}/actions/learn/stop",
                json={"saveAsPattern": True, "patternName": "secret-knock"},
            )
            assert response.status_code == 200
            assert response.json()["type"] == "STOP_LEARN"

    @pytest.mark.asyncio
    async def test_publish_failure_returns_502(self, client: TestClient):
        """If MQTT publish fails, action returns 502."""
        device_id = "test-device-act-fail"

        with patch(
            "app.api.actions.publisher.publish",
            new_callable=AsyncMock,
            return_value=False,
        ):
            response = client.post(f"/api/v1/devices/{device_id}/actions/lock")
            assert response.status_code == 502
