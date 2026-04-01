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
