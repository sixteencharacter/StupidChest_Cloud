"""
Application settings using Pydantic v2 BaseSettings.

Environment variables are loaded from .env file and can be overridden
by actual environment variables.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MQTT Broker
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_USERNAME: Optional[str] = None
    MQTT_PASSWORD: Optional[str] = None
    MQTT_CLIENT_ID: str = "knocklock-api"

    # MQTT Topics
    MQTT_TOPIC_PREFIX: str = "knocklock/v1/devices"

    # Redis Keys
    EVENT_STREAM_KEY: str = "knocklock:events"
    DEVICE_STATE_KEY_PREFIX: str = "knocklock:device_state:"

    # Phase 2: Additional settings
    ONLINE_TTL_SEC: int = 30  # Device considered offline after this many seconds
    MAX_PAYLOAD_BYTES: int = 256000  # Max MQTT payload size
    EVENT_STREAM_MAXLEN: int = 10000  # Approximate max events in stream

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.APP_ENV.lower() == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.APP_ENV.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
