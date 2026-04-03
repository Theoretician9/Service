# Decomposition & Hypothesis Miniservice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 7th miniservice `decomposition_hypothesis` — a two-phase miniservice that decomposes a financial goal into deal scenarios and generates 20 actionable startup hypotheses, filtering them through user dialogue.

**Architecture:** Two-phase Celery execution within the existing miniservice framework. Phase 1 generates decomposition table + raw hypotheses, stores intermediate result in Redis, returns to agent for validation questions. Phase 2 filters hypotheses using validation answers, renders HTML report. Uses `sub_phase` field in `collected_fields` to track which phase the agent is in.

**Tech Stack:** Python 3.12, aiogram 3.x, Celery, Redis, Anthropic Claude (Haiku for agent, Sonnet for generation), Tavily (web search for avg check prices), Jinja2 (HTML reports)

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `app/miniservices/manifests/decomposition_hypothesis.json` | Manifest (source of truth): fields, LLM config, dependencies, output schema |
| `app/miniservices/agents/decomposition_hypothesis_agent.py` | Two-phase agent: collects decomp fields (phase 1), validates hypotheses (phase 2) |
| `app/miniservices/implementations/decomposition_hypothesis.py` | Service class: `generate_intermediate()` for Task 1, `execute()` for Task 2 |
| `templates/reports/decomposition_hypothesis.html` | Jinja2 HTML report template |

### Modified Files
| File | What Changes |
|------|-------------|
| `app/miniservices/agents/registry.py` | Register `DecompositionHypothesisAgent` |
| `app/orchestrator/dependency_resolver.py` | Add `decomposition_hypothesis` to graph + artifact mapping |
| `app/workers/miniservice_tasks.py` | Add `run_intermediate_task` Celery task + register implementation |
| `app/workers/notification_tasks.py` | Add `_format_decomp_hypothesis_text()` + update `NEXT_STEP_MAP` |
| `app/bot/handlers/message_handler.py` | Handle `sub_phase` transitions after intermediate task completes |
| `app/miniservices/session.py` | Add `get_decomp_raw` / `set_decomp_raw` Redis helpers |
| `app/bot/messages.py` | Add decomposition_hypothesis message templates |

---

## Task 1: Manifest + Dependency Graph

**Files:**
- Create: `app/miniservices/manifests/decomposition_hypothesis.json`
- Modify: `app/orchestrator/dependency_resolver.py`

- [ ] **Step 1: Create the manifest file**

```json
{
  "id": "decomposition_hypothesis",
  "schema_version": "1.0",
  "name": "Декомпозиция и гипотезы",
  "emoji": "📊",
  "description": "Разобью цель на конкретные сделки и сформирую план первых шагов",
  "credit_cost": 2,
  "available_on_free": true,
  "mode": "standard",
  "llm_config": {
    "slot_filling_provider": "anthropic",
    "slot_filling_model": "claude-haiku-4-5",
    "generation_provider": "anthropic",
    "generation_model": "claude-sonnet-4-5"
  },
  "tools": ["tavily", "pdf_gen", "html_report"],
  "tools_require_paid": [],
  "two_phase": true,
  "dependencies": ["goal_tree", "niche_table"],
  "input_schema": {
    "fields": [
      {
        "id": "business_role",
        "label": "Роль в нише",
        "type": "choice",
        "required": true,
        "choices": [
          "Сам оказываю услугу / произвожу продукт",
          "Агент — нахожу клиентов для других, получаю комиссию",
          "Посредник — перепродаю чужой продукт с наценкой",
          "Обучение / консалтинг / наставничество",
          "Другое"
        ],
        "question": "Как ты планируешь работать в этой нише?",
        "extract_from_free_text": false
      },
      {
        "id": "avg_check_base",
        "label": "Средний чек (базовый)",
        "type": "text",
        "required": true,
        "question": "Какой примерный средний чек в этой нише?",
        "hint": "Примерная сумма одной сделки/услуги",
        "extract_from_free_text": true
      },
      {
        "id": "commission_rate",
        "label": "Агентский процент (%)",
        "type": "text",
        "required": false,
        "question": "Какой процент комиссии ты получаешь?",
        "extract_from_free_text": true
      },
      {
        "id": "own_margin_possible",
        "label": "Может добавить свою наценку",
        "type": "yes_no",
        "required": false,
        "question": "Можешь ли добавить свою наценку к продукту/услуге?",
        "extract_from_free_text": false
      },
      {
        "id": "current_monthly_income",
        "label": "Текущий доход в месяц",
        "type": "text",
        "required": false,
        "question": "Какой сейчас доход в месяц?",
        "extract_from_free_text": true
      },
      {
        "id": "max_monthly_deals",
        "label": "Максимум сделок в месяц",
        "type": "text",
        "required": false,
        "question": "Сколько максимум сделок в месяц ты можешь обрабатывать?",
        "extract_from_free_text": true
      }
    ]
  },
  "question_plan": [
    {"field_id": "business_role", "step": 1, "condition": null},
    {"field_id": "avg_check_base", "step": 2, "condition": null},
    {"field_id": "commission_rate", "step": 3, "condition": {"field": "business_role", "value": "Агент — нахожу клиентов для других, получаю комиссию"}},
    {"field_id": "own_margin_possible", "step": 4, "condition": null},
    {"field_id": "current_monthly_income", "step": 5, "condition": null},
    {"field_id": "max_monthly_deals", "step": 6, "condition": null}
  ],
  "output_schema": {
    "version": "1.0",
    "artifact_type": "decomposition_hypothesis_report",
    "fields": ["decomposition", "hypotheses", "validation_context"]
  },
  "project_fields_mapping": {
    "hypothesis_table": "hypotheses",
    "business_model": "business_role_description"
  }
}
```

- [ ] **Step 2: Update dependency_resolver.py**

Add `decomposition_hypothesis` to `DEPENDENCY_GRAPH` and `ARTIFACT_TO_MINISERVICE`:

```python
# In DEPENDENCY_GRAPH, add after niche_selection:
"decomposition_hypothesis": ["goal_tree", "niche_table"],

# In ARTIFACT_TO_MINISERVICE, add:
"decomposition_hypothesis_report": "decomposition_hypothesis",
```

- [ ] **Step 3: Verify manifest loads**

```bash
cd /var/www/html/staging && python -c "
from app.miniservices.engine import load_manifest
m = load_manifest('decomposition_hypothesis')
print(f'Loaded: {m[\"id\"]} — {m[\"name\"]}')
print(f'Fields: {[f[\"id\"] for f in m[\"input_schema\"][\"fields\"]]}')
print(f'Dependencies: {m[\"dependencies\"]}')
"
```

Expected: prints manifest info without errors.

- [ ] **Step 4: Commit**

```bash
git add app/miniservices/manifests/decomposition_hypothesis.json app/orchestrator/dependency_resolver.py
git commit -m "feat: add decomposition_hypothesis manifest and dependency graph"
```

---

## Task 2: Redis Session Helpers + Bot Messages

**Files:**
- Modify: `app/miniservices/session.py`
- Modify: `app/bot/messages.py`

- [ ] **Step 1: Add Redis helpers for intermediate decomp data**

Add to `app/miniservices/session.py`:

