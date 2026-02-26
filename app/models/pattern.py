"""
Pydantic schemas for Knock Patterns.

Patterns are stored in Redis and pushed to devices via MQTT retained messages.
Matching is performed on the PC side (interval-based algorithm).
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────── Enums ────────────────────


class PatternAlgo(str, Enum):
    """Similarity algorithm used for pattern matching."""

    INTERVALS = "intervals"
    DTW = "dtw"
    COSINE = "cosine"


# ──────────────────── Representation ────────────────────


class PatternRepresentation(BaseModel):
    """
    Pattern data representation.

    For 'intervals' algo: store timing gaps between knocks (ms) + tolerance.
    For 'dtw'/'cosine': store featureTemplate (arbitrary dict).
    """

    type: str = Field(..., description="Representation type: 'intervals' or 'features'")
    intervalsMs: Optional[list[int]] = Field(
        None,
        description="Time gaps between knocks in ms (for intervals algo)",
    )
    toleranceMs: Optional[int] = Field(
        None,
        ge=0,
        description="Allowed deviation per interval in ms",
    )
    featureTemplate: Optional[dict] = Field(
        None,
        description="Arbitrary feature template for DTW/cosine matching",
    )


# ──────────────────── Request Schemas ────────────────────


class PatternCreate(BaseModel):
    """Request body for POST /patterns."""

    name: str = Field(..., min_length=1, max_length=128, description="Pattern display name")
    algo: PatternAlgo = Field(default=PatternAlgo.INTERVALS, description="Matching algorithm")
    representation: PatternRepresentation = Field(..., description="Pattern data")


class PatternUpdate(BaseModel):
    """Request body for PUT /patterns/{patternId}. Creates a new version."""

    name: str = Field(..., min_length=1, max_length=128)
    algo: PatternAlgo = Field(default=PatternAlgo.INTERVALS)
    representation: PatternRepresentation


class PatternActivateRequest(BaseModel):
    """Request body for POST /patterns/{patternId}/activate."""

    deviceId: str = Field(..., description="Target device ID to activate pattern on")
    syncNow: bool = Field(
        default=True,
        description="If true, immediately publish desired pattern to device via MQTT",
    )


# ──────────────────── Internal Record (Redis) ────────────────────


class PatternRecord(BaseModel):
    """
    Full pattern record stored in Redis.

    This is the internal representation — includes all metadata.
    """

    patternId: str = Field(..., description="Unique pattern identifier")
    name: str
    algo: PatternAlgo
    version: int = Field(default=1, ge=1, description="Monotonic version counter")
    isActive: bool = Field(default=False)
    representation: PatternRepresentation
    createdAt: datetime
    updatedAt: datetime


# ──────────────────── Response Schemas ────────────────────


class PatternSummary(BaseModel):
    """
    Pattern summary for list responses (no representation data).

    Matches Pattern schema in OpenAPI spec.
    """

    patternId: str
    name: str
    version: int
    algo: PatternAlgo
    isActive: bool
    createdAt: datetime


class PatternDetail(PatternSummary):
    """
    Full pattern detail including representation data.

    Matches PatternDetail schema in OpenAPI spec.
    """

    representation: PatternRepresentation
    updatedAt: datetime


class OperationAccepted(BaseModel):
    """Response for fire-and-forget operations (202 Accepted)."""

    status: str = Field(default="ACCEPTED")
    message: Optional[str] = None
