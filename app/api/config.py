"""
Config API endpoints.

GET  /api/v1/devices/{deviceId}/config       -> DeviceConfigSnapshot
PUT  /api/v1/devices/{deviceId}/config       -> DeviceConfigDesired
POST /api/v1/devices/{deviceId}/config/sync  -> issue SYNC_CONFIG command
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.core.logging import get_logger
from app.core.settings import get_settings
from app.models.api import (
    CommandIssued,
    CommandType,
    DeviceConfigDesired,
    DeviceConfigSnapshot,
)
from app.mqtt import publisher
from app.mqtt.topics import build_topic
from app.storage.redis import json_get, json_set

logger = get_logger(__name__)

router = APIRouter(prefix="/devices/{deviceId}/config", tags=["Config"])


@router.get(
    "",
    response_model=DeviceConfigSnapshot,
    summary="Get device configuration snapshot",
    description="Returns both the desired and reported configuration for a device.",
)
async def get_config(deviceId: str) -> DeviceConfigSnapshot:
    settings = get_settings()

    desired = await json_get(f"{settings.DESIRED_CONFIG_KEY_PREFIX}{deviceId}")
    reported = await json_get(f"{settings.REPORTED_CONFIG_KEY_PREFIX}{deviceId}")

    return DeviceConfigSnapshot(
        deviceId=deviceId,
        desired=desired,
        reported=reported,
    )


@router.put(
    "",
    response_model=DeviceConfigSnapshot,
    summary="Set desired device configuration",
    description=(
        "Stores the desired configuration in Redis and publishes it to the "
        "MQTT config/desired topic with retain=true."
    ),
)
async def put_config(deviceId: str, body: DeviceConfigDesired) -> DeviceConfigSnapshot:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    # Build the stored object (includes rev + data)
    desired_obj = {"rev": body.rev, "data": body.data}

    # Persist in Redis
    await json_set(f"{settings.DESIRED_CONFIG_KEY_PREFIX}{deviceId}", desired_obj)

    # Build MQTT payload per Wireless.pdf
    mqtt_payload = {
        "meta": {
            "schema": "device.config.v1",
            "rev": body.rev,
            "ts": now.isoformat(),
        },
        "data": body.data,
    }

    # Publish to .../config/desired with retain
    topic = build_topic(deviceId, "config", "desired")
    ok = await publisher.publish(topic, mqtt_payload, qos=1, retain=True)
    if not ok:
        logger.warning(f"Failed to publish desired config for {deviceId}")

    # Return snapshot (reported may already exist)
    reported = await json_get(f"{settings.REPORTED_CONFIG_KEY_PREFIX}{deviceId}")
    return DeviceConfigSnapshot(
        deviceId=deviceId,
        desired=desired_obj,
        reported=reported,
    )


@router.post(
    "/sync",
    response_model=CommandIssued,
    status_code=status.HTTP_200_OK,
    summary="Issue SYNC_CONFIG command",
    description="Tells the device to re-read its desired configuration.",
)
async def sync_config(deviceId: str) -> CommandIssued:
    now = datetime.now(timezone.utc)
    command_id = str(uuid.uuid4())

    mqtt_payload = {
        "meta": {
            "schema": "device.command.v1",
            "commandId": command_id,
            "ts": now.isoformat(),
            "issuedBy": "api",
        },
        "data": {
            "type": CommandType.SYNC_CONFIG.value,
            "params": {},
        },
    }

    from app.mqtt.topics import TOPIC_COMMANDS
    topic = build_topic(deviceId, TOPIC_COMMANDS)
    ok = await publisher.publish(topic, mqtt_payload, qos=1, retain=False)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to publish SYNC_CONFIG command to MQTT",
        )

    return CommandIssued(
        commandId=command_id,
        type=CommandType.SYNC_CONFIG,
        issuedAt=now,
    )