```python
DECOMP_RAW_TTL = 7200  # 2 hours

async def get_decomp_raw(run_id: str) -> dict | None:
    """Get intermediate decomposition + raw hypotheses from Redis."""
    key = f"decomp_raw:{run_id}"
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return None


async def set_decomp_raw(run_id: str, data: dict) -> None:
    """Store intermediate decomposition + raw hypotheses in Redis."""
    key = f"decomp_raw:{run_id}"
    await redis.set(key, json.dumps(data, ensure_ascii=False), ex=DECOMP_RAW_TTL)


async def clear_decomp_raw(run_id: str) -> None:
    """Clear intermediate decomp data."""
    key = f"decomp_raw:{run_id}"
    await redis.delete(key)


async def update_dialog_sub_phase(telegram_user_id: int, sub_phase: str) -> dict:
    """Update the sub_phase in dialog's collected_fields without incrementing step."""
    dialog = await get_dialog(telegram_user_id)
    if dialog is None:
        raise ValueError("No active dialog")
    dialog["collected_fields"]["sub_phase"] = sub_phase
    key = f"dialog:{telegram_user_id}"
    await redis.set(key, json.dumps(dialog), ex=DIALOG_TTL)
    return dialog
```

- [ ] **Step 2: Add message templates to messages.py**

Add to `app/bot/messages.py`:

```python
DECOMP_HYPOTHESIS_WELCOME = (
    "📊 <b>Декомпозиция и гипотезы</b>\n\n"
    "Разберём, сколько конкретно сделок нужно для твоей цели, "
    "и сформируем список первых шагов для старта.\n\n"
    "Сначала пара вопросов о том, как именно ты будешь работать в нише."
)

DECOMP_PROCESSING_INTERMEDIATE = (
    "⏳ Считаю цифры и генерирую гипотезы...\n\n"
    "Обычно занимает 20-30 секунд."
)

DECOMP_VALIDATION_INTRO = (
    "Цифры посчитаны ✓ Гипотезы сформированы ✓\n\n"
    "Теперь пара вопросов — это поможет убрать неподходящие варианты "
    "и сделать список максимально полезным именно для тебя."
)

DECOMP_PROCESSING_FINAL = (
    "⏳ Формирую финальный отчёт...\n\n"
    "Подготавливаю таблицы и карту гипотез."
)
```

- [ ] **Step 3: Commit**

```bash
git add app/miniservices/session.py app/bot/messages.py
git commit -m "feat: add decomp Redis helpers and message templates"
```

---

## Task 3: Agent — DecompositionHypothesisAgent

**Files:**
- Create: `app/miniservices/agents/decomposition_hypothesis_agent.py`
- Modify: `app/miniservices/agents/registry.py`

- [ ] **Step 1: Create the two-phase agent**

Create `app/miniservices/agents/decomposition_hypothesis_agent.py`:

```python
"""Two-phase agent for decomposition & hypothesis miniservice.

Phase 1 (decomp_collect): Collects business role, avg check, margins.
  Uses Tavily to suggest avg check before asking user.
  When done, signals [READY_FOR_DECOMP].

Phase 2 (hypothesis_validation): Asks 3-4 compact questions to filter
  20 raw hypotheses. When done, signals [READY_FOR_FINAL].
"""
from app.miniservices.agents.base_agent import BaseAgent, AgentResponse
from app.integrations.tavily import tavily_search
from app.miniservices.session import get_decomp_raw

import structlog

logger = structlog.get_logger()

PHASE_DECOMP_COLLECT = "decomp_collect"
PHASE_HYPOTHESIS_VALIDATION = "hypothesis_validation"

SYSTEM_PROMPT_DECOMP = """\
Ты — деловой ассистент, помогаешь предпринимателю разобраться в цифрах его бизнеса.

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
- Цель: {goal_statement}
- Ниша: {chosen_niche}
- Бизнес-модель: {business_model}
- Регион: {geography}
- Сроки: {goal_deadline}
- Текущая ситуация: {point_a}

{tavily_hint}

УЖЕ СОБРАННЫЕ ПОЛЯ:
{collected_summary}

ТВОЯ ЗАДАЧА:
Собери недостающие поля для построения таблицы декомпозиции:
1. business_role — как именно человек будет зарабатывать (если не заполнено)
2. avg_check_base — средний чек в нише (предложи данные из поиска если есть)
3. commission_rate — % комиссии (ТОЛЬКО если business_role = агент)
4. current_monthly_income — текущий доход (если не ясно из point_a)

Обязательные: business_role + avg_check_base. Остальные желательные.

ПРАВИЛА:
- Задавай 1-2 вопроса за раз, коротко и по делу
- НЕ здоровайся
- Когда предлагаешь данные из интернета — укажи что это оценка
- Если пользователь не хочет отвечать на необязательное — пропусти
- Когда business_role + avg_check_base собраны → ответь ТОЛЬКО: [READY_FOR_DECOMP]

ВАЛЮТА: Казахстан → тенге (₸), Россия → рубли (₽).

ФОРМАТ ОТВЕТА (JSON):
{{"text": "твой вопрос или подтверждение", "field_id": "id поля или null", "field_value": "значение или null"}}
"""

SYSTEM_PROMPT_VALIDATION = """\
Ты — деловой ассистент. Только что были сгенерированы гипотезы для старта в нише.
Задай пользователю 3-4 ёмких вопроса, чтобы отфильтровать неподходящие.

КОНТЕКСТ:
- Ниша: {chosen_niche}
- Регион: {geography}
- Бюджет на гипотезу: ≤ 5% от дохода

Краткий список гипотез (только названия):
{hypotheses_summary}

ПРАВИЛА:
- Группируй похожие гипотезы в один вопрос
- Вопросы выявляют ресурсы: связи, время, деньги, помощники
- Не более 4 вопросов за всё общение
- НЕ показывай список гипотез
- Если пользователь спрашивает про гипотезы — скажи что покажешь после уточнения
- После всех ответов → ответь ТОЛЬКО: [READY_FOR_FINAL]
- НЕ здоровайся

ФОРМАТ ОТВЕТА (JSON):
{{"text": "твои вопросы", "field_id": null, "field_value": null}}
"""


class DecompositionHypothesisAgent(BaseAgent):
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
        sub_phase = collected_fields.get("sub_phase", PHASE_DECOMP_COLLECT)

        if sub_phase == PHASE_HYPOTHESIS_VALIDATION:
            return await self._handle_validation(
                user_message, collected_fields, conversation_history, project_context
            )
        else:
            return await self._handle_decomp_collect(
                user_message, collected_fields, conversation_history, project_context
            )

    async def _handle_decomp_collect(
        self,
        user_message: str,
        collected_fields: dict,
        conversation_history: list[dict],
        project_context: dict,
    ) -> AgentResponse:
        # Build Tavily hint for avg check if we have niche + geography
        tavily_hint = ""
        if (
            "avg_check_base" not in collected_fields
            and project_context.get("chosen_niche")
            and project_context.get("geography")
        ):
            tavily_hint = await self._search_avg_check(
                project_context["chosen_niche"],
                project_context.get("geography", ""),
            )

        collected_summary = self._format_collected(collected_fields)

        system = SYSTEM_PROMPT_DECOMP.format(
            goal_statement=project_context.get("goal_statement", "не указана"),
            chosen_niche=project_context.get("chosen_niche", "не указана"),
            business_model=project_context.get("business_model", "не указана"),
            geography=project_context.get("geography", "не указан"),
            goal_deadline=project_context.get("goal_deadline", "не указан"),
            point_a=project_context.get("point_a", "не указана"),
            tavily_hint=tavily_hint,
            collected_summary=collected_summary,
        )

        messages = list(conversation_history)
        messages.append({"role": "user", "content": user_message})

        from app.integrations.llm_gateway import llm_gateway
        response = await llm_gateway.complete(
            provider="anthropic",
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        content = response.content.strip()

        # Check for ready signal
        if "[READY_FOR_DECOMP]" in content:
            return AgentResponse(
                text="",
                all_collected=True,
                ready_to_process=True,
            )

        # Parse JSON response
        parsed = self._parse_json_response(content)
        return AgentResponse(
            text=parsed.get("text", content),
            field_id=parsed.get("field_id"),
            field_value=parsed.get("field_value"),
        )

    async def _handle_validation(
        self,
        user_message: str,
        collected_fields: dict,
        conversation_history: list[dict],
        project_context: dict,
    ) -> AgentResponse:
        # Get hypotheses summary from collected_fields (put there by intermediate task)
        hypotheses_summary = collected_fields.get("hypotheses_summary", "")

        system = SYSTEM_PROMPT_VALIDATION.format(
            chosen_niche=project_context.get("chosen_niche", "не указана"),
            geography=project_context.get("geography", "не указан"),
            hypotheses_summary=hypotheses_summary,
        )

        messages = list(conversation_history)
        messages.append({"role": "user", "content": user_message})

        from app.integrations.llm_gateway import llm_gateway
        response = await llm_gateway.complete(
            provider="anthropic",
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        content = response.content.strip()

        if "[READY_FOR_FINAL]" in content:
            # Save validation answers to collected_fields for final generation
            validation_qa = self._extract_validation_qa(conversation_history, user_message)
            return AgentResponse(
                text="",
                field_id="validation_context",
                field_value=validation_qa,
                all_collected=True,
                ready_to_process=True,
            )

        parsed = self._parse_json_response(content)
        return AgentResponse(
            text=parsed.get("text", content),
        )

    async def _search_avg_check(self, niche: str, geography: str) -> str:
        """Search Tavily for average check info. Returns hint string for prompt."""
        try:
            queries = [
                f"средний чек {niche} {geography} 2025",
                f"стоимость услуги {niche} {geography}",
            ]
            results = []
            for q in queries:
                res = await tavily_search.search(q, max_results=3)
                results.extend(res)

            if results:
                snippets = [r.get("content", "")[:200] for r in results[:4]]
                return (
                    "ДАННЫЕ ИЗ ИНТЕРНЕТА О СРЕДНИХ ЧЕКАХ:\n"
                    + "\n".join(f"- {s}" for s in snippets if s)
                    + "\nИспользуй эти данные чтобы ПРЕДЛОЖИТЬ пользователю диапазон среднего чека."
                )
        except Exception as e:
            logger.debug("tavily_avg_check_search_failed", error=str(e))
        return ""

    def _format_collected(self, fields: dict) -> str:
        """Format collected fields for prompt."""
        if not fields:
            return "Пока ничего не собрано."
        lines = []
        skip = {"sub_phase", "decomp_table", "hypotheses_summary", "validation_context"}
        for k, v in fields.items():
            if k not in skip:
                lines.append(f"- {k}: {v}")
        return "\n".join(lines) if lines else "Пока ничего не собрано."

    def _parse_json_response(self, content: str) -> dict:
        """Try to parse JSON from LLM response, fallback to text."""
        import json
        # Remove markdown code blocks if present
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return {"text": content, "field_id": None, "field_value": None}

    def _extract_validation_qa(self, history: list[dict], last_message: str) -> str:
        """Extract Q&A pairs from validation phase conversation."""
        qa_parts = []
        for msg in history:
            role = "Вопрос" if msg["role"] == "assistant" else "Ответ"
            qa_parts.append(f"{role}: {msg['content']}")
        qa_parts.append(f"Ответ: {last_message}")
        return "\n".join(qa_parts)
```

