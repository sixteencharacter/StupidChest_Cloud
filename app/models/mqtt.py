"""
Pydantic models for MQTT message payloads.

Based on Wireless.pdf payload specifications.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.common import Meta


# --- Enums ---


class KnockAction(str, Enum):
    """Action taken after knock recognition."""

    UNLOCK = "unlock"
    DENY = "deny"
    NONE = "none"


class LogLevel(str, Enum):
    """Device log levels."""

    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class CommandStatus(str, Enum):
    """Command acknowledgment status."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


# --- Telemetry ---


class TelemetryData(BaseModel):
    """Telemetry data from device."""

    battery: Optional[int] = Field(None, ge=0, le=100, description="Battery level %")
    rssi: Optional[int] = Field(None, description="WiFi signal strength dBm")
    uptime: Optional[int] = Field(None, ge=0, description="Uptime in seconds")
    freeHeap: Optional[int] = Field(None, ge=0, description="Free heap memory bytes")
    temperature: Optional[float] = Field(None, description="Temperature in Celsius")


class TelemetryPayload(BaseModel):
    """Complete telemetry MQTT payload."""

    meta: Meta
    data: TelemetryData


# --- Knock Live ---


class KnockPoint(BaseModel):
    """A single knock event within a capture window."""

    tOffsetMs: int = Field(..., ge=0, description="Time offset from window start (ms)")
    amp: float = Field(..., ge=0, description="Knock amplitude (normalized 0+)")


class KnockFeatures(BaseModel):
    """Derived features computed from knock windows."""

    intervalsMs: Optional[list[int]] = Field(None, description="Time gaps between knocks (ms)")
    energy: Optional[float] = Field(None, ge=0, description="Total energy of the window")


class KnockLiveData(BaseModel):
    """Live knock window data — per spec knock.live.v1."""

    windowMs: Optional[int] = Field(None, ge=0, description="Capture window size (ms)")
    knocks: list[KnockPoint] = Field(..., description="Individual knock events in the window")
    features: Optional[KnockFeatures] = Field(None, description="Derived features (optional)")


class KnockLivePayload(BaseModel):
    """Complete knock/live MQTT payload."""

    meta: Meta
    data: KnockLiveData


# --- Knock Result ---


class KnockResultData(BaseModel):
    """Knock pattern recognition result."""

    matched: bool = Field(..., description="Whether pattern matched")
    patternId: Optional[str] = Field(None, description="Matched pattern ID")
    score: Optional[float] = Field(None, ge=0, le=1, description="Match confidence 0-1")
    threshold: Optional[float] = Field(None, ge=0, le=1, description="Match threshold")
    action: Optional[KnockAction] = Field(None, description="Action taken")
    latencyMs: Optional[int] = Field(None, ge=0, description="Processing latency ms")


class KnockResultPayload(BaseModel):
    """Complete knock/result MQTT payload."""

    meta: Meta
    data: KnockResultData


# --- Logs ---


class LogData(BaseModel):
    """Device log entry."""

    level: LogLevel = Field(..., description="Log level")
    message: str = Field(..., description="Log message")
    module: Optional[str] = Field(None, description="Source module")
    code: Optional[str] = Field(None, description="Error/event code")


class LogsPayload(BaseModel):
    """Complete logs MQTT payload."""

    meta: Meta
    data: LogData


# --- Command Ack ---


class CommandAckData(BaseModel):
    """Command acknowledgment data."""

    commandId: str = Field(..., description="Original command ID")
    status: CommandStatus = Field(..., description="Execution status")
    result: Optional[Any] = Field(None, description="Command result data")
    errorMessage: Optional[str] = Field(None, description="Error message if failed")
    executedAt: Optional[datetime] = Field(None, description="Execution timestamp")


class CommandAckPayload(BaseModel):
    """Complete command ack MQTT payload."""

    meta: Meta
    data: CommandAckData
