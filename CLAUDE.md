# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SaaS-маркетплейс агентных AI-решений — Telegram-бот для предпринимателей РФ/СНГ. Язык интерфейса — только русский. Полная спецификация: `spec_v01_final.md`.

## Directory Rules

- **Рабочая директория:** `/var/www/html/staging/` — весь код пишется только сюда
- **`/var/www/html/prod/`** — НИКОГДА не трогать, деплой туда только по ручной команде пользователя

## Tech Stack

- Python 3.12+, FastAPI (ASGI via uvicorn), aiogram 3.x (Telegram)
- SQLAlchemy 2.x async + Alembic (PostgreSQL 16+)
- Celery 5.x + Redis 7.x (очереди, кэш, состояние диалога)
- Pydantic 2.x (валидация), pydantic-settings (конфигурация через .env)
- LLM: Anthropic (Claude Haiku/Sonnet), OpenAI (GPT-4o-mini, DALL-E 3), Tavily (поиск)
- WeasyPrint (PDF), Jinja2 (шаблоны), structlog (логи), Sentry (мониторинг)

## Build & Run Commands

```bash
# Запуск всех сервисов
docker-compose up -d

# Только приложение
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Celery worker
celery -A app.workers.celery_app worker --loglevel=info --concurrency=4

# Celery beat (периодические задачи)
celery -A app.workers.celery_app beat --loglevel=info

# Миграции БД
alembic upgrade head

# Тесты
pytest
pytest tests/test_specific.py -v          # один файл
pytest tests/ -k "test_name" -v          # один тест
```

## Architecture

**Модульный монолит.** Один FastAPI-процесс, тяжёлые операции (LLM, поиск, генерация) — в Celery workers.

### Ключевые потоки

1. **Telegram Update:** webhook → middleware (auth, idempotency, rate_limit) → message_handler → ① smart_extractor → ② context_builder → ③ orchestrator → ④ action dispatcher
2. **Минисервис lifecycle:** INIT (проверка кредитов) → COLLECTING (slot-filling в Redis) → PROCESSING (Celery) → COMPLETED/FAILED
3. **Состояние диалога:** Redis key `dialog:{telegram_user_id}`, TTL 24h — определяет, в каком минисервисе находится пользователь
4. **Цепочка зависимостей:** `dep_chain:{uid}` в Redis, автоматический запуск недостающих минисервисов перед целевым

### Модули

- `app/bot/` — Telegram-слой: handlers, keyboards, middleware, текстовые шаблоны
- `app/orchestrator/` — единая точка принятия решений: orchestrator.py, context_builder.py, smart_extractor.py, dependency_resolver.py, intent.py, prompts.py
- `app/modules/` — бизнес-логика: users, projects, artifacts, billing, analytics (каждый: models.py, service.py, schemas.py)
- `app/miniservices/` — движок минисервисов: engine.py (оркестратор), base.py, session.py (Redis), manifests/ (JSON — source of truth), implementations/
- `app/integrations/` — внешние API: llm_gateway.py, tavily.py, google_sheets.py, image_gen.py, pdf_gen.py
- `app/workers/` — Celery tasks: miniservice_tasks, notification_tasks, billing_tasks, cleanup_tasks

### Критические правила

- **HTTP 200 Telegram:** всегда возвращать в течение 10 секунд, даже при ошибке
- **Идемпотентность:** `processed_update:{update_id}` в Redis, TTL 24h — повторный update не создаёт дублей
- **LLMGateway:** все LLM-вызовы только через единый класс, смена провайдера — через конфиг манифеста
- **Манифест = source of truth:** менять поведение минисервиса = менять его JSON-манифест
- **Кредиты:** списываются ТОЛЬКО при completed (полная стоимость) или partially_completed (половина), НИКОГДА при failed или cancel
- **Пользовательский текст:** только в `user`-роль сообщений LLM, никогда в `system`
- **Smart extractor:** вызывается на КАЖДОМ сообщении, извлекает поля для ВСЕХ минисервисов
- **Оркестратор:** единственная точка принятия решений, OrchestratorDecision с confidence
- **Подтверждение:** при confidence < 0.85 → кнопки [✅ Да] [❌ Нет], decision в Redis TTL 10мин
- **Спека:** если чего-то нет в spec_v01_final.md — этого нет в v0.1

## 6 Miniservices (v0.1)

| ID | Кредиты | Free | LLM генерации |
|----|---------|------|---------------|
| goal_setting | 1 | да | claude-sonnet-4-5 |
| niche_selection | 2 | да | claude-sonnet-4-5 + Tavily |
| supplier_search | 2 | да | claude-haiku-4-5 + Tavily + claude-sonnet-4-5 |
| sales_scripts | 2 | да | claude-sonnet-4-5 |
| ad_creation | 2 | да (текст) | gpt-4o-mini + DALL-E 3 (Paid) |
| lead_search | 3 | нет | claude-haiku-4-5 + Tavily + claude-sonnet-4-5 |

## Billing

- Free: 3 кредита/мес, 2 проекта, нет Sheets/изображений/lead_search
- Paid: 30 кредитов/мес, 20 проектов, 990₽/мес, ручная активация через admin-команды

## Bug Fixing Rules

- Do not fix symptoms before identifying the root cause.
- Fix at the source-of-truth (owner layer), not where the symptom appears.
- Avoid child-layer compensation (fallbacks, patches, duplicated logic, branching).
- Always do ultra-deep system research end-to-end before fixing:
  - top-down: route → page → container → orchestration → state
  - bottom-up: function → hook → service → API → DB
- Diagnose by layers: data/contracts → business logic → async/timing → UI state → integration → architecture
- If a bug appears in a child, inspect the parent/owner layer first.
- When changing a mechanic, align all directly coupled layers: contracts, handlers, queries, cache, serializers, loading/error states
- Be skeptical of one-file fixes; justify why other layers are unaffected.
- For frontend issues, inspect the full flow: route → layout → page → hooks → API → backend
- Prefer systemic fixes, but keep changes proportional.
- If re-architecture is required, define scope, risks, compatibility, and rollout order.