- [ ] **Step 2: Register agent in registry.py**

Add to `app/miniservices/agents/registry.py`:

```python
from app.miniservices.agents.decomposition_hypothesis_agent import DecompositionHypothesisAgent

register_agent("decomposition_hypothesis", DecompositionHypothesisAgent)
```

- [ ] **Step 3: Verify agent loads**

```bash
cd /var/www/html/staging && python -c "
from app.miniservices.agents.registry import get_agent
agent = get_agent('decomposition_hypothesis')
print(f'Agent: {type(agent).__name__}, model: {agent.model}')
"
```

- [ ] **Step 4: Commit**

```bash
git add app/miniservices/agents/decomposition_hypothesis_agent.py app/miniservices/agents/registry.py
git commit -m "feat: add DecompositionHypothesisAgent with two-phase support"
```

---

## Task 4: Implementation Service

**Files:**
- Create: `app/miniservices/implementations/decomposition_hypothesis.py`

- [ ] **Step 1: Create the service class**

```python
"""Decomposition & Hypothesis miniservice implementation.

Two execution modes:
- generate_intermediate(): Phase 1 — decomposition table + 20 raw hypotheses
- execute(): Phase 2 — filter hypotheses using validation context, render report
"""
import json

import structlog

from app.integrations.llm_gateway import llm_gateway
from app.integrations.tavily import tavily_search
from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult

logger = structlog.get_logger()


DECOMPOSITION_SYSTEM_PROMPT = """\
Ты — финансовый аналитик и бизнес-ментор. Создай подробную таблицу декомпозиции финансовой цели.

ЗАДАЧА:
Построй таблицу сценариев для достижения цели на основе входных данных.

СТРУКТУРА ОТВЕТА (строго JSON):
{{
  "goal_amount": <число — целевая сумма>,
  "goal_deadline_days": <число — дней на достижение>,
  "currency": "<₸ или ₽>",
  "currency_name": "<тенге или рублей>",
  "business_role_description": "<описание роли в одном предложении>",
  "scenarios": [
    {{
      "id": "conservative",
      "label": "Консервативный",
      "description": "<1 строка — суть сценария>",
      "avg_check": <число>,
      "your_income_per_deal": <число>,
      "margin_note": "<пояснение расчёта>",
      "deals_needed": <число>,
      "timeline_variants": [
        {{
          "days": <число>,
          "label": "<например '1 месяц'>",
          "deals_per_period": <число>,
          "deals_per_week": <дробное>,
          "days_between_deals": <дробное>
        }}
      ],
      "feasibility": "низкая | средняя | высокая",
      "feasibility_comment": "<почему>"
    }},
    {{
      "id": "base",
      "label": "Базовый",
      ...аналогично
    }},
    {{
      "id": "optimistic",
      "label": "Оптимистичный",
      ...только если own_margin_possible = true
    }},
    {{
      "id": "premium",
      "label": "Премиум-чек",
      ...сценарий с чеком в 1.5-2x от базового
    }}
  ],
  "recommended_scenario": "<id рекомендованного>",
  "recommended_reason": "<1-2 предложения>",
  "capacity_warning": "<null или предупреждение>",
  "key_insight": "<главный вывод 1-2 предложения>"
}}

ПРАВИЛА РАСЧЁТОВ:
- Агент: your_income_per_deal = avg_check × (commission_rate / 100)
- Посредник: your_income_per_deal = avg_check × (margin / 100)
- Прямая услуга: your_income_per_deal = avg_check
- deals_needed = ceil(goal_amount / your_income_per_deal)
- Все числа реалистичные для региона и ниши
- Сценарии отличаются по сути, не просто умножением"""


HYPOTHESES_RAW_SYSTEM_PROMPT = """\
Ты — предпринимательский наставник из {geography}. Сгенерируй 20 конкретных гипотез для старта.

КОНТЕКСТ:
- Ниша: {chosen_niche}
- Роль: {business_role}
- Регион: {geography}
- Цель: {goal_statement}
- Точка А: {point_a}
- Бизнес-модель: {business_model}

ХОРОШАЯ ГИПОТЕЗА:
- Конкретное действие на 1-2 дня
- Бесплатное или почти (до 5% от дохода)
- Создаёт контакт с клиентом или партнёром
- Не «изучи рынок», а «напиши в 10 чатов с таким оффером»

КАНАЛЫ (используй разные):
- Личные связи, тёплый круг
- Профессиональные объединения
- Telegram-чаты, WhatsApp-группы
- Коллаборации с не-конкурентами
- Онлайн-площадки (Olx, Avito, 2GIS)
- Офлайн-нетворкинг
- Контент (посты, видео, кейсы)
- Холодный аутрич
- Партнёрские программы

ОТВЕТ — строго JSON массив из 20 объектов:
[
  {{
    "id": 1,
    "title": "<5-8 слов>",
    "description": "<что делаем — 1-2 предложения>",
    "channel": "<канал>",
    "rationale": "<почему сработает — 1 предложение>",
    "estimated_hours": <число>,
    "estimated_cost": <число, 0 если бесплатно>,
    "can_delegate": true | false,
    "delegation_options": "<кому или null>",
    "geo_specific": true | false
  }},
  ...
]

РАЗНООБРАЗИЕ: мин. 5 через личные связи, 3 через онлайн, 3 через коллаборации, 2 бесплатных через ИИ."""


HYPOTHESES_FILTER_SYSTEM_PROMPT = """\
У тебя 20 сырых гипотез и ответы предпринимателя. Отфильтруй неподходящие, доработай подходящие.

КОНТЕКСТ:
- Ниша: {chosen_niche}
- Регион: {geography}
- Бюджет на гипотезу: ≤ 5% от дохода

ОТВЕТЫ ПОЛЬЗОВАТЕЛЯ:
{validation_qa}

СЫРЫЕ ГИПОТЕЗЫ:
{hypotheses_raw_json}

ФИЛЬТРАЦИЯ:
1. БЮДЖЕТ: estimated_cost слишком высокий → filtered_out
2. ВРЕМЯ: estimated_hours > 16 → filtered_out
3. РЕСУРСЫ: нужны связи/доступ которых нет → filtered_out

Если осталось ≥ 10 — оставь все активные. Если < 10 — дополни новыми.

Для каждой активной добавь:
- action_prompt: конкретный первый шаг (1 предложение, начинается с глагола)
- priority: 1-10

ОТВЕТ — строго JSON:
{{
  "hypotheses": [
    {{
      "id": <число>,
      "title": "<название>",
      "description": "<описание>",
      "channel": "<канал>",
      "rationale": "<обоснование>",
      "estimated_hours": <число>,
      "estimated_cost": <число>,
      "can_delegate": true | false,
      "delegation_options": "<кому / null>",
      "action_prompt": "<первый шаг>",
      "status": "active" | "filtered_out",
      "filter_reason": "<причина или null>",
      "priority": <1-10>,
      "geo_specific": true | false
    }}
  ],
  "summary": {{
    "total_active": <число>,
    "total_filtered": <число>,
    "total_hours_active": <сумма>,
    "total_cost_active": <сумма>,
    "free_hypotheses_count": <число>,
    "delegatable_count": <число>,
    "quick_wins": [<id гипотез на сегодня-завтра>]
  }},
  "personal_note": "<2-3 предложения персональный комментарий>"
}}"""


class DecompositionHypothesisService(MiniserviceBase):
    """Two-phase miniservice: decomposition + hypothesis generation."""

    async def generate_intermediate(self, ctx: MiniserviceContext) -> dict:
        """Phase 1: Generate decomposition table + 20 raw hypotheses.
        Called by execute_miniservice_intermediate Celery task.
        Returns dict with decomp_table and hypotheses_raw.
        """
        fields = ctx.collected_fields
        profile = ctx.project_profile or {}
        total_tokens = 0

        # --- Decomposition ---
        decomp_prompt = self._build_decomp_prompt(fields, profile)
        decomp_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            system=DECOMPOSITION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": decomp_prompt}],
            max_tokens=3000,
            temperature=0.4,
            run_id=ctx.run_id,
        )
        total_tokens += decomp_response.input_tokens + decomp_response.output_tokens
        decomp_table = self._parse_json(decomp_response.content)

        # --- Raw hypotheses ---
        hyp_system = HYPOTHESES_RAW_SYSTEM_PROMPT.format(
            geography=profile.get("geography", "Россия"),
            chosen_niche=profile.get("chosen_niche", "не указана"),
            business_role=fields.get("business_role", "не указана"),
            goal_statement=profile.get("goal_statement", "не указана"),
            point_a=profile.get("point_a", "не указана"),
            business_model=profile.get("business_model", fields.get("business_role", "")),
        )
        hyp_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            system=hyp_system,
            messages=[{"role": "user", "content": "Сгенерируй 20 гипотез."}],
            max_tokens=4000,
            temperature=0.7,
            run_id=ctx.run_id,
        )
        total_tokens += hyp_response.input_tokens + hyp_response.output_tokens
        hypotheses_raw = self._parse_json(hyp_response.content)
        if not isinstance(hypotheses_raw, list):
            hypotheses_raw = hypotheses_raw.get("hypotheses", [])

        return {
            "decomp_table": decomp_table,
            "hypotheses_raw": hypotheses_raw,
            "tokens_used": total_tokens,
        }

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        """Phase 2: Filter hypotheses + render final report.
        Called by standard execute_miniservice Celery task.
        """
        fields = ctx.collected_fields
        profile = ctx.project_profile or {}
        total_tokens = 0

        decomp_table = fields.get("decomp_table", {})
        hypotheses_raw = fields.get("hypotheses_raw", [])
        validation_context = fields.get("validation_context", "")

        # Filter and finalize hypotheses
        filter_system = HYPOTHESES_FILTER_SYSTEM_PROMPT.format(
            chosen_niche=profile.get("chosen_niche", "не указана"),
            geography=profile.get("geography", "Россия"),
            validation_qa=validation_context,
            hypotheses_raw_json=json.dumps(hypotheses_raw, ensure_ascii=False)[:6000],
        )
        filter_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            system=filter_system,
            messages=[{"role": "user", "content": "Отфильтруй и доработай гипотезы."}],
            max_tokens=5000,
            temperature=0.3,
            run_id=ctx.run_id,
        )
        total_tokens += filter_response.input_tokens + filter_response.output_tokens
        hypotheses_final = self._parse_json(filter_response.content)

        # Build final content
        content = {
            "decomposition": decomp_table,
            "hypotheses": hypotheses_final.get("hypotheses", []),
            "summary": hypotheses_final.get("summary", {}),
            "personal_note": hypotheses_final.get("personal_note", ""),
            "business_role_description": decomp_table.get("business_role_description", ""),
            "user_name": profile.get("name", ""),
            "chosen_niche": profile.get("chosen_niche", ""),
            "geography": profile.get("geography", ""),
            "goal_statement": profile.get("goal_statement", ""),
        }

        summary_parts = []
        active = hypotheses_final.get("summary", {}).get("total_active", 0)
        scenarios = len(decomp_table.get("scenarios", []))
        summary_parts.append(f"Декомпозиция: {scenarios} сценария.")
        summary_parts.append(f"Гипотезы: {active} активных.")
        if hypotheses_final.get("personal_note"):
            summary_parts.append(hypotheses_final["personal_note"][:150])

        return MiniserviceResult(
            artifact_type="decomposition_hypothesis_report",
            title="Декомпозиция и гипотезы",
            content=content,
            summary=" ".join(summary_parts),
            llm_tokens_used=total_tokens,
            web_searches_used=0,
        )

    def _build_decomp_prompt(self, fields: dict, profile: dict) -> str:
        """Build user prompt for decomposition generation."""
        parts = [
            f"Цель: {profile.get('goal_statement', 'не указана')}",
            f"Точка А: {profile.get('point_a', 'не указана')}",
            f"Срок: {profile.get('goal_deadline', 'не указан')}",
            f"Ниша: {profile.get('chosen_niche', 'не указана')}",
            f"Регион: {profile.get('geography', 'Россия')}",
            f"Роль в нише: {fields.get('business_role', 'не указана')}",
            f"Средний чек: {fields.get('avg_check_base', 'не указан')}",
        ]
        if fields.get("commission_rate"):
            parts.append(f"Комиссия: {fields['commission_rate']}%")
        if fields.get("own_margin_possible"):
            parts.append(f"Своя наценка возможна: {fields['own_margin_possible']}")
        if fields.get("current_monthly_income"):
            parts.append(f"Текущий доход: {fields['current_monthly_income']}")
        if fields.get("max_monthly_deals"):
            parts.append(f"Макс. сделок/мес: {fields['max_monthly_deals']}")
        return "\n".join(parts)

    def _parse_json(self, content: str) -> dict | list:
        """Parse JSON from LLM response."""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.error("decomp_json_parse_error", content=cleaned[:200])
            return {}
```

