# app/miniservices/implementations/decomposition_hypothesis.py
"""Decomposition & hypothesis miniservice implementation.

Two-stage execution:
1. generate_intermediate() — builds financial decomposition table + 20 raw hypotheses
2. execute() — filters hypotheses using validation_context, returns final artifact
"""
import json
import re

import structlog

from app.integrations.llm_gateway import llm_gateway
from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPTS
# ─────────────────────────────────────────────────────────────

DECOMPOSITION_SYSTEM_PROMPT = """\
Ты — финансовый аналитик. Строишь таблицу сценариев декомпозиции: \
сколько нужно продать товаров/услуг, чтобы достичь финансовой цели.

ВХОДНЫЕ ДАННЫЕ:
- Цель (goal_statement) — месячный доход или общая сумма
- Ниша (chosen_niche) — что именно продаём
- Средний чек (avg_check_base) — цена за единицу
- Роль (business_role) — производитель, посредник или совмещение
- Комиссия (commission_rate) — только для посредников
- Конверсия (conversion_rate) — из лида в продажу (по умолчанию 5%)
- Повторные покупки (repeat_rate) — доля повторных (по умолчанию 0%)
- Постоянные расходы (fixed_costs) — ежемесячные (по умолчанию 0)
- Срок (goal_deadline) — за какой период достичь цели

ЗАДАЧА:
Построй таблицу с 4 сценариями: conservative, base, optimistic, premium.

Для каждого сценария рассчитай:
- avg_check — средний чек (conservative = avg_check_base * 0.7, base = avg_check_base, \
  optimistic = avg_check_base * 1.3, premium = avg_check_base * 2.0)
- margin — маржа на единицу (для посредника: avg_check * commission_rate)
- deals_per_month — сколько сделок нужно в месяц
- deals_per_week — сделок в неделю
- deals_per_day — сделок в день (рабочих дней = 22)
- leads_per_month — сколько лидов нужно (deals / conversion_rate)
- monthly_revenue — выручка в месяц
- monthly_costs — расходы (fixed_costs + переменные)
- monthly_profit — чистая прибыль
- months_to_goal — месяцев до цели

ФОРМАТ ОТВЕТА — строго JSON:
{
  "scenarios": {
    "conservative": {
      "label": "Консервативный",
      "avg_check": 0,
      "margin": 0,
      "deals_per_month": 0,
      "deals_per_week": 0,
      "deals_per_day": 0.0,
      "leads_per_month": 0,
      "monthly_revenue": 0,
      "monthly_costs": 0,
      "monthly_profit": 0,
      "months_to_goal": 0
    },
    "base": { ... },
    "optimistic": { ... },
    "premium": { ... }
  },
  "key_insight": "Главный вывод из декомпозиции — 1-2 предложения",
  "bottleneck": "Главное узкое место — где будет сложнее всего",
  "recommendation": "Какой сценарий реалистичнее всего и почему"
}

ПРАВИЛА:
- Все цифры — целые числа (кроме deals_per_day, может быть дробным).
- Валюта — {currency}. Не добавляй символ валюты в числа.
- Если goal_statement содержит месячный доход — используй его как target.
- Если содержит общую сумму — раздели на количество месяцев из goal_deadline.
- Расчёты должны быть математически верными.
- Никакого текста вне JSON."""

