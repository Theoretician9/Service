"""Single entry point for all non-command Telegram messages.
Routes through the full orchestrator pipeline (spec 3.3)."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import confirmation_keyboard, result_actions_keyboard
from app.bot.messages import (
    BUG_REPORT_THANKS,
    CANCEL_CONFIRMED,
    CREDITS_EXHAUSTED,
    ERROR_GENERIC,
    LEAD_SEARCH_PAID_ONLY,
    ONBOARDING_PROJECT_ASK,
    PROCESSING,
    PROJECT_CREATED,
    PROJECT_LIMIT_REACHED,
    UPGRADE_INFO,
)
from app.config import settings
from app.miniservices.engine import (
    all_required_collected,
    get_next_question,
    load_manifest,
)
from app.miniservices.session import (
    append_agent_conversation,
    append_conversation,
    clear_dialog,
    clear_pending_confirmation,
    get_active_project,
    get_agent_conversation,
    get_dialog,
    get_pending_confirmation,
    set_active_project,
    set_dep_chain,
    set_dialog,
    set_extracted_fields,
    set_pending_confirmation,
    update_dialog_field,
)
from app.miniservices.agents.registry import get_agent
from app.modules.analytics.service import AnalyticsService
from app.modules.artifacts.models import MiniserviceRun
from app.modules.billing.service import BillingService
from app.modules.projects.service import ProjectService
from app.modules.users.models import User
from app.modules.users.service import UserService
from app.orchestrator.context_builder import build_context
from app.orchestrator.intent import OrchestratorAction, OrchestratorDecision
from app.orchestrator.orchestrator import decide
from app.orchestrator.smart_extractor import extract_fields
from app.workers.miniservice_tasks import run_miniservice_task
from app.logging_config import get_conversation_logger

logger = structlog.get_logger()
conv_logger = get_conversation_logger()
router = Router(name="message_handler")


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------


@router.message()
async def handle_message(
    message: Message, user: User, db_session: AsyncSession
) -> None:
    """Process every incoming text message through the orchestrator pipeline."""
    text = (message.text or "").strip()
    if not text:
        return

    telegram_id = user.telegram_id

    # Log every incoming user message
    dialog = await get_dialog(telegram_id)
    conv_logger.info(
        "user_message",
        telegram_id=telegram_id,
        user_name=user.first_name,
        text=text,
        has_active_dialog=bool(dialog and dialog.get("miniservice_id")),
        miniservice_id=dialog.get("miniservice_id") if dialog else None,
    )

    try:
        # ① Smart extractor (best-effort) --------------------------------
        await _run_smart_extraction(telegram_id, text)

        # ── Pre-save choice fields before agent call (saves LLM tokens) ──
        # If active dialog and next field is choice, save the match
        # but let the agent formulate the next question with context
        dialog = await get_dialog(telegram_id)
        if dialog and dialog.get("miniservice_id"):
            ms_id = dialog["miniservice_id"]
            collected = dialog.get("collected_fields", {})
            next_field = get_next_question(ms_id, collected)

            if next_field and next_field.get("type") in ("choice", "multi_choice", "yes_no"):
                matched = _match_choice_field(text, next_field)
                if matched is not None:
                    field_id = next_field["id"]
                    await update_dialog_field(telegram_id, field_id, matched)
                    # Check if all done
                    updated_dialog = await get_dialog(telegram_id)
                    updated_collected = updated_dialog.get("collected_fields", {})
                    if all_required_collected(ms_id, updated_collected):
                        run_id = updated_dialog["run_id"]
                        from app.database import async_session as _async_session
                        async with _async_session() as _s:
                            from sqlalchemy import update as sa_update
                            await _s.execute(
                                sa_update(MiniserviceRun)
                                .where(MiniserviceRun.id == uuid.UUID(run_id))
                                .values(collected_fields=updated_collected)
                            )
                            await _s.commit()
                        run_miniservice_task.delay(run_id)
                        await message.answer(f"✅ Записал: {matched}\n\n⏳ Все данные собраны. Анализирую...")
                        return
                    # Field saved — fall through to agent for next question
                    # (agent sees updated collected_fields and asks contextually)

        # ── Route to miniservice agent if active dialog ──────────────
        if dialog and dialog.get("miniservice_id"):
            agent = get_agent(dialog["miniservice_id"])
            if agent:
                ms_id = dialog["miniservice_id"]
                collected = dialog.get("collected_fields", {})

                # Get agent conversation history (separate from main)
                agent_history = await get_agent_conversation(telegram_id, limit=15)

                # Build project context
                context_data = await build_context(telegram_id, db_session)
                project_ctx: dict[str, Any] = {}
                if context_data.active_project:
                    project_ctx = dict(context_data.active_project.profile or {})
                    project_ctx["project_name"] = context_data.active_project.name

                # Call agent
                agent_response = await agent.handle_message(
                    user_message=text,
                    collected_fields=collected,
                    conversation_history=agent_history,
                    project_context=project_ctx,
                )

                # Log agent response
                conv_logger.info(
                    "agent_response",
                    telegram_id=telegram_id,
                    user_name=user.first_name,
                    miniservice_id=ms_id,
                    text=agent_response.text[:500] if agent_response.text else None,
                    field_id=agent_response.field_id,
                    field_value=agent_response.field_value,
                    all_collected=agent_response.all_collected,
                    ready_to_process=agent_response.ready_to_process,
                )

                # Save field if accepted (single canonical save point)
                if agent_response.field_id and agent_response.field_value:
                    await update_dialog_field(telegram_id, agent_response.field_id, agent_response.field_value)

                # Check if ready to process
                if agent_response.ready_to_process:
                    updated = await get_dialog(telegram_id)
                    if updated:
                        run_id = updated["run_id"]
                        updated_collected = updated.get("collected_fields", {})

                        # Sync collected_fields to DB
                        from app.database import async_session as _async_session
                        async with _async_session() as _s:
                            from sqlalchemy import update as sa_update
                            await _s.execute(
                                sa_update(MiniserviceRun)
                                .where(MiniserviceRun.id == uuid.UUID(run_id))
                                .values(collected_fields=updated_collected)
                            )
                            await _s.commit()

                        # Check if this is a two-phase miniservice
                        sub_phase = updated_collected.get("sub_phase", "")
                        manifest = load_manifest(ms_id)
                        is_two_phase = manifest.get("two_phase", False)

                        if is_two_phase and sub_phase != "hypothesis_validation":
                            # Phase 1: launch intermediate task
                            from app.workers.miniservice_tasks import run_intermediate_task
                            from app.bot.messages import DECOMP_PROCESSING_INTERMEDIATE
                            run_intermediate_task.delay(run_id)
                            await message.answer(DECOMP_PROCESSING_INTERMEDIATE)
                        else:
                            # Phase 2 or standard: launch final task
                            if is_two_phase:
                                from app.bot.messages import DECOMP_PROCESSING_FINAL
                                await message.answer(DECOMP_PROCESSING_FINAL)
                            else:
                                await message.answer(PROCESSING)
                            run_miniservice_task.delay(run_id)
                elif agent_response.all_collected and not agent_response.ready_to_process:
                    # All fields collected but waiting for confirmation
                    await message.answer(agent_response.text)
                else:
                    # Normal response (probing, clarifying, next question)
                    if agent_response.text:
                        await message.answer(agent_response.text)

                # Save to agent conversation (NOT main conversation)
                await append_agent_conversation(telegram_id, "user", text)
                if agent_response.text:
                    await append_agent_conversation(telegram_id, "assistant", agent_response.text)
                return

        # ② Build OrchestratorContext -------------------------------------
        context = await build_context(telegram_id, db_session)

        # ③ Orchestrator decides (LLM) ------------------------------------
        decision = await decide(context, text)
        logger.debug("orchestrator_decided", action=str(decision.action), response_preview=decision.response_text[:80] if decision.response_text else None)

        # Log orchestrator decision
        conv_logger.info(
            "orchestrator_decision",
            telegram_id=telegram_id,
            user_name=user.first_name,
            action=decision.action.value if hasattr(decision.action, 'value') else str(decision.action),
            confidence=decision.confidence,
            response=decision.response_text[:500] if decision.response_text else None,
            params=decision.params,
            needs_confirmation=decision.needs_confirmation,
        )

        # Save conversation history
        await append_conversation(telegram_id, "user", text)
        if decision.response_text:
            await append_conversation(telegram_id, "assistant", decision.response_text)

        # ④ Confirmation gate --------------------------------------------
        # ④ Confirmation gate — only for non-collecting actions
        # Mentor dialogue (CONTINUE_COLLECTING, RESPOND during active_run)
        # should never show confirmation buttons
        if decision.needs_confirmation and decision.action not in (
            OrchestratorAction.CONTINUE_COLLECTING,
            OrchestratorAction.RESPOND,
            OrchestratorAction.ONBOARDING,
        ):
            await _handle_confirmation_request(message, telegram_id, decision)
            return

        # ⑤ Dispatch action -----------------------------------------------
        await _dispatch_action(message, user, db_session, telegram_id, decision)

    except Exception as exc:
        logger.error("handler_exception", error=str(exc), error_type=type(exc).__name__, exc_info=True)
        conv_logger.error(
            "handler_error",
            telegram_id=telegram_id,
            user_name=user.first_name,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        await message.answer(ERROR_GENERIC)


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------


def _match_choice_field(user_text: str, field: dict) -> str | None:
    """Match user's text to a choice field option using strict validation."""
    from app.services.choice_validator import match_choice_field
    return match_choice_field(user_text, field)