- [ ] **Step 2: Verify import**

```bash
cd /var/www/html/staging && python -c "
from app.miniservices.implementations.decomposition_hypothesis import DecompositionHypothesisService
print('OK:', DecompositionHypothesisService.__name__)
"
```

- [ ] **Step 3: Commit**

```bash
git add app/miniservices/implementations/decomposition_hypothesis.py
git commit -m "feat: add DecompositionHypothesisService with two-phase generation"
```

---

## Task 5: Celery Tasks — Intermediate + Final

**Files:**
- Modify: `app/workers/miniservice_tasks.py`

- [ ] **Step 1: Register implementation and add intermediate task**

In `app/workers/miniservice_tasks.py`:

1. Add `"decomposition_hypothesis"` to `_IMPLEMENTATIONS`:
```python
"decomposition_hypothesis": "app.miniservices.implementations.decomposition_hypothesis.DecompositionHypothesisService",
```

2. Add the new intermediate task function after `_execute_miniservice`:

```python
async def _execute_miniservice_intermediate(run_id: str) -> None:
    """Execute Phase 1 of a two-phase miniservice.

    Generates intermediate results (decomp table + raw hypotheses),
    stores them in Redis and collected_fields, then updates sub_phase
    so the agent can start validation dialogue.

    Does NOT change run status to completed — run stays in 'collecting'.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings as _settings

    _engine = create_async_engine(
        _settings.database_url, pool_size=2, max_overflow=2, echo=False
    )
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    run_uuid = uuid.UUID(run_id)

    async with _session_factory() as session:
        stmt = select(MiniserviceRun).where(MiniserviceRun.id == run_uuid)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            logger.error("intermediate_run_not_found", run_id=run_id)
            return

        miniservice_id = run.miniservice_id

        try:
            # Load project profile
            project_profile = None
            if run.project_id:
                proj_stmt = select(Project).where(Project.id == run.project_id)
                proj_result = await session.execute(proj_stmt)
                project = proj_result.scalar_one_or_none()
                if project:
                    project_profile = {
                        "name": project.name,
                        "goal_statement": project.goal_statement,
                        "point_a": project.point_a,
                        "point_b": project.point_b,
                        "goal_deadline": project.goal_deadline,
                        "chosen_niche": project.chosen_niche,
                        "business_model": project.business_model,
                        "geography": project.geography,
                        "budget_range": project.budget_range,
                    }

            # Get collected fields from Redis
            user_stmt = select(User).where(User.id == run.user_id)
            user_result = await session.execute(user_stmt)
            user_obj = user_result.scalar_one_or_none()

            collected = run.collected_fields or {}
            if user_obj:
                from app.miniservices.session import get_dialog
                dialog = await get_dialog(user_obj.telegram_id)
                if dialog and dialog.get("collected_fields"):
                    collected = {**collected, **dialog["collected_fields"]}

            ctx = MiniserviceContext(
                run_id=run_uuid,
                user_id=run.user_id,
                project_id=run.project_id,
                miniservice_id=miniservice_id,
                collected_fields=collected,
                project_profile=project_profile,
            )

            # Execute Phase 1
            implementation = _load_implementation(miniservice_id)
            intermediate_result = await implementation.generate_intermediate(ctx)

            # Store raw data in Redis for Phase 2
            from app.miniservices.session import set_decomp_raw
            await set_decomp_raw(run_id, intermediate_result)

            # Update collected_fields with decomp results and switch sub_phase
            collected["sub_phase"] = "hypothesis_validation"
            collected["decomp_table"] = intermediate_result["decomp_table"]
            collected["hypotheses_raw"] = intermediate_result["hypotheses_raw"]

            # Build hypotheses summary for validation agent
            hyp_titles = [
                f"{h.get('id', i+1)}. {h.get('title', '')}"
                for i, h in enumerate(intermediate_result.get("hypotheses_raw", []))
            ]
            collected["hypotheses_summary"] = "\n".join(hyp_titles)

            run.collected_fields = collected
            run.llm_tokens_used = (run.llm_tokens_used or 0) + intermediate_result.get("tokens_used", 0)
            await session.commit()

            # Update Redis dialog with new sub_phase
            if user_obj:
                from app.miniservices.session import update_dialog_sub_phase, clear_agent_conversation
                await update_dialog_sub_phase(user_obj.telegram_id, "hypothesis_validation")
                # Clear agent conversation for fresh validation phase
                await clear_agent_conversation(user_obj.telegram_id)

            logger.info(
                "intermediate_phase_completed",
                run_id=run_id,
                miniservice_id=miniservice_id,
                hypotheses_count=len(intermediate_result.get("hypotheses_raw", [])),
            )

            # Send notification to user that Phase 1 is done
            if user_obj:
                from app.workers.notification_tasks import send_intermediate_notification
                send_intermediate_notification.delay(run_id)

        except Exception as exc:
            logger.error(
                "intermediate_execution_failed",
                run_id=run_id,
                error=str(exc),
            )
            # Don't fail the run — just log. User can retry.
            raise


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def run_intermediate_task(self, run_id: str):
    """Celery task: execute Phase 1 of two-phase miniservice."""
    try:
        asyncio.run(_execute_miniservice_intermediate(run_id))
    except Exception as exc:
        logger.error("intermediate_task_error", run_id=run_id, error=str(exc))
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("intermediate_task_max_retries", run_id=run_id)
```

