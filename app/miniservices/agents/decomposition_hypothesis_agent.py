# app/miniservices/agents/decomposition_hypothesis_agent.py
"""Two-phase conversation agent for decomposition & hypothesis miniservice.

Phase 1 (decomp_collect): Collects business_role, avg_check_base, commission_rate,
    and optional fields needed to build a financial decomposition table.
Phase 2 (hypothesis_validation): Asks 3-4 compact questions about user's resources
    to filter raw hypotheses down to actionable ones.
"""
import json
import re

import structlog

from app.integrations.llm_gateway import llm_gateway
from app.integrations.tavily import tavily_search
from app.miniservices.agents.base_agent import BaseAgent, AgentResponse

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────
# PHASE 1 — Decomposition data collection
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_DECOMP = """\
Ты — финансовый аналитик. Твоя задача — собрать данные для построения \
финансовой декомпозиции (сколько и чего нужно продать, чтобы достичь цели).

Ты НЕ строишь декомпозицию сам — это сделает отдельная система. Ты только собираешь параметры.

═══════════════════════════════════════════
ПЕРСОНА И ТОН
═══════════════════════════════════════════

• Деловой, конкретный, без инфобиза и мотивашек.
• Короткие подтверждения: «Записал.» / «Понял.»
• НИКОГДА не здоровайся. Пользователь уже в диалоге.
• Задавай 1–2 вопроса за раз, не больше.

═══════════════════════════════════════════
КОНТЕКСТ ПРОЕКТА
═══════════════════════════════════════════

{project_context_block}

═══════════════════════════════════════════
ПОДСКАЗКИ ПО ЦЕНАМ ИЗ ПОИСКА
═══════════════════════════════════════════

{tavily_hints}

═══════════════════════════════════════════
УЖЕ СОБРАНО
═══════════════════════════════════════════

{collected_block}

═══════════════════════════════════════════
КАКИЕ ПОЛЯ СОБИРАЕМ
═══════════════════════════════════════════

ОБЯЗАТЕЛЬНЫЕ:
1. business_role — роль в бизнесе. Варианты:
   (1) Производитель / оказываю услугу сам
   (2) Посредник / агент / дропшиппер
   (3) Совмещаю оба варианта
   Если из контекста ясно (supplier_search → есть поставщик) — предложи вариант.

2. avg_check_base — базовый средний чек за единицу товара/услуги в {currency}.
   Используй подсказки из поиска если есть. Если пользователь не знает — предложи \
   диапазон из поиска и спроси: «Ориентируемся на X {currency}?»

УСЛОВНО-ОБЯЗАТЕЛЬНЫЕ:
3. commission_rate — процент комиссии (ТОЛЬКО если business_role = посредник/агент).
   Типичные: 10–30%. Спроси только если роль = посредник.

ОПЦИОНАЛЬНЫЕ (собирай если пользователь сам упомянет):
4. conversion_rate — конверсия из лида в продажу (по умолчанию 5%)
5. repeat_rate — доля повторных покупок (по умолчанию 0%)
6. fixed_costs — постоянные расходы в месяц

═══════════════════════════════════════════
ЛОГИКА СБОРА
═══════════════════════════════════════════

1. Начни с business_role — если из контекста ясна роль, предложи и попроси подтвердить.
2. Затем avg_check_base — покажи подсказку из поиска если есть.
3. Если роль = посредник → спроси commission_rate.
4. Когда business_role + avg_check_base собраны (+ commission_rate если посредник) → сигнал [READY_FOR_DECOMP].

ВАЛЮТА: {currency}

═══════════════════════════════════════════
ФОРМАТ ОТВЕТА — СТРОГО JSON
═══════════════════════════════════════════

Каждый ответ — ТОЛЬКО валидный JSON-объект. Никакого текста до или после.

{{
  "text": "текст ответа пользователю",
  "field_id": "business_role | avg_check_base | commission_rate | conversion_rate | repeat_rate | fixed_costs | null",
  "field_value": "принятое значение или null"
}}

Когда все обязательные поля собраны, добавь маркер [READY_FOR_DECOMP] В КОНЕЦ текста.

ПРАВИЛА:
• field_id = null → уточняешь, поле НЕ принято
• field_id заполнен → field_value обязателен
• Маркер [READY_FOR_DECOMP] — ТОЛЬКО когда business_role + avg_check_base собраны \
  (+ commission_rate если посредник)
"""

