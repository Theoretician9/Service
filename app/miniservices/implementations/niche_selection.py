import json
import re

import structlog

from app.integrations.llm_gateway import llm_gateway
from app.integrations.tavily import tavily_search
from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult

logger = structlog.get_logger()

GENERATION_SYSTEM_PROMPT = """Ты — бизнес-аналитик. Прямой, без воды, без мотивашек. Работаешь с конкретными данными пользователя и результатами поиска.

ЗАДАЧА: На основе ВСЕХ данных пользователя (профессиональный опыт, интересы, окружение, запросы друзей/знакомых) подобрать РОВНО 10 РАЗНЫХ ниш из РАЗНЫХ сфер жизни человека.

ИСТОЧНИКИ НИШ — ниши ОБЯЗАТЕЛЬНО должны быть из разных источников:
- "experience" — из профессионального опыта (чем зарабатывал)
- "interest" — из хобби и интересов (что нравится делать)
- "social" — из социального капитала (чем занимаются друзья, родственники)
- "requests" — из запросов окружения (что просят сделать)
- "combination" — из смежных или неожиданных комбинаций нескольких источников

КРИТИЧЕСКИ ВАЖНО ПРО РАЗНООБРАЗИЕ:
- МАКСИМУМ 2 ниши из одной сферы (например IT или стройка)
- Если человек упомянул 5 разных работ — хотя бы 3 ниши должны быть из разных работ
- Ниши НЕ про одно и то же: "бот для X", "бот для Y", "бот для Z" — это НЕ разные ниши
- Примеры РАЗНЫХ ниш: одна про IT (боты), одна про стройку, одна про сельское хозяйство, одна про консалтинг, одна про торговлю
- Используй ВСЮ информацию из work_history — каждая прошлая работа может стать нишей

КРИТЕРИИ ОЦЕНКИ (1-5):
- speed_to_money — как быстро можно получить первые деньги (ГЛАВНЫЙ критерий)
- profit_per_deal — сколько можно заработать с одной сделки
- entry_threshold — порог входа (1 = легко войти, 5 = сложно)
- resource_fit — насколько ресурсы пользователя подходят
- feasibility — реалистичность запуска за 1-3 месяца
- total = speed_to_money + profit_per_deal + entry_threshold + resource_fit + feasibility (max 25)

Топ-5 ниш — полная декомпозиция, числовая модель и план тестирования на 14 дней.
Ниши 6-10 — описание, оценка и почему может сработать.

ФОРМАТ ОТВЕТА — строго JSON без markdown-обёртки:
{
  "top_niches": [
    {
      "rank": 1,
      "name": "Название ниши",
      "description": "Короткое описание — 1-2 предложения",
      "why_fits_you": "Почему подходит именно этому человеку — конкретно",
      "source": "experience|interest|social|requests|combination",
      "scores": {
        "speed_to_money": 4,
        "profit_per_deal": 3,
        "entry_threshold": 2,
        "resource_fit": 5,
        "feasibility": 4,
        "total": 18
      },
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
        "deals_per_month": "30",
        "deals_per_week": "8",
        "assumptions": ["Допущение 1"]
      },
      "test_plan_14_days": {
        "days_1_3": ["Конкретное действие 1", "Действие 2"],
        "days_4_7": ["Действие 3", "Действие 4"],
        "days_8_14": ["Действие 5", "Действие 6"]
      }
    }
  ],
  "extra_niches": [
    {
      "rank": 6,
      "name": "Название ниши",
      "description": "Короткое описание",
      "why_might_work": "Почему может сработать",
      "source": "experience|interest|social|requests|combination",
      "scores": {
        "speed_to_money": 3,
        "profit_per_deal": 4,
        "entry_threshold": 3,
        "resource_fit": 3,
        "feasibility": 3,
        "total": 16
      }
    }
  ],
  "recommendation": "Общая рекомендация — почему именно первая ниша лучше других",
  "recommended_niche": "Название лучшей ниши",
  "search_data_used": true,
  "assumptions": ["Допущение 1"]
}

ПРАВИЛА:
- РОВНО 5 top_niches (rank 1-5) и РОВНО 5 extra_niches (rank 6-10).
- Все цифры — реалистичные, основанные на данных поиска и здравом смысле.
- Рекомендация — одна ниша. Объясни почему она лучше для этого человека.
- Поле source — обязательно для каждой ниши, указывает откуда взята идея.
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
            max_tokens=16000,
            temperature=0.3,
            run_id=ctx.run_id,
        )
        total_tokens += generation_response.input_tokens + generation_response.output_tokens

        # Parse LLM JSON response
        parsed = self._parse_response(generation_response.content)

        # Generate summary via Claude Haiku
        recommended = parsed.get("recommended_niche", "не определена")
        recommendation = parsed.get("recommendation", "")
        first_step = ""
        top_niches = parsed.get("top_niches", [])
        if top_niches and top_niches[0].get("test_plan_14_days", {}).get("days_1_3"):
            first_step = top_niches[0]["test_plan_14_days"]["days_1_3"][0]

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
        work = fields.get('work_history', 'не указан')
        parts.append(f"ВСЕ РАБОТЫ И ЗАНЯТИЯ за 10 лет (КРИТИЧЕСКИ ВАЖНО — каждая работа = потенциальная ниша):\n{work}")
        parts.append(f"Что просят друзья/знакомые: {fields.get('environment_requests', 'не указано')}")
        parts.append(f"Что нравится делать: {fields.get('personal_interest', 'не указано')}")
        parts.append(f"Социальный капитал — чем занимаются люди вокруг: {fields.get('social_capital', 'не указано')}")

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

        return "\n".join(parts)

    async def _run_searches(self, fields: dict, geography: str, run_id) -> list[dict]:
        """Run Tavily searches based on user data. Up to 10 searches."""
        search_queries = []

        practical_exp = fields.get("work_history", "")
        personal_interest = fields.get("personal_interest", "")
        environment_requests = fields.get("environment_requests", "")
        social_capital = fields.get("social_capital", "")
        fmt = fields.get("format", [])
        if isinstance(fmt, list):
            fmt_str = " ".join(fmt)
        else:
            fmt_str = fmt

        # Search based on practical experience — main source
        if practical_exp:
            search_queries.append(f"{practical_exp} бизнес {geography} спрос цены 2026")
            # Extract key skills for a second query
            exp_short = practical_exp[:80]
            search_queries.append(f"{exp_short} услуги заработок {geography} 2026")

        # Search based on personal interests
        if personal_interest:
            search_queries.append(f"{personal_interest} заработок бизнес {geography} 2026")

        # Search based on environment requests
        if environment_requests:
            search_queries.append(f"{environment_requests} бизнес услуги {geography} 2026")

        # Search based on social capital
        if social_capital:
            search_queries.append(f"{social_capital} бизнес ниша {geography} 2026")

        # Search based on format preference
        if fmt_str and fmt_str != "Всё рассмотреть":
            search_queries.append(f"{fmt_str} {geography} тренды спрос 2026")

        # Combination searches
        if practical_exp and personal_interest:
            search_queries.append(
                f"{practical_exp[:50]} {personal_interest[:50]} бизнес идеи {geography} 2026"
            )

        if environment_requests and practical_exp:
            search_queries.append(
                f"{environment_requests[:50]} {practical_exp[:50]} ниша {geography} 2026"
            )

        # General trending niches for this geography
        search_queries.append(f"прибыльные ниши малый бизнес {geography} 2026 тренды")

        # Low-entry niches
        capital = fields.get("available_capital", "")
        if capital:
            search_queries.append(f"бизнес {capital} стартовый капитал {geography} 2026")

        # Limit to 10 searches
        search_queries = search_queries[:10]

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
                "top_niches": [],
                "extra_niches": [],
                "niches": [],
                "recommendation": "Не удалось сформировать рекомендацию — попробуйте ещё раз",
                "recommended_niche": "",
                "search_data_used": False,
                "assumptions": ["Ошибка парсинга ответа LLM"],
            }

        # Ensure all required top-level fields exist
        defaults = {
            "top_niches": [],
            "extra_niches": [],
            "recommendation": "",
            "recommended_niche": "",
            "search_data_used": False,
            "assumptions": [],
        }
        for key, default_val in defaults.items():
            if key not in parsed:
                parsed[key] = default_val

        # Validate top_niches structure
        for niche in parsed.get("top_niches", []):
            niche_defaults = {
                "rank": 0,
                "name": "",
                "description": "",
                "why_fits_you": "",
                "source": "combination",
                "scores": {
                    "speed_to_money": 0,
                    "profit_per_deal": 0,
                    "entry_threshold": 0,
                    "resource_fit": 0,
                    "feasibility": 0,
                    "total": 0,
                },
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
                    "deals_per_month": "",
                    "deals_per_week": "",
                    "assumptions": [],
                },
                "test_plan_14_days": {
                    "days_1_3": [],
                    "days_4_7": [],
                    "days_8_14": [],
                },
            }
            for key, default_val in niche_defaults.items():
                if key not in niche:
                    niche[key] = default_val
            # Ensure scores sub-fields
            if isinstance(niche.get("scores"), dict):
                for sk in ("speed_to_money", "profit_per_deal", "entry_threshold", "resource_fit", "feasibility", "total"):
                    if sk not in niche["scores"]:
                        niche["scores"][sk] = 0

        # Validate extra_niches structure
        for niche in parsed.get("extra_niches", []):
            niche_defaults = {
                "rank": 0,
                "name": "",
                "description": "",
                "why_might_work": "",
                "source": "combination",
                "scores": {
                    "speed_to_money": 0,
                    "profit_per_deal": 0,
                    "entry_threshold": 0,
                    "resource_fit": 0,
                    "feasibility": 0,
                    "total": 0,
                },
            }
            for key, default_val in niche_defaults.items():
                if key not in niche:
                    niche[key] = default_val
            if isinstance(niche.get("scores"), dict):
                for sk in ("speed_to_money", "profit_per_deal", "entry_threshold", "resource_fit", "feasibility", "total"):
                    if sk not in niche["scores"]:
                        niche["scores"][sk] = 0

        # Backward compatibility: map top_niches + extra_niches to legacy "niches" field
        # for project_fields_mapping (niche_candidates -> niches)
        legacy_niches = []
        for niche in parsed.get("top_niches", []):
            legacy_niche = {
                "name": niche.get("name", ""),
                "description": niche.get("description", ""),
                "potential": niche.get("scores", {}).get("total", 0),
                "competition": 3,  # default legacy value
                "entry_threshold": niche.get("scores", {}).get("entry_threshold", 0),
                "resource_fit": niche.get("scores", {}).get("resource_fit", 0),
                "speed_to_money": niche.get("scores", {}).get("speed_to_money", 0),
                "profit_per_deal": niche.get("scores", {}).get("profit_per_deal", 0),
                "feasibility": niche.get("scores", {}).get("feasibility", 0),
                "total_score": niche.get("scores", {}).get("total", 0),
                "decomposition": niche.get("decomposition", {}),
                "numbers": niche.get("numbers", {}),
            }
            legacy_niches.append(legacy_niche)
        for niche in parsed.get("extra_niches", []):
            legacy_niche = {
                "name": niche.get("name", ""),
                "description": niche.get("description", ""),
                "potential": niche.get("scores", {}).get("total", 0),
                "competition": 3,
                "entry_threshold": niche.get("scores", {}).get("entry_threshold", 0),
                "resource_fit": niche.get("scores", {}).get("resource_fit", 0),
                "speed_to_money": niche.get("scores", {}).get("speed_to_money", 0),
                "profit_per_deal": niche.get("scores", {}).get("profit_per_deal", 0),
                "feasibility": niche.get("scores", {}).get("feasibility", 0),
                "total_score": niche.get("scores", {}).get("total", 0),
            }
            legacy_niches.append(legacy_niche)
        parsed["niches"] = legacy_niches

        return parsed