- [ ] **Step 2: Commit**

```bash
git add app/workers/miniservice_tasks.py
git commit -m "feat: add intermediate Celery task for two-phase miniservices"
```

---

## Task 6: Notification Support

**Files:**
- Modify: `app/workers/notification_tasks.py`

- [ ] **Step 1: Add intermediate notification and result formatter**

Add to `app/workers/notification_tasks.py`:

1. Add `_format_decomp_hypothesis_text` function:

```python
def _format_decomp_hypothesis_text(content: dict, summary: str) -> str:
    """Format decomposition_hypothesis_report artifact."""
    parts = []
    parts.append("📊 <b>Декомпозиция и гипотезы — готово!</b>\n")

    decomp = content.get("decomposition", {})
    recommended = decomp.get("recommended_scenario", "")
    key_insight = _safe_str(decomp.get("key_insight"))
    scenarios = decomp.get("scenarios", [])

    if key_insight:
        parts.append(f"💡 {key_insight}\n")

    if scenarios:
        parts.append(f"📈 <b>{len(scenarios)} сценария:</b>")
        for s in scenarios:
            label = _safe_str(s.get("label"))
            income = s.get("your_income_per_deal", "?")
            deals = s.get("deals_needed", "?")
            feasibility = _safe_str(s.get("feasibility"))
            marker = " ★" if s.get("id") == recommended else ""
            parts.append(f"  • {label}{marker}: {income} за сделку, {deals} сделок")
        parts.append("")

    hyp_summary = content.get("summary", {})
    active = hyp_summary.get("total_active", 0)
    free_count = hyp_summary.get("free_hypotheses_count", 0)
    quick_wins = hyp_summary.get("quick_wins", [])

    parts.append(f"💡 <b>Гипотезы:</b> {active} активных, {free_count} бесплатных")
    if quick_wins:
        parts.append(f"⚡ {len(quick_wins)} можно начать сегодня")

    note = _safe_str(content.get("personal_note"))
    if note:
        parts.append(f"\n📝 {note}")

    parts.append("\n📄 Полный отчёт с таблицами и картой гипотез — в файле ниже.")

    return "\n".join(parts)
```

