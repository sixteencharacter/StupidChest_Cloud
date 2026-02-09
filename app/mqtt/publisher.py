"""
MQTT publish abstraction.

Provides a clean interface for publishing messages to MQTT topics
with JSON serialization and logging.
"""

import json
from datetime import datetime
from typing import Any

import aiomqtt

from app.core.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)


def _json_serializer(obj: Any) -> str:
    """JSON serializer that handles datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


async def publish(
    topic: str,
    payload_dict: dict[str, Any],
    qos: int = 1,
    retain: bool = False,
) -> bool:
    """
    Publish a JSON-serialized message to an MQTT topic.

    Creates a short-lived connection for each publish. Acceptable for
    MVP command/config traffic; a persistent publisher can be added later.

    Args:
        topic: Target MQTT topic
        payload_dict: Payload to JSON-serialize and publish
        qos: Quality of Service level (0, 1, or 2)
        retain: Whether the broker should retain this message

    Returns:
        True if published successfully, False otherwise
    """
    settings = get_settings()

    payload_bytes = json.dumps(payload_dict, default=_json_serializer).encode("utf-8")

    logger.info(
        f"MQTT publish: topic={topic}, retain={retain}, qos={qos}, "
        f"size={len(payload_bytes)} bytes"
    )
    logger.debug(f"MQTT publish payload: {payload_bytes[:500]}")

    try:
        async with aiomqtt.Client(
            hostname=settings.MQTT_BROKER_HOST,
            port=settings.MQTT_BROKER_PORT,
            username=settings.MQTT_USERNAME if settings.MQTT_USERNAME else None,
            password=settings.MQTT_PASSWORD if settings.MQTT_PASSWORD else None,
            identifier=f"{settings.MQTT_CLIENT_ID}-pub",
        ) as client:
            await client.publish(topic, payload_bytes, qos=qos, retain=retain)
            logger.info(f"Published to {topic}: {len(payload_bytes)} bytes (retain={retain})")
            return True

    except Exception as e:
        logger.error(f"Failed to publish to {topic}: {e}")
        return False
