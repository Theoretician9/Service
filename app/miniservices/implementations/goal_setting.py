import json

import structlog

from app.integrations.llm_gateway import llm_gateway
from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult

logger = structlog.get_logger()

GENERATION_SYSTEM_PROMPT = """Ты — жёсткий бизнес-аналитик. НЕ мотиватор. Работаешь ТОЛЬКО с конкретными данными пользователя.

ПРАВИЛА:
- SMART-цель: конкретная сумма С ВАЛЮТОЙ (₽, ₸ или BYN) + конкретный способ заработка + конкретный срок. Пример: "Заработать 200 000₽ за 3 месяца на продаже саженцев сосен через Авито и местные рынки".
- ВАЛЮТА ОБЯЗАТЕЛЬНА: всегда указывай символ валюты (₽, ₸, BYN) рядом с каждой суммой в smart_goal, point_a, point_b, action_plan и success_metrics. Если валюта не указана в данных пользователя — используй ₽ как дефолт, но ВСЕГДА ставь символ.
- НЕ ПИШИ мотивационные фразы, общие слова, "преодоление инерции", "реализация потенциала". Только факты и цифры.
- Все данные берутся СТРОГО из того, что написал пользователь. Если пользователь не назвал конкретную сумму — спроси через "не указано", не придумывай.
- План действий — конкретные шаги, а не "исследовать рынок". Что именно сделать, где, как.
- Метрики — цифры: количество продаж, сумма выручки, количество клиентов.
- Риски — реальные для этого бизнеса, не абстрактные.

ВАЖНО: point_a и point_b должны быть ПЕРЕФОРМУЛИРОВАНЫ красиво и грамотно на основе слов пользователя. Не копируй дословно — улучши формулировку, сохранив смысл и конкретику.

Ответ верни СТРОГО в JSON формате (без markdown-обёртки):
{
  "smart_goal": "конкретная цель с цифрами и сроками на основе данных пользователя",
  "point_a": "красиво переформулированная текущая ситуация пользователя",
  "point_b": "красиво переформулированная желаемая ситуация пользователя",
  "real_motivation": "настоящая причина пользователя, его слова — не твоя интерпретация",
  "why_tree": ["конкретная причина 1 из слов пользователя", "причина 2", "причина 3"],
  "constraint_tree": ["конкретное ограничение — конкретное решение"],
  "action_plan": [
    {"week": "Неделя 1", "actions": ["1-2 конкретных действия"]},
    {"week": "Неделя 2", "actions": ["1-2 действия"]},
    {"week": "Неделя 3", "actions": ["1-2 действия"]},
    {"week": "Неделя 4", "actions": ["1-2 действия"]}
  ],
  "success_metrics": ["конкретная метрика с цифрой"],
  "risks": ["конкретный риск для этого бизнеса — что делать"]
}"""

SUMMARY_SYSTEM_PROMPT = """Ты — бизнес-ассистент. Напиши краткое резюме (2-3 предложения) по результатам постановки цели.
Упомяни саму SMART-цель, ключевой срок и главное действие из плана. Пиши на русском, дружелюбно."""


class GoalSettingService(MiniserviceBase):
    """Постановка целей — SMART goal tree generation.
    LLM: claude-sonnet for generation, claude-haiku for summary.
    project_fields_written: goal_statement, success_metrics, constraints, timeline
    """

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        fields = ctx.collected_fields
        total_tokens = 0

        # Build user prompt from collected fields
        user_prompt = self._build_prompt(fields, ctx.project_profile)

        # Main generation call — Claude Sonnet
        generation_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            system=GENERATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=3000,
            temperature=0.4,
            run_id=ctx.run_id,
        )
        total_tokens += generation_response.input_tokens + generation_response.output_tokens

        # Parse LLM JSON response
        parsed = self._parse_response(generation_response.content, fields)

        # Generate summary via Claude Haiku
        summary_prompt = (
            f"SMART-цель: {parsed['smart_goal']}\n"
            f"Срок: {fields.get('goal_deadline', 'не указан')}\n"
            f"План: {json.dumps(parsed['action_plan'], ensure_ascii=False)[:500]}"
        )
        summary_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-haiku-4-5",
            system=SUMMARY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=200,
            temperature=0.5,
            run_id=ctx.run_id,
        )
        total_tokens += summary_response.input_tokens + summary_response.output_tokens

        logger.info(
            "goal_setting_completed",
            run_id=str(ctx.run_id),
            total_tokens=total_tokens,
        )

        return MiniserviceResult(
            artifact_type="goal_tree",
            title="Дерево целей",
            content=parsed,
            summary=summary_response.content.strip(),
            llm_tokens_used=total_tokens,
        )

    def _build_prompt(self, fields: dict, project_profile: dict | None) -> str:
        parts = []

        if project_profile:
            profile_parts = []
            if project_profile.get("name"):
                profile_parts.append(f"Проект: {project_profile['name']}")
            if project_profile.get("chosen_niche"):
                profile_parts.append(f"Ниша: {project_profile['chosen_niche']}")
            if project_profile.get("business_model"):
                profile_parts.append(f"Бизнес-модель: {project_profile['business_model']}")
            if profile_parts:
                parts.append("Контекст проекта:\n" + "\n".join(profile_parts))

        parts.append(f"Точка А (где сейчас): {fields.get('point_a', 'не указано')}")
        parts.append(f"Точка Б (куда хочу): {fields.get('point_b', 'не указано')}")
        parts.append(f"Срок достижения: {fields.get('goal_deadline', 'не указан')}")
        parts.append(f"Почему важно: {fields.get('why_important', 'не указано')}")

        if fields.get("constraints"):
            parts.append(f"Ограничения: {fields['constraints']}")
        if fields.get("success_metric"):
            parts.append(f"Метрика успеха (от пользователя): {fields['success_metric']}")

        return "\n\n".join(parts)

    def _parse_response(self, raw_content: str, fields: dict) -> dict:
        """Parse LLM response, handling possible markdown wrapping."""
        import re
        content = raw_content.strip()

        # Strip markdown code block if present
        if "```" in content:
            # Extract content between ``` markers
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()
            else:
                lines = content.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                content = "\n".join(lines)

        # Try to find JSON object in the text
        parsed = None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON object within text
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        if not parsed or not isinstance(parsed, dict):
            logger.warning("goal_setting_json_parse_failed", raw=content[:200])
            parsed = {
                "smart_goal": "Цель не сформулирована — попробуйте ещё раз",
                "real_motivation": "",
                "why_tree": [],
                "constraint_tree": [],
                "action_plan": [],
                "success_metrics": [],
                "risks": [],
            }

        # Enrich with original user input
        auto_filled = []
        for key in ["smart_goal", "why_tree", "constraint_tree", "action_plan", "success_metrics", "risks", "real_motivation"]:
            if key not in parsed:
                parsed[key] = [] if key in ("why_tree", "constraint_tree", "success_metrics", "risks") else ""
                auto_filled.append(key)

        # Use LLM-refined versions of point_a/point_b if available,
        # otherwise fall back to user's raw input
        if "point_a" not in parsed or not parsed["point_a"]:
            parsed["point_a"] = fields.get("point_a", "")
        if "point_b" not in parsed or not parsed["point_b"]:
            parsed["point_b"] = fields.get("point_b", "")
        if "goal_deadline" not in parsed or not parsed["goal_deadline"]:
            parsed["goal_deadline"] = fields.get("goal_deadline", "")
        parsed["auto_filled_fields"] = auto_filled

        return parsed
