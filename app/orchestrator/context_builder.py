"""Builds OrchestratorContext from DB and Redis for each user message."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.miniservices.engine import get_all_manifests
from app.miniservices.session import (
    get_active_project,
    get_conversation,
    get_dep_chain,
    get_dialog,
    get_extracted_fields,
)
from app.modules.artifacts.models import Artifact
from app.modules.billing.models import UserPlan
from app.modules.projects.models import Project
from app.modules.users.models import User

logger = structlog.get_logger()


@dataclass
class ActiveRunInfo:
    miniservice_id: str
    step: int
    collected_fields: dict
    project_id: UUID
    short_answer_count: int = 0


@dataclass
class ProjectSummary:
    id: UUID
    name: str
    profile: dict
    artifacts: list[dict] = field(default_factory=list)


@dataclass
class DepChainInfo:
    target_miniservice: str
    chain: list[str]
    project_id: UUID


@dataclass
class MiniserviceInfo:
    id: str
    name: str
    credit_cost: int
    available_on_free: bool
    requires: list[str]
    provides: list[str]


@dataclass
class OrchestratorContext:
    user_id: UUID
    user_first_name: str
    plan_type: str
    credits_remaining: int
    credits_monthly_limit: int
    credits_reset_at: datetime
    onboarding_completed: bool
    active_run: ActiveRunInfo | None = None
    active_project: ProjectSummary | None = None
    all_projects: list[ProjectSummary] = field(default_factory=list)
    active_dep_chain: DepChainInfo | None = None
    extracted_fields: dict = field(default_factory=dict)
    conversation_history: list[dict] = field(default_factory=list)
    available_miniservices: list[MiniserviceInfo] = field(default_factory=list)


# ── Dependency graph (mirrors dependency_resolver.py) ───────────────

from app.orchestrator.dependency_resolver import DEPENDENCY_GRAPH


def _build_project_profile(project: Project) -> dict:
    """Extract non-null profile fields from a Project into a dict."""
    profile_fields = [
        "goal_statement", "point_a", "point_b", "goal_deadline",
        "success_metrics", "constraints", "niche_candidates", "chosen_niche",
        "hypothesis_table", "geography", "budget_range", "business_model",
    ]
    profile = {}
    for f in profile_fields:
        val = getattr(project, f, None)
        if val is not None:
            profile[f] = val
    return profile


async def _load_project_artifacts(
    db_session: AsyncSession, project_id: UUID
) -> list[dict]:
    """Load current artifacts for a project."""
    stmt = (
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.is_current.is_(True))
        .order_by(Artifact.created_at.desc())
    )
    result = await db_session.execute(stmt)
    artifacts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "artifact_type": a.artifact_type,
            "miniservice_id": a.miniservice_id,
            "title": a.title,
            "summary": a.summary,
            "version": a.version,
        }
        for a in artifacts
    ]


def _build_miniservice_info_list() -> list[MiniserviceInfo]:
    """Build list of MiniserviceInfo from all manifests."""
    manifests = get_all_manifests()
    result = []
    for ms_id, manifest in manifests.items():
        requires = DEPENDENCY_GRAPH.get(ms_id, [])
        provides = []
        output_schema = manifest.get("output_schema", {})
        if output_schema.get("artifact_type"):
            provides.append(output_schema["artifact_type"])

        result.append(MiniserviceInfo(
            id=ms_id,
            name=manifest["name"],
            credit_cost=manifest["credit_cost"],
            available_on_free=manifest["available_on_free"],
            requires=requires,
            provides=provides,
        ))
    return result


async def build_context(telegram_user_id: int, db_session: AsyncSession) -> OrchestratorContext:
    """Build OrchestratorContext from DB and Redis.

    Loads user, plan, active run, active project, all projects,
    dependency chain, extracted fields, conversation history,
    and available miniservices.
    """
    # ── Load user from DB ───────────────────────────────────────────
    stmt = select(User).where(User.telegram_id == telegram_user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"User not found for telegram_id={telegram_user_id}")

    # ── Load user plan from DB (create if missing) ──────────────────
    from app.modules.billing.service import BillingService
    billing_svc = BillingService(db_session)
    user_plan = await billing_svc.get_or_create_plan(user.id)

    plan_type = user_plan.plan_type
    credits_remaining = user_plan.credits_remaining
    credits_monthly_limit = user_plan.credits_monthly_limit
    credits_reset_at = user_plan.credits_reset_at

    # ── Load active run from Redis (dialog state) ───────────────────
    active_run: ActiveRunInfo | None = None
    dialog = await get_dialog(telegram_user_id)
    if dialog:
        project_id_str = dialog.get("project_id")
        active_run = ActiveRunInfo(
            miniservice_id=dialog["miniservice_id"],
            step=dialog.get("step", 1),
            collected_fields=dialog.get("collected_fields", {}),
            project_id=UUID(project_id_str) if project_id_str else UUID(int=0),
            short_answer_count=dialog.get("short_answer_count", 0),
        )

    # ── Load active project ─────────────────────────────────────────
    # Try Redis first, then fallback to DB (last updated project)
    active_project: ProjectSummary | None = None
    active_proj_redis = await get_active_project(telegram_user_id)

    if active_proj_redis:
        proj_id = UUID(active_proj_redis["project_id"])
        proj_stmt = select(Project).where(Project.id == proj_id)
        proj_result = await db_session.execute(proj_stmt)
        project = proj_result.scalar_one_or_none()
        if project:
            artifacts = await _load_project_artifacts(db_session, project.id)
            active_project = ProjectSummary(
                id=project.id,
                name=project.name,
                profile=_build_project_profile(project),
                artifacts=artifacts,
            )

    if active_project is None:
        # Fallback: last updated active project
        fallback_stmt = (
            select(Project)
            .where(Project.user_id == user.id, Project.status == "active")
            .order_by(Project.updated_at.desc())
            .limit(1)
        )
        fallback_result = await db_session.execute(fallback_stmt)
        project = fallback_result.scalar_one_or_none()
        if project:
            artifacts = await _load_project_artifacts(db_session, project.id)
            active_project = ProjectSummary(
                id=project.id,
                name=project.name,
                profile=_build_project_profile(project),
                artifacts=artifacts,
            )

    # ── Load all user projects from DB ──────────────────────────────
    all_projects_stmt = (
        select(Project)
        .where(Project.user_id == user.id, Project.status == "active")
        .order_by(Project.updated_at.desc())
    )
    all_projects_result = await db_session.execute(all_projects_stmt)
    all_projects_rows = all_projects_result.scalars().all()
    all_projects: list[ProjectSummary] = []
    for p in all_projects_rows:
        # Skip loading artifacts for all projects (too heavy); only active project gets them
        all_projects.append(ProjectSummary(
            id=p.id,
            name=p.name,
            profile=_build_project_profile(p),
        ))

    # ── Load dep chain from Redis ───────────────────────────────────
    active_dep_chain: DepChainInfo | None = None
    dep_chain_data = await get_dep_chain(telegram_user_id)
    if dep_chain_data:
        active_dep_chain = DepChainInfo(
            target_miniservice=dep_chain_data["target_miniservice"],
            chain=dep_chain_data["chain"],
            project_id=UUID(dep_chain_data["project_id"]),
        )

    # ── Load extracted fields from Redis ────────────────────────────
    extracted_fields = await get_extracted_fields(telegram_user_id)

    # ── Load conversation history from Redis ────────────────────────
    conversation_history = await get_conversation(
        telegram_user_id, limit=settings.orchestrator_history_messages
    )

    # ── Load available miniservices from manifests ──────────────────
    available_miniservices = _build_miniservice_info_list()

    return OrchestratorContext(
        user_id=user.id,
        user_first_name=user.first_name,
        plan_type=plan_type,
        credits_remaining=credits_remaining,
        credits_monthly_limit=credits_monthly_limit,
        credits_reset_at=credits_reset_at,
        onboarding_completed=user.onboarding_completed,
        active_run=active_run,
        active_project=active_project,
        all_projects=all_projects,
        active_dep_chain=active_dep_chain,
        extracted_fields=extracted_fields,
        conversation_history=conversation_history,
        available_miniservices=available_miniservices,
    )
