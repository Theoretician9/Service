"""Test scenarios runner — sends messages through orchestrator pipeline and collects responses."""
import asyncio
import json
import uuid
from datetime import datetime, timezone

SCENARIOS = [
    {
        "id": "s0",
        "title": "5 000 ₽ → 20 млн рублей за 1 месяц",
        "type": "critical",
        "messages": [
            "Хочу заработать 20 миллионов рублей. Сейчас получаю 5000, но думаю это реально за месяц — видел в интернете схемы.",
            "Ну просто хочу жить нормально, не считать деньги",
            "Ну хотя бы 60–70 тысяч, это было бы уже намного лучше",
        ],
    },
    {
        "id": "s1",
        "title": "Студент без денег → компания на 1 млрд за 3 месяца",
        "type": "critical",
        "messages": [
            "Я студент, денег нет совсем, опыта в бизнесе нет. Но хочу создать компанию на миллиард рублей за 3 месяца. Помоги поставить цель.",
            "Умею делать сайты. Немного. Ещё хорошо объясняю сложные вещи простыми словами.",
            "Наверное сайты. Хочу попробовать.",
        ],
    },
    {
        "id": "s2",
        "title": "Размытая цель: «хочу много денег, ну миллион»",
        "type": "warning",
        "messages": [
            "Хочу много зарабатывать. Ну там миллион наверное. Не знаю за сколько, как получится",
            "Ну зарабатывать. В месяц.",
            "Ну лет за 2-3 наверное",
            "Перепродаю. Беру у людей дёшево — продаю дороже.",
        ],
    },
    {
        "id": "s3",
        "title": "Рост ×10 за год — магазин в одиночку",
        "type": "warning",
        "messages": [
            "Есть интернет-магазин спортпита, оборот 200к в месяц, работаю один. Хочу вырасти до 2 миллионов за год. Реально?",
            "Хм, об этом не думал. Нанимать страшновато, не знаю как с людьми работать.",
            "Ладно, тогда давай 500к в месяц за год — это я один потяну?",
        ],
    },
    {
        "id": "s4",
        "title": "Менеджер → консалтинг ×4 (должен принять)",
        "type": "pass",
        "messages": [
            "Менеджер по продажам, 80к/мес, 5 лет опыта. Хочу уйти в консалтинг по продажам и зарабатывать 300к/мес через год.",
            "У меня есть портфолио — увеличил продажи в трёх компаниях на 40-60%. Хочу помогать малому бизнесу.",
            "Свобода и возможность работать на себя. Устал от корпоративной политики.",
        ],
    },
    {
        "id": "s5",
        "title": "Пекарня с нуля — бюджет 500 тыс.",
        "type": "pass",
        "messages": [
            "Работаю поваром 10 лет, зарплата 50к. Хочу открыть свою пекарню. Есть 500 тысяч накоплений. Цель — 150к чистыми в месяц через год.",
            "Планирую домашнюю пекарню — хлеб, выпечка на заказ. Потом точку на рынке.",
            "Это моя мечта с детства. Хочу кормить людей вкусным хлебом и не зависеть от начальства.",
        ],
    },
    {
        "id": "s6",
        "title": "Пользователь упорно спорит и настаивает на нереальном",
        "type": "critical",
        "messages": [
            "Хочу 50 миллионов в месяц. У меня ничего нет, но я верю в себя.",
            "Нет, я точно знаю что это реально. Я видел в тиктоке парня который сделал это за 2 недели.",
            "Мне плевать на статистику. Я особенный. Ставь мне цель 50 миллионов.",
            "Ладно... может 500 тысяч за полгода?",
        ],
    },
    {
        "id": "s7",
        "title": "Пользователь уклоняется — отвечает «да», «не знаю», «ну»",
        "type": "warning",
        "messages": [
            "Хочу бизнес",
            "Не знаю",
            "Ну",
            "Да",
            "Окей, хочу продавать товары на маркетплейсах, зарабатывать 100к в месяц за полгода",
        ],
    },
]


