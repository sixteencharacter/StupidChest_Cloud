"""
Patterns API endpoints.

Endpoints for managing knock patterns.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/patterns", tags=["Patterns"])


@router.get("/")
async def list_patterns():
    """List all registered knock patterns."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/")
async def create_pattern():
    """Register a new knock pattern."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{pattern_id}")
async def get_pattern(pattern_id: str):
    """Get a specific pattern by ID."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/{pattern_id}")
async def delete_pattern(pattern_id: str):
    """Delete a pattern."""
    raise HTTPException(status_code=501, detail="Not implemented")
