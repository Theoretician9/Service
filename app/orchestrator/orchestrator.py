"""Main orchestrator: decides what to do with each user message."""

import json

import structlog

from app.config import settings
from app.integrations.llm_gateway import llm_gateway
from app.orchestrator.context_builder import OrchestratorContext
from app.orchestrator.intent import OrchestratorAction, OrchestratorDecision
from app.orchestrator.prompts import build_dynamic_context, build_system_prompt

logger = structlog.get_logger()

# Low-confidence response when LLM fails
_FALLBACK_RESPONSE = OrchestratorDecision(
    action=OrchestratorAction.RESPOND,
    response_text="Произошла ошибка при обработке сообщения. Попробуй ещё раз или напиши /help.",
    confidence=1.0,
    params={},
    needs_confirmation=False,
)

_ONBOARDING_RESPONSE = OrchestratorDecision(
    action=OrchestratorAction.ONBOARDING,
    response_text="Давай познакомимся! Расскажи немного о себе — кто ты и чем занимаешься?",
    confidence=1.0,
    params={},
    needs_confirmation=False,
)


def _parse_decision(raw: str, threshold: float) -> OrchestratorDecision:
    """Parse LLM JSON response into OrchestratorDecision.

    Raises ValueError if parsing fails.
    """
    content = raw.strip()
    # Strip markdown code block if present
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines).strip()

    data = json.loads(content)

    action_str = data.get("action", "RESPOND")
    try:
        action = OrchestratorAction(action_str)
    except ValueError:
        logger.warning("orchestrator_unknown_action", action=action_str)
        action = OrchestratorAction.RESPOND

    confidence = float(data.get("confidence", 0.5))
    needs_confirmation = data.get("needs_confirmation", False)

    # Override needs_confirmation based on threshold
    if confidence < threshold:
        needs_confirmation = True

    response_text = data.get("response_text", "")
    params = data.get("params", {})
    confirmation_text = data.get("confirmation_text")

    # Generate confirmation text if needed but not provided
    if needs_confirmation and not confirmation_text:
        confirmation_text = f"Я правильно понял? {response_text}"

    return OrchestratorDecision(
        action=action,
        response_text=response_text,
        confidence=confidence,
        params=params if isinstance(params, dict) else {},
        needs_confirmation=needs_confirmation,
        confirmation_text=confirmation_text,
    )


def _handle_active_run_context(context: OrchestratorContext, user_message: str) -> OrchestratorDecision | None:
    """Fast-path: if there's an active run, default to CONTINUE_COLLECTING.

    Returns None if no fast-path applies (let LLM decide).
    """
    if not context.active_run:
        return None

    # Check for explicit cancel intent (simple heuristic before LLM)
    cancel_keywords = {"отмена", "отменить", "стоп", "cancel", "/cancel", "выход", "назад"}
    if user_message.strip().lower() in cancel_keywords:
        return OrchestratorDecision(
            action=OrchestratorAction.CANCEL_RUN,
            response_text="Отменяю текущий запуск.",
            confidence=1.0,
            params={},
            needs_confirmation=False,
        )

    # Don't fast-path — let LLM decide between CONTINUE_COLLECTING and other intents
    return None


async def decide(context: OrchestratorContext, user_message: str) -> OrchestratorDecision:
    """Process user message and return decision.

    Calls Claude Sonnet with full context to determine the next action.
    Always returns a valid OrchestratorDecision, even on errors.
    """
    # ── Handle onboarding ───────────────────────────────────────────
    if not context.onboarding_completed:
        # If onboarding not completed, route to onboarding flow
        return OrchestratorDecision(
            action=OrchestratorAction.ONBOARDING,
            response_text="",
            confidence=1.0,
            params={"user_message": user_message},
            needs_confirmation=False,
        )

    # ── Fast-path for active run cancel ─────────────────────────────
    fast_path = _handle_active_run_context(context, user_message)
    if fast_path is not None:
        return fast_path

    # ── Build prompts ───────────────────────────────────────────────
    system_prompt = build_system_prompt(context)
    dynamic_context = build_dynamic_context(context)

    user_content = f"--- КОНТЕКСТ ---\n{dynamic_context}\n\n--- СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ ---\n{user_message}"

    response = None
    try:
        response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            messages=[
                {"role": "user", "content": user_content},
            ],
            system=system_prompt,
            max_tokens=1000,
            temperature=0.3,
        )

        decision = _parse_decision(
            response.content,
            threshold=settings.orchestrator_confidence_threshold,
        )

        logger.info(
            "orchestrator_decision",
            action=decision.action.value,
            confidence=decision.confidence,
            needs_confirmation=decision.needs_confirmation,
            params_keys=list(decision.params.keys()),
        )

        return decision

    except json.JSONDecodeError:
        preview = response.content[:200] if response else "N/A"
        logger.warning("orchestrator_json_parse_error", response_preview=preview)
        return OrchestratorDecision(
            action=OrchestratorAction.RESPOND,
            response_text="Не удалось обработать ответ. Попробуй переформулировать запрос.",
            confidence=0.5,
            params={},
            needs_confirmation=False,
        )
    except Exception:
        logger.exception("orchestrator_error")
        return _FALLBACK_RESPONSE