async def _run_smart_extraction(telegram_id: int, text: str) -> None:
    """Run smart extractor (best-effort, never raises)."""
    try:
        dialog = await get_dialog(telegram_id)
        active_project = await get_active_project(telegram_id)
        context_dict: dict[str, Any] = {
            "dialog": dialog,
            "active_project": active_project,
        }
        extracted = await extract_fields(text, context_dict)
        if extracted:
            await set_extracted_fields(telegram_id, extracted)
            # If there is an active dialog, apply matching fields
            if dialog:
                ms_id = dialog.get("miniservice_id", "")
                ms_fields = extracted.get(ms_id, {})
                for field_id, value in ms_fields.items():
                    if field_id not in dialog.get("collected_fields", {}):
                        await update_dialog_field(telegram_id, field_id, value)
    except Exception:
        logger.debug("smart_extraction_skipped", telegram_id=telegram_id)


async def _handle_confirmation_request(
    message: Message,
    telegram_id: int,
    decision: OrchestratorDecision,
) -> None:
    """Store decision in Redis and ask user to confirm."""
    decision_dict = dataclasses.asdict(decision)
    decision_dict["action"] = decision.action.value
    await set_pending_confirmation(telegram_id, decision_dict)

    text = decision.confirmation_text or decision.response_text
    await message.answer(text, reply_markup=confirmation_keyboard())
    logger.info(
        "confirmation_requested",
        telegram_id=telegram_id,
        action=decision.action.value,
    )


