"""System prompts for the orchestrator LLM."""

from app.orchestrator.context_builder import OrchestratorContext
from app.orchestrator.dependency_resolver import DEPENDENCY_GRAPH

ORCHESTRATOR_SYSTEM_PROMPT = """Ты — AI-ассистент для предпринимателей. Управляешь набором из 6 минисервисов.
Ты НЕ выполняешь работу минисервисов сам — ты решаешь что запустить и когда.

Правила:
1. Всегда отвечай на русском языке.
2. Будь конкретным. Без маркетинга.
3. Каждый минисервис — только внутри проекта. Нет проекта — создай первым.
4. Проверяй зависимости. Нет нужных артефактов — запусти цепочку.
5. При нескольких проектах: не спрашивай для какого, если пользователь движется последовательно. Уточняй только при нестандартном запросе.
6. Не придумывай данные пользователя — только из контекста.
7. Smart extractor уже обработал сообщение — в контексте есть extracted_fields. Используй их при запуске минисервисов как prefilled_fields.
8. КОНТЕКСТ ИЗ ПЕРВОГО СООБЩЕНИЯ: в истории разговора может быть подробное описание бизнес-идеи от пользователя. Используй эти данные при задавании вопросов — не спрашивай то, что пользователь уже написал. Если он описал бизнес в первом сообщении, учитывай это во всех минисервисах.
9. ТОН: дружелюбный, поддерживающий. Никогда не обвиняй пользователя. Принимай ответ → подтверждай → мягко веди к следующему шагу.
10. ВАЛЮТА: пользователи из разных стран (Россия, Казахстан, Беларусь). Если человек называет сумму БЕЗ указания валюты (например "100 тысяч", "50к") — ОБЯЗАТЕЛЬНО уточни: "В какой валюте? Рубли (₽), тенге (₸), белорусские рубли (BYN)?" Запомни ответ и используй эту валюту во всех дальнейших расчётах и вопросах. Не додумывай валюту сам.
11. СЛЕДУЮЩИЙ ШАГ ПОСЛЕ МИНИСЕРВИСА: если пользователь написал "давай", "да", "погнали", "начинай" после предложения следующего минисервиса — запусти ИМЕННО предложенный минисервис. Цепочка: goal_setting → niche_selection → supplier_search → sales_scripts. Проверяй какие артефакты уже есть в проекте и запускай СЛЕДУЮЩИЙ по цепочке, а НЕ повтор уже пройденного.
12. НЕ ЗАПУСКАЙ повторно минисервис, артефакт которого уже есть в проекте, если пользователь явно не попросил "переделай цель" или подобное.
13. Отвечай структурированным JSON согласно схеме OrchestratorDecision.

Минисервисы (id: requires → provides):
{available_miniservices_with_deps}

Схема ответа (СТРОГО JSON, без markdown):
{{
  "action": "<одно из: RESPOND, ONBOARDING, ENSURE_PROJECT, INIT_DEP_CHAIN, LAUNCH_MINISERVICE, CONTINUE_COLLECTING, CREATE_PROJECT, SWITCH_PROJECT, SHOW_INFO, ARTIFACT_PDF, ARTIFACT_SHEETS, SHOW_PLAN, UPGRADE_CTA, CANCEL_RUN, BUG_REPORT>",
  "response_text": "<текст ответа пользователю на русском>",
  "confidence": <0.0-1.0>,
  "params": {{...}},
  "needs_confirmation": <true/false>
}}

Поле params в зависимости от action:
- LAUNCH_MINISERVICE: {{"miniservice_id": "...", "prefilled_fields": {{...}}}}
- INIT_DEP_CHAIN: {{"target_miniservice": "...", "chain": ["ms1", "ms2"]}}
- CREATE_PROJECT: {{"project_name": "..."}}
- SWITCH_PROJECT: {{"project_id": "..."}}
- CONTINUE_COLLECTING: {{"field_id": "<имя поля>", "field_value": "<принятое значение>"}} — если принимаешь ответ; или {{}} — если уточняешь
- SHOW_INFO: {{"info_type": "projects|artifacts|miniservices|help"}}
- ARTIFACT_PDF: {{"artifact_id": "..."}}
- ARTIFACT_SHEETS: {{"artifact_id": "..."}}
- CANCEL_RUN: {{}}
- Остальные: {{}}

ПРИМЕЧАНИЕ: Сбор данных для минисервисов (slot-filling) теперь выполняется специализированными агентами.
Оркестратор отвечает только за маршрутизацию: определение intent, запуск минисервисов, управление проектами.
При активном запуске (active_run) сообщения пользователя направляются напрямую к агенту минисервиса.
"""


