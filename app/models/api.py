"""
Pydantic models for Phase 3 REST API: Config, Actions, Events, Stats.

Based on Wireless.pdf payload and REST specifications.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────── Config ────────────────────


class DeviceConfigDesired(BaseModel):
    """Request body for PUT /devices/{deviceId}/config."""

    rev: int = Field(..., description="Configuration revision number")
    data: dict[str, Any] = Field(..., description="Desired configuration object")


class DeviceConfigSnapshot(BaseModel):
    """Response for GET /devices/{deviceId}/config."""

    deviceId: str
    desired: Optional[dict[str, Any]] = Field(None, description="Last desired config stored")
    reported: Optional[dict[str, Any]] = Field(None, description="Last reported config from device")


# ──────────────────── Actions / Commands ────────────────────


class CommandType(str, Enum):
    """Types of commands that can be issued to a device."""

    LOCK = "LOCK"
    UNLOCK = "UNLOCK"
    SYNC_CONFIG = "SYNC_CONFIG"
    START_LEARN = "START_LEARN"
    STOP_LEARN = "STOP_LEARN"


class UnlockParams(BaseModel):
    """Optional params for UNLOCK action."""

    durationMs: Optional[int] = Field(None, ge=0, description="Duration in ms to keep unlocked")


class StartLearnParams(BaseModel):
    """Optional params for START_LEARN action."""

    sessionName: Optional[str] = Field(None, description="Learning session name")
    maxDurationMs: Optional[int] = Field(None, ge=0, description="Max learning duration ms")


class StopLearnParams(BaseModel):
    """Optional params for STOP_LEARN action."""

    saveAsPattern: Optional[bool] = Field(None, description="Whether to save recorded pattern")
    patternName: Optional[str] = Field(None, description="Name for the saved pattern")
    algo: Optional[str] = Field(None, description="Algorithm to use for pattern processing")


class CommandIssued(BaseModel):
    """Response after issuing a command to a device."""

    status: str = Field(default="ISSUED", description="Command dispatch status")
    commandId: str = Field(..., description="UUID of the issued command")
    type: CommandType = Field(..., description="Command type")
    issuedAt: datetime = Field(..., description="Timestamp when command was issued")


# ──────────────────── Events ────────────────────


class EventType(str, Enum):
    """Supported event types stored in stream."""

    knock_live = "knock_live"
    knock_result = "knock_result"
    telemetry = "telemetry"
    command_ack = "command_ack"
    system_log = "system_log"
    logs = "logs"
    config_reported = "config_reported"


class Event(BaseModel):
    """Single event in the stream."""

    eventId: str
    deviceId: str
    type: str
    ts: Optional[str] = Field(None, description="Device-side timestamp")
    serverReceivedTs: str = Field(..., description="Server-side timestamp")
    matched: Optional[bool] = None
    score: Optional[float] = None
    pattern: Optional[str] = None
    payload: Optional[Any] = None
    streamId: Optional[str] = Field(None, description="Redis stream entry ID")


class PagedEvents(BaseModel):
    """Paginated event list response."""

    items: list[Event]
    nextCursor: Optional[str] = Field(None, description="Cursor for next page (stream ID)")


# ──────────────────── Stats ────────────────────


class BucketSize(str, Enum):
    """Supported bucket sizes for stats aggregation."""

    TEN_SEC = "10s"
    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    FIFTEEN_MIN = "15m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class KnockBucketPoint(BaseModel):
    """A single time bucket in the knock stats series."""

    t: str = Field(..., description="Bucket start time (ISO 8601)")
    total: int = Field(0, description="Total knock attempts")
    matched: int = Field(0, description="Matched knock attempts")
    failed: int = Field(0, description="Failed knock attempts")


class KnockStats(BaseModel):
    """Response for GET /stats/knocks."""

    deviceId: str
    bucket: str = Field(..., description="Bucket size used")
    series: list[KnockBucketPoint]
