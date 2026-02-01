"""
Pydantic models for device state.

Represents the current state snapshot stored in Redis.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DeviceStatus(str, Enum):
    """Device connectivity status."""

    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class TelemetrySnapshot(BaseModel):
    """Latest telemetry snapshot."""

    battery: Optional[int] = None
    rssi: Optional[int] = None
    uptime: Optional[int] = None
    freeHeap: Optional[int] = None
    temperature: Optional[float] = None
    ts: Optional[datetime] = None


class KnockResultSummary(BaseModel):
    """Summary of last knock result."""

    matched: bool
    patternId: Optional[str] = None
    score: Optional[float] = None
    threshold: Optional[float] = None
    action: Optional[str] = None
    latencyMs: Optional[int] = None
    ts: datetime


class DeviceState(BaseModel):
    """
    Device state snapshot stored in Redis.

    Updated by MQTT handlers on each message.
    """

    deviceId: str = Field(..., description="Device identifier")
    status: DeviceStatus = Field(default=DeviceStatus.UNKNOWN, description="Connectivity status")
    lastSeen: Optional[datetime] = Field(None, description="Last message received")
    updatedAt: Optional[datetime] = Field(None, description="Last state update")
    telemetry: Optional[TelemetrySnapshot] = Field(None, description="Latest telemetry")
    lastKnockResult: Optional[KnockResultSummary] = Field(None, description="Last knock result")
    lastLog: Optional[dict] = Field(None, description="Last log entry")


class DeviceStateResponse(BaseModel):
    """API response for device state."""

    deviceId: str
    status: DeviceStatus
    lastSeen: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    telemetry: Optional[TelemetrySnapshot] = None
    lastKnockResult: Optional[KnockResultSummary] = None