async def _handle_active_collecting(
    message: Message,
    user: User,
    db_session: AsyncSession,
    telegram_id: int,
    text: str,
    dialog: dict,
) -> None:
    """Handle message when user is in active slot-filling.

    The user's message is the answer to the current question.
    Find which field we're currently asking, save the value, advance.
    """
    miniservice_id = dialog["miniservice_id"]
    collected = dialog.get("collected_fields", {})

    # Check for cancel intent first
    cancel_keywords = {"отмена", "отменить", "стоп", "cancel", "/cancel", "выход", "назад"}
    if text.strip().lower() in cancel_keywords:
        await clear_dialog(telegram_id)
        await message.answer(CANCEL_CONFIRMED)
        return

    # Find the current question (first unanswered field)
    next_field = get_next_question(miniservice_id, collected)
    if next_field:
        field_id = next_field["id"]
        # Save user's answer as this field's value
        await update_dialog_field(telegram_id, field_id, text)
        collected[field_id] = text

    # Check if all required fields are now collected
    if all_required_collected(miniservice_id, collected):
        # All done — trigger processing via Celery
        run_id = dialog["run_id"]
        celery_result = run_miniservice_task.delay(run_id)
        await message.answer(PROCESSING)
        logger.info(
            "miniservice_all_collected",
            telegram_id=telegram_id,
            miniservice_id=miniservice_id,
        )
        return

    # Ask next question
    next_field = get_next_question(miniservice_id, collected)
    if next_field:
        question = next_field.get("question", next_field.get("label", "Уточни:"))
        hint = next_field.get("hint")
        if hint:
            question = f"{question}\n\n💡 {hint}"
        await message.answer(question)
    else:
        # Shouldn't happen, but fallback
        run_id = dialog["run_id"]
        run_miniservice_task.delay(run_id)
        await message.answer(PROCESSING)

    # Save conversation
    await append_conversation(telegram_id, "user", text)


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------


