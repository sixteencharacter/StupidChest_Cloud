"""
Device-related Pydantic schemas placeholder.

Will be implemented in Phase 2.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceBase(BaseModel):
    """Base device schema."""

    name: Optional[str] = None
    firmware_version: Optional[str] = None


class DeviceCreate(DeviceBase):
    """Schema for device registration."""

    device_id: str = Field(..., description="Unique device identifier")


class DeviceResponse(DeviceBase):
    """Schema for device response."""

    device_id: str
    is_online: bool = False
    last_seen: Optional[datetime] = None
    created_at: datetime


class DeviceState(BaseModel):
    """Schema for device state in Redis."""

    device_id: str
    is_online: bool = False
    battery_level: Optional[int] = None
    rssi: Optional[int] = None
    last_telemetry: Optional[datetime] = None
    last_seen: Optional[datetime] = None
