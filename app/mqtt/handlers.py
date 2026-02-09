"""
MQTT message handlers.

Routes incoming MQTT messages to appropriate handlers and persists to Redis.
"""

import json
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.mqtt import (
    CommandAckPayload,
    KnockLivePayload,
    KnockResultPayload,
    LogsPayload,
    TelemetryPayload,
)
from app.mqtt.topics import (
    get_message_type_from_topic,
    parse_command_id_from_ack_topic,
    parse_device_id_from_topic,
)
from app.storage.events import append_event
from app.storage.redis import json_set
from app.storage.state import (
    update_knock_result,
    update_last_log,
    update_telemetry,
    upsert_state,
)

logger = get_logger(__name__)


class PayloadTooLargeError(Exception):
    """Raised when payload exceeds MAX_PAYLOAD_BYTES."""

    pass


class PayloadValidationError(Exception):
    """Raised when payload fails validation."""

    pass


async def route_message(topic: str, payload: bytes) -> None:
    """
    Route an incoming MQTT message to the appropriate handler.

    Args:
        topic: The MQTT topic the message was received on
        payload: The raw message payload bytes

    Raises:
        PayloadTooLargeError: If payload exceeds limit
        PayloadValidationError: If payload validation fails
    """
    settings = get_settings()

    # Guard: Check payload size
    if len(payload) > settings.MAX_PAYLOAD_BYTES:
        logger.warning(f"Payload too large: {len(payload)} bytes > {settings.MAX_PAYLOAD_BYTES}")
        raise PayloadTooLargeError(f"Payload size {len(payload)} exceeds limit {settings.MAX_PAYLOAD_BYTES}")

    # Parse device_id from topic (source of truth)
    device_id = parse_device_id_from_topic(topic)
    message_type = get_message_type_from_topic(topic)

    if not device_id:
        logger.warning(f"Could not parse device_id from topic: {topic}")
        return

    if not message_type:
        logger.warning(f"Unknown message type for topic: {topic}")
        return

    # Parse JSON payload
    try:
        payload_dict = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Invalid JSON payload from {device_id}: {e}")
        raise PayloadValidationError(f"Invalid JSON: {e}")

    logger.info(f"Processing message: device={device_id}, type={message_type}, size={len(payload)} bytes")

    # Route to appropriate handler based on message type
    try:
        match message_type:
            case "telemetry":
                await handle_telemetry(device_id, payload_dict)
            case "knock_live":
                await handle_knock_live(device_id, payload_dict)
            case "knock_result":
                await handle_knock_result(device_id, payload_dict)
            case "logs":
                await handle_logs(device_id, payload_dict)
            case "command_ack":
                command_id = parse_command_id_from_ack_topic(topic)
                await handle_command_ack(device_id, command_id, payload_dict)
            case "config_reported":
                await handle_config_reported(device_id, payload_dict)
            case _:
                logger.warning(f"Unhandled message type: {message_type}")
    except ValidationError as e:
        logger.error(f"Payload validation failed for {message_type}: {e}")
        raise PayloadValidationError(f"Validation error: {e}")


async def handle_telemetry(device_id: str, payload_dict: dict[str, Any]) -> None:
    """
    Handle device telemetry messages.

    - Validates payload
    - Appends event to Redis Stream
    - Updates device state with telemetry snapshot
    """
    # Validate payload
    payload = TelemetryPayload.model_validate(payload_dict)

    # Verify device ID matches if present in meta
    if payload.meta.deviceId and payload.meta.deviceId != device_id:
        logger.warning(f"Device ID mismatch: topic={device_id}, meta={payload.meta.deviceId}")

    # Append to event stream
    await append_event(
        event_type="telemetry",
        device_id=device_id,
        payload=payload_dict,
        event_id=payload.meta.eventId,
        device_ts=payload.meta.ts,
    )

    # Update device state with telemetry
    await update_telemetry(
        device_id=device_id,
        telemetry_data=payload.data.model_dump(exclude_none=True),
        ts=payload.meta.ts,
    )

    logger.info(f"Telemetry processed: device={device_id}, battery={payload.data.battery}, rssi={payload.data.rssi}")


