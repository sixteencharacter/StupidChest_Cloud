"""
Logging configuration for the application.

Configures standard Python logging with structured output format
suitable for both development and production environments.
"""

import logging
import sys
from typing import Optional

from app.core.settings import get_settings


def configure_logging(level: Optional[str] = None) -> None:
    """
    Configure application logging.

    Args:
        level: Optional log level override. If not provided, uses LOG_LEVEL from settings.
    """
    settings = get_settings()
    log_level = level or settings.LOG_LEVEL

    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # Override any existing configuration
    )

    # Set specific log levels for noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured at {log_level} level")
    logger.info(f"Running in {settings.APP_ENV} environment")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
