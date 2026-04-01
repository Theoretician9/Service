import json
import re

import structlog

from app.integrations.llm_gateway import llm_gateway
from app.integrations.tavily import tavily_search
from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult

logger = structlog.get_logger()

GENERATION_SYSTEM_PROMPT = """Ты — жёсткий бизнес-аналитик, не коуч. Без воды, без инфобиза, без мотивашек.
Работаешь с конкретными данными пользователя и результатами поиска.

ЗАДАЧА: Подобрать РОВНО 3 ниши, оценить каждую по 6 критериям, дать декомпозицию, числовую модель и рекомендацию.

КРИТЕРИИ ОЦЕНКИ (1-5):
- speed_to_money — как быстро можно получить первые деньги (ГЛАВНЫЙ критерий)
- profit_per_deal — сколько можно заработать с одной сделки
- entry_threshold — порог входа (1 = легко войти, 5 = сложно)
- resource_fit — насколько ресурсы пользователя подходят
- feasibility — реалистичность запуска за 1-3 месяца

Также заполни legacy-поля:
- potential (1-5) — потенциал ниши
- competition (1-5) — уровень конкуренции (1 = низкая, 5 = высокая)

total_score = speed_to_money + profit_per_deal + (6 - entry_threshold) + resource_fit + feasibility
(entry_threshold инвертируется: чем ниже порог, тем лучше)

ФОРМАТ ОТВЕТА — строго JSON без markdown-обёртки:
{
  "niches": [
    {
      "name": "Название ниши",
      "description": "Короткое описание — 1-2 предложения",
      "potential": 4,
      "competition": 3,
      "entry_threshold": 2,
      "resource_fit": 4,
      "speed_to_money": 5,
      "profit_per_deal": 3,
      "feasibility": 4,
      "total_score": 20,
      "decomposition": {
        "product": "Что конкретно продаём",
        "audience_segments": ["Сегмент 1", "Сегмент 2"],
        "channels": ["Канал продаж 1", "Канал 2"],
        "demand_hypotheses": ["Гипотеза спроса 1"],
        "risks": ["Конкретный риск 1"],
        "first_tests": ["Тест 1 — что сделать, чтобы проверить"]
      },
      "numbers": {
        "income_target": "150 000 ₽/мес",
        "estimated_profit_per_deal": "5 000 ₽",
        "deals_needed_total": "30",
        "deals_per_month": "30",
        "deals_per_week": "8",
        "assumptions": ["Допущение 1"]
      }
    }
  ],
  "recommendation": "Почему именно эта ниша лучше других — конкретно",
  "recommended_niche": "Название лучшей ниши",
  "why_not_others": ["Ниша X: причина", "Ниша Y: причина"],
  "action_plan_14_days": {
    "days_1_3": ["Конкретное действие 1", "Действие 2"],
    "days_4_7": ["Действие 3", "Действие 4"],
    "days_8_14": ["Действие 5", "Действие 6"]
  },
  "red_flags": ["Когда менять нишу — конкретный сигнал"],
  "search_data_used": true,
  "assumptions": ["Если данных поиска не хватило — какие допущения сделаны"]
}

ПРАВИЛА:
- РОВНО 3 ниши. Не больше, не меньше.
- Все цифры — реалистичные, основанные на данных поиска и здравом смысле.
- Рекомендация — одна ниша. Объясни почему она, и почему не другие.
- План на 14 дней — конкретные действия, не "исследуй рынок".
- Red flags — конкретные сигналы, когда бросить и менять нишу.
- Короткие блоки. Конкретика. Никакой воды."""

SUMMARY_SYSTEM_PROMPT = """Ты — бизнес-ассистент. Напиши краткое резюме (2-3 предложения) по результатам подбора ниш.
Упомяни рекомендованную нишу, главный аргумент в её пользу и первый шаг из плана. Пиши на русском, по делу."""