async def _dispatch_action(
    message: Message,
    user: User,
    db_session: AsyncSession,
    telegram_id: int,
    decision: OrchestratorDecision,
) -> None:
    """Route to the correct handler based on OrchestratorDecision.action."""
    action = decision.action
    params = decision.params or {}

    if action == OrchestratorAction.RESPOND:
        await message.answer(decision.response_text)

    elif action == OrchestratorAction.ONBOARDING:
        await _action_onboarding(message, user, db_session, params)

    elif action == OrchestratorAction.ENSURE_PROJECT:
        await _action_ensure_project(message, user, db_session, params)

    elif action == OrchestratorAction.CREATE_PROJECT:
        await _action_create_project(message, user, db_session, params)

    elif action == OrchestratorAction.LAUNCH_MINISERVICE:
        # Check if this is a "ready to process" signal for active run
        dialog = await get_dialog(telegram_id)
        if dialog and params.get("ready_to_process"):
            run_id = dialog["run_id"]
            # Sync collected_fields from Redis to DB before launching task
            collected = dialog.get("collected_fields", {})
            if collected:
                from sqlalchemy import update as sa_update
                await db_session.execute(
                    sa_update(MiniserviceRun)
                    .where(MiniserviceRun.id == uuid.UUID(run_id))
                    .values(collected_fields=collected)
                )
                await db_session.commit()
            run_miniservice_task.delay(run_id)
            await message.answer(PROCESSING)
        else:
            await _action_launch_miniservice(message, user, db_session, telegram_id, params)

    elif action == OrchestratorAction.CONTINUE_COLLECTING:
        await _action_continue_collecting(message, telegram_id, params, response_text=decision.response_text)

    elif action == OrchestratorAction.SHOW_INFO:
        await message.answer(decision.response_text)

    elif action == OrchestratorAction.SHOW_PLAN:
        await message.answer(decision.response_text)

    elif action == OrchestratorAction.UPGRADE_CTA:
        await message.answer(UPGRADE_INFO)

    elif action == OrchestratorAction.CANCEL_RUN:
        await _action_cancel_run(message, telegram_id)

    elif action == OrchestratorAction.BUG_REPORT:
        await _action_bug_report(message, user, db_session, params)

    elif action == OrchestratorAction.INIT_DEP_CHAIN:
        await _action_init_dep_chain(message, user, db_session, telegram_id, params)

    elif action == OrchestratorAction.SWITCH_PROJECT:
        await _action_switch_project(message, user, db_session, telegram_id, params)

    elif action in (OrchestratorAction.ARTIFACT_PDF, OrchestratorAction.ARTIFACT_SHEETS):
        # Handled via callback buttons, but if orchestrator routes here directly
        await message.answer(decision.response_text or PROCESSING)

    else:
        # Catch-all for any new actions
        if decision.response_text:
            await message.answer(decision.response_text)


# ---------------------------------------------------------------------------
# Individual action handlers
# ---------------------------------------------------------------------------


async def _action_onboarding(
    message: Message,
    user: User,
    db_session: AsyncSession,
    params: dict,
) -> None:
    """Handle onboarding steps — stateful, checks what's already filled.

    First message after welcome is critical — it may contain rich context
    about the user's business. We save it fully and extract fields for
    future miniservices via smart extractor.
    """
    user_message = params.get("user_message", message.text or "")
    telegram_id = user.telegram_id

    # Step 1: role not set yet → save role/goal + extract context, ask for project name
    if not user.onboarding_role:
        user.onboarding_role = "Предприниматель"
        user.onboarding_primary_goal = user_message[:256]
        await db_session.commit()

        # Save full first message to conversation history — orchestrator will see it later
        await append_conversation(telegram_id, "user", user_message)

        await message.answer(ONBOARDING_PROJECT_ASK)
        logger.info("onboarding_role_set", telegram_id=telegram_id)
        return

    # Step 2: role set but onboarding not complete → create project
    project_name = user_message.strip()[:128] or "Мой проект"
    project_service = ProjectService(db_session)
    project = await project_service.create(user_id=user.id, name=project_name)
    await set_active_project(telegram_id, str(project.id), project.name)

    user.onboarding_completed = True
    await db_session.commit()

    # Auto-launch goal_setting — don't ask "what to run", just start
    await message.answer(
        f"📁 Проект «{project.name}» создан!\n\n"
        "Начнём с постановки целей — это поможет понять куда двигаться."
    )

    # Auto-launch goal_setting miniservice
    await _action_launch_miniservice(
        message, user, db_session, telegram_id,
        {"miniservice_id": "goal_setting", "project_id": str(project.id)},
    )
    logger.info("onboarding_completed", telegram_id=telegram_id)


