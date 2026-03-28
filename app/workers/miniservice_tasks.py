import sentry_sdk
import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger()


class LLMTimeoutError(Exception):
    pass


class LLMAPIError(Exception):
    pass


class LLMRateLimitError(Exception):
    pass


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    soft_time_limit=110,
    time_limit=120,
)
def run_miniservice_task(self, run_id: str):
    """Execute miniservice processing in Celery worker."""
    try:
        logger.info("miniservice_task_started", run_id=run_id)
        # TODO: load run, load manifest, execute implementation, save artifact
    except LLMRateLimitError as exc:
        raise self.retry(exc=exc, countdown=15)
    except (LLMTimeoutError, LLMAPIError) as exc:
        raise self.retry(exc=exc, countdown=5)
    except Exception as exc:
        logger.error("miniservice_task_failed", run_id=run_id, error=str(exc))
        sentry_sdk.capture_exception(exc)