2. Update `_format_artifact_text` to handle the new type:

```python
if artifact_type == "decomposition_hypothesis_report":
    return _format_decomp_hypothesis_text(content, summary)
```

3. Update `NEXT_STEP_MAP` — add entry for `niche_selection` to suggest decomposition next, and add entry for `decomposition_hypothesis`:

```python
# Update niche_selection entry:
"niche_selection": {
    "recommended": "decomposition_hypothesis",
    "recommended_name": "Декомпозиция и гипотезы",
    "recommended_cost": 2,
    "text": (
        "📍 Следующий шаг — декомпозиция цели и гипотезы для старта.\n"
        "Разложу цель на конкретные сделки и сформирую план первых действий.\n\n"
        "Напиши «давай» чтобы перейти к декомпозиции.\n"
        "Или выбери другой инструмент:\n"
        "• Поиск поставщиков (2 кр.)\n"
        "• Скрипты продаж (2 кр.)\n"
        "• Продающие объявления (2 кр.)\n"
        "• Поиск клиентов (3 кр., Paid)"
    ),
},

# Add decomposition_hypothesis entry:
"decomposition_hypothesis": {
    "recommended": "supplier_search",
    "recommended_name": "Поиск поставщиков",
    "recommended_cost": 2,
    "text": (
        "📍 Следующий шаг — найти поставщиков или написать скрипты продаж.\n\n"
        "Напиши «давай» или выбери:\n"
        "• Поиск поставщиков (2 кр.)\n"
        "• Скрипты продаж (2 кр.)\n"
        "• Продающие объявления (2 кр.)\n"
        "• Поиск клиентов (3 кр., Paid)"
    ),
},
```

4. Add intermediate notification function:

```python
async def _send_intermediate(run_id: str) -> None:
    """Send notification that Phase 1 is complete, validation phase starting."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings as _settings
    from app.bot.messages import DECOMP_VALIDATION_INTRO

    _engine = create_async_engine(_settings.database_url, pool_size=2, max_overflow=2)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    run_uuid = uuid.UUID(run_id)

    async with _session_factory() as session:
        stmt = select(MiniserviceRun).where(MiniserviceRun.id == run_uuid)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            return

        user_stmt = select(User).where(User.id == run.user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if not user:
            return

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(token=_settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    await bot.send_message(
        chat_id=user.telegram_id,
        text=DECOMP_VALIDATION_INTRO,
        parse_mode="HTML",
    )

    await bot.session.close()
    logger.info("intermediate_notification_sent", run_id=run_id, telegram_id=user.telegram_id)


@celery_app.task
def send_intermediate_notification(run_id: str):
    """Notify user that Phase 1 is complete and validation starts."""
    logger.info("sending_intermediate_notification", run_id=run_id)
    asyncio.run(_send_intermediate(run_id))
```

- [ ] **Step 2: Commit**

```bash
git add app/workers/notification_tasks.py
git commit -m "feat: add decomp notification formatter and intermediate notification"
```

---

## Task 7: Message Handler — Two-Phase Support

**Files:**
- Modify: `app/bot/handlers/message_handler.py`

- [ ] **Step 1: Update agent routing to handle sub_phase transitions**

In the agent routing section (around line 135-206), update the `ready_to_process` handling to detect two-phase miniservices:

Replace the block starting at `if agent_response.ready_to_process:` (lines 177-193) with:

```python
                # Check if ready to process
                if agent_response.ready_to_process:
                    updated = await get_dialog(telegram_id)
                    if updated:
                        run_id = updated["run_id"]
                        updated_collected = updated.get("collected_fields", {})

                        # Save field if agent returned one (e.g. validation_context)
                        if agent_response.field_id and agent_response.field_value:
                            updated_collected[agent_response.field_id] = agent_response.field_value

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
                            from app.bot.messages import DECOMP_PROCESSING_FINAL
                            if is_two_phase:
                                await message.answer(DECOMP_PROCESSING_FINAL)
                            else:
                                await message.answer(PROCESSING)
                            run_miniservice_task.delay(run_id)
```

- [ ] **Step 2: Commit**

```bash
git add app/bot/handlers/message_handler.py
git commit -m "feat: message handler supports two-phase miniservice routing"
```

---

## Task 8: HTML Report Template

**Files:**
- Create: `templates/reports/decomposition_hypothesis.html`

- [ ] **Step 1: Create Jinja2 HTML report template**

