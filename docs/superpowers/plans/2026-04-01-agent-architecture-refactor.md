# Agent Architecture Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate orchestrator (routing) from miniservice agents (conversation handling) so each miniservice has its own LLM agent with specialized prompt, while the user only talks to the orchestrator.

**Architecture:** User ↔ Orchestrator (lightweight router) ↔ Miniservice Agent (specialized LLM). When no active_run, orchestrator handles routing/intent. When active_run exists, messages go to the miniservice's dedicated agent. Agent responses are relayed back through orchestrator to user.

**Tech Stack:** Python 3.12, FastAPI, aiogram, Claude Sonnet/Haiku via LLMGateway, Redis for agent state

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/miniservices/agents/__init__.py` | Create | Package init |
| `app/miniservices/agents/base_agent.py` | Create | BaseAgent class — conversation loop, field management, quality evaluation |
| `app/miniservices/agents/goal_setting_agent.py` | Create | Goal setting mentor agent — persona, reality filter, motivation probing |
| `app/miniservices/agents/niche_selection_agent.py` | Create | Niche selection analyst agent — data collection, search queries |
| `app/orchestrator/orchestrator.py` | Modify | Strip slot-filling logic, delegate to agents |
| `app/orchestrator/prompts.py` | Modify | Remove МЕНТОР-РЕЖИМ, keep only routing rules |
| `app/bot/handlers/message_handler.py` | Modify | Route active_run messages to agent, not orchestrator |
| `app/miniservices/session.py` | Modify | Add agent conversation state |

---

### Task 1: Create BaseAgent class

**Files:**
- Create: `app/miniservices/agents/__init__.py`
- Create: `app/miniservices/agents/base_agent.py`

- [ ] **Step 1: Create agents package**

```python
# app/miniservices/agents/__init__.py
# empty
```

- [ ] **Step 2: Implement BaseAgent**

```python
# app/miniservices/agents/base_agent.py
"""Base agent for miniservice conversations.

Each miniservice agent:
- Has its own system prompt and persona
- Evaluates answer quality for each field
- Decides when to accept, probe deeper, or move to next field
- Returns structured response with field_id/value or follow-up question
"""
import json
import structlog
from dataclasses import dataclass
from app.integrations.llm_gateway import llm_gateway
from app.miniservices.engine import load_manifest, get_next_question, all_required_collected

logger = structlog.get_logger()


@dataclass
class AgentResponse:
    """Response from miniservice agent to orchestrator."""
    text: str                      # Response text to show user
    field_id: str | None = None    # Field accepted (None = probing/clarifying)
    field_value: str | None = None # Accepted value
    all_collected: bool = False    # All required fields done
    ready_to_process: bool = False # User confirmed, launch generation