HYPOTHESES_RAW_SYSTEM_PROMPT = """\
Ты — стратег по росту бизнеса. Генерируешь 20 конкретных, \
ДЕЙСТВЕННЫХ гипотез для достижения цели в выбранной нише.

ВХОДНЫЕ ДАННЫЕ:
- Ниша: {chosen_niche}
- Бизнес-модель: {business_model}
- География: {geography}
- Цель: {goal_statement}
- Декомпозиция (базовый сценарий): {base_scenario}
- Узкое место: {bottleneck}

ЗАДАЧА:
Сгенерируй РОВНО 20 гипотез. Каждая гипотеза — это конкретное действие, \
которое можно начать делать на этой неделе.

ТРЕБОВАНИЯ К РАЗНООБРАЗИЮ (обязательно покрыть ВСЕ категории):
- 4-5 гипотез: привлечение клиентов (маркетинг, реклама, контент)
- 3-4 гипотезы: каналы продаж (где и как продавать)
- 3-4 гипотезы: продукт/услуга (что улучшить, какой пакет, upsell)
- 2-3 гипотезы: партнёрства и коллаборации
- 2-3 гипотезы: автоматизация и масштабирование
- 2-3 гипотезы: удержание и повторные продажи

ФОРМАТ ОТВЕТА — строго JSON:
{{
  "hypotheses": [
    {{
      "id": 1,
      "title": "Краткое название гипотезы (до 10 слов)",
      "description": "Что конкретно делаем — 1-2 предложения",
      "category": "acquisition | channels | product | partnerships | automation | retention",
      "effort": "low | medium | high",
      "expected_impact": "low | medium | high",
      "time_to_test": "1-3 дня | 1 неделя | 2 недели | 1 месяц",
      "budget_required": "0 | до 5000 | 5000-20000 | 20000+"
    }}
  ]
}}

ПРАВИЛА:
- РОВНО 20 гипотез, id от 1 до 20.
- budget_required — в {currency}.
- Гипотезы должны быть КОНКРЕТНЫМИ: не «запустить рекламу», \
  а «запустить таргет ВК на аудиторию X с оффером Y».
- Каждая гипотеза — независимое действие, можно начать отдельно.
- Никакого текста вне JSON."""

HYPOTHESES_FILTER_SYSTEM_PROMPT = """\
Ты — бизнес-аналитик. Фильтруешь и приоритизируешь гипотезы на основе \
реальных ресурсов и ограничений пользователя.

ВХОДНЫЕ ДАННЫЕ:
- Сырые гипотезы: {hypotheses_json}
- Контекст валидации (ответы пользователя о ресурсах): {validation_context}
- Бюджет на тесты: определи из контекста валидации
- Доступное время: определи из контекста валидации
- Навыки/инструменты: определи из контекста валидации
- Ограничения: определи из контекста валидации

ЗАДАЧА:
1. Отфильтруй гипотезы, которые НЕ подходят по ресурсам.
2. Оставшиеся — отсортируй по приоритету (impact / effort).
3. Для топ-10 добавь action_prompt (конкретный первый шаг) и priority.
4. Остальные подходящие — в список «на потом».

ФОРМАТ ОТВЕТА — строго JSON:
{{
  "top_hypotheses": [
    {{
      "id": 1,
      "title": "Название",
      "description": "Описание",
      "category": "категория",
      "priority": "P1 | P2 | P3",
      "action_prompt": "Конкретный первый шаг — что сделать СЕГОДНЯ",
      "why_fits": "Почему подходит этому пользователю — 1 предложение",
      "expected_result": "Что получим через неделю тестирования"
    }}
  ],
  "backlog_hypotheses": [
    {{
      "id": 15,
      "title": "Название",
      "category": "категория",
      "reason_postponed": "Почему отложили — 1 предложение"
    }}
  ],
  "filtered_out": [
    {{
      "id": 18,
      "title": "Название",
      "reason": "Почему не подходит — 1 предложение"
    }}
  ],
  "execution_plan": {{
    "week_1": ["Действие 1 (гипотеза #N)", "Действие 2"],
    "week_2": ["Действие 3", "Действие 4"],
    "week_3_4": ["Действие 5", "Действие 6"]
  }},
  "summary": "Общая рекомендация — 2-3 предложения. Что делать в первую очередь и почему."
}}

ПРАВИЛА:
- top_hypotheses: 7–10 штук, отсортированы по priority (P1 первые).
- P1 — делать на этой неделе, P2 — на следующей, P3 — через 2 недели.
- action_prompt — КОНКРЕТНЫЙ первый шаг, не абстрактный.
- Не придумывай новые гипотезы — работай только с входным списком.
- execution_plan — план на 4 недели из топ-гипотез.
- Никакого текста вне JSON."""


