"""Structured conversation logging configuration.

Configures structlog to write to both stdout AND a JSONL file at /app/logs/conversations.jsonl.
Each log line is a JSON object with: timestamp, event, user_telegram_id, miniservice_id, etc.
"""

import logging
import os
import sys
from pathlib import Path

import structlog


LOGS_DIR = Path("/app/logs")
CONVERSATIONS_LOG_FILE = LOGS_DIR / "conversations.jsonl"


def _ensure_logs_dir() -> None:
    """Create logs directory if it doesn't exist."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    """Configure structlog with dual output: stdout + JSONL file.

    Call this once at application startup (main.py lifespan or worker init).
    """
    _ensure_logs_dir()

    # --- stdlib file handler for conversation JSONL ---
    file_handler = logging.FileHandler(
        str(CONVERSATIONS_LOG_FILE), mode="a", encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)

    # --- stdlib stdout handler ---
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)

    # Root logger that structlog will delegate to
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # Remove existing handlers to avoid duplicates on reload
    root_logger.handlers.clear()
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)

    # structlog shared processors
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Formatter that renders each log event as a single JSON line
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
    )

    for handler in root_logger.handlers:
        handler.setFormatter(json_formatter)


def get_conversation_logger():
    """Return a structlog logger bound with logger_name='conversation'.

    Use this logger for all conversation-related events so they can be
    filtered/grepped easily in the JSONL file.
    """
    return structlog.get_logger(logger_name="conversation")
