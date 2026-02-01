"""
Tests for MQTT ingest handlers.

Tests that messages are correctly parsed, validated, and stored in Redis.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.models.mqtt import TelemetryPayload, KnockResultPayload
from app.mqtt.handlers import (
    PayloadTooLargeError,
    PayloadValidationError,
    route_message,
)


# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def fixture_bytes(name: str) -> bytes:
    """Load a fixture as bytes."""
    return json.dumps(load_fixture(name)).encode("utf-8")


class TestPayloadValidation:
    """Tests for payload validation."""

    def test_telemetry_payload_valid(self):
        """Test that valid telemetry payload passes validation."""
        data = load_fixture("telemetry_payload.json")
        payload = TelemetryPayload.model_validate(data)

        assert payload.meta.schema_ == "telemetry/v1"
        assert payload.meta.deviceId == "test-device-001"
        assert payload.data.battery == 85
        assert payload.data.rssi == -45

    def test_knock_result_payload_valid(self):
        """Test that valid knock result payload passes validation."""
        data = load_fixture("knock_result_payload.json")
        payload = KnockResultPayload.model_validate(data)

        assert payload.meta.schema_ == "knock_result/v1"
        assert payload.data.matched is True
        assert payload.data.score == 0.95
        assert payload.data.action.value == "unlock"


class TestRouteMessage:
    """Tests for route_message function."""

    @pytest.mark.asyncio
    async def test_payload_too_large(self):
        """Test that oversized payloads are rejected."""
        topic = "knocklock/v1/devices/test-device/telemetry"
        # Create a payload larger than MAX_PAYLOAD_BYTES
        large_payload = b"x" * 300000

        with patch("app.mqtt.handlers.get_settings") as mock_settings:
            mock_settings.return_value.MAX_PAYLOAD_BYTES = 256000
            with pytest.raises(PayloadTooLargeError):
                await route_message(topic, large_payload)

    @pytest.mark.asyncio
    async def test_invalid_json_rejected(self):
        """Test that invalid JSON is rejected."""
        topic = "knocklock/v1/devices/test-device/telemetry"
        invalid_json = b"not valid json {"

        with patch("app.mqtt.handlers.get_settings") as mock_settings:
            mock_settings.return_value.MAX_PAYLOAD_BYTES = 256000
            with pytest.raises(PayloadValidationError):
                await route_message(topic, invalid_json)

    @pytest.mark.asyncio
    async def test_unknown_topic_ignored(self):
        """Test that unknown topics are silently ignored."""
        topic = "unknown/topic/path"
        payload = b'{"test": "data"}'

        with patch("app.mqtt.handlers.get_settings") as mock_settings:
            mock_settings.return_value.MAX_PAYLOAD_BYTES = 256000
            # Should not raise, just log and return
            await route_message(topic, payload)

    @pytest.mark.asyncio
    async def test_telemetry_handler_called(self):
        """Test that telemetry messages are routed to handler."""
        topic = "knocklock/v1/devices/test-device-001/telemetry"
        payload = fixture_bytes("telemetry_payload.json")

        with patch("app.mqtt.handlers.get_settings") as mock_settings:
            mock_settings.return_value.MAX_PAYLOAD_BYTES = 256000
            with patch("app.mqtt.handlers.handle_telemetry", new_callable=AsyncMock) as mock_handler:
                await route_message(topic, payload)
                mock_handler.assert_called_once()
                # Verify device_id was extracted from topic
                call_args = mock_handler.call_args
                assert call_args[0][0] == "test-device-001"

    @pytest.mark.asyncio
    async def test_knock_result_handler_called(self):
        """Test that knock result messages are routed to handler."""
        topic = "knocklock/v1/devices/test-device-001/knock/result"
        payload = fixture_bytes("knock_result_payload.json")

        with patch("app.mqtt.handlers.get_settings") as mock_settings:
            mock_settings.return_value.MAX_PAYLOAD_BYTES = 256000
            with patch("app.mqtt.handlers.handle_knock_result", new_callable=AsyncMock) as mock_handler:
                await route_message(topic, payload)
                mock_handler.assert_called_once()


class TestHandlerIntegration:
    """Integration tests for handlers with Redis (requires running Redis)."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_telemetry_stores_state(self):
        """Test that telemetry updates device state in Redis."""
        # This test requires a running Redis instance
        # Skip if Redis is not available
        pytest.skip("Integration test - requires Redis")