async def _action_ensure_project(
    message: Message,
    user: User,
    db_session: AsyncSession,
    params: dict,
) -> None:
    """Ensure user has an active project, or ask for a name."""
    active = await get_active_project(user.telegram_id)
    if active:
        await message.answer(params.get("response_text", f"Активный проект: {active['project_name']}"))
        return

    projects = await ProjectService(db_session).get_user_projects(user.id)
    if projects:
        project = projects[0]
        await set_active_project(user.telegram_id, str(project.id), project.name)
        await message.answer(f"Установлен проект «{project.name}». Продолжаем!")
    else:
        await message.answer(
            "У тебя ещё нет проекта. Напиши название для нового проекта:"
        )


async def _action_create_project(
    message: Message,
    user: User,
    db_session: AsyncSession,
    params: dict,
) -> None:
    """Create a new project."""
    project_service = ProjectService(db_session)
    billing_service = BillingService(db_session)
    plan = await billing_service.get_plan(user.id)

    max_projects = settings.max_projects_paid if (plan and plan.plan_type == "paid") else settings.max_projects_free
    current_count = await project_service.count_active(user.id)

    if current_count >= max_projects:
        await message.answer(
            PROJECT_LIMIT_REACHED.format(current=current_count, max=max_projects)
        )
        return

    name = params.get("project_name", "Новый проект")[:128]
    project = await project_service.create(user_id=user.id, name=name)
    await set_active_project(user.telegram_id, str(project.id), project.name)
    await message.answer(PROJECT_CREATED.format(name=project.name))
    logger.info("project_created", telegram_id=user.telegram_id, project_name=project.name)


