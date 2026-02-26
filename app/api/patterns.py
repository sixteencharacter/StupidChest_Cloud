"""
Patterns API endpoints.

Full CRUD for knock patterns stored in Redis, plus an activate endpoint
that pushes the desired pattern to a PC device via MQTT retained message.

Routes:
    GET    /api/v1/patterns                      - List all patterns
    POST   /api/v1/patterns                      - Create a new pattern
    GET    /api/v1/patterns/{patternId}           - Get pattern detail
    PUT    /api/v1/patterns/{patternId}           - Update (bumps version)
    DELETE /api/v1/patterns/{patternId}           - Delete
    POST   /api/v1/patterns/{patternId}/activate  - Activate for a device
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.logging import get_logger
from app.models.pattern import (
    OperationAccepted,
    PatternActivateRequest,
    PatternCreate,
    PatternDetail,
    PatternRecord,
    PatternSummary,
    PatternUpdate,
)
from app.mqtt import publisher
from app.storage.patterns import (
    delete_pattern,
    get_pattern,
    list_patterns,
    new_pattern_id,
    now_utc,
    save_pattern,
    set_active_pattern,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/patterns", tags=["Patterns"])


# ──────────────────── Helpers ────────────────────


def _to_summary(record: PatternRecord) -> PatternSummary:
    return PatternSummary(
        patternId=record.patternId,
        name=record.name,
        version=record.version,
        algo=record.algo,
        isActive=record.isActive,
        createdAt=record.createdAt,
    )


def _to_detail(record: PatternRecord) -> PatternDetail:
    return PatternDetail(
        patternId=record.patternId,
        name=record.name,
        version=record.version,
        algo=record.algo,
        isActive=record.isActive,
        createdAt=record.createdAt,
        representation=record.representation,
        updatedAt=record.updatedAt,
    )


# ──────────────────── Endpoints ────────────────────


@router.get(
    "/",
    response_model=list[PatternSummary],
    summary="List all knock patterns",
    description=(
        "Returns all registered knock patterns sorted by createdAt (newest first). "
        "Use `activeOnly=true` to filter only patterns currently set as active."
    ),
)
async def list_patterns_endpoint(
    activeOnly: bool = Query(default=False, description="Filter to active patterns only"),
) -> list[PatternSummary]:
    records = await list_patterns(active_only=activeOnly)
    return [_to_summary(r) for r in records]


@router.post(
    "/",
    response_model=PatternDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new knock pattern",
    description=(
        "Registers a new knock pattern with the given name, algorithm, and representation. "
        "For the `intervals` algorithm, provide `representation.intervalsMs` (list of timing "
        "gaps in ms between knocks) and optionally `representation.toleranceMs`."
    ),
)
async def create_pattern(body: PatternCreate) -> PatternDetail:
    now = now_utc()
    record = PatternRecord(
        patternId=new_pattern_id(),
        name=body.name,
        algo=body.algo,
        version=1,
        isActive=False,
        representation=body.representation,
        createdAt=now,
        updatedAt=now,
    )
    await save_pattern(record)
    logger.info(f"Pattern created: id={record.patternId}, name={record.name}")
    return _to_detail(record)


@router.get(
    "/{patternId}",
    response_model=PatternDetail,
    summary="Get pattern details",
    description="Returns full pattern detail including the representation (intervals data).",
)
async def get_pattern_endpoint(patternId: str) -> PatternDetail:
    record = await get_pattern(patternId)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern '{patternId}' not found",
        )
    return _to_detail(record)


@router.put(
    "/{patternId}",
    response_model=PatternDetail,
    summary="Update a knock pattern",
    description=(
        "Updates the pattern name, algorithm, and representation. "
        "Increments the version counter — the PC should reload the "
        "pattern if it receives a newer version via MQTT."
    ),
)
async def update_pattern(patternId: str, body: PatternUpdate) -> PatternDetail:
    existing = await get_pattern(patternId)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern '{patternId}' not found",
        )

    now = now_utc()
    updated = PatternRecord(
        patternId=existing.patternId,
        name=body.name,
        algo=body.algo,
        version=existing.version + 1,  # bump version
        isActive=existing.isActive,
        representation=body.representation,
        createdAt=existing.createdAt,
        updatedAt=now,
    )
    await save_pattern(updated)
    logger.info(f"Pattern updated: id={patternId}, new_version={updated.version}")
    return _to_detail(updated)


@router.delete(
    "/{patternId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knock pattern",
    description="Permanently removes the pattern from the system.",
)
async def delete_pattern_endpoint(patternId: str) -> None:
    existed = await delete_pattern(patternId)
    if not existed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern '{patternId}' not found",
        )
    logger.info(f"Pattern deleted: id={patternId}")


@router.post(
    "/{patternId}/activate",
    response_model=OperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Activate a pattern for a device",
    description=(
        "Sets the pattern as active for the given device and — if `syncNow=true` — "
        "immediately publishes the pattern to the device via MQTT retained message "
        "(`config/pattern/desired`). The PC will receive this on its next connect "
        "or immediately if already online."
    ),
)
async def activate_pattern(
    patternId: str,
    body: PatternActivateRequest,
) -> OperationAccepted:
    record = await get_pattern(patternId)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pattern '{patternId}' not found",
        )

    # Mark active=True and persist
    now = now_utc()
    activated = PatternRecord(
        patternId=record.patternId,
        name=record.name,
        algo=record.algo,
        version=record.version,
        isActive=True,
        representation=record.representation,
        createdAt=record.createdAt,
        updatedAt=now,
    )
    await save_pattern(activated)

    # Record which pattern this device is using
    await set_active_pattern(body.deviceId, patternId)

    logger.info(f"Pattern activated: id={patternId}, device={body.deviceId}")

    # Push to device via MQTT if requested
    if body.syncNow:
        ok = await publisher.publish_pattern_desired(body.deviceId, activated)
        if not ok:
            logger.warning(
                f"Pattern activation saved but MQTT push failed: "
                f"device={body.deviceId}, pattern={patternId}"
            )
            return OperationAccepted(
                status="ACCEPTED",
                message=(
                    "Pattern activated in storage but MQTT push failed. "
                    "Device will receive it on next reconnect."
                ),
            )

        logger.info(f"Pattern pushed via MQTT: device={body.deviceId}, pattern={patternId}")

    return OperationAccepted(
        status="ACCEPTED",
        message=f"Pattern '{patternId}' activated for device '{body.deviceId}'.",
    )
