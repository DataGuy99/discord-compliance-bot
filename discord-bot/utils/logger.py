"""
Structured logging configuration for Discord bot
"""

import os
import structlog

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def setup_logging():
    """
    Configure structlog for Discord bot with JSON output.
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


logger = setup_logging()