async def _action_launch_miniservice(
    message: Message,
    user: User,
    db_session: AsyncSession,
    telegram_id: int,
    params: dict,
) -> None:
    """Check credits, create MiniserviceRun, set dialog, spawn Celery task."""
    miniservice_id: str = params.get("miniservice_id", "")
    if not miniservice_id:
        await message.answer(ERROR_GENERIC)
        return

    manifest = load_manifest(miniservice_id)
    credit_cost: int = manifest.get("credit_cost", 1)
    available_on_free: bool = manifest.get("available_on_free", True)

    # Check plan restrictions
    billing_service = BillingService(db_session)
    plan = await billing_service.get_or_create_plan(user.id)
    plan_type = plan.plan_type

    if not available_on_free and plan_type == "free":
        await message.answer(LEAD_SEARCH_PAID_ONLY)
        return

    # Check / reserve credits (admins have unlimited)
    if not settings.is_admin(telegram_id) and (plan is None or plan.credits_remaining < credit_cost):
        await message.answer(CREDITS_EXHAUSTED.format(cost=credit_cost))
        return

    reserved = await billing_service.reserve_credits(user.id, credit_cost, telegram_id=telegram_id)
    if not reserved:
        await message.answer(CREDITS_EXHAUSTED.format(cost=credit_cost))
        return

    # Active project
    active_project = await get_active_project(telegram_id)
    if not active_project:
        await message.answer("Сначала нужно выбрать проект. Напиши название:")
        # Refund since we can't proceed
        await billing_service.refund_credits(user.id, credit_cost)
        return

    project_id = uuid.UUID(active_project["project_id"])

    # Pre-fill fields from multiple sources:
    # 1. Params from orchestrator (prefilled_fields)
    # 2. Extracted fields from Redis (smart extractor)
    # 3. Project profile data mapped to miniservice fields
    collected_fields = params.get("collected_fields", {}) or params.get("prefilled_fields", {})

    # Merge extracted fields for this miniservice
    from app.miniservices.session import get_extracted_fields
    extracted = await get_extracted_fields(telegram_id)
    ms_extracted = extracted.get(miniservice_id, {})
    for k, v in ms_extracted.items():
        if k not in collected_fields:
            collected_fields[k] = v

    # Create MiniserviceRun in DB
    run = MiniserviceRun(
        user_id=user.id,
        project_id=project_id,
        miniservice_id=miniservice_id,
        mode=params.get("mode", "standalone"),
        status="collecting",
        collected_fields=collected_fields,
        credits_spent=credit_cost,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    # Check if all required fields are already collected
    if all_required_collected(miniservice_id, collected_fields):
        # Go straight to processing
        run.status = "processing"
        await db_session.commit()

        await set_dialog(
            telegram_id,
            miniservice_id=miniservice_id,
            run_id=run.id,
            project_id=project_id,
            step=0,
            collected_fields=collected_fields,
        )

        celery_result = run_miniservice_task.delay(str(run.id))
        run.celery_task_id = celery_result.id
        await db_session.commit()

        await message.answer(PROCESSING)
        logger.info(
            "miniservice_launched",
            telegram_id=telegram_id,
            miniservice_id=miniservice_id,
            run_id=str(run.id),
        )
    else:
        # Start collecting — set dialog and ask first question
        await set_dialog(
            telegram_id,
            miniservice_id=miniservice_id,
            run_id=run.id,
            project_id=project_id,
            step=1,
            collected_fields=collected_fields,
        )

        # Let the agent introduce the miniservice with context (not a raw manifest question)
        from app.miniservices.agents.registry import get_agent as _get_agent
        agent = _get_agent(miniservice_id)
        if agent:
            # Build project context for agent
            project_ctx: dict = {}
            # Get project from DB
            from sqlalchemy import select as sa_select
            from app.modules.projects.models import Project
            proj_stmt = sa_select(Project).where(Project.id == project_id)
            proj_result = await db_session.execute(proj_stmt)
            project = proj_result.scalar_one_or_none()
            if project:
                for pf in ["name", "goal_statement", "point_a", "point_b", "goal_deadline", "constraints", "chosen_niche", "geography", "budget_range"]:
                    val = getattr(project, pf, None)
                    if val:
                        project_ctx[pf] = val

            intro = await agent.handle_message(
                user_message="[СТАРТ СЕССИИ]",
                collected_fields=collected_fields,
                conversation_history=[],
                project_context=project_ctx,
            )
            await message.answer(intro.text)
            await append_agent_conversation(telegram_id, "assistant", intro.text)
        else:
            next_field = get_next_question(miniservice_id, collected_fields)
            if next_field:
                question = next_field.get("question", next_field.get("label", "Уточни данные:"))
                await message.answer(question)
            else:
                await message.answer("Расскажи подробнее о задаче:")

        logger.info(
            "miniservice_collecting",
            telegram_id=telegram_id,
            miniservice_id=miniservice_id,
            run_id=str(run.id),
        )


async def _action_continue_collecting(
    message: Message,
    telegram_id: int,
    params: dict,
    response_text: str = "",
) -> None:
    """Apply field value from orchestrator and check completion.

    The orchestrator (mentor) already evaluated the answer quality.
    If field_id + field_value are in params → answer accepted, save it.
    If not → orchestrator is probing deeper (response_text has the question).
    """
    field_id: str = params.get("field_id", "")
    field_value: str = params.get("field_value", "")

    if field_id and field_value:
        dialog = await update_dialog_field(telegram_id, field_id, field_value)
    else:
        dialog = await get_dialog(telegram_id)
        if not dialog:
            await message.answer(ERROR_GENERIC)
            return

    miniservice_id = dialog["miniservice_id"]
    collected = dialog["collected_fields"]

    if all_required_collected(miniservice_id, collected):
        # All fields collected → sync to DB
        run_id = dialog["run_id"]
        from app.database import async_session as _async_session
        async with _async_session() as _session:
            from sqlalchemy import update as sa_update
            await _session.execute(
                sa_update(MiniserviceRun)
                .where(MiniserviceRun.id == uuid.UUID(run_id))
                .values(collected_fields=collected)
            )
            await _session.commit()

        # If orchestrator already said "ready?" in response_text, show it
        # Otherwise ask for confirmation before processing
        if response_text:
            await message.answer(response_text)
        else:
            await message.answer(
                "✅ Все данные собраны. Запускаю анализ?\n\n"
                "(Напиши «да» или «готов»)"
            )
        return  # Wait for user confirmation — LAUNCH_MINISERVICE with ready_to_process will trigger
        logger.info(
            "miniservice_all_collected",
            telegram_id=telegram_id,
            miniservice_id=miniservice_id,
            run_id=run_id,
        )
    elif response_text:
        # Orchestrator (mentor) generated the next question/probe via LLM
        await message.answer(response_text)
    else:
            await message.answer("Расскажи подробнее:")


async def _action_cancel_run(message: Message, telegram_id: int) -> None:
    """Clear dialog and confirm cancellation.
    For two-phase miniservices: partial refund if Phase 1 already completed.
    """
    dialog = await get_dialog(telegram_id)

    if dialog:
        collected = dialog.get("collected_fields", {})
        ms_id = dialog.get("miniservice_id", "")
        sub_phase = collected.get("sub_phase", "")

        # Check if two-phase and Phase 1 already done
        if sub_phase == "hypothesis_validation":
            manifest = load_manifest(ms_id)
            full_cost = manifest.get("credit_cost", 2)
            partial_refund = full_cost // 2  # refund half

            if partial_refund > 0:
                from app.database import async_session as _async_session
                async with _async_session() as _s:
                    from sqlalchemy import select as sa_select
                    from app.modules.users.models import User as _User
                    user_stmt = sa_select(_User).where(_User.telegram_id == telegram_id)
                    user_result = await _s.execute(user_stmt)
                    user_obj = user_result.scalar_one_or_none()
                    if user_obj:
                        billing = BillingService(_s)
                        await billing.refund_credits(user_obj.id, partial_refund)
                        await _s.commit()

            logger.info(
                "run_cancelled_partial_refund",
                telegram_id=telegram_id,
                miniservice_id=ms_id,
                refunded=partial_refund,
            )

    await clear_dialog(telegram_id)
    await message.answer(CANCEL_CONFIRMED)
    logger.info("run_cancelled", telegram_id=telegram_id)


async def _action_bug_report(
    message: Message,
    user: User,
    db_session: AsyncSession,
    params: dict,
) -> None:
    """Save bug report to DB."""
    report_text = params.get("text", "")
    if report_text:
        analytics = AnalyticsService(db_session)
        await analytics.create_bug_report(user.id, report_text)
    await message.answer(BUG_REPORT_THANKS)
    logger.info("bug_report_saved", telegram_id=user.telegram_id)


async def _action_init_dep_chain(
    message: Message,
    user: User,
    db_session: AsyncSession,
    telegram_id: int,
    params: dict,
) -> None:
    """Save dependency chain to Redis and launch the first miniservice."""
    chain: list[str] = params.get("chain", [])
    target: str = params.get("target_miniservice", "")

    active_project = await get_active_project(telegram_id)
    if not active_project:
        await message.answer("Сначала создай проект.")
        return

    project_id = active_project["project_id"]

    if not chain:
        await message.answer(ERROR_GENERIC)
        return

    # Save the full chain
    await set_dep_chain(telegram_id, target, chain, project_id)

    # Launch the first miniservice in the chain
    first_ms = chain[0]
    launch_params = {
        "miniservice_id": first_ms,
        "mode": "sequential",
        "collected_fields": params.get("collected_fields", {}),
    }
    decision = OrchestratorDecision(
        action=OrchestratorAction.LAUNCH_MINISERVICE,
        response_text="",
        confidence=1.0,
        params=launch_params,
        needs_confirmation=False,
    )
    await _dispatch_action(message, user, db_session, telegram_id, decision)

    logger.info(
        "dep_chain_initiated",
        telegram_id=telegram_id,
        target=target,
        chain=chain,
    )


async def _action_switch_project(
    message: Message,
    user: User,
    db_session: AsyncSession,
    telegram_id: int,
    params: dict,
) -> None:
    """Switch to a different project."""
    project_id_str = params.get("project_id")
    project_name = params.get("project_name")

    if project_id_str and project_name:
        await set_active_project(telegram_id, project_id_str, project_name)
        await clear_dialog(telegram_id)
        await message.answer(f"Переключился на проект «{project_name}».")
    else:
        # List projects for selection
        projects = await ProjectService(db_session).get_user_projects(user.id)
        if not projects:
            await message.answer("У тебя нет проектов. Напиши название для нового:")
            return
        lines = ["Выбери проект (напиши номер):\n"]
        for i, p in enumerate(projects, 1):
            lines.append(f"{i}. {p.name}")
        await message.answer("\n".join(lines))


# ---------------------------------------------------------------------------
# Fallback (used when orchestrator stubs are not yet implemented)
# ---------------------------------------------------------------------------


async def _fallback_response(
    message: Message, user: User, db_session: AsyncSession, text: str
) -> None:
    """Legacy flow used when orchestrator raises NotImplementedError."""
    telegram_id = user.telegram_id

    # Onboarding: user hasn't completed it yet
    if not user.onboarding_completed:
        await _handle_onboarding_legacy(message, user, db_session, text)
        return

    # Check active project
    active = await get_active_project(telegram_id)
    if not active:
        projects = await ProjectService(db_session).get_user_projects(user.id)
        if not projects:
            await _create_project_from_message(message, user, db_session, text)
            return
        else:
            project = projects[0]
            await set_active_project(telegram_id, str(project.id), project.name)
            active = {"project_id": str(project.id), "project_name": project.name}

    await message.answer(
        f"Работаем в проекте «{active['project_name']}».\n\n"
        "Оркестратор пока в разработке. Скоро я смогу:\n"
        "- Запускать минисервисы\n"
        "- Извлекать данные из сообщений\n"
        "- Строить цепочки зависимостей\n\n"
        "Пока доступны команды: /help, /projects, /plan, /cancel"
    )


async def _handle_onboarding_legacy(
    message: Message, user: User, db_session: AsyncSession, text: str
) -> None:
    """Handle onboarding when orchestrator is not yet implemented."""
    if not user.onboarding_role:
        role = "Предприниматель"
        goal = text[:64]
        user.onboarding_role = role
        user.onboarding_primary_goal = goal
        await db_session.commit()
        await message.answer(ONBOARDING_PROJECT_ASK)
        logger.info("onboarding_role_set", telegram_id=user.telegram_id, role=role)
        return

    if not user.onboarding_completed:
        project_name = text[:128]
        await _create_project_from_message(message, user, db_session, project_name)
        user.onboarding_completed = True
        await db_session.commit()
        logger.info("onboarding_completed", telegram_id=user.telegram_id)


async def _create_project_from_message(
    message: Message, user: User, db_session: AsyncSession, name: str
) -> None:
    """Create a project and set it as active."""
    project_service = ProjectService(db_session)
    project = await project_service.create(user_id=user.id, name=name)
    await set_active_project(user.telegram_id, str(project.id), project.name)
    await message.answer(PROJECT_CREATED.format(name=project.name))
    logger.info("project_created", telegram_id=user.telegram_id, project_name=project.name)


# ---------------------------------------------------------------------------
# Callback query handlers
# ---------------------------------------------------------------------------


@router.callback_query(F.data.in_({"confirm_yes", "confirm_no"}))
async def handle_confirmation(
    callback: CallbackQuery, user: User, db_session: AsyncSession
) -> None:
    """Handle confirmation buttons for pending decisions."""
    telegram_id = user.telegram_id

    try:
        pending = await get_pending_confirmation(telegram_id)
        if not pending:
            await callback.answer("Действие устарело.", show_alert=True)
            return

        await clear_pending_confirmation(telegram_id)

        if callback.data == "confirm_no":
            await callback.answer("Отменено.")
            if callback.message:
                await callback.message.edit_text("Отменено.")
            return

        # Reconstruct decision and dispatch
        decision = OrchestratorDecision(
            action=OrchestratorAction(pending["action"]),
            response_text=pending.get("response_text", ""),
            confidence=pending.get("confidence", 1.0),
            params=pending.get("params", {}),
            needs_confirmation=False,
        )

        await callback.answer("Выполняю...")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        await _dispatch_action(
            callback.message, user, db_session, telegram_id, decision
        )
        logger.info(
            "confirmation_accepted",
            telegram_id=telegram_id,
            action=pending["action"],
        )

    except Exception:
        logger.exception("confirmation_handler_error", telegram_id=telegram_id)
        await callback.answer("Ошибка обработки.", show_alert=True)


@router.callback_query(F.data.in_({"export_pdf", "export_sheets"}))
async def handle_export(
    callback: CallbackQuery, user: User, db_session: AsyncSession
) -> None:
    """Handle PDF/Sheets export buttons on result messages."""
    telegram_id = user.telegram_id

    try:
        dialog = await get_dialog(telegram_id)
        active_project = await get_active_project(telegram_id)

        if not active_project:
            await callback.answer("Нет активного проекта.", show_alert=True)
            return

        if callback.data == "export_pdf":
            await callback.answer("Генерирую PDF...")
            # TODO: spawn pdf_gen Celery task
            if callback.message:
                await callback.message.answer("Генерация PDF запущена, пришлю файл через минуту.")
            logger.info("export_pdf_requested", telegram_id=telegram_id)

        elif callback.data == "export_sheets":
            billing_service = BillingService(db_session)
            plan = await billing_service.get_plan(user.id)

            if not plan or plan.plan_type != "paid":
                await callback.answer(
                    "Google Sheets доступен на тарифе Paid.", show_alert=True
                )
                return

            await callback.answer("Экспортирую в Sheets...")
            # TODO: spawn sheets_export Celery task
            if callback.message:
                await callback.message.answer(
                    "Экспорт в Google Sheets запущен, пришлю ссылку через минуту."
                )
            logger.info("export_sheets_requested", telegram_id=telegram_id)

    except Exception:
        logger.exception("export_handler_error", telegram_id=telegram_id)
        await callback.answer("Ошибка при экспорте.", show_alert=True)
