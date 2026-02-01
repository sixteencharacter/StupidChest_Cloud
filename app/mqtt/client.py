import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import aiomqtt

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.mqtt.handlers import route_message
from app.mqtt.topics import get_subscribe_topics

logger = get_logger(__name__)

# Global MQTT client task
_mqtt_task: Optional[asyncio.Task] = None
_shutdown_event: Optional[asyncio.Event] = None


async def _mqtt_listener() -> None:
    """
    Main MQTT listener coroutine.

    Connects to the broker, subscribes to topics, and processes messages.
    Reconnects automatically on connection loss.
    """
    settings = get_settings()
    topics = get_subscribe_topics()

    reconnect_interval = 5  # seconds

    while not _shutdown_event.is_set():
        try:
            logger.info(f"Connecting to MQTT broker at {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")

            async with aiomqtt.Client(
                hostname=settings.MQTT_BROKER_HOST,
                port=settings.MQTT_BROKER_PORT,
                username=settings.MQTT_USERNAME if settings.MQTT_USERNAME else None,
                password=settings.MQTT_PASSWORD if settings.MQTT_PASSWORD else None,
                identifier=settings.MQTT_CLIENT_ID,
            ) as client:
                # Subscribe to all topics
                for topic in topics:
                    await client.subscribe(topic)
                    logger.info(f"Subscribed to: {topic}")

                logger.info("MQTT client connected and subscribed to all topics")

                # Process messages
                async for message in client.messages:
                    topic = str(message.topic)
                    payload = message.payload

                    # Ensure payload is bytes
                    if isinstance(payload, str):
                        payload = payload.encode()

                    logger.debug(f"MQTT message received: {topic} ({len(payload)} bytes)")

                    try:
                        await route_message(topic, payload)
                    except Exception as e:
                        logger.error(f"Error processing message on {topic}: {e}")

        except aiomqtt.MqttError as e:
            if _shutdown_event.is_set():
                break
            logger.error(f"MQTT connection error: {e}. Reconnecting in {reconnect_interval}s...")
            await asyncio.sleep(reconnect_interval)

        except asyncio.CancelledError:
            logger.info("MQTT listener cancelled")
            break

        except Exception as e:
            if _shutdown_event.is_set():
                break
            logger.error(f"Unexpected MQTT error: {e}. Reconnecting in {reconnect_interval}s...")
            await asyncio.sleep(reconnect_interval)

    logger.info("MQTT listener stopped")


async def start_mqtt() -> None:
    """
    Start the MQTT client listener.

    Should be called during FastAPI lifespan startup.
    """
    global _mqtt_task, _shutdown_event

    logger.info("Starting MQTT client...")
    _shutdown_event = asyncio.Event()
    _mqtt_task = asyncio.create_task(_mqtt_listener())
    logger.info("MQTT client task created")


async def stop_mqtt() -> None:
    """
    Stop the MQTT client listener.

    Should be called during FastAPI lifespan shutdown.
    """
    global _mqtt_task, _shutdown_event

    if _shutdown_event:
        logger.info("Signaling MQTT shutdown...")
        _shutdown_event.set()

    if _mqtt_task:
        logger.info("Cancelling MQTT task...")
        _mqtt_task.cancel()
        try:
            await _mqtt_task
        except asyncio.CancelledError:
            pass
        _mqtt_task = None

    logger.info("MQTT client stopped")


async def publish_message(topic: str, payload: bytes | str, qos: int = 1) -> bool:
    """
    Publish a message to an MQTT topic.

    Note: This creates a new connection for each publish. For production,
    consider maintaining a persistent publish client.

    Args:
        topic: Target topic
        payload: Message payload (bytes or string)
        qos: Quality of Service level (0, 1, or 2)

    Returns:
        True if published successfully
    """
    settings = get_settings()

    if isinstance(payload, str):
        payload = payload.encode()

    try:
        async with aiomqtt.Client(
            hostname=settings.MQTT_BROKER_HOST,
            port=settings.MQTT_BROKER_PORT,
            username=settings.MQTT_USERNAME if settings.MQTT_USERNAME else None,
            password=settings.MQTT_PASSWORD if settings.MQTT_PASSWORD else None,
            identifier=f"{settings.MQTT_CLIENT_ID}-pub",
        ) as client:
            await client.publish(topic, payload, qos=qos)
            logger.info(f"Published to {topic}: {len(payload)} bytes")
            return True

    except Exception as e:
        logger.error(f"Failed to publish to {topic}: {e}")
        return False
