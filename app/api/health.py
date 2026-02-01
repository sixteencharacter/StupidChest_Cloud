"""
Health check router.

Provides endpoints for health checks and readiness probes.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.settings import get_settings
from app.storage.redis import health_check as redis_health_check

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    environment: str
    version: str = "1.0.0"


class ReadinessResponse(BaseModel):
    """Readiness check response with dependency status."""

    status: str
    redis: bool
    mqtt: bool  # Placeholder - will check MQTT connection in Phase 2


@router.get(
    "/healthz",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Basic health check endpoint for liveness probes.",
)
async def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        environment=settings.APP_ENV,
    )


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness Check",
    description="Readiness check with dependency status.",
)
async def readiness_check() -> ReadinessResponse:
    redis_ok = await redis_health_check()

    # MQTT health check placeholder - will implement in Phase 2
    mqtt_ok = True  # Assume OK for now

    overall_status = "ready" if redis_ok and mqtt_ok else "not_ready"

    return ReadinessResponse(
        status=overall_status,
        redis=redis_ok,
        mqtt=mqtt_ok,
    )
