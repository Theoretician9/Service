"""Simulate Sergey going through goal_setting → niche_selection."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


# Sergey's conversation lines for each phase
ONBOARDING_MSGS = [
    "Привет! Меня зовут Сергей, 38 лет, из Екатеринбурга. Работаю менеджером по закупкам в строительной компании, зарплата 90-110к. Хочу начать своё дело — сначала выйти на +50-100 тысяч сверху к зарплате, потом уйти с работы. Есть семья, двое детей, кредит 600к. Свободного капитала максимум 150-200 тысяч.",
    "Бизнес Сергея",
]

GOAL_SETTING_MSGS = [
    # point_a
    "Ну смотри, я менеджер по закупкам в строительной компании. Получаю около 100к, но чувствую что потолок. 16 лет по найму, сначала на заводе слесарем, потом мастером, теперь вот закупки. Стабильно, но роста нет. Кредит 600к висит, платёж 25 тысяч в месяц. Жена, двое детей.",
    # point_b
    "Хочу выйти хотя бы на 150-200 тысяч в месяц суммарно. То есть +50-100к сверху к зарплате. Работать частично на себя, чтобы не зависеть только от одного источника. А через год-полтора может и уволиться, если пойдёт.",
    # goal_deadline
    "Ну давай 6 месяцев на первые деньги. Через полгода хочу уже стабильно получать дополнительный доход.",
    # why_important
    "Честно? Устал чувствовать что время уходит. Мне 38, дети растут, а я на одной зарплате сижу. Хочу чтобы семья жила лучше, чтобы не считать каждую копейку. И вообще... хочу доказать себе что могу не только по найму.",
    # ready
    "Готов, давай",
]

NICHE_SELECTION_MSGS = [
    # geography
    "Россия, Екатеринбург и область",
    # available_capital
    "150-200 тысяч, но если честно страшновато их тратить",
    # competencies
    "Закупки, работа с поставщиками, знаю стройматериалы, умею договариваться и находить выгодные условия. Организовать процесс могу.",
    # format
    "Товары скорее, ну может и услуги тоже. Всё рассмотреть наверное",
    # channels
    "Ну офлайн точно, может маркетплейсы. Соцсети не очень умею, но не против попробовать",
    # practical_experience
    "10 лет на заводе — слесарь, мастер смены. 6 лет менеджер по закупкам. Умею работать с поставщиками, знаю как выбивать скидки, разбираюсь в стройматериалах.",
    # environment_requests
    "Часто просят помочь найти материалы подешевле, посоветовать где купить, свести с поставщиками. Знакомые бригады спрашивают где заказать.",
    # personal_interest
    "Мне нравится разбираться в теме и находить выгодные варианты. Прям кайфую когда удаётся выторговать хорошие условия. Не люблю монотонную тупую работу.",
    # available_time
    "10-20 часов в неделю, по будням вечерами 2-3 часа, выходные могу больше",
    # priority
    "Быстрые деньги, мне сейчас важнее начать зарабатывать а не строить идеальный бизнес",
    # ready
    "Давай, запускай анализ",
]


async def run_full_simulation():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings
    from app.orchestrator.orchestrator import decide
    from app.orchestrator.context_builder import build_context
    from app.miniservices.session import (
        set_dialog, get_dialog, update_dialog_field, clear_dialog,
        set_active_project, append_conversation, clear_conversation,
    )
    from app.miniservices.engine import get_next_question, all_required_collected, load_manifest
    from app.modules.users.models import User
    from app.modules.billing.models import UserPlan
    from app.modules.projects.models import Project
    from app.modules.artifacts.models import MiniserviceRun, Artifact
    from app.orchestrator.intent import OrchestratorAction

    engine = create_async_engine(settings.database_url, pool_size=2, max_overflow=2)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    TG_ID = 777000038  # Fake telegram ID for Sergey
    full_log = []  # {"phase": str, "role": str, "text": str, "meta": str|None}

    async with sf() as session:
        # ── Create Sergey ────────────────────────────────────────
        user = User(telegram_id=TG_ID, first_name="Сергей", username="sergey38", onboarding_completed=False)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        plan = UserPlan(
            user_id=user.id, plan_type="free", credits_remaining=99,
            credits_monthly_limit=99, credits_reset_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        session.add(plan)
        await session.commit()

        # ═══════════════════════════════════════════════════════════
        # PHASE: ONBOARDING
        # ═══════════════════════════════════════════════════════════
        full_log.append({"phase": "onboarding", "role": "system", "text": "Сергей нажимает /start"})
        full_log.append({"phase": "onboarding", "role": "bot", "text": "Привет! Я — AI-ассистент для предпринимателей 🚀\n\n..." })

        # First message — rich context
        msg = ONBOARDING_MSGS[0]
        full_log.append({"phase": "onboarding", "role": "user", "text": msg})

        # Simulate onboarding step 1
        user.onboarding_role = "Предприниматель"
        user.onboarding_primary_goal = msg[:256]
        await session.commit()
        await append_conversation(TG_ID, "user", msg)

        full_log.append({"phase": "onboarding", "role": "bot", "text": "Отлично! Все результаты работы будут сохраняться в проект...\nДавай создадим проект — как его назвать?"})

        # Project name
        msg = ONBOARDING_MSGS[1]
        full_log.append({"phase": "onboarding", "role": "user", "text": msg})

        project = Project(user_id=user.id, name=msg)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        await set_active_project(TG_ID, str(project.id), project.name)

        user.onboarding_completed = True
        await session.commit()

        full_log.append({"phase": "onboarding", "role": "bot", "text": f"📁 Проект «{project.name}» создан!\nНачнём с постановки целей."})

        # ═══════════════════════════════════════════════════════════
        # PHASE: GOAL_SETTING
        # ═══════════════════════════════════════════════════════════
        run_gs = MiniserviceRun(
            user_id=user.id, project_id=project.id,
            miniservice_id="goal_setting", mode="standalone", status="collecting",
            collected_fields={},
        )
        session.add(run_gs)
        await session.commit()
        await session.refresh(run_gs)

        await set_dialog(TG_ID, miniservice_id="goal_setting", run_id=run_gs.id,
                         project_id=project.id, step=1, collected_fields={})

        print("[GOAL_SETTING] Starting...")

        for msg in GOAL_SETTING_MSGS:
            full_log.append({"phase": "goal_setting", "role": "user", "text": msg})
            await append_conversation(TG_ID, "user", msg)

            context = await build_context(TG_ID, session)
            decision = await decide(context, msg)

            action = decision.action.value
            params = decision.params or {}
            response = decision.response_text

            # Save field if accepted
            field_id = params.get("field_id", "")
            field_value = params.get("field_value", "")
            if field_id and field_value:
                await update_dialog_field(TG_ID, field_id, field_value)

            meta = f"[{action}]"
            if field_id:
                meta += f" saved: {field_id}"
            if params.get("ready_to_process"):
                meta += " → PROCESSING"

            full_log.append({"phase": "goal_setting", "role": "bot", "text": response, "meta": meta})
            await append_conversation(TG_ID, "assistant", response)
            print(f"  [{action}] {response[:80]}...")

            # If ready to process — run generation
            if params.get("ready_to_process") or action == "LAUNCH_MINISERVICE" and params.get("ready_to_process"):
                # Sync fields to DB
                dialog = await get_dialog(TG_ID)
                if dialog:
                    run_gs.collected_fields = dialog.get("collected_fields", {})
                    run_gs.status = "processing"
                    await session.commit()

                # Run goal_setting generation
                from app.miniservices.implementations.goal_setting import GoalSettingService
                from app.miniservices.base import MiniserviceContext
                gs_ctx = MiniserviceContext(
                    run_id=run_gs.id, user_id=user.id, project_id=project.id,
                    miniservice_id="goal_setting",
                    collected_fields=run_gs.collected_fields,
                    project_profile={"name": project.name},
                )
                print("  Generating goal_tree...")
                gs_service = GoalSettingService()
                gs_result = await gs_service.execute(gs_ctx)

                # Save artifact
                artifact_gs = Artifact(
                    user_id=user.id, project_id=project.id, run_id=run_gs.id,
                    miniservice_id="goal_setting", artifact_type="goal_tree",
                    artifact_schema_version="1.0", title="Дерево целей",
                    content=gs_result.content, summary=gs_result.summary,
                )
                session.add(artifact_gs)
                run_gs.status = "completed"
                run_gs.completed_at = datetime.now(timezone.utc)
                await session.commit()

                # Update project profile
                from app.modules.projects.service import ProjectService
                ps = ProjectService(session)
                manifest = load_manifest("goal_setting")
                mapping = manifest.get("project_fields_mapping", {})
                for proj_field, artifact_field in mapping.items():
                    val = gs_result.content.get(artifact_field)
                    if val is not None:
                        await ps.update_profile_field(project.id, proj_field, val)

                # Format text result
                from app.workers.notification_tasks import _format_goal_tree_text
                result_text = _format_goal_tree_text(gs_result.content, gs_result.summary)
                full_log.append({"phase": "goal_setting", "role": "bot", "text": result_text, "meta": "[RESULT]"})

                # Generate HTML report
                from app.integrations.html_report import html_report
                filename = await html_report.generate("goal_tree", gs_result.content, str(run_gs.id))
                if filename:
                    full_log.append({"phase": "goal_setting", "role": "bot", "text": f"📄 HTML отчёт: reports/{filename}", "meta": "[HTML]"})

                full_log.append({"phase": "goal_setting", "role": "bot", "text": "📍 Следующий логичный шаг — выбор ниши."})
                await clear_dialog(TG_ID)
                print("  ✅ goal_tree generated!")
                break

        # ═══════════════════════════════════════════════════════════
        # PHASE: NICHE_SELECTION
        # ═══════════════════════════════════════════════════════════
        await session.refresh(project)  # Get updated profile

        run_ns = MiniserviceRun(
            user_id=user.id, project_id=project.id,
            miniservice_id="niche_selection", mode="standalone", status="collecting",
            collected_fields={},
        )
        session.add(run_ns)
        await session.commit()
        await session.refresh(run_ns)

        await set_dialog(TG_ID, miniservice_id="niche_selection", run_id=run_ns.id,
                         project_id=project.id, step=1, collected_fields={})

        print("\n[NICHE_SELECTION] Starting...")

        for msg in NICHE_SELECTION_MSGS:
            full_log.append({"phase": "niche_selection", "role": "user", "text": msg})
            await append_conversation(TG_ID, "user", msg)

            context = await build_context(TG_ID, session)
            decision = await decide(context, msg)

            action = decision.action.value
            params = decision.params or {}
            response = decision.response_text

            field_id = params.get("field_id", "")
            field_value = params.get("field_value", "")
            if field_id and field_value:
                await update_dialog_field(TG_ID, field_id, field_value)

            meta = f"[{action}]"
            if field_id:
                meta += f" saved: {field_id}"
            if params.get("ready_to_process"):
                meta += " → PROCESSING"

            full_log.append({"phase": "niche_selection", "role": "bot", "text": response, "meta": meta})
            await append_conversation(TG_ID, "assistant", response)
            print(f"  [{action}] {response[:80]}...")

            if params.get("ready_to_process"):
                dialog = await get_dialog(TG_ID)
                if dialog:
                    run_ns.collected_fields = dialog.get("collected_fields", {})
                    run_ns.status = "processing"
                    await session.commit()

                from app.miniservices.implementations.niche_selection import NicheSelectionService
                from app.miniservices.base import MiniserviceContext

                proj_profile = {
                    "name": project.name,
                    "goal_statement": project.goal_statement,
                    "point_a": project.point_a,
                    "point_b": project.point_b,
                    "goal_deadline": project.goal_deadline,
                    "chosen_niche": project.chosen_niche,
                    "geography": project.geography,
                    "budget_range": project.budget_range,
                    "business_model": project.business_model,
                }

                ns_ctx = MiniserviceContext(
                    run_id=run_ns.id, user_id=user.id, project_id=project.id,
                    miniservice_id="niche_selection",
                    collected_fields=run_ns.collected_fields,
                    project_profile=proj_profile,
                )
                print("  Generating niche_table (with Tavily search)...")
                ns_service = NicheSelectionService()
                ns_result = await ns_service.execute(ns_ctx)

                artifact_ns = Artifact(
                    user_id=user.id, project_id=project.id, run_id=run_ns.id,
                    miniservice_id="niche_selection", artifact_type="niche_table",
                    artifact_schema_version="1.0", title="Выбор ниши",
                    content=ns_result.content, summary=ns_result.summary,
                )
                session.add(artifact_ns)
                run_ns.status = "completed"
                run_ns.completed_at = datetime.now(timezone.utc)
                await session.commit()

                from app.workers.notification_tasks import _format_niche_table_text
                result_text = _format_niche_table_text(ns_result.content, ns_result.summary)
                full_log.append({"phase": "niche_selection", "role": "bot", "text": result_text, "meta": "[RESULT]"})

                filename = await html_report.generate("niche_table", ns_result.content, str(run_ns.id))
                if filename:
                    full_log.append({"phase": "niche_selection", "role": "bot", "text": f"📄 HTML отчёт: reports/{filename}", "meta": "[HTML]"})

                print("  ✅ niche_table generated!")
                break

    await engine.dispose()
    return full_log


def build_report_html(log: list) -> str:
    """Build a Telegram-style conversation HTML report."""
    html = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Тест: Сергей — goal_setting → niche_selection</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f0f13;color:#e4e4e7;line-height:1.6;padding:20px;max-width:720px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}
.sub{color:#71717a;font-size:13px;margin-bottom:24px}
.phase{margin-bottom:32px}
.phase-title{font-size:16px;font-weight:600;color:#6366f1;margin-bottom:12px;padding:8px 12px;background:#1f1f23;border-radius:8px;border-left:3px solid #6366f1}
.msg{padding:10px 14px;border-radius:12px;margin-bottom:6px;max-width:85%;white-space:pre-wrap;word-wrap:break-word;font-size:14px}
.msg-user{background:#1e3a5f;margin-left:auto;text-align:left}
.msg-bot{background:#1f1f23;margin-right:auto}
.msg-system{background:#2a1f2e;margin:8px 0;font-size:12px;color:#a78bfa;text-align:center;max-width:100%;border-radius:8px}
.msg-result{background:#1a2e1a;border:1px solid #22c55e33;margin-right:auto}
.msg-html{background:#1f1a2e;border:1px solid #6366f133;margin-right:auto;font-size:12px}
.label{font-size:11px;font-weight:600;margin-bottom:3px}
.label-user{color:#38bdf8}
.label-bot{color:#a78bfa}
.meta{font-size:10px;color:#52525b;margin-top:3px}
a{color:#6366f1}
</style></head><body>
<h1>🧪 Тест: Сергей, 38 лет, Екатеринбург</h1>
<div class="sub">goal_setting → niche_selection | """ + datetime.now().strftime("%Y-%m-%d %H:%M") + """</div>
"""

    current_phase = None
    phase_names = {"onboarding": "👋 Онбординг", "goal_setting": "🎯 Постановка целей", "niche_selection": "🔍 Выбор ниши"}

    for entry in log:
        phase = entry.get("phase", "")
        if phase != current_phase:
            if current_phase:
                html += "</div>\n"
            current_phase = phase
            html += f'<div class="phase"><div class="phase-title">{phase_names.get(phase, phase)}</div>\n'

        role = entry["role"]
        text = entry["text"].replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        meta = entry.get("meta", "")

        if role == "user":
            html += f'<div class="msg msg-user"><div class="label label-user">Сергей</div>{text}</div>\n'
        elif role == "bot" and meta and "[RESULT]" in meta:
            html += f'<div class="msg msg-result"><div class="label label-bot">Бот [РЕЗУЛЬТАТ]</div>{text}</div>\n'
        elif role == "bot" and meta and "[HTML]" in meta:
            # Extract filename for link
            fname = entry["text"].split("reports/")[-1] if "reports/" in entry["text"] else ""
            html += f'<div class="msg msg-html">📄 <a href="reports/{fname}" target="_blank">Открыть HTML отчёт</a></div>\n'
        elif role == "bot":
            html += f'<div class="msg msg-bot"><div class="label label-bot">Бот</div>{text}'
            if meta:
                html += f'<div class="meta">{meta}</div>'
            html += '</div>\n'
        elif role == "system":
            html += f'<div class="msg msg-system">{text}</div>\n'

    if current_phase:
        html += "</div>\n"

    html += "</body></html>"
    return html


async def main():
    print("Starting Sergey simulation...")
    log = await run_full_simulation()
    html = build_report_html(log)
    path = Path("/app/reports/sergey_test_full.html")
    path.write_text(html, encoding="utf-8")
    print(f"\n✅ Report saved to {path}")
    print(f"Total messages: {len(log)}")


if __name__ == "__main__":
    asyncio.run(main())
