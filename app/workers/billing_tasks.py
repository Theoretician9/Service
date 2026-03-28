import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task
def reset_monthly_credits():
    """Reset credits for all users on 1st of each month."""
    logger.info("resetting_monthly_credits")
    # TODO: reset credits_remaining to credits_monthly_limit for all plans
