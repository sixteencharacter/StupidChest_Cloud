"""
Common Pydantic models shared across the application.

Based on Wireless.pdf meta schema.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Meta(BaseModel):
    """
    Common metadata for all MQTT messages.

    As per Wireless.pdf spec.
    """

    schema_: str = Field(..., alias="schema", description="Schema identifier (e.g., 'telemetry/v1')")
    deviceId: Optional[str] = Field(None, description="Device ID (may be overridden by topic)")
    ts: datetime = Field(..., description="Timestamp from device")
    seq: Optional[int] = Field(None, description="Sequence number")
    eventId: Optional[str] = Field(None, description="Unique event identifier")
    sessionId: Optional[str] = Field(None, description="Device session ID")

    model_config = {"populate_by_name": True}


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error details")
