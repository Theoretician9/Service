import os
from pathlib import Path

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task
def cleanup_expired_dialogs():
    """Clean up expired dialog states from Redis (backup for TTL)."""
    logger.info("cleanup_expired_dialogs")


@celery_app.task
def cleanup_tmp_pdfs():
    """Delete old PDF files from /tmp/pdf/."""
    tmp_dir = Path("/tmp/pdf")
    if tmp_dir.exists():
        for f in tmp_dir.iterdir():
            try:
                os.remove(f)
            except OSError:
                pass
    logger.info("cleanup_tmp_pdfs_done")


@celery_app.task
def detect_abandoned_onboarding():
    """Find users with onboarding_completed=False and created_at > 24h ago."""
    logger.info("detect_abandoned_onboarding")
    # TODO: query users, create analytics events
