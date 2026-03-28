import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task
def send_result_notification(run_id: str):
    """Send miniservice result to user via Telegram."""
    logger.info("sending_result", run_id=run_id)
    # TODO: load run + artifact, format message, send via bot


@celery_app.task
def send_failure_notification(run_id: str):
    """Notify user about failed miniservice run."""
    logger.info("sending_failure", run_id=run_id)
    # TODO: load run, send error message via bot
