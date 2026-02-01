# Models package
"""
Pydantic schemas for API request/response models.

This package contains:
- Common models (Meta, ErrorResponse)
- MQTT payload models
- Device state models
"""

from app.models.common import ErrorResponse, Meta
from app.models.mqtt import (
    CommandAckData,
    CommandAckPayload,
    CommandStatus,
    KnockAction,
    KnockLiveData,
    KnockLivePayload,
    KnockResultData,
    KnockResultPayload,
    LogData,
    LogLevel,
    LogsPayload,
    TelemetryData,
    TelemetryPayload,
)
from app.models.state import (
    DeviceState,
    DeviceStateResponse,
    DeviceStatus,
    KnockResultSummary,
    TelemetrySnapshot,
)

__all__ = [
    # Common
    "Meta",
    "ErrorResponse",
    # MQTT
    "TelemetryData",
    "TelemetryPayload",
    "KnockLiveData",
    "KnockLivePayload",
    "KnockResultData",
    "KnockResultPayload",
    "LogData",
    "LogsPayload",
    "CommandAckData",
    "CommandAckPayload",
    "KnockAction",
    "LogLevel",
    "CommandStatus",
    # State
    "DeviceStatus",
    "TelemetrySnapshot",
    "KnockResultSummary",
    "DeviceState",
    "DeviceStateResponse",
]