async def run_scenario(scenario: dict) -> list[dict]:
    """Run a single scenario through the orchestrator and collect dialog."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings
    from app.orchestrator.orchestrator import decide
    from app.orchestrator.context_builder import build_context, OrchestratorContext
    from app.miniservices.session import (
        set_dialog, get_dialog, update_dialog_field, clear_dialog,
        set_active_project, append_conversation, set_extracted_fields,
        get_extracted_fields, clear_conversation,
    )
    from app.miniservices.engine import get_next_question, all_required_collected, load_manifest
    from app.modules.users.models import User
    from app.modules.billing.models import UserPlan
    from app.modules.projects.models import Project
    from app.modules.artifacts.models import MiniserviceRun

    engine = create_async_engine(settings.database_url, pool_size=2, max_overflow=2)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create test user with unique telegram_id
    test_tg_id = 900000000 + hash(scenario["id"]) % 100000
    dialog_log = []

    async with session_factory() as session:
        # Create user
        user = User(
            telegram_id=test_tg_id,
            first_name="Тестовый",
            username=f"test_{scenario['id']}",
            onboarding_completed=True,
            onboarding_role="Предприниматель",
            onboarding_primary_goal="тест",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Create plan
        plan = UserPlan(
            user_id=user.id,
            plan_type="free",
            credits_remaining=10,
            credits_monthly_limit=10,
            credits_reset_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        session.add(plan)
        await session.commit()

        # Create project
        project = Project(
            user_id=user.id,
            name=f"Тест: {scenario['title'][:50]}",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        await set_active_project(test_tg_id, str(project.id), project.name)

        # Create miniservice run for goal_setting
        run = MiniserviceRun(
            user_id=user.id,
            project_id=project.id,
            miniservice_id="goal_setting",
            mode="standalone",
            status="collecting",
            collected_fields={},
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        # Set dialog
        await set_dialog(
            test_tg_id,
            miniservice_id="goal_setting",
            run_id=run.id,
            project_id=project.id,
            step=1,
            collected_fields={},
        )

        # Run through messages
        for msg_text in scenario["messages"]:
            dialog_log.append({"role": "user", "text": msg_text})

            # Save to conversation
            await append_conversation(test_tg_id, "user", msg_text)

            # Build context and get decision
            try:
                context = await build_context(test_tg_id, session)
                decision = await decide(context, msg_text)

                response = decision.response_text
                action = decision.action.value
                params = decision.params or {}

                # If orchestrator accepted a field, save it
                field_id = params.get("field_id", "")
                field_value = params.get("field_value", "")
                if field_id and field_value:
                    await update_dialog_field(test_tg_id, field_id, field_value)

                await append_conversation(test_tg_id, "assistant", response)

                dialog_log.append({
                    "role": "bot",
                    "text": response,
                    "action": action,
                    "field_saved": f"{field_id}={field_value}" if field_id else None,
                })

            except Exception as e:
                dialog_log.append({"role": "bot", "text": f"ERROR: {type(e).__name__}: {e}", "action": "ERROR"})

        # Check final state
        final_dialog = await get_dialog(test_tg_id)
        collected = final_dialog.get("collected_fields", {}) if final_dialog else {}
        dialog_log.append({
            "role": "system",
            "text": f"Собранные поля: {json.dumps(collected, ensure_ascii=False)}",
        })

        # Cleanup
        await clear_dialog(test_tg_id)
        await clear_conversation(test_tg_id)

    await engine.dispose()
    return dialog_log


def generate_html_report(results: dict) -> str:
    """Generate HTML report from test results."""
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Результаты тестирования сценариев</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f0f13; color: #e4e4e7; line-height: 1.6; padding: 20px;
    max-width: 900px; margin: 0 auto;
}
h1 { font-size: 24px; margin-bottom: 8px; }
.subtitle { color: #71717a; font-size: 14px; margin-bottom: 32px; }
.scenario { background: #18181b; border-radius: 16px; padding: 24px; margin-bottom: 24px; border: 1px solid #27272a; }
.scenario-header { margin-bottom: 16px; }
.scenario-title { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; margin-right: 8px; }
.badge-critical { background: rgba(239,68,68,0.15); color: #ef4444; }
.badge-warning { background: rgba(245,158,11,0.15); color: #f59e0b; }
.badge-pass { background: rgba(34,197,94,0.15); color: #22c55e; }
.msg { padding: 10px 14px; border-radius: 12px; margin-bottom: 8px; }
.msg-user { background: #1e3a5f; margin-left: 40px; }
.msg-bot { background: #1f1f23; margin-right: 40px; }
.msg-system { background: #2a1f2e; margin: 0; font-size: 12px; color: #a78bfa; }
.msg-label { font-size: 11px; font-weight: 600; margin-bottom: 4px; }
.msg-label-user { color: #38bdf8; }
.msg-label-bot { color: #a78bfa; }
.msg-action { font-size: 11px; color: #71717a; margin-top: 4px; }
.field-saved { color: #22c55e; font-size: 11px; }
</style>
</head>
<body>
<h1>Результаты тестирования сценариев</h1>
<div class="subtitle">""" + datetime.now().strftime("%Y-%m-%d %H:%M") + """ UTC | 8 сценариев</div>
"""

    for scenario_id, data in results.items():
        scenario = data["scenario"]
        dialog = data["dialog"]
        badge_class = {"critical": "badge-critical", "warning": "badge-warning", "pass": "badge-pass"}[scenario["type"]]

        html += f"""
<div class="scenario">
<div class="scenario-header">
<span class="badge {badge_class}">{scenario["type"].upper()}</span>
<span class="scenario-title">{scenario["title"]}</span>
</div>
"""
        for msg in dialog:
            role = msg["role"]
            text = msg["text"].replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

            if role == "user":
                html += f'<div class="msg msg-user"><div class="msg-label msg-label-user">Пользователь</div>{text}</div>\n'
            elif role == "bot":
                action = msg.get("action", "")
                field = msg.get("field_saved", "")
                html += f'<div class="msg msg-bot"><div class="msg-label msg-label-bot">Бот [{action}]</div>{text}'
                if field:
                    html += f'<div class="field-saved">✅ Сохранено: {field}</div>'
                html += '</div>\n'
            elif role == "system":
                html += f'<div class="msg msg-system">{text}</div>\n'

        html += "</div>\n"

    html += "</body></html>"
    return html


async def main():
    results = {}
    for i, scenario in enumerate(SCENARIOS):
        print(f"[{i+1}/{len(SCENARIOS)}] Running: {scenario['title']}...")
        try:
            dialog = await run_scenario(scenario)
            results[scenario["id"]] = {"scenario": scenario, "dialog": dialog}
            print(f"  ✅ Done, {len(dialog)} messages")
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results[scenario["id"]] = {
                "scenario": scenario,
                "dialog": [{"role": "system", "text": f"ОШИБКА: {e}"}],
            }

    html = generate_html_report(results)
    output_path = "/app/reports/test_scenarios_results.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
