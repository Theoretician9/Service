from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "ai_marketplace",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.miniservice_tasks",
        "app.workers.notification_tasks",
        "app.workers.billing_tasks",
        "app.workers.cleanup_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.tz,
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "reset_monthly_credits": {
        "task": "app.workers.billing_tasks.reset_monthly_credits",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),
    },
    "cleanup_expired_dialogs": {
        "task": "app.workers.cleanup_tasks.cleanup_expired_dialogs",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup_tmp_pdfs": {
        "task": "app.workers.cleanup_tasks.cleanup_tmp_pdfs",
        "schedule": crontab(hour=4, minute=0),
    },
}