class DecompositionHypothesisService(MiniserviceBase):
    """Decomposition table + hypothesis generation and filtering.

    Two-stage:
    1. generate_intermediate() — decomposition + 20 raw hypotheses
    2. execute() — filter hypotheses with validation_context, build final artifact
    """

    async def generate_intermediate(self, ctx: MiniserviceContext) -> dict:
        """Phase 1: Build decomposition table + generate 20 raw hypotheses.

        Called after decomp_collect phase completes.
        Returns dict with decomp_table, hypotheses_raw, tokens_used.
        """
        fields = ctx.collected_fields
        profile = ctx.project_profile or {}
        total_tokens = 0

        # Determine currency
        geography = profile.get("geography", fields.get("geography", "Россия"))
        currency = self._currency_for_geography(geography)

        # ── Step 1: Build decomposition table ──

        decomp_prompt = self._build_decomp_prompt(fields, profile, currency)

        decomp_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            system=DECOMPOSITION_SYSTEM_PROMPT.replace("{currency}", currency),
            messages=[{"role": "user", "content": decomp_prompt}],
            max_tokens=4000,
            temperature=0.2,
            run_id=ctx.run_id,
        )
        total_tokens += decomp_response.input_tokens + decomp_response.output_tokens

        decomp_table = self._parse_json_response(decomp_response.content, "decomp_table")

        # ── Step 2: Generate 20 raw hypotheses ──

        # Extract base scenario for hypothesis context
        base_scenario = ""
        scenarios = decomp_table.get("scenarios", {})
        base = scenarios.get("base", {})
        if base:
            base_scenario = (
                f"Чек: {base.get('avg_check', '?')} {currency}, "
                f"сделок/мес: {base.get('deals_per_month', '?')}, "
                f"лидов/мес: {base.get('leads_per_month', '?')}, "
                f"прибыль/мес: {base.get('monthly_profit', '?')} {currency}"
            )

        chosen_niche = profile.get("chosen_niche", fields.get("chosen_niche", "не указана"))
        business_model = profile.get("business_model", fields.get("business_model", ""))
        goal_statement = profile.get("goal_statement", fields.get("goal_statement", ""))
        bottleneck = decomp_table.get("bottleneck", "не определено")

        hyp_system = (HYPOTHESES_RAW_SYSTEM_PROMPT
            .replace("{chosen_niche}", str(chosen_niche))
            .replace("{business_model}", str(business_model))
            .replace("{geography}", str(geography))
            .replace("{goal_statement}", str(goal_statement))
            .replace("{base_scenario}", str(base_scenario))
            .replace("{bottleneck}", str(bottleneck))
            .replace("{currency}", str(currency))
        )

        hyp_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            system=hyp_system,
            messages=[{"role": "user", "content": "Сгенерируй 20 гипотез."}],
            max_tokens=8000,
            temperature=0.5,
            run_id=ctx.run_id,
        )
        total_tokens += hyp_response.input_tokens + hyp_response.output_tokens

        hypotheses_data = self._parse_json_response(hyp_response.content, "hypotheses_raw")
        hypotheses_raw = hypotheses_data.get("hypotheses", [])

        logger.info(
            "decomp_intermediate_completed",
            run_id=str(ctx.run_id),
            scenarios_count=len(scenarios),
            hypotheses_count=len(hypotheses_raw),
            tokens_used=total_tokens,
        )

        return {
            "decomp_table": decomp_table,
            "hypotheses_raw": hypotheses_raw,
            "tokens_used": total_tokens,
        }

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        """Phase 2: Filter hypotheses using validation_context, build final artifact."""
        fields = ctx.collected_fields
        profile = ctx.project_profile or {}
        total_tokens = 0

        # Get intermediate results from collected_fields
        decomp_table = fields.get("decomp_table", {})
        hypotheses_raw = fields.get("hypotheses_raw", [])
        validation_context = fields.get("validation_context", "")
        intermediate_tokens = fields.get("intermediate_tokens_used", 0)

        geography = profile.get("geography", fields.get("geography", "Россия"))
        currency = self._currency_for_geography(geography)

        # ── Filter hypotheses with validation context ──

        hypotheses_json = json.dumps(hypotheses_raw, ensure_ascii=False, indent=2)

        filter_system = (HYPOTHESES_FILTER_SYSTEM_PROMPT
            .replace("{hypotheses_json}", str(hypotheses_json))
            .replace("{validation_context}", str(validation_context))
        )

        filter_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            system=filter_system,
            messages=[{"role": "user", "content": "Отфильтруй и приоритизируй гипотезы."}],
            max_tokens=8000,
            temperature=0.3,
            run_id=ctx.run_id,
        )
        total_tokens += filter_response.input_tokens + filter_response.output_tokens

        filtered = self._parse_json_response(filter_response.content, "hypotheses_filtered")

        # ── Build final content ──

        content = {
            "decomp_table": decomp_table,
            "hypotheses_raw_count": len(hypotheses_raw),
            "hypotheses_filtered": filtered,
            "currency": currency,
            "geography": geography,
        }

        # Build summary
        top_count = len(filtered.get("top_hypotheses", []))
        backlog_count = len(filtered.get("backlog_hypotheses", []))
        filtered_out_count = len(filtered.get("filtered_out", []))
        summary_text = filtered.get("summary", "")

        base_scenario = decomp_table.get("scenarios", {}).get("base", {})
        decomp_summary = ""
        if base_scenario:
            decomp_summary = (
                f"Базовый сценарий: {base_scenario.get('deals_per_month', '?')} сделок/мес, "
                f"прибыль {base_scenario.get('monthly_profit', '?')} {currency}/мес. "
            )

        summary = (
            f"{decomp_summary}"
            f"Из 20 гипотез отобрано {top_count} приоритетных, "
            f"{backlog_count} в бэклоге, {filtered_out_count} отфильтровано. "
            f"{summary_text}"
        )

        total_tokens += intermediate_tokens

        logger.info(
            "decomp_hypothesis_completed",
            run_id=str(ctx.run_id),
            top_hypotheses=top_count,
            backlog=backlog_count,
            filtered_out=filtered_out_count,
            total_tokens=total_tokens,
        )

        return MiniserviceResult(
            artifact_type="decomposition_hypothesis_report",
            title="Декомпозиция и гипотезы",
            content=content,
            summary=summary,
            llm_tokens_used=total_tokens,
            web_searches_used=0,
        )

    # ── Helpers ──────────────────────────────────────────────

    def _build_decomp_prompt(self, fields: dict, profile: dict, currency: str) -> str:
        """Build user prompt for decomposition LLM call."""
        parts = []

        goal = profile.get("goal_statement", "")
        if goal:
            parts.append(f"Цель: {goal}")

        chosen_niche = profile.get("chosen_niche", "")
        if chosen_niche:
            parts.append(f"Ниша: {chosen_niche}")

        deadline = profile.get("goal_deadline", "")
        if deadline:
            parts.append(f"Срок: {deadline}")

        parts.append(f"Роль: {fields.get('business_role', 'не указана')}")
        parts.append(f"Средний чек: {fields.get('avg_check_base', '?')} {currency}")

        commission = fields.get("commission_rate")
        if commission:
            parts.append(f"Комиссия: {commission}%")

        conversion = fields.get("conversion_rate", "5%")
        parts.append(f"Конверсия: {conversion}")

        repeat = fields.get("repeat_rate", "0%")
        parts.append(f"Повторные покупки: {repeat}")

        fixed = fields.get("fixed_costs", "0")
        parts.append(f"Постоянные расходы: {fixed} {currency}/мес")

        return "\n".join(parts)

    def _parse_json_response(self, raw_content: str, context: str) -> dict:
        """Parse LLM JSON response with robust fallback."""
        content = raw_content.strip()

        # Strip markdown code block if present
        if "```" in content:
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()
            else:
                lines = content.split("\n")
                lines = [ln for ln in lines if not ln.strip().startswith("```")]
                content = "\n".join(lines)

        # Try to parse JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning(
            "decomp_json_parse_failed",
            context=context,
            raw_preview=content[:300],
        )

        # Return minimal fallback depending on context
        if context == "decomp_table":
            return {
                "scenarios": {},
                "key_insight": "Ошибка парсинга — попробуйте ещё раз",
                "bottleneck": "",
                "recommendation": "",
            }
        elif context == "hypotheses_raw":
            return {"hypotheses": []}
        elif context == "hypotheses_filtered":
            return {
                "top_hypotheses": [],
                "backlog_hypotheses": [],
                "filtered_out": [],
                "execution_plan": {},
                "summary": "Ошибка фильтрации — попробуйте ещё раз",
            }
        return {}

    def _currency_for_geography(self, geography: str) -> str:
        """Return currency symbol based on geography."""
        geo_lower = geography.lower() if geography else ""
        if "казахстан" in geo_lower:
            return "₸"
        elif "беларусь" in geo_lower:
            return "BYN"
        elif "узбекистан" in geo_lower:
            return "сум"
        elif "кыргызстан" in geo_lower or "киргиз" in geo_lower:
            return "сом"
        else:
            return "₽"