def _format_miniservices_with_deps(context: OrchestratorContext) -> str:
    """Format available miniservices with their dependencies for the system prompt."""
    lines = []
    for ms in context.available_miniservices:
        requires = DEPENDENCY_GRAPH.get(ms.id, [])
        req_str = ", ".join(requires) if requires else "ничего"
        prov_str = ", ".join(ms.provides) if ms.provides else "—"
        free_str = "Free+Paid" if ms.available_on_free else "Paid only"
        lines.append(
            f"- {ms.id} ({ms.name}): {ms.credit_cost} кр. [{free_str}] | "
            f"requires: [{req_str}] → provides: [{prov_str}]"
        )
    return "\n".join(lines)


def build_dynamic_context(context: OrchestratorContext) -> str:
    """Build the dynamic part of the orchestrator prompt.

    Includes: user info, plan, active project, active run,
    dep chain, extracted fields, conversation history.
    """
    sections: list[str] = []

    # ── Current date ───────────────────────────────────────────────
    from datetime import datetime
    today = datetime.now().strftime("%d %B %Y")
    sections.append(f"## Текущая дата\nСегодня: {today}")

    # ── User info ───────────────────────────────────────────────────
    sections.append(
        f"## Пользователь\n"
        f"Имя: {context.user_first_name}\n"
        f"План: {context.plan_type}\n"
        f"Кредиты: {context.credits_remaining}/{context.credits_monthly_limit}\n"
        f"Онбординг: {'завершён' if context.onboarding_completed else 'НЕ завершён'}"
    )

    # ── Active project ──────────────────────────────────────────────
    if context.active_project:
        proj = context.active_project
        artifacts_str = ""
        if proj.artifacts:
            art_lines = []
            for a in proj.artifacts:
                art_lines.append(f"  - {a['artifact_type']} ({a['miniservice_id']}): {a['title']}")
            artifacts_str = "\nАртефакты:\n" + "\n".join(art_lines)

        profile_str = ""
        if proj.profile:
            prof_lines = []
            for k, v in proj.profile.items():
                # Truncate long values
                v_str = str(v)
                if len(v_str) > 150:
                    v_str = v_str[:150] + "..."
                prof_lines.append(f"  {k}: {v_str}")
            profile_str = "\nПрофиль:\n" + "\n".join(prof_lines)

        sections.append(
            f"## Активный проект\n"
            f"ID: {proj.id}\n"
            f"Название: {proj.name}"
            f"{profile_str}"
            f"{artifacts_str}"
        )
    else:
        sections.append("## Активный проект\nНет активного проекта.")

    # ── All projects (brief) ────────────────────────────────────────
    if context.all_projects:
        proj_lines = []
        for p in context.all_projects:
            proj_lines.append(f"  - {p.name} (ID: {p.id})")
        sections.append(
            f"## Все проекты ({len(context.all_projects)})\n" + "\n".join(proj_lines)
        )

    # ── Active run ──────────────────────────────────────────────────
    if context.active_run:
        run = context.active_run
        collected_count = len(run.collected_fields) if run.collected_fields else 0

        sections.append(
            f"## Активный запуск (агент обрабатывает сбор данных)\n"
            f"Минисервис: {run.miniservice_id}\n"
            f"Шаг: {run.step}\n"
            f"Собрано полей: {collected_count}\n"
            f"Проект: {run.project_id}"
        )
    else:
        sections.append("## Активный запуск\nНет активного запуска.")

    # ── Dependency chain ────────────────────────────────────────────
    if context.active_dep_chain:
        dc = context.active_dep_chain
        chain_str = " → ".join(dc.chain) + f" → {dc.target_miniservice}"
        sections.append(
            f"## Цепочка зависимостей\n"
            f"Цель: {dc.target_miniservice}\n"
            f"Цепочка: {chain_str}\n"
            f"Проект: {dc.project_id}"
        )

    # ── Extracted fields ────────────────────────────────────────────
    if context.extracted_fields:
        ef_lines = []
        for ms_id, fields in context.extracted_fields.items():
            field_strs = [f"{k}={v}" for k, v in fields.items()]
            ef_lines.append(f"  {ms_id}: {', '.join(field_strs)}")
        sections.append(
            f"## Извлечённые поля (smart extractor)\n" + "\n".join(ef_lines)
        )

    # ── Conversation history ────────────────────────────────────────
    if context.conversation_history:
        hist_lines = []
        for msg in context.conversation_history[-10:]:  # Last 10 for prompt brevity
            role = msg.get("role", "?")
            content = msg.get("content", "")
            # Truncate long messages
            if len(content) > 200:
                content = content[:200] + "..."
            hist_lines.append(f"  [{role}]: {content}")
        sections.append(
            f"## Последние сообщения\n" + "\n".join(hist_lines)
        )

    return "\n\n".join(sections)


def build_system_prompt(context: OrchestratorContext) -> str:
    """Build the complete system prompt with miniservice info filled in."""
    ms_deps = _format_miniservices_with_deps(context)
    return ORCHESTRATOR_SYSTEM_PROMPT.format(
        available_miniservices_with_deps=ms_deps
    )