class NicheSelectionService(MiniserviceBase):
    """Выбор ниши + декомпозиция — niche analysis with Tavily search.
    LLM: claude-sonnet + Tavily.
    project_fields_written: niche_candidates, hypothesis_table, geography, budget_range, business_model
    """

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        fields = ctx.collected_fields
        total_tokens = 0
        total_searches = 0

        # Build initial prompt to understand what niches to research
        user_prompt = self._build_prompt(fields, ctx.project_profile)

        # Run Tavily searches for potential niches
        geography = fields.get("geography", "Россия")
        search_results = await self._run_searches(fields, geography, ctx.run_id)
        total_searches = len(search_results)

        # Build search context for LLM
        search_context = self._format_search_results(search_results)

        # Full user prompt with search data
        full_prompt = user_prompt
        if search_context:
            full_prompt += f"\n\n--- ДАННЫЕ ИЗ ПОИСКА ---\n{search_context}"
        else:
            full_prompt += "\n\nДанных из поиска нет — опирайся на свои знания, но отметь это в assumptions."

        # Main generation call — Claude Sonnet
        generation_response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-sonnet-4-5",
            system=GENERATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": full_prompt}],
            max_tokens=8000,
            temperature=0.3,
            run_id=ctx.run_id,
        )
        total_tokens += generation_response.input_tokens + generation_response.output_tokens

        # Parse LLM JSON response
        parsed = self._parse_response(generation_response.content)

        # Generate summary via Claude Haiku
        recommended = parsed.get("recommended_niche", "не определена")
        recommendation = parsed.get("recommendation", "")
        action_plan = parsed.get("action_plan_14_days", {})
        first_step = ""
        if action_plan.get("days_1_3"):
            first_step = action_plan["days_1_3"][0]

        summary_prompt = (
            f"Рекомендованная ниша: {recommended}\n"
            f"Аргумент: {recommendation[:300]}\n"
            f"Первый шаг: {first_step}"
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
            "niche_selection_completed",
            run_id=str(ctx.run_id),
            total_tokens=total_tokens,
            total_searches=total_searches,
            recommended_niche=recommended,
        )

        return MiniserviceResult(
            artifact_type="niche_table",
            title="Подбор ниши",
            content=parsed,
            summary=summary_response.content.strip(),
            llm_tokens_used=total_tokens,
            web_searches_used=total_searches,
        )

    def _build_prompt(self, fields: dict, project_profile: dict | None) -> str:
        parts = []

        # Project context (goal from goal_tree if available)
        if project_profile:
            profile_parts = []
            if project_profile.get("name"):
                profile_parts.append(f"Проект: {project_profile['name']}")
            if project_profile.get("goal_statement"):
                profile_parts.append(f"Цель: {project_profile['goal_statement']}")
            if project_profile.get("point_b"):
                profile_parts.append(f"Точка Б: {project_profile['point_b']}")
            if project_profile.get("goal_deadline"):
                profile_parts.append(f"Срок: {project_profile['goal_deadline']}")
            if profile_parts:
                parts.append("Контекст проекта:\n" + "\n".join(profile_parts))

        # Core fields
        parts.append(f"География: {fields.get('geography', 'не указана')}")
        parts.append(f"Стартовый капитал: {fields.get('available_capital', 'не указан')}")
        parts.append(f"Компетенции: {fields.get('competencies', 'не указаны')}")
        parts.append(f"Практический опыт (5-10 лет): {fields.get('practical_experience', 'не указан')}")

        # Optional enrichment fields
        if fields.get("environment_requests"):
            parts.append(f"Что просят друзья/знакомые: {fields['environment_requests']}")
        if fields.get("personal_interest"):
            parts.append(f"Что нравится делать: {fields['personal_interest']}")
        if fields.get("social_capital"):
            parts.append(f"Социальный капитал/связи: {fields['social_capital']}")

        # Format and channels
        fmt = fields.get("format", "не указан")
        if isinstance(fmt, list):
            fmt = ", ".join(fmt)
        parts.append(f"Формат бизнеса: {fmt}")

        channels = fields.get("channels", "не указаны")
        if isinstance(channels, list):
            channels = ", ".join(channels)
        parts.append(f"Каналы продаж: {channels}")

        # Time and priority
        parts.append(f"Доступное время: {fields.get('available_time', 'не указано')}")
        parts.append(f"Приоритет: {fields.get('priority', 'не указан')}")

        # Optional fields
        if fields.get("target_margin"):
            parts.append(f"Желаемая маржинальность: {fields['target_margin']}")
        if fields.get("operations_readiness") is not None:
            ready = "да" if fields["operations_readiness"] else "нет"
            parts.append(f"Готовность к операционке: {ready}")
        if fields.get("ai_interest") is not None:
            ai = "да" if fields["ai_interest"] else "нет"
            parts.append(f"Интерес к AI/нейросетям: {ai}")

        return "\n".join(parts)

    async def _run_searches(self, fields: dict, geography: str, run_id) -> list[dict]:
        """Run Tavily searches based on user competencies and interests. Up to 5 searches."""
        search_queries = []

        # Build search queries from user data
        competencies = fields.get("competencies", "")
        practical_exp = fields.get("practical_experience", "")
        fmt = fields.get("format", [])
        if isinstance(fmt, list):
            fmt_str = " ".join(fmt)
        else:
            fmt_str = fmt

        # Primary search: competencies + geography
        if competencies:
            search_queries.append(f"{competencies} {geography} спрос цены 2026")

        # Search based on practical experience
        if practical_exp:
            search_queries.append(f"{practical_exp} бизнес {geography} спрос цены 2026")

        # Search based on format preference
        if fmt_str and fmt_str != "Всё рассмотреть":
            search_queries.append(f"{fmt_str} {geography} тренды спрос 2026")

        # Search based on personal interest if provided
        if fields.get("personal_interest"):
            search_queries.append(f"{fields['personal_interest']} заработок {geography} 2026")

        # Search based on environment requests if provided
        if fields.get("environment_requests"):
            search_queries.append(f"{fields['environment_requests']} бизнес услуги {geography} 2026")

        # Limit to 5 searches
        search_queries = search_queries[:5]

        results = []
        for query in search_queries:
            try:
                search_result = await tavily_search.search(query, max_results=3)
                results.append({"query": query, "results": search_result})
                logger.info("tavily_search_done", query=query, results_count=len(search_result), run_id=str(run_id))
            except Exception as e:
                logger.warning("tavily_search_failed", query=query, error=str(e), run_id=str(run_id))
                results.append({"query": query, "results": []})

        return results

    def _format_search_results(self, search_results: list[dict]) -> str:
        """Format Tavily search results for LLM context."""
        if not search_results:
            return ""

        parts = []
        for item in search_results:
            query = item["query"]
            results = item["results"]
            if not results:
                continue

            parts.append(f"Запрос: {query}")
            for r in results:
                title = r.get("title", "")
                content = r.get("content", "")
                # Truncate long content
                if len(content) > 400:
                    content = content[:400] + "..."
                parts.append(f"  - {title}: {content}")
            parts.append("")

        return "\n".join(parts)

    def _parse_response(self, raw_content: str) -> dict:
        """Parse LLM response, handling possible markdown wrapping."""
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
        parsed = None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        if not parsed or not isinstance(parsed, dict):
            logger.warning("niche_selection_json_parse_failed", raw=content[:300])
            parsed = {
                "niches": [],
                "recommendation": "Не удалось сформировать рекомендацию — попробуйте ещё раз",
                "recommended_niche": "",
                "why_not_others": [],
                "action_plan_14_days": {"days_1_3": [], "days_4_7": [], "days_8_14": []},
                "red_flags": [],
                "search_data_used": False,
                "assumptions": ["Ошибка парсинга ответа LLM"],
            }

        # Ensure all required top-level fields exist
        defaults = {
            "niches": [],
            "recommendation": "",
            "recommended_niche": "",
            "why_not_others": [],
            "action_plan_14_days": {"days_1_3": [], "days_4_7": [], "days_8_14": []},
            "red_flags": [],
            "search_data_used": False,
            "assumptions": [],
        }
        for key, default_val in defaults.items():
            if key not in parsed:
                parsed[key] = default_val

        # Validate niches structure
        for niche in parsed.get("niches", []):
            niche_defaults = {
                "name": "",
                "description": "",
                "potential": 0,
                "competition": 0,
                "entry_threshold": 0,
                "resource_fit": 0,
                "speed_to_money": 0,
                "profit_per_deal": 0,
                "feasibility": 0,
                "total_score": 0,
                "decomposition": {
                    "product": "",
                    "audience_segments": [],
                    "channels": [],
                    "demand_hypotheses": [],
                    "risks": [],
                    "first_tests": [],
                },
                "numbers": {
                    "income_target": "",
                    "estimated_profit_per_deal": "",
                    "deals_needed_total": "",
                    "deals_per_month": "",
                    "deals_per_week": "",
                    "assumptions": [],
                },
            }
            for key, default_val in niche_defaults.items():
                if key not in niche:
                    niche[key] = default_val

        return parsed