async def handle_knock_live(device_id: str, payload_dict: dict[str, Any]) -> None:
    """
    Handle live knock pattern streaming.

    - Validates payload
    - Appends event to Redis Stream
    - Updates device lastSeen
    """
    # Validate payload
    payload = KnockLivePayload.model_validate(payload_dict)

    # Append to event stream
    await append_event(
        event_type="knock_live",
        device_id=device_id,
        payload=payload_dict,
        event_id=payload.meta.eventId,
        device_ts=payload.meta.ts,
        extra_fields={"sampleCount": len(payload.data.samples)},
    )

    # Update device lastSeen (just touch the state)
    await upsert_state(device_id, {})

    logger.debug(f"Knock live processed: device={device_id}, samples={len(payload.data.samples)}")


async def handle_knock_result(device_id: str, payload_dict: dict[str, Any]) -> None:
    """
    Handle knock pattern recognition results.

    - Validates payload
    - Appends event to Redis Stream
    - Updates device state with knock result summary
    """
    # Validate payload
    payload = KnockResultPayload.model_validate(payload_dict)
    data = payload.data

    # Append to event stream with extra fields for querying
    await append_event(
        event_type="knock_result",
        device_id=device_id,
        payload=payload_dict,
        event_id=payload.meta.eventId,
        device_ts=payload.meta.ts,
        extra_fields={
            "matched": data.matched,
            "score": data.score,
            "patternId": data.patternId,
            "action": data.action.value if data.action else None,
        },
    )

    # Update device state with knock result
    await update_knock_result(
        device_id=device_id,
        matched=data.matched,
        ts=payload.meta.ts,
        pattern_id=data.patternId,
        score=data.score,
        threshold=data.threshold,
        action=data.action.value if data.action else None,
        latency_ms=data.latencyMs,
    )

    logger.info(
        f"Knock result processed: device={device_id}, matched={data.matched}, "
        f"score={data.score}, pattern={data.patternId}"
    )


async def handle_logs(device_id: str, payload_dict: dict[str, Any]) -> None:
    """
    Handle device log messages.

    - Validates payload
    - Appends event to Redis Stream
    - Updates device state with last log
    """
    # Validate payload
    payload = LogsPayload.model_validate(payload_dict)
    data = payload.data

    # Append to event stream
    await append_event(
        event_type="logs",
        device_id=device_id,
        payload=payload_dict,
        event_id=payload.meta.eventId,
        device_ts=payload.meta.ts,
        extra_fields={
            "level": data.level.value,
            "module": data.module,
        },
    )

    # Update device state with last log
    log_summary = {
        "level": data.level.value,
        "message": data.message,
        "module": data.module,
        "ts": payload.meta.ts.isoformat(),
    }
    await update_last_log(device_id, log_summary)

    logger.info(f"Log processed: device={device_id}, level={data.level.value}, msg={data.message[:50]}")


async def handle_command_ack(
    device_id: str,
    command_id: str | None,
    payload_dict: dict[str, Any],
) -> None:
    """
    Handle command acknowledgment messages.

    - Validates payload
    - Appends event to Redis Stream
    - Updates device lastSeen
    """
    # Validate payload
    payload = CommandAckPayload.model_validate(payload_dict)
    data = payload.data

    # Use command_id from topic if not matching
    actual_command_id = command_id or data.commandId

    # Append to event stream
    await append_event(
        event_type="command_ack",
        device_id=device_id,
        payload=payload_dict,
        event_id=payload.meta.eventId,
        device_ts=payload.meta.ts,
        extra_fields={
            "commandId": actual_command_id,
            "status": data.status.value,
        },
    )

    # Update device lastSeen
    await upsert_state(device_id, {
        "lastCommandAck": {
            "commandId": actual_command_id,
            "status": data.status.value,
            "ts": payload.meta.ts.isoformat() if payload.meta.ts else None,
        },
    })

    logger.info(f"Command ack processed: device={device_id}, command={actual_command_id}, status={data.status.value}")


async def handle_config_reported(device_id: str, payload_dict: dict[str, Any]) -> None:
    """
    Handle config/reported messages from the device.

    Stores the reported config in Redis and appends a stream event.
    Payload shape (Wireless.pdf):
        { "meta": { "schema": "device.config.v1", ... }, "data": { ... } }
    """
    from app.core.settings import get_settings

    settings = get_settings()

    # Store full payload as reported config
    await json_set(
        f"{settings.REPORTED_CONFIG_KEY_PREFIX}{device_id}",
        payload_dict,
    )

    # Append event to stream
    await append_event(
        event_type="config_reported",
        device_id=device_id,
        payload=payload_dict,
    )

    # Touch device lastSeen
    await upsert_state(device_id, {})

    logger.info(f"Config reported processed: device={device_id}")
