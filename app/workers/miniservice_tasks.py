import asyncio
import uuid
from datetime import datetime, timezone

import sentry_sdk
import structlog
from sqlalchemy import select

from app.database import async_session
from app.miniservices.base import MiniserviceContext
from app.miniservices.engine import load_manifest
from app.modules.artifacts.models import Artifact, MiniserviceRun
from app.modules.artifacts.service import ArtifactService
from app.modules.billing.service import BillingService
from app.modules.projects.models import Project
from app.modules.users.models import User
from app.modules.projects.service import ProjectService
from app.workers.celery_app import celery_app

logger = structlog.get_logger()

# Implementation class registry
_IMPLEMENTATIONS = {
    "goal_setting": "app.miniservices.implementations.goal_setting.GoalSettingService",
    "niche_selection": "app.miniservices.implementations.niche_selection.NicheSelectionService",
    "supplier_search": "app.miniservices.implementations.supplier_search.SupplierSearchService",
    "sales_scripts": "app.miniservices.implementations.sales_scripts.SalesScriptsService",
    "ad_creation": "app.miniservices.implementations.ad_creation.AdCreationService",
    "lead_search": "app.miniservices.implementations.lead_search.LeadSearchService",
}


class LLMTimeoutError(Exception):
    pass


class LLMAPIError(Exception):
    pass


class LLMRateLimitError(Exception):
    pass


def _load_implementation(miniservice_id: str):
    """Dynamically load miniservice implementation class."""
    class_path = _IMPLEMENTATIONS.get(miniservice_id)
    if not class_path:
        raise ValueError(f"Unknown miniservice: {miniservice_id}")

    module_path, class_name = class_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