# ─────────────────────────────────────────────────────────────
# PHASE 2 — Hypothesis validation Q&A
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_VALIDATION = """\
Ты — бизнес-аналитик. Твоя задача — задать 3–4 компактных вопроса, чтобы понять \
ресурсы и возможности пользователя для фильтрации гипотез.

Ты НЕ показываешь список гипотез. Ты НЕ обсуждаешь отдельные гипотезы. \
Ты задаёшь общие вопросы о ресурсах, которые помогут системе отфильтровать неподходящие.

═══════════════════════════════════════════
КОНТЕКСТ
═══════════════════════════════════════════

Ниша: {chosen_niche}
География: {geography}
Количество сырых гипотез для фильтрации: {hypotheses_count}

═══════════════════════════════════════════
ПЕРСОНА И ТОН
═══════════════════════════════════════════

• Деловой, без воды. Не здоровайся.
• Вопросы — компактные, конкретные.
• Группируй связанные темы в один вопрос.

═══════════════════════════════════════════
КАКИЕ ВОПРОСЫ ЗАДАВАТЬ
═══════════════════════════════════════════

Задай 3–4 вопроса из этих категорий (группируй если можно):

1. СВЯЗИ И КОНТАКТЫ:
   «Есть ли знакомые в [нише/смежных сферах]? Кто из окружения мог бы стать \
   первым клиентом или партнёром?»

2. ВРЕМЯ И ДЕНЬГИ:
   «Сколько часов в неделю готов тратить? Какой бюджет на тесты в первый месяц?»

3. НАВЫКИ И ИНСТРУМЕНТЫ:
   «Есть ли опыт в продажах/маркетинге? Какие инструменты/площадки уже используешь?»

4. ОГРАНИЧЕНИЯ:
   «Есть ли жёсткие ограничения — например, нельзя работать оффлайн, нет авто, \
   не готов к холодным звонкам?»

═══════════════════════════════════════════
ЛОГИКА ДИАЛОГА
═══════════════════════════════════════════

• Задавай вопросы по одному или парами (связанные).
• После каждого ответа — коротко подтверди и задай следующий.
• Когда все 3–4 вопроса заданы и ответы получены → сигнал [READY_FOR_FINAL].
• Внутренне отслеживай: contacts_asked, resources_asked, skills_asked, constraints_asked.

═══════════════════════════════════════════
ФОРМАТ ОТВЕТА — СТРОГО JSON
═══════════════════════════════════════════

{{
  "text": "текст ответа/вопроса пользователю",
  "field_id": null,
  "field_value": null
}}

Когда все вопросы заданы и ответы получены, добавь [READY_FOR_FINAL] в текст.
Никогда НЕ показывай список гипотез пользователю.
"""