class BaseAgent:
    """Base conversation agent for miniservice slot-filling.

    Subclasses override:
    - system_prompt: str — agent's persona and rules
    - model: str — LLM model to use
    - max_tokens: int — max response tokens
    """

    system_prompt: str = ""
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 800
    temperature: float = 0.3
    miniservice_id: str = ""

    async def handle_message(
        self,
        user_message: str,
        collected_fields: dict,
        conversation_history: list[dict],
        project_context: dict,
    ) -> AgentResponse:
        """Process user message during slot-filling.

        Args:
            user_message: What user wrote
            collected_fields: Already collected {field_id: value}
            conversation_history: Recent messages [{role, content}]
            project_context: Project profile data from previous miniservices

        Returns:
            AgentResponse with text + optional field acceptance
        """
        manifest = load_manifest(self.miniservice_id)
        fields_schema = manifest.get("input_schema", {}).get("fields", [])

        # Build context for agent
        next_field = get_next_question(self.miniservice_id, collected_fields)
        all_done = all_required_collected(self.miniservice_id, collected_fields)

        # Build agent prompt with current state
        state_prompt = self._build_state_prompt(
            collected_fields, fields_schema, next_field, all_done, project_context
        )

        # Trim conversation history to last 15 messages
        recent_history = conversation_history[-15:] if conversation_history else []

        messages = []
        for msg in recent_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        # Call LLM
        try:
            response = await llm_gateway.complete(
                provider="anthropic",
                model=self.model,
                system=self.system_prompt + "\n\n" + state_prompt,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return self._parse_response(response.content, collected_fields)
        except Exception as e:
            logger.error("agent_error", agent=self.miniservice_id, error=str(e))
            return AgentResponse(
                text="Произошла ошибка. Попробуй ещё раз или напиши /cancel.",
            )

    def _build_state_prompt(
        self,
        collected: dict,
        fields_schema: list,
        next_field: dict | None,
        all_done: bool,
        project_context: dict,
    ) -> str:
        """Build dynamic state section for agent prompt."""
        from datetime import datetime
        parts = [f"Текущая дата: {datetime.now().strftime('%d %B %Y')}"]

        # Project context
        if project_context:
            ctx_items = [f"  {k}: {v}" for k, v in project_context.items() if v]
            if ctx_items:
                parts.append("Контекст проекта:\n" + "\n".join(ctx_items))

        # Collected fields
        if collected:
            coll_items = [f"  ✅ {k}: {v}" for k, v in collected.items()]
            parts.append("Уже собрано:\n" + "\n".join(coll_items))

        # Required fields with IDs
        required = [f for f in fields_schema if f.get("required")]
        missing = [f for f in required if f["id"] not in collected]

        fields_list = "\n".join(
            f"  {'✅' if f['id'] in collected else '⬜'} {f['id']} ({f.get('type','text')}): {f.get('question','')}"
            for f in required
        )
        parts.append(f"Все обязательные поля:\n{fields_list}")
        parts.append(f"Осталось заполнить: {len(missing)}")

        if all_done:
            parts.append("\n⚠️ ВСЕ ПОЛЯ СОБРАНЫ. Подведи итог и спроси подтверждение.")
        elif next_field:
            choices = next_field.get("choices", [])
            next_info = f"\nСЛЕДУЮЩЕЕ ПОЛЕ: {next_field['id']} (тип: {next_field.get('type','text')})"
            next_info += f"\nВопрос: {next_field.get('question','')}"
            if choices:
                next_info += "\nВарианты (СТРОГО из манифеста):\n" + "\n".join(
                    f"  {i+1}. {c}" for i, c in enumerate(choices)
                )
            parts.append(next_info)

        return "\n\n".join(parts)

    def _parse_response(self, raw: str, collected: dict) -> AgentResponse:
        """Parse agent LLM response into AgentResponse."""
        content = raw.strip()

        # Try to extract JSON block from response
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    text = content[:content.index("```")].strip()
                    return AgentResponse(
                        text=text or data.get("text", ""),
                        field_id=data.get("field_id"),
                        field_value=data.get("field_value"),
                        all_collected=data.get("all_collected", False),
                        ready_to_process=data.get("ready_to_process", False),
                    )
                except json.JSONDecodeError:
                    pass

        # Try to parse entire response as JSON
        try:
            data = json.loads(content)
            return AgentResponse(
                text=data.get("text", ""),
                field_id=data.get("field_id"),
                field_value=data.get("field_value"),
                all_collected=data.get("all_collected", False),
                ready_to_process=data.get("ready_to_process", False),
            )
        except json.JSONDecodeError:
            pass

        # Plain text response — agent is probing/clarifying
        return AgentResponse(text=content)
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('app/miniservices/agents/base_agent.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add app/miniservices/agents/
git commit -m "feat: add BaseAgent class for miniservice conversations"
```

---

### Task 2: Create GoalSettingAgent

**Files:**
- Create: `app/miniservices/agents/goal_setting_agent.py`

- [ ] **Step 1: Implement GoalSettingAgent**

The agent has mentor persona, reality filter rules, special handling for why_important. System prompt contains ALL the mentor rules currently in prompts.py МЕНТОР-РЕЖИМ section + reality filter.

```python
# app/miniservices/agents/goal_setting_agent.py
from app.miniservices.agents.base_agent import BaseAgent


class GoalSettingAgent(BaseAgent):
    miniservice_id = "goal_setting"
    model = "claude-sonnet-4-5"
    max_tokens = 800
    temperature = 0.3

    system_prompt = """Ты — бизнес-ментор-психолог. Твоя задача — помочь пользователю сформулировать SMART-цель через разговор.

ПЕРСОНА: Опытный ментор, дружелюбный но требовательный. Взрослый разговор на равных.

ТОН:
- ВСЕГДА сначала прими и подтверди: "Понял, записал."
- НИКОГДА: "это не то", "ты не ответил", "это не цель"
- Если ответ на другой вопрос — прими и мягко переведи к нужному
- Пример: "40к на заводе — понял, это наша точка старта. А теперь — куда хочешь прийти?"

ПРАВИЛА СБОРА ДАННЫХ:
1. Оценивай каждый ответ:
   - Конкретные факты/цифры → ПРИНЯТЬ
   - Короткий но по делу → ПРИНЯТЬ
   - Отписка/шутка → мягко УТОЧНИТЬ (до 3 раз)

2. why_important — ОСОБОЕ ПОЛЕ:
   - Нужна РЕАЛЬНАЯ мотивация
   - "Хочу денег" → "Понятно. А что изменится когда деньги будут?"
   - Не обвиняй — помогай раскрыться

3. ФИЛЬТР РЕАЛЬНОСТИ ЦЕЛИ:
   При получении point_b и goal_deadline проверь:
   - Рост >20x за <3 мес → нереально, объясни конкретно
   - Рост >100x за <12 мес → нереально
   - 0 капитала + цель >10 млн/мес за <6 мес → нереально
   - Нелегальное → "серьёзные юридические ограничения"

   При нереальной цели:
   - НЕ принимай поле (field_value пустой)
   - Назови несоответствие конкретно
   - Приведи пример для масштаба
   - Предложи 2-3 реалистичных варианта
   - Max 3 попытки, потом: "Запишем как есть, в отчёте отмечу"

4. ВАЛЮТА: если сумма без валюты — уточни (₽, ₸, BYN)

5. Когда ВСЕ ПОЛЯ собраны: подведи итог, спроси "Готов?"

ФОРМАТ ОТВЕТА — JSON:
{
  "text": "текст ответа пользователю",
  "field_id": "имя_поля или null если уточняешь",
  "field_value": "принятое значение или null",
  "all_collected": false,
  "ready_to_process": false
}

ВАЖНО: используй ТОЧНЫЕ field_id из списка полей. Не выдумывай свои."""
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('app/miniservices/agents/goal_setting_agent.py').read()); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add app/miniservices/agents/goal_setting_agent.py
git commit -m "feat: add GoalSettingAgent with mentor persona and reality filter"
```

---

### Task 3: Create NicheSelectionAgent

**Files:**
- Create: `app/miniservices/agents/niche_selection_agent.py`

- [ ] **Step 1: Implement NicheSelectionAgent**

Standard mode (not mentor). Collects data efficiently, doesn't repeat questions, uses project context.

```python
# app/miniservices/agents/niche_selection_agent.py
from app.miniservices.agents.base_agent import BaseAgent


class NicheSelectionAgent(BaseAgent):
    miniservice_id = "niche_selection"
    model = "claude-sonnet-4-5"
    max_tokens = 600
    temperature = 0.3

    system_prompt = """Ты — бизнес-аналитик. Собираешь данные для подбора ниш. Прямой, без воды.

ПРАВИЛА:
1. НЕ переспрашивай данные из контекста проекта (goal_statement, point_a, point_b)
2. Задавай вопросы по одному, кратко
3. Choice-поля — показывай ТОЛЬКО варианты из манифеста
4. Если ответ пользователя содержит данные для нескольких полей — прими все
5. Вопрос про work_history — КРИТИЧЕСКИ ВАЖЕН: "Перечисли ВСЕ работы за 10 лет"
6. ВАЛЮТА: если сумма без валюты — уточни (₽, ₸, BYN)

ТОН: дружелюбный, деловой. Короткие подтверждения: "Записал." + следующий вопрос.

Когда ВСЕ ПОЛЯ собраны: кратко подведи итог и спроси "Запускаю анализ?"

ФОРМАТ ОТВЕТА — JSON:
{
  "text": "текст ответа пользователю",
  "field_id": "имя_поля или null",
  "field_value": "принятое значение или null",
  "all_collected": false,
  "ready_to_process": false
}

ВАЖНО: используй ТОЧНЫЕ field_id из списка полей."""
```

- [ ] **Step 2: Verify syntax**

- [ ] **Step 3: Commit**

```bash
git add app/miniservices/agents/niche_selection_agent.py
git commit -m "feat: add NicheSelectionAgent for data collection"
```

---

### Task 4: Create agent registry and router

**Files:**
- Create: `app/miniservices/agents/registry.py`

- [ ] **Step 1: Implement registry**

```python
# app/miniservices/agents/registry.py
"""Registry mapping miniservice_id to its conversation agent."""
from app.miniservices.agents.base_agent import BaseAgent

_AGENTS: dict[str, type[BaseAgent]] = {}


def register_agent(miniservice_id: str, agent_class: type[BaseAgent]):
    _AGENTS[miniservice_id] = agent_class


def get_agent(miniservice_id: str) -> BaseAgent | None:
    cls = _AGENTS.get(miniservice_id)
    return cls() if cls else None


# Register all agents
from app.miniservices.agents.goal_setting_agent import GoalSettingAgent
from app.miniservices.agents.niche_selection_agent import NicheSelectionAgent

register_agent("goal_setting", GoalSettingAgent)
register_agent("niche_selection", NicheSelectionAgent)
```

- [ ] **Step 2: Verify imports**

Run: `python3 -c "from app.miniservices.agents.registry import get_agent; a = get_agent('goal_setting'); print(type(a).__name__)"`
Expected: GoalSettingAgent

- [ ] **Step 3: Commit**

```bash
git add app/miniservices/agents/registry.py
git commit -m "feat: add agent registry for miniservice routing"
```

---

### Task 5: Modify message_handler to route to agents

**Files:**
- Modify: `app/bot/handlers/message_handler.py`

- [ ] **Step 1: Add agent routing**

In `handle_message()`, after smart extraction and BEFORE orchestrator call, check for active dialog and route to agent:

```python
# After smart extraction, before orchestrator:

# ── Route to miniservice agent if active dialog ──────────────
dialog = await get_dialog(telegram_id)
if dialog and dialog.get("miniservice_id"):
    ms_id = dialog["miniservice_id"]
    collected = dialog.get("collected_fields", {})

    # Direct choice-field matching (no LLM needed)
    next_field = get_next_question(ms_id, collected)
    if next_field and next_field.get("type") in ("choice", "multi_choice", "yes_no"):
        matched = _match_choice_field(text, next_field)
        if matched is not None:
            # ... existing choice handling code ...
            return

    # Route to miniservice agent
    from app.miniservices.agents.registry import get_agent
    agent = get_agent(ms_id)
    if agent:
        # Build conversation history and project context
        history = await get_conversation(telegram_id, limit=15)
        context_data = await build_context(telegram_id, db_session)
        project_ctx = {}
        if context_data.active_project:
            project_ctx = context_data.active_project.profile or {}
            project_ctx["project_name"] = context_data.active_project.name

        # Call agent
        agent_response = await agent.handle_message(
            user_message=text,
            collected_fields=collected,
            conversation_history=history,
            project_context=project_ctx,
        )

        # Save field if accepted
        if agent_response.field_id and agent_response.field_value:
            await update_dialog_field(telegram_id, agent_response.field_id, agent_response.field_value)

        # Check if ready to process
        if agent_response.ready_to_process:
            updated = await get_dialog(telegram_id)
            run_id = updated["run_id"]
            # Sync to DB
            async with _async_session() as _s:
                await _s.execute(sa_update(MiniserviceRun).where(...).values(...))
                await _s.commit()
            run_miniservice_task.delay(run_id)
            await message.answer(PROCESSING)
        else:
            await message.answer(agent_response.text)

        await append_conversation(telegram_id, "user", text)
        if agent_response.text:
            await append_conversation(telegram_id, "assistant", agent_response.text)
        return

# ② Orchestrator handles non-active-run messages
# ... existing orchestrator code ...
```

- [ ] **Step 2: Verify syntax**

- [ ] **Step 3: Test with staging bot**

- [ ] **Step 4: Commit**

```bash
git add app/bot/handlers/message_handler.py
git commit -m "refactor: route active dialog messages to miniservice agents"
```

---

### Task 6: Simplify orchestrator prompts

**Files:**
- Modify: `app/orchestrator/prompts.py`

- [ ] **Step 1: Remove slot-filling rules from orchestrator prompt**

Remove these sections from ORCHESTRATOR_SYSTEM_PROMPT:
- МЕНТОР-РЕЖИМ (entire section)
- ФИЛЬТР РЕАЛЬНОСТИ ЦЕЛИ (entire section)
- CHOICE-ПОЛЯ rules
- "ВСЕ ПОЛЯ СОБРАНЫ" rules
- КОНТЕКСТ МЕЖДУ МИНИСЕРВИСАМИ (keep but simplify)

Keep:
- Routing rules (1-12)
- Action schema
- Miniservice info
- Date injection

The orchestrator now ONLY routes — agents handle conversation.

- [ ] **Step 2: Verify orchestrator still works for non-active-run messages**

- [ ] **Step 3: Commit**

```bash
git add app/orchestrator/prompts.py
git commit -m "refactor: strip slot-filling from orchestrator, agents handle it now"
```

---

### Task 7: Add agent conversation state to session

**Files:**
- Modify: `app/miniservices/session.py`

- [ ] **Step 1: Add agent_history functions**

The agent needs its own conversation history separate from the main orchestrator history. This keeps agent context focused.

```python
# Agent-specific conversation for slot-filling
# Key: agent_conversation:{telegram_user_id}
# Separate from main conversation:{uid} to keep contexts clean

AGENT_CONV_TTL = 24 * 3600  # 24 hours

async def get_agent_conversation(telegram_user_id: int, limit: int = 20) -> list[dict]:
    """Get agent-specific conversation history."""
    key = f"agent_conversation:{telegram_user_id}"
    raw = await redis.get(key)
    if not raw:
        return []
    messages = json.loads(raw)
    return messages[-limit:]

async def append_agent_conversation(telegram_user_id: int, role: str, content: str):
    """Append to agent conversation."""
    key = f"agent_conversation:{telegram_user_id}"
    raw = await redis.get(key)
    messages = json.loads(raw) if raw else []
    messages.append({"role": role, "content": content})
    # Keep max 30 messages
    if len(messages) > 30:
        messages = messages[-30:]
    await redis.set(key, json.dumps(messages, ensure_ascii=False), ex=AGENT_CONV_TTL)

async def clear_agent_conversation(telegram_user_id: int):
    """Clear agent conversation when miniservice completes."""
    await redis.delete(f"agent_conversation:{telegram_user_id}")
```

- [ ] **Step 2: Update worker to clear agent conversation on completion**

In `miniservice_tasks.py`, after `clear_dialog()`, add `clear_agent_conversation()`.

- [ ] **Step 3: Commit**

```bash
git add app/miniservices/session.py app/workers/miniservice_tasks.py
git commit -m "feat: add agent conversation state to Redis"
```

---

### Task 8: Integration test and deploy

- [ ] **Step 1: Rebuild and test staging**

```bash
sg docker -c "docker compose build app worker && docker compose up -d app worker"
```

- [ ] **Step 2: Test goal_setting flow**

Write /start, go through onboarding, verify agent handles conversation.

- [ ] **Step 3: Test niche_selection flow**

After goal_setting, verify niche_selection agent collects data.

- [ ] **Step 4: Sync to prod**

Copy changed files to /var/www/html/prod/, rebuild prod containers.

- [ ] **Step 5: Commit and push**

```bash
git add -A
git commit -m "feat: agent-based architecture — orchestrator routes, agents converse"
git push origin main
```
