from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import actions, config, events, health, patterns, stats
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.mqtt.client import start_mqtt, stop_mqtt
from app.storage.redis import close_redis, get_redis

# Configure logging
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown of:
    - Redis connection
    - MQTT client
    """
    settings = get_settings()
    logger.info(f"Starting KnockLock API ({settings.APP_ENV})")

    # Startup
    try:
        # Initialize Redis connection
        await get_redis()
        logger.info("Redis initialized")

        # Start MQTT client
        await start_mqtt()
        logger.info("MQTT client started")

        yield

    finally:
        # Shutdown
        logger.info("Shutting down KnockLock API...")

        # Stop MQTT client
        await stop_mqtt()
        logger.info("MQTT client stopped")

        # Close Redis connection
        await close_redis()
        logger.info("Redis connection closed")

        logger.info("Shutdown complete")


# init app
app = FastAPI(
    #whatever you want to put here
    title="StiupidAssChest So Cool API",

    description="""
    Backend API for the StupidAssChest IoT SMART lock system.

    ## Features 
    - Device management and registration
    - Knock pattern recording and matching
    - Real-time device telemetry
    - Command dispatch via MQTT
    - Device configuration (desired/reported) with MQTT retained messages
    - Lock/Unlock/Learn actions via REST → MQTT
    - Cursor-based event queries with filtering
    - Knock statistics with configurable bucket sizes

    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {
            "name": "Health",
            "description": "Liveness and readiness probes for the API.",
        },
        {
            "name": "Config",
            "description": (
                "Device configuration management. "
                "Set desired config (published to MQTT with retain=true) "
                "and read reported config sent back by the device."
            ),
        },
        {
            "name": "Actions",
            "description": (
                "Issue commands to devices via MQTT. "
                "Supports LOCK, UNLOCK, START_LEARN, and STOP_LEARN."
            ),
        },
        {
            "name": "Events",
            "description": (
                "Query the device event stream (Redis Stream). "
                "Supports cursor-based pagination, type/matched filtering, "
                "and time-window queries."
            ),
        },
        {
            "name": "Stats",
            "description": (
                "Aggregated statistics from event stream data. "
                "Knock stats supports buckets: 10s, 1m, 5m, 15m, 1h, 1d."
            ),
        },
        {
            "name": "Patterns",
            "description": "Knock pattern CRUD (placeholder for future phase).",
        },
    ],
)

# Config CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #for now, or maybe forever haha idk
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(patterns.router, prefix="/api/v1")
app.include_router(config.router, prefix="/api/v1")
app.include_router(actions.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint - redirect info."""
    return {
        "message": "KnockLock IoT API",
        "docs": "/docs",
        "health": "/healthz",
    }