async def _execute_miniservice(run_id: str) -> None:
    """Async implementation of miniservice execution."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings as _settings

    # Create fresh engine for this event loop (Celery worker has its own loop)
    _engine = create_async_engine(
        _settings.database_url, pool_size=2, max_overflow=2, echo=False
    )
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    run_uuid = uuid.UUID(run_id)

    async with _session_factory() as session:
        # Load the run
        stmt = select(MiniserviceRun).where(MiniserviceRun.id == run_uuid)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            logger.error("miniservice_run_not_found", run_id=run_id)
            return

        miniservice_id = run.miniservice_id
        manifest = load_manifest(miniservice_id)

        try:
            # Update status to processing
            run.status = "processing"
            run.started_at = datetime.now(timezone.utc)
            await session.commit()

            # Load project profile if exists
            project_profile = None
            if run.project_id:
                proj_stmt = select(Project).where(Project.id == run.project_id)
                proj_result = await session.execute(proj_stmt)
                project = proj_result.scalar_one_or_none()
                if project:
                    project_profile = {
                        "name": project.name,
                        "description": project.description,
                        "goal_statement": project.goal_statement,
                        "point_a": project.point_a,
                        "point_b": project.point_b,
                        "goal_deadline": project.goal_deadline,
                        "chosen_niche": project.chosen_niche,
                        "business_model": project.business_model,
                        "geography": project.geography,
                        "budget_range": project.budget_range,
                    }

            # Get latest collected_fields from Redis (most up-to-date)
            from app.miniservices.session import get_dialog
            # Find user's telegram_id to query Redis
            user_stmt = select(User).where(User.id == run.user_id)
            user_result = await session.execute(user_stmt)
            user_obj = user_result.scalar_one_or_none()

            collected = run.collected_fields or {}
            if user_obj:
                dialog = await get_dialog(user_obj.telegram_id)
                if dialog and dialog.get("collected_fields"):
                    # Merge: Redis fields take priority (most recent)
                    redis_fields = dialog["collected_fields"]
                    collected = {**collected, **redis_fields}
                    # Also update DB for consistency
                    if redis_fields != run.collected_fields:
                        run.collected_fields = collected
                        await session.commit()

            # Build context
            ctx = MiniserviceContext(
                run_id=run_uuid,
                user_id=run.user_id,
                project_id=run.project_id,
                miniservice_id=miniservice_id,
                collected_fields=collected,
                project_profile=project_profile,
            )

            # Load and execute implementation
            implementation = _load_implementation(miniservice_id)
            ms_result = await implementation.execute(ctx)

            # Save artifact
            artifact_svc = ArtifactService(session)
            artifact = await artifact_svc.create_artifact(
                user_id=run.user_id,
                project_id=run.project_id,
                run_id=run_uuid,
                miniservice_id=miniservice_id,
                artifact_type=ms_result.artifact_type,
                title=ms_result.title,
                content=ms_result.content,
                summary=ms_result.summary,
            )

            # Update project profile fields from manifest mapping
            if run.project_id and manifest.get("project_fields_mapping"):
                project_svc = ProjectService(session)
                for project_field, artifact_field in manifest["project_fields_mapping"].items():
                    value = ms_result.content.get(artifact_field)
                    if value is not None:
                        await project_svc.update_profile_field(
                            run.project_id, project_field, value
                        )

            # Deduct credits (get telegram_id for admin check)
            credit_cost = manifest.get("credit_cost", 1)
            billing_svc = BillingService(session)
            user_stmt = select(User).where(User.id == run.user_id)
            user_result = await session.execute(user_stmt)
            user_obj = user_result.scalar_one_or_none()
            tg_id = user_obj.telegram_id if user_obj else None
            await billing_svc.reserve_credits(run.user_id, credit_cost, telegram_id=tg_id)

            # Update run status
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.credits_spent = credit_cost
            run.llm_tokens_used = ms_result.llm_tokens_used
            run.web_searches_used = ms_result.web_searches_used
            await session.commit()

            logger.info(
                "miniservice_completed",
                run_id=run_id,
                miniservice_id=miniservice_id,
                credits_spent=credit_cost,
                tokens_used=ms_result.llm_tokens_used,
            )

            # Clear dialog and agent conversation from Redis after completion
            if user_obj:
                from app.miniservices.session import clear_dialog, clear_agent_conversation
                await clear_dialog(user_obj.telegram_id)
                await clear_agent_conversation(user_obj.telegram_id)

            # Send result notification
            from app.workers.notification_tasks import send_result_notification
            send_result_notification.delay(run_id)

            # Handle dependency chain — launch next miniservice if configured
            dep_chain = manifest.get("dep_chain")
            if dep_chain:
                _launch_next_in_chain(dep_chain, run)

        except Exception as exc:
            # Mark run as failed (will be overwritten on successful retry)
            run.status = "failed"
            run.error_message = str(exc)[:1000]
            run.completed_at = datetime.now(timezone.utc)
            await session.commit()

            logger.error(
                "miniservice_execution_failed",
                run_id=run_id,
                miniservice_id=miniservice_id,
                error=str(exc),
            )

            # DON'T send failure notification here — Celery may retry successfully.
            # Failure notification is sent from the task wrapper only on max_retries.

            # Re-raise for Celery retry logic
            raise

    # Don't dispose engine here — asyncio.run() closes the loop and
    # disposing within it can cause "Event loop is closed" on next task.
    # Engine will be garbage collected.


def _launch_next_in_chain(dep_chain: list, completed_run: MiniserviceRun) -> None:
    """Launch the next miniservice in a dependency chain."""
    # dep_chain is a list of miniservice_ids to run sequentially
    current_idx = None
    for i, ms_id in enumerate(dep_chain):
        if ms_id == completed_run.miniservice_id:
            current_idx = i
            break

    if current_idx is not None and current_idx + 1 < len(dep_chain):
        next_ms_id = dep_chain[current_idx + 1]
        logger.info(
            "launching_next_in_chain",
            current=completed_run.miniservice_id,
            next=next_ms_id,
        )
        # The next miniservice run should already be created by the handler
        # This is a placeholder for chain orchestration


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    soft_time_limit=300,
    time_limit=360,
)
def run_miniservice_task(self, run_id: str):
    """Execute miniservice processing in Celery worker."""
    try:
        logger.info("miniservice_task_started", run_id=run_id)
        # Create a fresh event loop each time to avoid "Event loop is closed"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_execute_miniservice(run_id))
        finally:
            loop.close()
    except LLMRateLimitError as exc:
        raise self.retry(exc=exc, countdown=15)
    except (LLMTimeoutError, LLMAPIError) as exc:
        raise self.retry(exc=exc, countdown=5)
    except Exception as exc:
        logger.error("miniservice_task_failed", run_id=run_id, error=str(exc))
        sentry_sdk.capture_exception(exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        # Max retries reached — NOW send failure notification
        logger.error("miniservice_task_max_retries", run_id=run_id, error=str(exc))
        from app.workers.notification_tasks import send_failure_notification
        send_failure_notification.delay(run_id)
