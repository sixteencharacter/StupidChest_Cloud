import pytest

from app.mqtt.topics import (
    build_topic,
    get_message_type_from_topic,
    get_subscribe_topics,
    parse_command_id_from_ack_topic,
    parse_device_id_from_topic,
)


class TestBuildTopic:
    """Tests for build_topic function."""

    def test_build_simple_topic(self):
        """Test building a simple topic."""
        topic = build_topic("abc123", "telemetry")
        assert topic == "knocklock/v1/devices/abc123/telemetry"

    def test_build_topic_with_sub_id(self):
        """Test building a topic with sub-identifier."""
        topic = build_topic("abc123", "commands", "cmd-001")
        assert topic == "knocklock/v1/devices/abc123/commands/cmd-001"

    def test_build_config_topic(self):
        """Test building a config topic."""
        topic = build_topic("device-xyz", "config")
        assert topic == "knocklock/v1/devices/device-xyz/config"


class TestParseDeviceId:
    """Tests for parse_device_id_from_topic function."""

    def test_parse_from_telemetry_topic(self):
        """Test parsing device ID from telemetry topic."""
        device_id = parse_device_id_from_topic("knocklock/v1/devices/abc123/telemetry")
        assert device_id == "abc123"

    def test_parse_from_knock_topic(self):
        """Test parsing device ID from knock topic."""
        device_id = parse_device_id_from_topic("knocklock/v1/devices/xyz789/knock/live")
        assert device_id == "xyz789"

    def test_parse_from_ack_topic(self):
        """Test parsing device ID from ack topic."""
        device_id = parse_device_id_from_topic("knocklock/v1/devices/dev-001/commands/cmd-123/ack")
        assert device_id == "dev-001"

    def test_parse_invalid_topic_returns_none(self):
        """Test that invalid topic returns None."""
        device_id = parse_device_id_from_topic("invalid/topic")
        assert device_id is None


class TestParseCommandId:
    """Tests for parse_command_id_from_ack_topic function."""

    def test_parse_command_id(self):
        """Test parsing command ID from ack topic."""
        command_id = parse_command_id_from_ack_topic(
            "knocklock/v1/devices/abc123/commands/cmd-456/ack"
        )
        assert command_id == "cmd-456"

    def test_non_ack_topic_returns_none(self):
        """Test that non-ack topic returns None."""
        command_id = parse_command_id_from_ack_topic(
            "knocklock/v1/devices/abc123/telemetry"
        )
        assert command_id is None


class TestGetMessageType:
    """Tests for get_message_type_from_topic function."""

    def test_telemetry_type(self):
        """Test telemetry message type detection."""
        msg_type = get_message_type_from_topic("knocklock/v1/devices/abc/telemetry")
        assert msg_type == "telemetry"

    def test_knock_live_type(self):
        """Test knock_live message type detection."""
        msg_type = get_message_type_from_topic("knocklock/v1/devices/abc/knock/live")
        assert msg_type == "knock_live"

    def test_knock_result_type(self):
        """Test knock_result message type detection."""
        msg_type = get_message_type_from_topic("knocklock/v1/devices/abc/knock/result")
        assert msg_type == "knock_result"

    def test_logs_type(self):
        """Test logs message type detection."""
        msg_type = get_message_type_from_topic("knocklock/v1/devices/abc/logs")
        assert msg_type == "logs"

    def test_command_ack_type(self):
        """Test command_ack message type detection."""
        msg_type = get_message_type_from_topic("knocklock/v1/devices/abc/commands/123/ack")
        assert msg_type == "command_ack"

    def test_unknown_type_returns_none(self):
        """Test unknown topic returns None."""
        msg_type = get_message_type_from_topic("knocklock/v1/devices/abc/unknown")
        assert msg_type is None


class TestGetSubscribeTopics:
    """Tests for get_subscribe_topics function."""

    def test_returns_all_topics(self):
        """Test that all required topics are returned."""
        topics = get_subscribe_topics()

        assert len(topics) == 5
        assert any("telemetry" in t for t in topics)
        assert any("knock/live" in t for t in topics)
        assert any("knock/result" in t for t in topics)
        assert any("logs" in t for t in topics)
        assert any("commands/+/ack" in t for t in topics)

    def test_topics_have_wildcard(self):
        """Test that topics use + wildcard for device_id."""
        topics = get_subscribe_topics()
        for topic in topics:
            assert "/+/" in topic
