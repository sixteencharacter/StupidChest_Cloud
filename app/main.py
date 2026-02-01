from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, patterns
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

    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint - redirect info."""
    return {
        "message": "KnockLock IoT API",
        "docs": "/docs",
        "health": "/healthz",
    }