class DecompositionHypothesisAgent(BaseAgent):
    """Two-phase agent: decomposition data collection + hypothesis validation."""

    miniservice_id = "decomposition_hypothesis"
    model = "claude-haiku-4-5"
    max_tokens = 800
    temperature = 0.3

    async def handle_message(
        self,
        user_message: str,
        collected_fields: dict,
        conversation_history: list[dict],
        project_context: dict,
    ) -> AgentResponse:
        sub_phase = collected_fields.get("sub_phase", "decomp_collect")

        if sub_phase == "hypothesis_validation":
            return await self._handle_validation(
                user_message, collected_fields, conversation_history, project_context,
            )
        else:
            return await self._handle_decomp_collect(
                user_message, collected_fields, conversation_history, project_context,
            )

    # ── Phase 1: Decomposition data collection ──────────────

    async def _handle_decomp_collect(
        self,
        user_message: str,
        collected_fields: dict,
        conversation_history: list[dict],
        project_context: dict,
    ) -> AgentResponse:
        # Determine currency from geography
        geography = project_context.get("geography", "Россия")
        currency = self._currency_for_geography(geography)

        # Run Tavily search for avg check hints (best-effort)
        tavily_hints = await self._search_avg_check(project_context, currency)

        # Build project context block
        project_context_block = self._build_project_context_block(project_context)

        # Build collected fields block
        collected_block = self._build_collected_block(collected_fields)

        # Format system prompt
        system = SYSTEM_PROMPT_DECOMP.format(
            project_context_block=project_context_block,
            tavily_hints=tavily_hints or "Нет данных из поиска.",
            collected_block=collected_block or "Пока ничего не собрано.",
            currency=currency,
        )

        # Build messages
        recent_history = conversation_history[-15:] if conversation_history else []
        messages = [{"role": m["role"], "content": m["content"]} for m in recent_history]
        messages.append({"role": "user", "content": user_message})

        # Call LLM
        response = await self._call_llm(system, messages)
        if response is None:
            return AgentResponse(text="Произошла ошибка. Попробуй ещё раз или напиши /cancel.")

        return self._parse_agent_response(response.content, phase="decomp")

    # ── Phase 2: Hypothesis validation Q&A ───────────────────

    async def _handle_validation(
        self,
        user_message: str,
        collected_fields: dict,
        conversation_history: list[dict],
        project_context: dict,
    ) -> AgentResponse:
        chosen_niche = project_context.get("chosen_niche", "не указана")
        geography = project_context.get("geography", "Россия")
        hypotheses_summary = collected_fields.get("hypotheses_summary", "")

        # Count hypotheses from summary
        hypotheses_count = len(hypotheses_summary.split("\n")) if hypotheses_summary else 0

        system = SYSTEM_PROMPT_VALIDATION.format(
            chosen_niche=chosen_niche,
            geography=geography,
            hypotheses_count=hypotheses_count,
        )

        recent_history = conversation_history[-15:] if conversation_history else []
        messages = [{"role": m["role"], "content": m["content"]} for m in recent_history]
        messages.append({"role": "user", "content": user_message})

        response = await self._call_llm(system, messages)
        if response is None:
            return AgentResponse(text="Произошла ошибка. Попробуй ещё раз или напиши /cancel.")

        return self._parse_agent_response(response.content, phase="validation")

    # ── Helpers ──────────────────────────────────────────────

    async def _search_avg_check(self, project_context: dict, currency: str) -> str:
        """Search Tavily for average check hints. Best-effort, never fails."""
        chosen_niche = project_context.get("chosen_niche", "")
        geography = project_context.get("geography", "Россия")
        business_model = project_context.get("business_model", "")

        if not chosen_niche:
            return ""

        query_parts = [chosen_niche]
        if business_model:
            query_parts.append(business_model)
        query_parts.extend(["средний чек цена", geography, "2026"])
        query = " ".join(query_parts)

        try:
            results = await tavily_search.search(query, max_results=3)
            if not results:
                return ""

            hints = []
            for r in results:
                title = r.get("title", "")
                content = r.get("content", "")
                if len(content) > 300:
                    content = content[:300] + "..."
                hints.append(f"- {title}: {content}")

            return f"Поисковый запрос: {query}\n" + "\n".join(hints)
        except Exception as e:
            logger.warning("decomp_tavily_search_failed", error=str(e))
            return ""

    def _build_project_context_block(self, project_context: dict) -> str:
        """Format project context for system prompt."""
        if not project_context:
            return "Контекст проекта отсутствует."

        mapping = {
            "goal_statement": "Цель",
            "chosen_niche": "Выбранная ниша",
            "business_model": "Бизнес-модель",
            "geography": "География",
            "goal_deadline": "Срок",
            "point_a": "Точка А",
        }

        parts = []
        for key, label in mapping.items():
            val = project_context.get(key)
            if val:
                parts.append(f"{label}: {val}")

        return "\n".join(parts) if parts else "Контекст проекта отсутствует."

    def _build_collected_block(self, collected_fields: dict) -> str:
        """Format already collected fields."""
        display_fields = {
            "business_role": "Роль в бизнесе",
            "avg_check_base": "Средний чек",
            "commission_rate": "Комиссия",
            "conversion_rate": "Конверсия",
            "repeat_rate": "Повторные покупки",
            "fixed_costs": "Постоянные расходы",
        }

        parts = []
        for field_id, label in display_fields.items():
            val = collected_fields.get(field_id)
            if val is not None:
                parts.append(f"✅ {label}: {val}")

        return "\n".join(parts) if parts else ""

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

    async def _call_llm(self, system: str, messages: list[dict]):
        """Call LLM with retry on rate limit. Returns LLMResponse or None."""
        import asyncio
        import time

        max_retries = 3
        delays = [5, 15, 30]

        for attempt in range(max_retries):
            try:
                t0 = time.monotonic()
                response = await llm_gateway.complete(
                    provider="anthropic",
                    model=self.model,
                    system=system,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
                duration_ms = int((time.monotonic() - t0) * 1000)
                logger.info(
                    "decomp_agent_llm_call",
                    model=self.model,
                    tokens_in=response.input_tokens,
                    tokens_out=response.output_tokens,
                    duration_ms=duration_ms,
                    attempt=attempt + 1,
                )
                return response
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "rate_limit" in err_str) and attempt < max_retries - 1:
                    logger.warning(
                        "decomp_agent_rate_limited",
                        attempt=attempt + 1,
                        delay=delays[attempt],
                        error=err_str,
                    )
                    await asyncio.sleep(delays[attempt])
                    continue
                logger.error("decomp_agent_error", error=err_str)
                return None

        return None

    def _parse_agent_response(self, raw: str, phase: str) -> AgentResponse:
        """Parse LLM JSON response with fallback to plain text."""
        content = raw.strip()

        # Try to extract JSON from markdown code block
        json_data = None
        if "```" in content:
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
            if match:
                try:
                    json_data = json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass

        # Try to parse entire response as JSON
        if json_data is None:
            try:
                json_data = json.loads(content)
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in text
        if json_data is None:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    json_data = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Fallback: plain text response
        if json_data is None:
            ready = "[READY_FOR_DECOMP]" in content or "[READY_FOR_FINAL]" in content
            clean_text = content.replace("[READY_FOR_DECOMP]", "").replace("[READY_FOR_FINAL]", "").strip()
            return AgentResponse(
                text=clean_text,
                ready_to_process=ready,
            )

        text = json_data.get("text", "")
        field_id = json_data.get("field_id")
        field_value = json_data.get("field_value")

        # Check for ready signals in text
        ready_to_process = False
        if phase == "decomp" and "[READY_FOR_DECOMP]" in text:
            ready_to_process = True
            text = text.replace("[READY_FOR_DECOMP]", "").strip()
        elif phase == "validation" and "[READY_FOR_FINAL]" in text:
            ready_to_process = True
            text = text.replace("[READY_FOR_FINAL]", "").strip()

        # For validation phase completion, extract conversation as validation_context
        if phase == "validation" and ready_to_process:
            # Return the full validation text as field_value for downstream processing
            return AgentResponse(
                text=text,
                field_id="validation_context",
                field_value=text,
                ready_to_process=True,
            )

        return AgentResponse(
            text=text,
            field_id=field_id,
            field_value=field_value,
            ready_to_process=ready_to_process,
        )
