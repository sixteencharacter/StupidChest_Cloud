"""
Actions API endpoints.

POST /api/v1/devices/{deviceId}/actions/lock
POST /api/v1/devices/{deviceId}/actions/unlock
POST /api/v1/devices/{deviceId}/actions/learn/start
POST /api/v1/devices/{deviceId}/actions/learn/stop
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.core.logging import get_logger
from app.models.api import (
    CommandIssued,
    CommandType,
    StartLearnParams,
    StopLearnParams,
    UnlockParams,
)
from app.mqtt import publisher
from app.mqtt.topics import build_topic

logger = get_logger(__name__)

router = APIRouter(prefix="/devices/{deviceId}/actions", tags=["Actions"])


async def _issue_command(
    device_id: str,
    command_type: CommandType,
    params: dict | None = None,
) -> CommandIssued:
    """
    Shared helper: build MQTT command payload, publish, return CommandIssued.
    """
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
            "type": command_type.value,
            "params": params or {},
        },
    }

    from app.mqtt.topics import TOPIC_COMMANDS
    topic = build_topic(device_id, TOPIC_COMMANDS)
    ok = await publisher.publish(topic, mqtt_payload, qos=1, retain=False)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to publish {command_type.value} command to MQTT",
        )

    return CommandIssued(
        commandId=command_id,
        type=command_type,
        issuedAt=now,
    )


@router.post(
    "/lock",
    response_model=CommandIssued,
    summary="Lock the device",
    description="Issues a LOCK command to the device via MQTT.",
)
async def action_lock(deviceId: str) -> CommandIssued:
    return await _issue_command(deviceId, CommandType.LOCK)


@router.post(
    "/unlock",
    response_model=CommandIssued,
    summary="Unlock the device",
    description="Issues an UNLOCK command to the device via MQTT. Optionally specify durationMs.",
)
async def action_unlock(
    deviceId: str,
    body: UnlockParams | None = None,
) -> CommandIssued:
    params = {}
    if body and body.durationMs is not None:
        params["durationMs"] = body.durationMs
    return await _issue_command(deviceId, CommandType.UNLOCK, params)


@router.post(
    "/learn/start",
    response_model=CommandIssued,
    summary="Start pattern learning",
    description="Issues a START_LEARN command to the device via MQTT.",
)
async def action_learn_start(
    deviceId: str,
    body: StartLearnParams | None = None,
) -> CommandIssued:
    params = {}
    if body:
        if body.sessionName is not None:
            params["sessionName"] = body.sessionName
        if body.maxDurationMs is not None:
            params["maxDurationMs"] = body.maxDurationMs
    return await _issue_command(deviceId, CommandType.START_LEARN, params)


@router.post(
    "/learn/stop",
    response_model=CommandIssued,
    summary="Stop pattern learning",
    description="Issues a STOP_LEARN command to the device via MQTT.",
)
async def action_learn_stop(
    deviceId: str,
    body: StopLearnParams | None = None,
) -> CommandIssued:
    params = {}
    if body:
        if body.saveAsPattern is not None:
            params["saveAsPattern"] = body.saveAsPattern
        if body.patternName is not None:
            params["patternName"] = body.patternName
        if body.algo is not None:
            params["algo"] = body.algo
    return await _issue_command(deviceId, CommandType.STOP_LEARN, params)