Create `templates/reports/decomposition_hypothesis.html` — a self-contained HTML file with inline CSS:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Декомпозиция и гипотезы</title>
    <link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@400;600;700&family=Noto+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #FAF8F4;
            --surface: #FFFFFF;
            --accent: #1A6B4A;
            --accent-light: #E8F5EE;
            --warning: #B8610A;
            --text-primary: #1C1C1C;
            --text-secondary: #6B6B6B;
            --border: #E2DDD6;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Noto Sans', sans-serif;
            background: var(--bg);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 20px;
            max-width: 800px;
            margin: 0 auto;
        }
        h1, h2, h3 { font-family: 'Unbounded', sans-serif; }
        .header {
            text-align: center;
            padding: 30px 20px;
            border-bottom: 2px solid var(--border);
            margin-bottom: 30px;
        }
        .header h1 { font-size: 1.5em; color: var(--accent); margin-bottom: 8px; }
        .header .meta { color: var(--text-secondary); font-size: 0.9em; }
        .section { margin-bottom: 30px; }
        .section h2 {
            font-size: 1.2em;
            color: var(--accent);
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border);
        }
        .insight-box {
            background: var(--accent-light);
            border-left: 4px solid var(--accent);
            padding: 15px 20px;
            margin-bottom: 20px;
            border-radius: 0 8px 8px 0;
            font-style: italic;
        }
        .scenario-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        .scenario-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 18px;
        }
        .scenario-card.recommended {
            border-color: var(--accent);
            box-shadow: 0 0 0 1px var(--accent);
        }
        .scenario-card h3 {
            font-size: 1em;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .scenario-card .star { color: var(--accent); }
        .scenario-card .stat { margin: 4px 0; font-size: 0.9em; }
        .scenario-card .stat b { color: var(--accent); }
        .scenario-card .feasibility {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: 600;
            margin-top: 8px;
        }
        .feasibility-high { background: #d4edda; color: #155724; }
        .feasibility-medium { background: #fff3cd; color: #856404; }
        .feasibility-low { background: #f8d7da; color: #721c24; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 0.9em;
        }
        th, td {
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            background: var(--accent-light);
            font-weight: 600;
            color: var(--accent);
        }
        .meta-bar {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            margin-bottom: 15px;
            font-size: 0.9em;
            color: var(--text-secondary);
        }
        .meta-bar span { display: flex; align-items: center; gap: 4px; }
        .hypothesis-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .hypothesis-card.quick-win { border-left: 4px solid var(--accent); }
        .card-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }
        .card-number {
            background: var(--accent-light);
            color: var(--accent);
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.85em;
        }
        .card-title { font-weight: 600; flex: 1; }
        .channel-badge {
            background: #f0f0f0;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            color: var(--text-secondary);
        }
        .action-prompt {
            background: var(--accent-light);
            padding: 10px 14px;
            border-radius: 6px;
            margin: 10px 0;
            font-size: 0.9em;
        }
        .action-prompt .icon { color: var(--accent); margin-right: 6px; }
        .card-meta {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            font-size: 0.85em;
            color: var(--text-secondary);
            margin-top: 8px;
        }
        .meta-free { color: var(--accent); font-weight: 600; }
        .card-rationale {
            font-size: 0.85em;
            color: var(--text-secondary);
            margin-top: 6px;
            font-style: italic;
        }
        .filtered-section { margin-top: 20px; }
        .filtered-section summary {
            cursor: pointer;
            color: var(--text-secondary);
            font-weight: 500;
        }
        .filtered-item {
            padding: 8px 12px;
            border-bottom: 1px solid var(--border);
            font-size: 0.85em;
            color: var(--text-secondary);
        }
        .footer {
            text-align: center;
            padding: 20px;
            color: var(--text-secondary);
            font-size: 0.8em;
            border-top: 1px solid var(--border);
            margin-top: 30px;
        }
        .personal-note {
            background: #FFF8E7;
            border-left: 4px solid var(--warning);
            padding: 15px 20px;
            border-radius: 0 8px 8px 0;
            margin: 15px 0;
        }
        @media (max-width: 600px) {
            body { padding: 10px; }
            .scenario-grid { grid-template-columns: 1fr; }
            .meta-bar { flex-direction: column; gap: 6px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Декомпозиция и гипотезы</h1>
        <div class="meta">
            {% if user_name %}{{ user_name }} · {% endif %}
            {% if chosen_niche %}{{ chosen_niche }} · {% endif %}
            {% if geography %}{{ geography }}{% endif %}
        </div>
    </div>

    {% if goal_statement %}
    <div class="section">
        <h2>🎯 Цель</h2>
        <div class="insight-box">{{ goal_statement }}</div>
    </div>
    {% endif %}

    {% set decomp = decomposition %}
    {% if decomp %}
    <div class="section">
        <h2>📈 Декомпозиция</h2>

        {% if decomp.key_insight %}
        <div class="insight-box">{{ decomp.key_insight }}</div>
        {% endif %}

        {% if decomp.capacity_warning %}
        <div class="personal-note">⚠️ {{ decomp.capacity_warning }}</div>
        {% endif %}

        <div class="scenario-grid">
            {% for s in decomp.scenarios %}
            <div class="scenario-card {% if s.id == decomp.recommended_scenario %}recommended{% endif %}">
                <h3>
                    {% if s.id == decomp.recommended_scenario %}<span class="star">★</span>{% endif %}
                    {{ s.label }}
                </h3>
                <div class="stat">Чек: <b>{{ s.avg_check }}</b></div>
                <div class="stat">Ваш доход: <b>{{ s.your_income_per_deal }}</b></div>
                <div class="stat">Сделок: <b>{{ s.deals_needed }}</b></div>
                {% if s.margin_note %}
                <div class="stat" style="font-size:0.8em;color:var(--text-secondary)">{{ s.margin_note }}</div>
                {% endif %}
                <span class="feasibility feasibility-{{ s.feasibility|replace('высокая','high')|replace('средняя','medium')|replace('низкая','low') }}">
                    {{ s.feasibility }}
                </span>
            </div>
            {% endfor %}
        </div>

        {% if decomp.recommended_reason %}
        <p style="font-size:0.9em;color:var(--text-secondary)">
            <b>Почему {{ decomp.recommended_scenario }}:</b> {{ decomp.recommended_reason }}
        </p>
        {% endif %}

        {% set rec_scenario = None %}
        {% for s in decomp.scenarios %}
            {% if s.id == decomp.recommended_scenario %}
                {% set rec_scenario = s %}
            {% endif %}
        {% endfor %}
        {% if rec_scenario and rec_scenario.timeline_variants %}
        <h3 style="margin:20px 0 10px;font-size:1em;">Временные горизонты ({{ rec_scenario.label }})</h3>
        <table>
            <thead>
                <tr>
                    <th>Срок</th>
                    <th>Сделок</th>
                    <th>В неделю</th>
                    <th>Между сделками</th>
                </tr>
            </thead>
            <tbody>
                {% for tv in rec_scenario.timeline_variants %}
                <tr>
                    <td>{{ tv.label }}</td>
                    <td><b>{{ tv.deals_per_period }}</b></td>
                    <td>{{ tv.deals_per_week }}</td>
                    <td>{{ tv.days_between_deals }} дн.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endif %}
    </div>
    {% endif %}

    <div class="section">
        <h2>💡 Гипотезы</h2>

        {% if summary %}
        <div class="meta-bar">
            <span>✅ {{ summary.total_active }} активных</span>
            <span>⏱ ~{{ summary.total_hours_active }} ч всего</span>
            <span>🆓 {{ summary.free_hypotheses_count }} бесплатных</span>
            <span>👥 {{ summary.delegatable_count }} делегируемых</span>
        </div>
        {% endif %}

        {% if personal_note %}
        <div class="personal-note">📝 {{ personal_note }}</div>
        {% endif %}

        {% set quick_win_ids = summary.quick_wins if summary else [] %}
        {% set active_hyps = [] %}
        {% set filtered_hyps = [] %}
        {% for h in hypotheses %}
            {% if h.status == 'active' %}
                {% set _ = active_hyps.append(h) %}
            {% else %}
                {% set _ = filtered_hyps.append(h) %}
            {% endif %}
        {% endfor %}

        {% if quick_win_ids %}
        <h3 style="color:var(--accent);margin:15px 0 10px;">⚡ Быстрые победы</h3>
        {% for h in active_hyps %}
            {% if h.id in quick_win_ids %}
            <div class="hypothesis-card quick-win">
                <div class="card-header">
                    <span class="card-number">#{{ h.id }}</span>
                    <span class="card-title">{{ h.title }}</span>
                    <span class="channel-badge">{{ h.channel }}</span>
                </div>
                <p>{{ h.description }}</p>
                {% if h.action_prompt %}
                <div class="action-prompt"><span class="icon">▶</span> {{ h.action_prompt }}</div>
                {% endif %}
                <div class="card-meta">
                    <span>⏱ {{ h.estimated_hours }} ч</span>
                    <span class="{% if h.estimated_cost == 0 %}meta-free{% endif %}">
                        {% if h.estimated_cost == 0 %}бесплатно{% else %}{{ h.estimated_cost }}{% endif %}
                    </span>
                    {% if h.can_delegate %}<span>👥 {{ h.delegation_options }}</span>{% endif %}
                </div>
                {% if h.rationale %}
                <p class="card-rationale">{{ h.rationale }}</p>
                {% endif %}
            </div>
            {% endif %}
        {% endfor %}
        {% endif %}

        <h3 style="margin:20px 0 10px;">Все активные гипотезы</h3>
        {% for h in active_hyps %}
            {% if h.id not in quick_win_ids %}
            <div class="hypothesis-card">
                <div class="card-header">
                    <span class="card-number">#{{ h.id }}</span>
                    <span class="card-title">{{ h.title }}</span>
                    <span class="channel-badge">{{ h.channel }}</span>
                </div>
                <p>{{ h.description }}</p>
                {% if h.action_prompt %}
                <div class="action-prompt"><span class="icon">▶</span> {{ h.action_prompt }}</div>
                {% endif %}
                <div class="card-meta">
                    <span>⏱ {{ h.estimated_hours }} ч</span>
                    <span class="{% if h.estimated_cost == 0 %}meta-free{% endif %}">
                        {% if h.estimated_cost == 0 %}бесплатно{% else %}{{ h.estimated_cost }}{% endif %}
                    </span>
                    {% if h.can_delegate %}<span>👥 {{ h.delegation_options }}</span>{% endif %}
                </div>
                {% if h.rationale %}
                <p class="card-rationale">{{ h.rationale }}</p>
                {% endif %}
            </div>
            {% endif %}
        {% endfor %}

        {% if filtered_hyps %}
        <div class="filtered-section">
            <details>
                <summary>Отфильтрованные ({{ filtered_hyps|length }})</summary>
                {% for h in filtered_hyps %}
                <div class="filtered-item">
                    <b>#{{ h.id }} {{ h.title }}</b> — {{ h.filter_reason }}
                </div>
                {% endfor %}
            </details>
        </div>
        {% endif %}
    </div>

    <div class="footer">
        {% if summary %}
        Суммарно: ~{{ summary.total_hours_active }} часов · {{ summary.total_cost_active }} на все гипотезы<br>
        {% endif %}
        AgentFlow · Отчёт v1.0
    </div>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add templates/reports/decomposition_hypothesis.html
git commit -m "feat: add Jinja2 HTML report template for decomposition_hypothesis"
```

---

## Task 9: Cancel Logic — Partial Refund

**Files:**
- Modify: `app/bot/handlers/message_handler.py`

- [ ] **Step 1: Update _action_cancel_run to handle partial refund for two-phase**

Replace `_action_cancel_run` function:

```python
async def _action_cancel_run(message: Message, telegram_id: int) -> None:
    """Clear dialog and confirm cancellation.
    For two-phase miniservices: partial refund if Phase 1 already completed.
    """
    dialog = await get_dialog(telegram_id)

    if dialog:
        run_id = dialog.get("run_id")
        collected = dialog.get("collected_fields", {})
        ms_id = dialog.get("miniservice_id", "")
        sub_phase = collected.get("sub_phase", "")

        # Check if two-phase and Phase 1 already done
        if sub_phase == "hypothesis_validation" and run_id:
            # Phase 1 completed — partial refund (1 credit instead of full 2)
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
```

- [ ] **Step 2: Commit**

```bash
git add app/bot/handlers/message_handler.py
git commit -m "feat: partial refund on cancel after Phase 1 of two-phase miniservice"
```

---

## Task 10: Integration Test + Deploy

**Files:**
- No new files

- [ ] **Step 1: Verify all imports work**

```bash
cd /var/www/html/staging && python -c "
from app.miniservices.engine import load_manifest
from app.miniservices.agents.registry import get_agent
from app.miniservices.implementations.decomposition_hypothesis import DecompositionHypothesisService
from app.orchestrator.dependency_resolver import DEPENDENCY_GRAPH, ARTIFACT_TO_MINISERVICE, resolve_missing
from app.miniservices.session import get_decomp_raw, set_decomp_raw, update_dialog_sub_phase
from app.workers.miniservice_tasks import run_intermediate_task

m = load_manifest('decomposition_hypothesis')
agent = get_agent('decomposition_hypothesis')
deps = resolve_missing('decomposition_hypothesis', [])

print(f'Manifest: {m[\"id\"]} — {m[\"name\"]}')
print(f'Agent: {type(agent).__name__}')
print(f'Deps to resolve (empty project): {deps}')
print(f'Deps to resolve (has goal_tree): {resolve_missing(\"decomposition_hypothesis\", [\"goal_tree\"])}')
print(f'Deps to resolve (both done): {resolve_missing(\"decomposition_hypothesis\", [\"goal_tree\", \"niche_table\"])}')
print(f'ARTIFACT_TO_MINISERVICE has decomp: {\"decomposition_hypothesis_report\" in ARTIFACT_TO_MINISERVICE}')
print('All imports OK')
"
```

Expected output: All imports succeed, dependency resolution works correctly.

- [ ] **Step 2: Rebuild and restart staging containers**

```bash
cd /var/www/html/staging && docker compose build app worker && docker compose restart app worker beat
```

- [ ] **Step 3: Verify services are running**

```bash
cd /var/www/html/staging && docker compose ps
```

Expected: All 5 services `Up`.

- [ ] **Step 4: Final commit with all changes**

```bash
git add -A && git status
git commit -m "feat: decomposition_hypothesis miniservice — complete implementation"
```

- [ ] **Step 5: Deploy to production**

```bash
rsync -av --exclude='__pycache__' --exclude='.git' --exclude='*.pyc' --exclude='.env' /var/www/html/staging/app/ /var/www/html/prod/app/
rsync -av /var/www/html/staging/templates/ /var/www/html/prod/templates/
cd /var/www/html/prod && docker compose restart app worker beat
```
