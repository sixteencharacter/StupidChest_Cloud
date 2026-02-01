"""
Pattern-related Pydantic schemas placeholder.

Will be implemented in Phase 2.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PatternBase(BaseModel):
    """Base pattern schema."""

    name: str = Field(..., description="Pattern display name")
    description: Optional[str] = None


class PatternCreate(PatternBase):
    """Schema for creating a pattern."""

    # Pattern data will be added from device recording
    pass


class PatternResponse(PatternBase):
    """Schema for pattern response."""

    pattern_id: str
    user_id: str
    created_at: datetime
    is_active: bool = True
