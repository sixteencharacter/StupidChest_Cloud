"""
MQTT topic utilities and constants.

Defines topic patterns for the KnockLock IoT protocol and provides
utilities for building and parsing topic strings.

Topic Structure (as per Wireless.pdf):
    knocklock/v1/devices/{device_id}/{message_type}[/{sub_type}]

Subscribe Topics (device -> cloud):
    - knocklock/v1/devices/+/telemetry      - Device telemetry data
    - knocklock/v1/devices/+/knock/live     - Live knock pattern streaming
    - knocklock/v1/devices/+/knock/result   - Knock pattern recognition result
    - knocklock/v1/devices/+/logs           - Device logs
    - knocklock/v1/devices/+/commands/+/ack - Command acknowledgments

Publish Topics (cloud -> device):
    - knocklock/v1/devices/{device_id}/commands/{command_id} - Send commands
    - knocklock/v1/devices/{device_id}/config                - Configuration updates
"""

import re
from typing import Optional

from app.core.settings import get_settings

# Topic suffix constants
TOPIC_TELEMETRY = "telemetry"
TOPIC_KNOCK_LIVE = "knock/live"
TOPIC_KNOCK_RESULT = "knock/result"
TOPIC_LOGS = "logs"
TOPIC_COMMANDS = "commands"
TOPIC_COMMANDS_ACK = "commands/+/ack"
TOPIC_CONFIG = "config"
TOPIC_CONFIG_DESIRED = "config/desired"
TOPIC_CONFIG_REPORTED = "config/reported"


def get_subscribe_topics() -> list[str]:
    """
    Get list of topics to subscribe to with wildcards.

    Returns:
        List of topic patterns with + wildcards for device_id
    """
    settings = get_settings()
    prefix = settings.MQTT_TOPIC_PREFIX

    return [
        f"{prefix}/+/{TOPIC_TELEMETRY}",
        f"{prefix}/+/{TOPIC_KNOCK_LIVE}",
        f"{prefix}/+/{TOPIC_KNOCK_RESULT}",
        f"{prefix}/+/{TOPIC_LOGS}",
        f"{prefix}/+/{TOPIC_COMMANDS_ACK}",
        f"{prefix}/+/{TOPIC_CONFIG_REPORTED}",
    ]


def build_topic(device_id: str, kind: str, sub_id: Optional[str] = None) -> str:
    """
    Build a complete topic string for publishing.

    Args:
        device_id: The device identifier
        kind: Topic type (e.g., "commands", "config", "telemetry")
        sub_id: Optional sub-identifier (e.g., command_id for commands)

    Returns:
        Complete topic string

    Examples:
        >>> build_topic("abc123", "commands", "cmd-001")
        'knocklock/v1/devices/abc123/commands/cmd-001'
        >>> build_topic("abc123", "config")
        'knocklock/v1/devices/abc123/config'
    """
    settings = get_settings()
    prefix = settings.MQTT_TOPIC_PREFIX

    if sub_id:
        return f"{prefix}/{device_id}/{kind}/{sub_id}"
    return f"{prefix}/{device_id}/{kind}"


def parse_device_id_from_topic(topic: str) -> Optional[str]:
    """
    Extract device_id from a topic string.

    Args:
        topic: Full topic string

    Returns:
        Device ID or None if not found

    Examples:
        >>> parse_device_id_from_topic("knocklock/v1/devices/abc123/telemetry")
        'abc123'
    """
    settings = get_settings()
    prefix = settings.MQTT_TOPIC_PREFIX.replace("/", r"\/")

    # Pattern: prefix/{device_id}/...
    pattern = rf"^{prefix}/([^/]+)/.*$"
    match = re.match(pattern, topic)

    if match:
        return match.group(1)
    return None


def parse_command_id_from_ack_topic(topic: str) -> Optional[str]:
    """
    Extract command_id from a command acknowledgment topic.

    Args:
        topic: Full topic string for command ack

    Returns:
        Command ID or None if not an ack topic

    Examples:
        >>> parse_command_id_from_ack_topic("knocklock/v1/devices/abc123/commands/cmd-001/ack")
        'cmd-001'
    """
    settings = get_settings()
    prefix = settings.MQTT_TOPIC_PREFIX.replace("/", r"\/")

    # Pattern: prefix/{device_id}/commands/{command_id}/ack
    pattern = rf"^{prefix}/[^/]+/commands/([^/]+)/ack$"
    match = re.match(pattern, topic)

    if match:
        return match.group(1)
    return None


def get_message_type_from_topic(topic: str) -> Optional[str]:
    """
    Determine the message type from a topic string.

    Args:
        topic: Full topic string

    Returns:
        Message type identifier (e.g., "telemetry", "knock_live", "command_ack")
    """
    if topic.endswith("/telemetry"):
        return "telemetry"
    elif topic.endswith("/knock/live"):
        return "knock_live"
    elif topic.endswith("/knock/result"):
        return "knock_result"
    elif topic.endswith("/logs"):
        return "logs"
    elif "/commands/" in topic and topic.endswith("/ack"):
        return "command_ack"
    elif topic.endswith("/config/reported"):
        return "config_reported"
    return None
