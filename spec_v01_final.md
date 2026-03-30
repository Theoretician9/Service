# Техническая спецификация v0.1
## SaaS-маркетплейс агентных AI-решений для предпринимателей

**Версия:** 0.1 | **Дата:** Март 2026 | **Статус:** Финальная спека для разработки

---

## Как читать этот документ

Документ является единственным источником истины для разработки v0.1. Каждый раздел написан так, чтобы исключить «додумывание» в процессе. Если что-то не описано здесь — это не входит в v0.1. Любые решения, не отражённые в документе, требуют явного обновления спеки перед реализацией.

| Разделы | Содержание |
|---------|-----------|
| 1–3 | Продуктовый контекст, стек, архитектура |
| 4–5 | Модели данных, конфигурация окружения |
| 6 | Онбординг (разговорный) |
| 7 | Оркестратор — главный мозг бота |
| 8–9 | Движок минисервисов, спецификация каждого |
| 10–12 | Проекты, артефакты, конфликты контекста |
| 13–15 | LLM-стратегия, интеграции, биллинг |
| 16–19 | Безопасность, обработка ошибок, аналитика, деплой |
| 20 | Что явно НЕ входит в v0.1 |

---

## 1. Продуктовый контекст

### 1.1 Суть продукта

Платформа из 6 специализированных AI-минисервисов для предпринимателей. Каждый минисервис — AI-интервьюер и аналитик, который ведёт разговор и создаёт конкретный бизнес-артефакт: дерево целей, таблицу ниш, список поставщиков, скрипт продаж, объявления, список клиентов.

Минисервисы работают **последовательно в рамках одного проекта**: артефакт предыдущего становится контекстом для следующего. Никакого «быстрого режима» вне проекта — каждый результат всегда принадлежит проекту. Пользователь взаимодействует через **единый разговорный интерфейс**: оркестратор понимает намерение из обычного сообщения, сам решает что запустить и в каком порядке.

### 1.2 Минисервисы и их последовательность

| № | Минисервис | Артефакт | Зависит от |
|---|-----------|---------|-----------|
| 1 | Постановка целей | `goal_tree` | — |
| 2 | Выбор ниши + декомпозиция | `niche_table` | `goal_tree` |
| 3 | Поиск поставщиков | `supplier_list` | `niche_table` |
| 4 | Скрипты продаж | `sales_script` | `goal_tree`, `niche_table` |
| 5 | Продающие объявления | `ad_set` | `niche_table` |
| 6 | Поиск клиентов | `lead_list` | `niche_table`, `goal_tree` |

> Зависимости — не жёсткая блокировка, а сигнал оркестратору: если нужных артефактов нет, он запускает цепочку недостающих минисервисов сначала. Для пользователя это выглядит как единый процесс.

### 1.3 Цели v0.1

| Цель | Критерий достижения |
|------|---------------------|
| Запустить 6 минисервисов | Каждый проходит полный цикл: сбор вводных → генерация → артефакт |
| Freemium-монетизация | Лимиты Free работают, апгрейд до Paid функционирует |
| Проект как единица работы | Все минисервисы внутри проекта, артефакты накапливаются |
| Разговорный UX | Пользователь общается естественным языком, оркестратор управляет всем |
| Извлечение максимума из каждого сообщения | Оркестратор всегда извлекает все полезные данные, не только ответ на текущий вопрос |
| Расширяемость минисервисов | Артефакт, логика, вопросы меняются без правок движка |
| Устойчивость | Корректная обработка ошибок LLM, таймаутов, flood control |
| Аналитика | Ключевые события собираются и доступны через /admin_stats |

### 1.4 Аудитория и канал

Предприниматели и специалисты из РФ+СНГ. Язык — только русский. Канал в v0.1 — только Telegram-бот.

---

## 2. Технический стек

### 2.1 Обоснование выбора Python

- Лучшая экосистема для LLM-интеграций: все провайдеры имеют Python SDK
- aiogram 3.x — современный async-фреймворк для Telegram
- FastAPI — лучший Python-фреймворк для async REST API
- Cursor и Claude Code показывают наивысшее качество генерации Python-кода
- Полный набор библиотек: PDF, Google Sheets, очереди, поиск

### 2.2 Полный стек

| Компонент | Технология | Версия | Назначение |
|-----------|-----------|--------|------------|
| Язык | Python | 3.12+ | Основной язык |
| Telegram | aiogram | 3.x | Обработка Telegram updates |
| API сервер | FastAPI | 0.111+ | HTTP API, webhook endpoint |
| ASGI сервер | uvicorn | 0.29+ | Запуск FastAPI |
| ORM | SQLAlchemy | 2.x async | Работа с PostgreSQL |
| Миграции | Alembic | 1.13+ | Версионирование схемы БД |
| База данных | PostgreSQL | 16+ | Основное хранилище |
| Очереди задач | Celery | 5.x | Выполнение тяжёлых задач (LLM, поиск) |
| Брокер / кэш | Redis | 7.x | Брокер Celery, кэш, состояние диалога |
| Валидация | Pydantic | 2.x | Схемы данных |
| Конфигурация | pydantic-settings | 2.x | Все env-переменные через .env |
| HTTP клиент | httpx | 0.27+ | Внешние API-запросы |
| Шаблонизатор | Jinja2 | 3.x | HTML-шаблоны для PDF |
| Логирование | structlog | 24.x | Структурированные логи в JSON |
| Мониторинг | Sentry SDK | 2.x | Error tracking |
| PDF генерация | WeasyPrint | 62+ | HTML → PDF |
| Google Sheets | google-api-python-client | 2.x | Экспорт таблиц |
| Веб-поиск | tavily-python | — | Структурированный поиск |
| Изображения | openai | 1.x | DALL-E 3 |
| Контейнеры | Docker + docker-compose | — | Деплой на VPS |
| Тесты | pytest + pytest-asyncio | — | Тестирование |

### 2.3 LLM-провайдеры

| Провайдер | Модель | Использование |
|-----------|--------|---------------|
| Anthropic | claude-sonnet-4-5 | Оркестратор, ментор (goal_setting), выбор ниши, скрипты продаж |
| Anthropic | claude-haiku-4-5 | Smart extractor (извлечение полей), валидация, lead_search |
| OpenAI | gpt-4o-mini | Тексты продающих объявлений |
| OpenAI | DALL-E 3 | Изображения для объявлений (только Paid) |
| Tavily | Search API | Поиск поставщиков, клиентов, обогащение данных |

**Абстракция.** Все вызовы через единый `LLMGateway`. Смена провайдера — изменение конфига манифеста, не кода.

---

## 3. Системная архитектура

### 3.1 Принципы

- **Оркестратор как единственная точка входа.** Каждое сообщение проходит через Orchestrator LLM.
- **Smart extractor на каждом сообщении.** Из каждого сообщения пользователя извлекается максимум данных для всех минисервисов — не только ответ на текущий вопрос.
- **Всё внутри проекта.** Ни один минисервис не запускается вне проекта.
- **Зависимости между минисервисами.** Перед запуском проверяются необходимые артефакты.
- **Расширяемость.** Логика каждого минисервиса в манифесте. Движок (`engine.py`) не меняется.
- **Modular monolith.** Один Python-процесс с чёткими модульными границами.
- **Stateless API + очереди.** HTTP-слой не держит состояние. Тяжёлое — в Celery.
- **Идемпотентность.** Повторный Telegram update не создаёт дублей.

### 3.2 Структура директорий

```
project/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── redis_client.py
│   │
│   ├── bot/
│   │   ├── router.py              # Webhook endpoint: POST /webhook/{secret}
│   │   ├── dispatcher.py          # Все сообщения → orchestrator
│   │   ├── handlers/
│   │   │   ├── message_handler.py # Единая точка входа
│   │   │   ├── artifact.py        # PDF, Sheets по кнопкам
│   │   │   └── payments.py        # Заготовка (не активна в v0.1)
│   │   ├── keyboards/             # Бинарные кнопки: подтверждение, PDF/Sheets
│   │   ├── messages.py            # Системные текстовые шаблоны
│   │   └── middleware/
│   │       ├── auth.py
│   │       ├── idempotency.py
│   │       └── rate_limit.py
│   │
│   ├── orchestrator/
│   │   ├── orchestrator.py        # Основная логика
│   │   ├── context_builder.py     # Сборка OrchestratorContext
│   │   ├── dependency_resolver.py # Разрешение зависимостей минисервисов
│   │   ├── smart_extractor.py     # Извлечение полей из КАЖДОГО сообщения
│   │   ├── intent.py              # OrchestratorAction, OrchestratorDecision
│   │   └── prompts.py             # Системный промпт оркестратора
│   │
│   ├── modules/
│   │   ├── users/         # models.py, service.py, schemas.py
│   │   ├── projects/      # models.py, service.py, schemas.py
│   │   ├── artifacts/     # models.py, service.py, schemas.py
│   │   ├── billing/       # models.py, service.py, schemas.py
│   │   └── analytics/     # models.py, service.py
│   │
│   ├── miniservices/
│   │   ├── engine.py              # Оркестратор выполнения workflow (не меняется)
│   │   ├── base.py                # MiniserviceBase — базовый класс
│   │   ├── session.py             # Состояние диалога в Redis
│   │   ├── manifests/             # JSON-манифесты — source of truth
│   │   │   ├── goal_setting.json
│   │   │   ├── niche_selection.json
│   │   │   ├── supplier_search.json
│   │   │   ├── sales_scripts.json
│   │   │   ├── ad_creation.json
│   │   │   └── lead_search.json
│   │   └── implementations/       # Кастомная логика (опционально сверх манифеста)
│   │       ├── goal_setting.py    # Ментор-психолог логика
│   │       ├── niche_selection.py
│   │       ├── supplier_search.py
│   │       ├── sales_scripts.py
│   │       ├── ad_creation.py
│   │       └── lead_search.py
│   │
│   ├── integrations/
│   │   ├── llm_gateway.py
│   │   ├── tavily.py
│   │   ├── google_sheets.py
│   │   ├── image_gen.py
│   │   └── pdf_gen.py
│   │
│   └── workers/
│       ├── celery_app.py
│       ├── miniservice_tasks.py
│       ├── notification_tasks.py
│       ├── billing_tasks.py
│       └── cleanup_tasks.py
│
├── templates/pdf/
│   ├── base.html
│   ├── goal_tree.html
│   ├── niche_table.html
│   ├── supplier_list.html
│   ├── sales_script.html
│   ├── ad_set.html
│   └── lead_list.html
│
├── migrations/
├── tests/
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── requirements.txt
```

### 3.3 Поток обработки Telegram Update

```
Telegram → POST /webhook/{secret}
  → Middleware: проверка X-Telegram-Bot-Api-Secret-Token
  → Middleware: идемпотентность (Redis, TTL 24h)
  → Middleware: auth (найти/создать User)
  → Middleware: rate_limit
  → message_handler.py
      ① smart_extractor.py → ExtractedFields (из КАЖДОГО сообщения)
         → сохранить в Redis: extracted_fields:{uid}, TTL 2 часа
         → применить к active_run.collected_fields (если active_run есть)
      ② context_builder.py → OrchestratorContext (с учётом свежих extracted_fields)
      ③ orchestrator.py → OrchestratorDecision
      ④ Если needs_confirmation = True:
            → сохранить decision в Redis: pending_confirmation:{uid}, TTL 10 мин
            → отправить confirmation_text + кнопки [✅ Да] [❌ Нет]
            → завершить обработку (ждать ответа)
      ⑤ Диспетчер action:
          RESPOND              → отправить response_text
          ONBOARDING           → шаг онбординга
          ENSURE_PROJECT       → создать/выбрать проект, затем продолжить
          INIT_DEP_CHAIN       → записать цепочку в Redis, запустить первый
          LAUNCH_MINISERVICE   → проверить кредиты → Celery task → «⏳ Начинаем...»
          CONTINUE_COLLECTING  → применить extracted value → следующий вопрос или PROCESSING
          PROJECT_ACTION       → создать/переключить/архивировать
          SHOW_INFO            → показать данные проекта/артефактов
          ARTIFACT_PDF         → генерировать и отправить PDF
          ARTIFACT_SHEETS      → экспорт в Google Sheets
          SHOW_PLAN            → показать тариф
          UPGRADE_CTA          → предложить апгрейд
          CANCEL_RUN           → отменить текущий запуск
          BUG_REPORT           → сохранить баг-репорт
  → Вернуть HTTP 200 (всегда, даже при ошибке)
```

> **Критично:** HTTP 200 в течение 10 секунд. Всё тяжёлое — в Celery.

> **Ответ на подтверждение (кнопки [✅ Да] / [❌ Нет]):** `callback_query` → достать `pending_confirmation:{uid}` из Redis → выполнить сохранённый decision (Да) или вызвать оркестратор с пометкой «отклонено» (Нет).

### 3.4 Состояние в Redis

**Активный запуск** (`dialog:{telegram_user_id}`) — TTL 24 часа:
```json
{
  "miniservice_id": "goal_setting",
  "run_id": "uuid",
  "step": 2,
  "collected_fields": {"point_a": "..."},
  "project_id": "uuid",
  "short_answer_count": 0
}
```
> `short_answer_count` — счётчик уклончивых/коротких ответов для fallback-логики ментора.

**Очередь зависимостей** (`dep_chain:{telegram_user_id}`) — TTL 24 часа:
```json
{
  "target_miniservice": "sales_scripts",
  "chain": ["goal_setting", "niche_selection"],
  "project_id": "uuid"
}
```
Создаётся при `INIT_DEP_CHAIN` **до** запуска первого минисервиса из цепочки. После завершения каждого минисервиса в цепочке берётся следующий из `chain`. После исчерпания — запускается `target_miniservice`. Ключ удаляется после запуска `target_miniservice`.

**История разговора** (`conversation:{telegram_user_id}`) — TTL 7 дней:
```json
[{"role": "user"|"assistant", "content": "..."}]
```
Последние `ORCHESTRATOR_HISTORY_MESSAGES` сообщений.

**Активный проект** (`active_project:{telegram_user_id}`) — TTL 7 дней:
```json
{"project_id": "uuid", "project_name": "Магазин кроссовок"}
```
При истечении TTL (пользователь вернулся после >7 дней) — `context_builder.py` делает запрос в БД и восстанавливает ключ из последнего использованного проекта (`projects ORDER BY updated_at DESC LIMIT 1`).

**Извлечённые поля** (`extracted_fields:{telegram_user_id}`) — TTL 2 часа:
```json
{
  "goal_setting": {"point_a": "...", "point_b": "..."},
  "niche_selection": {"geography": "Казахстан", "available_capital": "до 50 тыс."},
  "supplier_search": {"supplier_origin": ["Китай"]}
}
```
Обновляется при каждом вызове `smart_extractor`. При запуске минисервиса — его блок берётся как `prefilled_fields`.

**Ожидающее подтверждение** (`pending_confirmation:{telegram_user_id}`) — TTL 10 минут:
```json
{
  "action": "LAUNCH_MINISERVICE",
  "params": {"miniservice_id": "supplier_search", "project_id": "uuid"},
  "response_text": "..."
}
```
Создаётся когда `needs_confirmation = True`. Удаляется после ответа пользователя или истечения TTL.

---

## 4. Модели данных

### 4.1 User

```python
class User(Base):
    __tablename__ = "users"

    id: UUID                              # PK, default uuid4
    telegram_id: BigInteger               # UNIQUE, NOT NULL, indexed
    username: String(64)                  # nullable
    first_name: String(128)               # NOT NULL
    language_code: String(8)              # default "ru"
    onboarding_completed: Boolean         # default False
    onboarding_role: String(64)           # nullable
    onboarding_primary_goal: String(64)   # nullable
    is_blocked: Boolean                   # default False
    created_at: DateTime
    updated_at: DateTime
```

### 4.2 UserPlan

```python
class UserPlan(Base):
    __tablename__ = "user_plans"

    id: UUID
    user_id: UUID                         # FK users.id, UNIQUE
    plan_type: Enum("free", "paid")       # default "free"
    credits_remaining: Integer            # default 3
    credits_monthly_limit: Integer        # 3 для free, 30 для paid
    credits_reset_at: DateTime
    paid_until: DateTime                  # nullable
    created_at: DateTime
    updated_at: DateTime
```

### 4.3 Project

```python
class Project(Base):
    __tablename__ = "projects"

    id: UUID
    user_id: UUID                         # FK users.id, indexed
    name: String(128)                     # NOT NULL
    description: Text                     # nullable
    status: Enum("active", "archived")    # default "active"

    # ── ProjectProfile ────────────────────────────────────────────────────
    # Заполняется постепенно артефактами минисервисов.
    # Источник каждого поля указан в comment.

    # из goal_setting:
    goal_statement: Text                  # nullable — итоговая SMART-формулировка
    point_a: Text                         # nullable — текущее положение
    point_b: Text                         # nullable — желаемое будущее
    goal_deadline: String(128)            # nullable — дата/срок в свободном формате
                                          # НЕ DateTime: хранится как текст ("к июлю 2026")
    success_metrics: JSONB                # nullable — список метрик ["string"]
    constraints: JSONB                    # nullable — список ограничений ["string"]
                                          # заполняется из constraint_tree артефакта

    # из niche_selection:
    niche_candidates: JSONB               # nullable — все кандидаты с оценками
    chosen_niche: String(256)             # nullable — рекомендованная ниша
                                          # берётся из niche_table.recommendation
    hypothesis_table: JSONB               # nullable — таблица гипотез
    geography: String(128)                # nullable
    budget_range: String(128)             # nullable — mapped из available_capital choice
    business_model: String(64)            # nullable — mapped из format choice
                                          # Товары → B2C, Услуги → B2B, оба → hybrid

    created_at: DateTime
    updated_at: DateTime
```

> **Примечание по `goal_deadline`:** поле хранится как `String(128)`, не `DateTime`. Пользователи указывают срок в свободном тексте ("к июлю", "через год", "31 декабря 2026"). Преобразование в дату не производится — хранится как есть.

> **Примечание по `budget_range`:** при записи из `niche_selection` выбор `available_capital` маппируется: "до 50 тыс." → "до 50 000 ₽", "50–200 тыс." → "50 000–200 000 ₽" и т.д.

> **Примечание по `business_model`:** при записи из `niche_selection` выбор `format` маппируется: "Товары" → "B2C", "Услуги" → "B2B", "Товары + Услуги" или "Всё рассмотреть" → "hybrid".

> **`target_audience` и `product_description`** — убраны из ProjectProfile. Ни один минисервис их не пишет. Данные о ЦА хранятся внутри артефактов (в `niche_table.decomposition.audience_segments`, `ad_set.target_audience` и т.д.) и используются как контекст для оркестратора через `Artifact.summary`.

### 4.4 MiniserviceRun

```python
class MiniserviceRun(Base):
    __tablename__ = "miniservice_runs"

    id: UUID
    user_id: UUID                         # FK users.id, indexed
    project_id: UUID                      # FK projects.id, NOT NULL
                                          # project_id ВСЕГДА заполнен — не nullable
    miniservice_id: String(64)            # NOT NULL
    mode: Enum("sequential", "standalone")# sequential — часть dep_chain
                                          # standalone — прямой запрос
                                          # Устанавливается в INIT:
                                          #   dep_chain существует → sequential
                                          #   иначе → standalone
    status: Enum(
        "collecting",
        "processing",
        "completed",
        "failed",
        "partially_completed"
    )
    collected_fields: JSONB               # NOT NULL, default {}
    celery_task_id: String(255)           # nullable
    error_message: Text                   # nullable
    credits_spent: Integer                # default 0
    llm_tokens_used: Integer              # default 0
    web_searches_used: Integer            # default 0
    started_at: DateTime
    completed_at: DateTime                # nullable
    created_at: DateTime
```

### 4.5 Artifact

```python
class Artifact(Base):
    __tablename__ = "artifacts"

    id: UUID
    user_id: UUID                         # FK users.id, indexed
    project_id: UUID                      # FK projects.id, NOT NULL
    run_id: UUID                          # FK miniservice_runs.id
    miniservice_id: String(64)            # NOT NULL
    artifact_type: String(64)             # NOT NULL
    artifact_schema_version: String(16)   # NOT NULL, default "1.0"
    title: String(256)                    # NOT NULL
    version: Integer                      # default 1
    is_current: Boolean                   # default True
    is_outdated: Boolean                  # default False
    content: JSONB                        # NOT NULL
    summary: Text                         # NOT NULL
                                          # Генерируется воркером после создания content:
                                          # LLM (Haiku) с промптом
                                          # «Напиши 2-3 предложения о результате для использования
                                          # как контекст в следующих шагах»
    google_sheets_url: String(512)        # nullable
    created_at: DateTime
```

> **`summary` генерируется автоматически** в конце PROCESSING-шага, после создания `content`. Используется Haiku одним коротким вызовом. Этот вызов входит в `MiniserviceRun.llm_tokens_used`.

### 4.6 ChangeProposal

```python
class ChangeProposal(Base):
    __tablename__ = "change_proposals"

    id: UUID
    project_id: UUID                      # FK projects.id, indexed
    run_id: UUID                          # FK miniservice_runs.id
    proposed_changes: JSONB               # {field: {old_value, new_value}}
    conflict_fields: JSONB
    affected_artifact_ids: JSONB
    explanation: Text                     # NOT NULL — LLM-генерация
    status: Enum("pending", "accepted", "rejected")  # default "pending"
    created_at: DateTime
    resolved_at: DateTime                 # nullable
```

### 4.7 AnalyticsEvent

```python
class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: UUID
    user_id: UUID                         # FK users.id, nullable, indexed
    event_type: String(64)                # NOT NULL, indexed
    properties: JSONB                     # default {}
    created_at: DateTime                  # default now, indexed
```

### 4.8 BugReport

```python
class BugReport(Base):
    __tablename__ = "bug_reports"

    id: UUID
    user_id: UUID                         # FK users.id
    text: Text                            # NOT NULL
    created_at: DateTime
```

### 4.9 Идемпотентность Update (Redis)

- Ключ: `processed_update:{update_id}`, TTL 24 часа

---

## 5. Конфигурация окружения (.env)

```bash
# ── Telegram ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=      # случайная строка 32+ символа
TELEGRAM_WEBHOOK_URL=         # https://yourdomain.com/webhook/{TELEGRAM_WEBHOOK_SECRET}
BOT_ADMIN_CHAT_ID=

# ── База данных ────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/dbname
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=

# ── Redis ──────────────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# ── LLM ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# ── Поиск ─────────────────────────────────────────────────────────────────
TAVILY_API_KEY=

# ── Google Sheets ──────────────────────────────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_JSON=   # base64-encoded JSON сервисного аккаунта
                                # Получить: Google Cloud → IAM → Service Accounts → Create key (JSON)
GOOGLE_SERVICE_ACCOUNT_EMAIL=  # email аккаунта — показывается пользователю при первом экспорте

# ── Мониторинг ─────────────────────────────────────────────────────────────
SENTRY_DSN=                    # обязательно в production
ENVIRONMENT=development         # development | production
LOG_LEVEL=INFO

# ── Биллинг ───────────────────────────────────────────────────────────────
FREE_PLAN_MONTHLY_CREDITS=3
PAID_PLAN_MONTHLY_CREDITS=30
PAID_PLAN_PRICE_RUB=990
MAX_PROJECTS_FREE=2
MAX_PROJECTS_PAID=20

# ── Лимиты ────────────────────────────────────────────────────────────────
LLM_REQUEST_TIMEOUT_SECONDS=60
MAX_MESSAGE_LENGTH=4000
ORCHESTRATOR_HISTORY_MESSAGES=20
ORCHESTRATOR_CONFIDENCE_THRESHOLD=0.85
MENTOR_MAX_FALLBACK_ATTEMPTS=3     # после N попыток ментор использует лучшее из собранного
```

---

## 6. Онбординг-поток

### 6.1 Триггер и ветвление

**Команда `/start`:**
- `onboarding_completed = False` → онбординг
- `onboarding_completed = True` → оркестратор приветствует и ждёт намерения

### 6.2 Приветственное сообщение

```
Привет! Я — AI-ассистент для предпринимателей 🚀

Помогаю с реальными задачами:
1. Поставить цель
2. Подобрать нишу и найти поставщиков
3. Сделать декомпозицию и подобрать гипотезы
4. Написать скрипты продаж
5. Оформить объявления
6. Найти клиентов

Не просто чат — готовые инструменты с результатом на выходе:
PDF, таблицы, картинки.

Можем прямо сейчас начать последовательно с постановки цели —
просто напиши мне об этом и мы начнём.

Или выбери то, что для тебя сейчас наиболее актуально.
```

Кнопок нет — пользователь отвечает в свободной форме.

### 6.3 Разговорный онбординг

Оркестратор ведёт онбординг через естественный разговор. Из первого ответа пользователя smart_extractor (как и всегда) извлекает максимум данных, оркестратор сохраняет:
- `onboarding_role` — кем считает себя пользователь
- `onboarding_primary_goal` — что хочет решить прямо сейчас
- Любые данные для минисервисов → в `extracted_fields:{uid}`

Если роль или цель не ясны — задаёт уточняющий вопрос. Максимум 2 уточнения.

**Завершение онбординга**

После получения `onboarding_primary_goal`:

```
Отлично! Все результаты работы будут сохраняться в проект —
это позволяет каждому следующему инструменту знать,
что сделали предыдущие.

Давай создадим проект — как его назвать?
(Можешь написать название бизнеса, идеи или просто «Первый проект»)
```

→ `user.onboarding_completed = True`
→ Оркестратор создаёт проект с введённым названием
→ Переходит к рекомендованному минисервису или тому, что назвал пользователь

### 6.4 Рекомендованный минисервис

| onboarding_primary_goal | Рекомендованный минисервис |
|-------------------------|---------------------------|
| Найти нишу / идею | goal_setting → niche_selection |
| Найти поставщиков | goal_setting → niche_selection → supplier_search |
| Настроить продажи | goal_setting → niche_selection → sales_scripts |
| Найти клиентов | goal_setting → niche_selection → lead_search |
| Разобраться с целями | goal_setting |
| Начать с начала / последовательно | goal_setting |

---

## 7. Оркестратор

Оркестратор — единственная точка принятия решений. Каждое сообщение обрабатывается им.

### 7.1 Smart Extractor — извлечение на каждом сообщении

`smart_extractor.py` вызывается **для каждого входящего сообщения** — шаг ① в потоке (раздел 3.3). Это не опциональная функция, а обязательный первый шаг обработки.

**Что делает:**
1. Получает текст сообщения + текущий контекст (активный минисервис, его поля)
2. LLM (Haiku) одним вызовом пытается извлечь полезные данные для ВСЕХ минисервисов
3. Возвращает `ExtractedFields` — словарь `{miniservice_id: {field_id: value}}`
4. Обновляет Redis: `extracted_fields:{uid}` (merge с существующим, новые данные приоритетнее)
5. Если `active_run` существует — немедленно применяет соответствующие поля к `collected_fields`

**Примеры когда это работает:**

*Во время сбора полей goal_setting:*
Ментор спросил только про point_a, а пользователь написал:
> «Сейчас работаю менеджером, хочу открыть магазин кроссовок к лету, бюджет есть тысяч 200»

Smart extractor вытащит: `point_a`, частично `point_b`, `goal_deadline`, `available_capital` для niche_selection. Следующие вопросы по уже извлечённым полям не задаются.

*Вне минисервиса:*
Пользователь пишет первое сообщение с богатым контекстом — все данные раскладываются в `extracted_fields` и будут использованы при запуске соответствующих минисервисов.

**Что НЕ делает smart extractor:** не запускает минисервисы, не изменяет ProjectProfile, не принимает решений. Только извлекает и сохраняет данные.

**Обработка ошибок:** если LLM не ответил или вернул невалидный JSON — продолжаем без извлечения, обычный поток оркестратора.

### 7.2 OrchestratorContext

`context_builder.py` собирает из БД и Redis перед каждым вызовом:

```python
@dataclass
class OrchestratorContext:
    # Пользователь
    user_id: UUID
    user_first_name: str
    plan_type: str                  # "free" | "paid"
    credits_remaining: int
    credits_monthly_limit: int
    credits_reset_at: datetime
    onboarding_completed: bool

    # Активный запуск (если есть)
    active_run: ActiveRunInfo | None
    # ActiveRunInfo: miniservice_id, step, collected_fields,
    #                project_id, short_answer_count

    # Активный проект
    active_project: ProjectSummary | None
    # ProjectSummary: id, name, ProjectProfile,
    #                 список артефактов (тип, версия, summary, дата)

    # Все проекты пользователя
    all_projects: list[ProjectSummary]

    # Активная цепочка зависимостей (если есть)
    active_dep_chain: DepChainInfo | None
    # DepChainInfo: target_miniservice, chain[], project_id

    # Последние извлечённые поля
    extracted_fields: dict          # из Redis extracted_fields:{uid}

    # История разговора
    conversation_history: list[Message]

    # Доступные минисервисы
    available_miniservices: list[MiniserviceInfo]
    # MiniserviceInfo: id, name, credit_cost, available_on_free, requires, provides
```

### 7.3 OrchestratorDecision

```python
@dataclass
class OrchestratorDecision:
    action: OrchestratorAction
    response_text: str              # текст пользователю
    confidence: float               # 0.0–1.0
    params: dict                    # параметры action
    needs_confirmation: bool        # True если confidence < ORCHESTRATOR_CONFIDENCE_THRESHOLD
    confirmation_text: str | None   # текст для показа при needs_confirmation=True
```

> **Механизм подтверждения:** если `needs_confirmation = True`, dispatcher сохраняет весь `OrchestratorDecision` в Redis (`pending_confirmation:{uid}`, TTL 10 мин) и отправляет `confirmation_text` с кнопками. Решение по action принимается только после ответа пользователя. Отдельного action-типа `CONFIRM` нет — это флаг на любом action.

### 7.4 Типы action

| Action | Когда | Params |
|--------|-------|--------|
| `RESPOND` | Ответить на вопрос, дать информацию | — |
| `ONBOARDING` | Шаг онбординга | `step`, `extracted_fields` |
| `ENSURE_PROJECT` | Нет активного проекта — создать/выбрать | `suggested_name` |
| `INIT_DEP_CHAIN` | Не хватает артефактов-зависимостей | `target_miniservice`, `missing_miniservices: list`, `project_id` |
| `LAUNCH_MINISERVICE` | Запустить минисервис (зависимости закрыты) | `miniservice_id`, `project_id`, `prefilled_fields` |
| `CONTINUE_COLLECTING` | Продолжить slot-filling активного run | `field_id`, `extracted_value` |
| `CREATE_PROJECT` | Создать проект | `name`, `description` |
| `SWITCH_PROJECT` | Переключиться на другой проект | `project_id` |
| `SHOW_INFO` | Показать данные о проекте/артефактах | `project_id \| null`, `artifact_type \| null` |
| `ARTIFACT_PDF` | Скачать PDF | `artifact_id` |
| `ARTIFACT_SHEETS` | Экспорт в Google Sheets | `artifact_id` |
| `SHOW_PLAN` | Показать тариф | — |
| `UPGRADE_CTA` | Предложить апгрейд | `trigger` |
| `CANCEL_RUN` | Отменить текущий запуск | — |
| `BUG_REPORT` | Сохранить баг-репорт | `text` |

### 7.5 Логика принятия решений

```
1. Если active_run != null (идёт slot-filling):
   → Smart extractor уже применил свои находки к collected_fields (шаг ①)
   → Оркестратор проверяет: остались ли ещё незаполненные обязательные поля?
       Нет → CONTINUE_COLLECTING (перейти к PROCESSING)
       Да → CONTINUE_COLLECTING (задать следующий незаполненный вопрос)
   → Если пользователь явно хочет отменить → CANCEL_RUN
   → Если пользователь хочет другой минисервис → needs_confirmation = True
       «Хочешь прервать [текущий] и начать [новый]?»

2. Если active_run == null:
   → Классифицировать намерение
   → Проверить наличие активного проекта:
       Нет проекта → ENSURE_PROJECT (до любого запуска)
   → Если намерение = запустить минисервис:
       Взять prefilled_fields из extracted_fields[miniservice_id]
       Проверить зависимости (dependency_resolver.py)
       Зависимости не закрыты → INIT_DEP_CHAIN
       Зависимости закрыты → LAUNCH_MINISERVICE
   → Вычислить confidence

3. Проверка confidence:
   → >= ORCHESTRATOR_CONFIDENCE_THRESHOLD (0.85) → выполнить напрямую
   → < 0.85 → needs_confirmation = True, сохранить decision в Redis
```

### 7.6 Разрешение зависимостей (`dependency_resolver.py`)

```
INIT_DEP_CHAIN поведение:
1. Определить список недостающих артефактов
2. Выстроить минимальную цепочку в правильном порядке
   (только те, которых реально нет в проекте)
3. Записать в Redis: dep_chain:{uid}
   {target_miniservice, chain: [id1, id2, ...], project_id}
4. Сообщить пользователю прозрачно:
   «Чтобы сделать [запрошенное], нужно сначала [список].
    Начнём с [первого] — это займёт несколько минут.»
5. Запустить LAUNCH_MINISERVICE для первого из chain
6. После завершения каждого — автоматически брать следующий из chain
7. После исчерпания chain — запустить target_miniservice
8. Удалить dep_chain:{uid}
```

Для пользователя — единый плавный процесс.

### 7.7 Проектная осведомлённость

**При запуске минисервиса:**
- Нет проектов → ENSURE_PROJECT: «Как назовём проект?»
- Один проект → использовать автоматически: «Работаем в проекте «{название}»»
- Несколько проектов + пользователь движется последовательно (следующий шаг цепочки) → использовать активный, не спрашивать
- Несколько проектов + нестандартный запрос → уточнить: «Для какого проекта?» → needs_confirmation = True

**Стандартный запрос** — следующий логичный шаг в цепочке текущего проекта или явно связан с текущим разговором.

**Нестандартный запрос** — упоминание другого проекта, перепрыжка без контекста, запрос не связанный с текущей темой.

**Форматы ответов:**

При «все проекты»:
```
У тебя 2 активных проекта:

📁 Магазин кроссовок
Ниша: кроссовки оптом из Китая
Цель: выйти на оборот 500 тыс./мес к июлю
Артефактов: 6 | Последнее: 04 мар

📁 Услуги дизайна
Ниша: не задана | Цель: не задана
Артефактов: 2 | Последнее: 28 фев
```

При «один проект»:
```
📁 Магазин кроссовок

── Профиль ──────────────────────
Точка А: нет онлайн-продаж, работаю только офлайн
Точка Б: 500 тыс./мес оборот через маркетплейсы
Дедлайн: к июлю 2026
Ниша: кроссовки оптом из Китая
Модель: B2C, Region: Россия, Бюджет: 200–500 тыс.

── Артефакты ────────────────────
• Дерево целей (v1, 01 мар) — цель поставлена, план на месяц готов
• Таблица ниш (v1, 02 мар) — рекомендована ниша кроссовок
• Список поставщиков (v2, 04 мар) — 8 поставщиков из Китая
```

### 7.8 Fallback: если пользователь не идёт на контакт

Применяется во время slot-filling (все минисервисы, особенно ментор-режим).

```
short_answer_count хранится в dialog:{uid}.short_answer_count

На каждый уклончивый/слишком короткий ответ: short_answer_count += 1

Если short_answer_count < MENTOR_MAX_FALLBACK_ATTEMPTS:
   → Продолжать задавать вопросы, перефразировать, пробовать другой заход

Если short_answer_count >= MENTOR_MAX_FALLBACK_ATTEMPTS:
   → Для необязательных полей: использовать разумные дефолты
   → Для обязательных полей: генерировать наиболее вероятное значение
     на основе собранного контекста + данных из ProjectProfile
   → Помечать auto-filled поля: {"value": "...", "_auto": true}
   → Уведомить пользователя: «Окей, буду работать с тем, что есть»
   → В артефакте пометить предположения явно
```

**Исключение для `why_important` в goal_setting:** это поле является сердцем ментор-режима. Автозаполнение для него запрещено даже при исчерпании попыток. Если пользователь не даёт ответа после `MENTOR_MAX_FALLBACK_ATTEMPTS`, ментор честно говорит: «Без понимания зачем тебе это — цель будет поверхностной. Можем вернуться к этому позже, но сейчас попробуй ответить одним словом.» И делает ещё одну попытку.

### 7.9 Системный промпт оркестратора

**Статичная часть (кэшируется у провайдера):**
```
Ты — AI-ассистент для предпринимателей. Управляешь набором из 6 минисервисов.
Ты НЕ выполняешь работу минисервисов сам — ты решаешь что запустить и когда.

Правила:
1. Всегда отвечай на русском языке.
2. Будь конкретным. Без маркетинга.
3. Каждый минисервис — только внутри проекта. Нет проекта — создай первым.
4. Проверяй зависимости. Нет нужных артефактов — запусти цепочку.
5. При нескольких проектах: не спрашивай для какого, если пользователь движется
   последовательно. Уточняй только при нестандартном запросе.
6. Не придумывай данные пользователя — только из контекста.
7. Smart extractor уже обработал сообщение — в контексте есть extracted_fields.
   Используй их при запуске минисервисов как prefilled_fields.
8. Отвечай структурированным JSON согласно схеме OrchestratorDecision.

Минисервисы (id: requires → provides):
{available_miniservices_with_deps}
```

**Динамическая часть:**
```
Пользователь: {first_name}, тариф: {plan_type}, кредитов: {credits_remaining}/{limit}
Активный проект: {active_project или "нет"}
Все проекты: {all_projects_summary}
Активный run: {active_run или "нет"}
Активная цепочка зависимостей: {active_dep_chain или "нет"}
Свежие извлечённые данные: {extracted_fields}

История:
{conversation_history}

Сообщение: {user_message}

→ OrchestratorDecision JSON
```

### 7.10 Команды как ярлыки

| Команда | Что происходит |
|---------|----------------|
| `/start` | Онбординг-контекст |
| `/help` | «Что ты умеешь?» |
| `/projects` | «Покажи все мои проекты» |
| `/artifacts` | «Покажи мои последние артефакты» |
| `/plan` | «Покажи мой тариф» |
| `/cancel` | Прямая отмена active_run (до оркестратора) + очистка dep_chain |
| `/reset` | Очистить conversation_history (до оркестратора) |
| `/delete_account` | Запрос удаления |

> `/cancel` также очищает `dep_chain:{uid}` если он существует.

### 7.11 Inline-кнопки

Только для бинарных выборов:
- `[✅ Да]` / `[❌ Нет]` — подтверждение (обрабатывает `pending_confirmation:{uid}`)
- `[📥 Скачать PDF]` / `[📊 Экспорт в Sheets]` — после завершения минисервиса
- `[✅ Принять изменения]` / `[❌ Оставить как было]` — ChangeProposal

### 7.12 Защита от зацикливания

- Максимум 3 попытки уточнить намерение → «Напиши подробнее, что именно хочешь»
- Ошибка LLM оркестратора → fallback: «Что-то пошло не так, попробуй ещё раз»
- `pending_confirmation` истекает через 10 минут → если пользователь не ответил, decision аннулируется

---

## 8. Движок минисервисов

### 8.1 Принцип расширяемости

Движок (`engine.py`) стабилен — не меняется при изменении минисервиса. Всё специфичное живёт в:
1. **Манифесте** (`manifests/{id}.json`) — вопросы, типы, схема выхода, зависимости
2. **Реализации** (`implementations/{id}.py`) — кастомная логика (необязательно)
3. **PDF-шаблоне** (`templates/pdf/{artifact_type}.html`)

Чтобы изменить что делает минисервис или что выдаёт — меняется только манифест. Движок не трогается.

### 8.2 Манифест минисервиса

```json
{
  "id": "goal_setting",
  "name": "Постановка целей",
  "emoji": "🎯",
  "description": "Помогу сформулировать цель, найти мотивацию и построить план",
  "credit_cost": 1,
  "available_on_free": true,
  "schema_version": "1.0",

  "requires": [],
  "provides": ["goal_tree"],

  "mode": "mentor",
  "mentor_config": {
    "persona": "бизнес-психолог, ментор, старший брат",
    "tone": "понимающий, взрослый, в меру жёсткий",
    "goal": "вытащить реальную мотивацию, сформулировать конкретную достижимую цель",
    "non_autofill_fields": ["why_important"]
  },

  "llm_config": {
    "slot_filling_provider": "anthropic",
    "slot_filling_model": "claude-haiku-4-5",
    "generation_provider": "anthropic",
    "generation_model": "claude-sonnet-4-5"
  },

  "tools": ["pdf_gen"],
  "tools_require_paid": [],

  "input_schema": {
    "fields": [
      {
        "id": "point_a",
        "label": "Точка А",
        "type": "text",
        "required": true,
        "max_length": 500,
        "question": "Опиши своё текущее положение: где ты сейчас находишься?",
        "extract_from_free_text": true
      },
      {
        "id": "point_b",
        "label": "Точка Б",
        "type": "text",
        "required": true,
        "max_length": 500,
        "question": "Что хочешь достичь? Опиши желаемое будущее конкретно",
        "extract_from_free_text": true
      },
      {
        "id": "goal_deadline",
        "label": "Дедлайн",
        "type": "text",
        "required": true,
        "max_length": 100,
        "question": "К какому сроку цель должна быть достигнута?",
        "extract_from_free_text": true
      },
      {
        "id": "why_important",
        "label": "Глубокая мотивация",
        "type": "text",
        "required": true,
        "max_length": 500,
        "question": "Почему именно эта цель важна для тебя? Что будет, если не достигнешь?",
        "extract_from_free_text": false,
        "mentor_note": "Ключевое поле. Нельзя автозаполнять. Если ответ поверхностный — копать глубже через «почему?». До 3 уточнений. Искать реальную мотивацию, не декларативную."
      },
      {
        "id": "constraints",
        "label": "Ограничения",
        "type": "text",
        "required": false,
        "max_length": 300,
        "question": "Какие есть ограничения? (бюджет, время, ресурсы)",
        "extract_from_free_text": true
      },
      {
        "id": "success_metric",
        "label": "Метрика успеха",
        "type": "text",
        "required": false,
        "max_length": 300,
        "question": "Как конкретно поймёшь, что цель достигнута?",
        "extract_from_free_text": true
      }
    ]
  },

  "question_plan": [
    {"field": "point_a"},
    {"field": "point_b"},
    {"field": "goal_deadline"},
    {"field": "why_important"},
    {"field": "constraints"},
    {"field": "success_metric"}
  ],

  "output_schema": {
    "version": "1.0",
    "type": "goal_tree",
    "fields": {
      "smart_goal": "string",
      "point_a": "string",
      "point_b": "string",
      "goal_deadline": "string",
      "real_motivation": "string",
      "why_tree": ["string"],
      "constraint_tree": ["string"],
      "action_plan": [{"week": "string", "actions": ["string"]}],
      "success_metrics": ["string"],
      "risks": ["string"],
      "auto_filled_fields": ["string"]
    }
  },

  "project_fields_mapping": {
    "goal_statement": "output.smart_goal",
    "point_a": "output.point_a",
    "point_b": "output.point_b",
    "goal_deadline": "output.goal_deadline",
    "success_metrics": "output.success_metrics",
    "constraints": "output.constraint_tree"
  },

  "test_cases": [
    {
      "input": {
        "point_a": "работаю в найме, хочу своё дело",
        "point_b": "свой прибыльный онлайн-магазин",
        "goal_deadline": "через год",
        "why_important": "хочу финансовую независимость и работать на себя"
      },
      "expected_artifact_type": "goal_tree",
      "expected_fields": ["smart_goal", "why_tree", "action_plan", "success_metrics"]
    }
  ]
}
```

> **`project_fields_mapping`** — явный маппинг: какое поле ProjectProfile берётся из какого поля output_schema. Заменяет неявный список `project_fields_written`. Движок использует этот маппинг для обновления ProjectProfile после генерации артефакта.

### 8.3 Поля манифеста

| Поле | Тип | Описание |
|------|-----|---------|
| `id` | string | Уникальный идентификатор (snake_case) |
| `name` / `emoji` / `description` | string | Для отображения |
| `credit_cost` | integer | Стоимость (1–5) |
| `available_on_free` | boolean | Доступен на Free |
| `schema_version` | string | Версия манифеста |
| `requires` | array[string] | Типы артефактов-зависимостей |
| `provides` | array[string] | Типы создаваемых артефактов |
| `mode` | enum | `"standard"` или `"mentor"` |
| `mentor_config` | object | Конфиг ментора (только если mode=mentor) |
| `mentor_config.non_autofill_fields` | array[string] | Поля, которые НЕЛЬЗЯ автозаполнять |
| `llm_config` | object | Провайдер/модель для slot-filling и генерации |
| `tools` | array | Разрешённые инструменты |
| `tools_require_paid` | array | Инструменты только для Paid |
| `input_schema.fields` | array | Поля для сбора |
| `question_plan` | array | Порядок вопросов |
| `output_schema` | object | Схема артефакта с версией |
| `project_fields_mapping` | object | `{project_field: "output.field_path"}` — явный маппинг |
| `test_cases` | array | Примеры для тестирования |

**Поля в `input_schema.fields`:**

| Подполе | Тип | Описание |
|---------|-----|---------|
| `id` | string | Имя поля (snake_case) |
| `label` | string | Название для логов |
| `type` | enum | `text`, `number`, `choice`, `multi_choice`, `yes_no` |
| `required` | boolean | Обязательное |
| `max_length` | integer | Для type=text |
| `choices` | array | Для choice/multi_choice |
| `question` | string | Текст вопроса |
| `hint` | string | Подсказка |
| `condition` | object | `{"field": "x", "value": "y"}` |
| `extract_from_free_text` | boolean | Разрешено ли smart_extractor'у извлекать это поле |
| `mentor_note` | string | Инструкция для ментор-режима |

### 8.4 Ментор-режим

В стандартном режиме: задал вопрос → принял любой ответ → следующий.

В ментор-режиме:
1. Задаёт вопрос в стиле, определённом `mentor_config.persona`
2. Оценивает качество ответа по `mentor_note`
3. Если поверхностный/нереалистичный — уточняет (до 3 раз на поле)
4. Поля из `non_autofill_fields` — никогда не автозаполняются
5. Если цель нереалистична — честно говорит и предлагает переформулировать

**Критерии оценки (goal_setting):**
- `point_a`: есть факты о текущем положении?
- `point_b`: измеримо? реалистично за срок?
- `why_important`: реальная мотивация или декларативное «надо/хочу»?

**Тон:** взрослый, понимающий, инициативный. В меру жёсткий — если цель размытая, скажет прямо.

### 8.5 Жизненный цикл выполнения

**1. INIT (инициируется `LAUNCH_MINISERVICE`)**
- Оркестратор передаёт: `miniservice_id`, `project_id`, `prefilled_fields` (из `extracted_fields`)
- Проверка кредитов. Нет → сообщение, предложить апгрейд
- Создание `MiniserviceRun` (`status=collecting`)
  - `mode = "sequential"` если `dep_chain:{uid}` существует, иначе `"standalone"`
- Запись состояния в Redis (`dialog:{uid}`)
- `prefilled_fields` + поля из ProjectProfile → `collected_fields` (без вопросов по ним)
- Оркестратор задаёт первый пропущенный обязательный вопрос

**2. COLLECTING**
- Входящее сообщение → smart_extractor применил результаты к `collected_fields`
- Оркестратор проверяет что ещё нужно → продолжает диалог
- В ментор-режиме: оценка качества → уточнение или фиксация
- Все required заполнены? → PROCESSING

**3. PROCESSING**
- `status = processing`, Celery task, «⏳ Анализирую...»
- Worker: LLM + поиск + генерация `content`
- Haiku генерирует `summary` из `content` (короткий отдельный вызов)
- Сохранение `Artifact` в БД
- Обновление ProjectProfile через `project_fields_mapping`
- Проверка конфликтов → ChangeProposal если нужен
- Если `dep_chain:{uid}` существует → взять следующий из chain

**4. COMPLETED**
- `status = completed`
- Списание кредитов: `credits_remaining -= credit_cost`
- Отправка результата (chunked если > 4000 символов)
- Кнопки: `[📥 PDF]` `[📊 Sheets]` (Sheets только Paid)
- Если `dep_chain` пуст и был active → запустить `target_miniservice`

**5. FAILED** — `credits_spent = 0`
**6. PARTIALLY_COMPLETED** — `credits_spent = credit_cost // 2`

### 8.6 Разбивка длинных сообщений

Если результат > 4000 символов: разбить по абзацам, «📄 Результат (часть 1/N):»

---

## 9. Спецификация минисервисов

> Структура артефакта, вопросы и логика каждого минисервиса описаны в его манифесте и меняются независимо от движка. Спецификации ниже — текущие версии (schema_version = 1.0).

---

### 9.1 Постановка целей (`goal_setting`)

**Стоимость:** 1 кредит | **Free:** ✅ | **Требует:** — | **Предоставляет:** `goal_tree`

**Режим:** `mentor`

**Поля для сбора:**

| Поле | Тип | Обяз. | Автоизвлечение | Описание |
|------|-----|-------|----------------|---------|
| `point_a` | text | ✅ | ✅ | Текущее положение |
| `point_b` | text | ✅ | ✅ | Желаемое будущее |
| `goal_deadline` | text | ✅ | ✅ | Срок в свободном формате |
| `why_important` | text | ✅ | ❌ | Глубокая мотивация — только через разговор |
| `constraints` | text | ❌ | ✅ | Ограничения |
| `success_metric` | text | ❌ | ✅ | Метрика достижения |

**Артефакт `goal_tree` (schema_version: 1.0):**
```json
{
  "smart_goal": "string",
  "point_a": "string",
  "point_b": "string",
  "goal_deadline": "string",
  "real_motivation": "string",
  "why_tree": ["string", "string", "string"],
  "constraint_tree": ["string"],
  "action_plan": [{"week": "string", "actions": ["string"]}],
  "success_metrics": ["string"],
  "risks": ["string"],
  "auto_filled_fields": ["string"]
}
```

**Формат вывода:**
```
🎯 Твоя SMART-цель:
[текст]

📍 Сейчас (точка А): [текст]
🏁 Куда идёшь (точка Б): [текст]
📅 Дедлайн: [срок]

💡 Почему это важно:
[реальная мотивация]

🌳 Три уровня «зачем»:
[список]

🚧 Что может помешать:
[список]

📅 30-дневный план:
Неделя 1: ...

📊 Метрики успеха:
[список]

⚠️ Риски:
[список]
```

**`project_fields_mapping`:** `goal_statement → smart_goal`, `point_a → point_a`, `point_b → point_b`, `goal_deadline → goal_deadline`, `success_metrics → success_metrics`, `constraints → constraint_tree`

---

### 9.2 Выбор ниши + декомпозиция (`niche_selection`)

**Стоимость:** 2 кредита | **Free:** ✅ | **Требует:** `goal_tree` | **Предоставляет:** `niche_table`

**Поля для сбора:**

| Поле | Тип | Обяз. | Вопрос |
|------|-----|-------|--------|
| `geography` | choice | ✅ | `[Россия / Казахстан / Беларусь / Весь СНГ]` |
| `available_capital` | choice | ✅ | `[до 50 тыс. / 50–200 тыс. / 200–500 тыс. / 500 тыс.+]` |
| `competencies` | text | ✅ | Что умеешь, какой опыт? |
| `format` | multi_choice | ✅ | `[Товары / Услуги / Инфопродукты / Всё рассмотреть]` |
| `channels` | multi_choice | ✅ | `[Маркетплейсы / Соцсети / Telegram / Офлайн / Всё]` |
| `target_margin` | choice | ❌ | `[до 20% / 20–40% / 40%+]` |
| `operations_readiness` | yes_no | ❌ | Готов к высокой операционной нагрузке? |

**Контекст из goal_tree:** `smart_goal`, `constraint_tree`, `goal_deadline` подставляются автоматически.

**Артефакт `niche_table` (schema_version: 1.0):**
```json
{
  "niches": [{
    "name": "string",
    "potential": "1-5",
    "competition": "1-5",
    "entry_threshold": "1-5",
    "resource_fit": "1-5",
    "total_score": "4-20",
    "decomposition": {
      "product": "string",
      "audience_segments": ["string"],
      "channels": ["string"],
      "demand_hypotheses": ["string"],
      "risks": ["string"],
      "first_tests": ["string"]
    }
  }],
  "recommendation": "string",
  "recommended_niche": "string"
}
```

**`project_fields_mapping`:** `niche_candidates → niches`, `chosen_niche → recommended_niche`, `hypothesis_table → niches[*].decomposition`, `geography → geography` (из collected_fields), `budget_range → available_capital` (mapped), `business_model → format` (mapped: Товары→B2C, Услуги→B2B, остальное→hybrid)

---

### 9.3 Поиск поставщиков (`supplier_search`)

**Стоимость:** 2 кредита | **Free:** ✅ | **Требует:** `niche_table` | **Предоставляет:** `supplier_list`

**Поля для сбора:**

| Поле | Тип | Обяз. | Вопрос |
|------|-----|-------|--------|
| `product_description` | text | ✅ | Что ищем? Характеристики (max 300 символов) |
| `target_geography` | choice | ✅ | `[Россия / Казахстан / Беларусь / СНГ / Несколько]` |
| `supplier_origin` | multi_choice | ✅ | `[Китай / Россия / Турция / Без разницы]` |
| `moq_preference` | choice | ❌ | `[до 10 шт / 10–50 / 50–200 / 200+]` |
| `budget_per_unit` | text | ❌ | Целевая цена за единицу? |
| `quality_requirements` | text | ❌ | Требования к качеству? |
| `payment_terms` | multi_choice | ❌ | `[Предоплата / Постоплата / Без разницы]` |

> Если `niche_table` существует — `product_description` и `target_geography` берутся из него автоматически как prefilled_fields.

> **Комплаенс:** только публичные источники через Tavily.

**Артефакт `supplier_list` (schema_version: 1.0):**
```json
{
  "suppliers": [{
    "name": "string",
    "country": "string",
    "type": "manufacturer | distributor | wholesaler",
    "url": "string | null",
    "moq": "string",
    "conditions": "string",
    "pros": ["string"],
    "cons": ["string"]
  }],
  "comparison_table": {
    "criteria": ["string"],
    "rows": [{"supplier": "string", "values": ["string"]}]
  },
  "email_templates": ["string", "string"],
  "verification_checklist": ["string"]
}
```

**`project_fields_mapping`:** `{}` (артефакт привязывается к проекту, ProjectProfile не обновляет)

---

### 9.4 Скрипты продаж (`sales_scripts`)

**Стоимость:** 2 кредита | **Free:** ✅ | **Требует:** `goal_tree`, `niche_table` | **Предоставляет:** `sales_script`

**Поля для сбора:**

| Поле | Тип | Обяз. | Вопрос |
|------|-----|-------|--------|
| `product_offer` | text | ✅ | Что продаём? Ключевые преимущества |
| `target_persona` | text | ✅ | Кто покупатель? Роль, боль, контекст |
| `sales_format` | choice | ✅ | `[Холодный звонок / Входящий / Переписка / Email]` |
| `business_type` | choice | ✅ | `[B2B / B2C]` |
| `average_check` | text | ❌ | Средний чек? |
| `main_objections` | text | ❌ | Частые возражения? |
| `brand_tone` | choice | ❌ | `[Дружелюбный / Экспертный / Напористый / Нейтральный]` |

> Если `niche_table` и `goal_tree` существуют — `product_offer`, `target_persona`, `business_type` берутся из них как prefilled_fields.

**Артефакт `sales_script` (schema_version: 1.0):**
```json
{
  "format": "call | chat | email",
  "script": {
    "opening": "string",
    "discovery_questions": ["string"],
    "presentation": "string",
    "closing": {"soft": "string", "direct": "string"}
  },
  "objection_map": [{"objection": "string", "responses": ["string", "string"]}],
  "followup_sequence": [
    {"day": 1, "message": "string"},
    {"day": 3, "message": "string"},
    {"day": 7, "message": "string"}
  ],
  "preparation_checklist": ["string"]
}
```

**`project_fields_mapping`:** `{}`

---

### 9.5 Продающие объявления (`ad_creation`)

**Стоимость:** 2 кредита | **Free:** ✅ (текст) | **Требует:** `niche_table` | **Предоставляет:** `ad_set`

**Поля для сбора:**

| Поле | Тип | Обяз. | Вопрос |
|------|-----|-------|--------|
| `platform` | choice | ✅ | `[Avito / OLX / Wildberries / ВКонтакте / Instagram / Telegram / Другое]` |
| `product_name` | text | ✅ | Что продаём? |
| `key_benefits` | text | ✅ | 3–5 главных преимуществ |
| `target_audience` | text | ✅ | Опиши покупателя |
| `price_positioning` | choice | ❌ | `[Эконом / Средний / Премиум]` |
| `unique_selling_point` | text | ❌ | Чем отличаешься? |
| `call_to_action` | text | ❌ | Желаемое действие покупателя? |
| `tone` | choice | ❌ | `[Дружелюбный / Деловой / Срочный / Экспертный]` |

Ограничения платформ в промпте: Avito заголовок ≤ 50, WB ≤ 100, Telegram ≤ 1024 символов.

**Артефакт `ad_set` (schema_version: 1.0):**
```json
{
  "platform": "string",
  "ad_variants": [{"title": "string", "body": "string", "cta": "string"}],
  "card_structure": {"title": "string", "description": "string", "keywords": ["string"]},
  "visual_checklist": ["string"],
  "images": ["url_string"]
}
```

**`project_fields_mapping`:** `{}`

---

### 9.6 Поиск клиентов (`lead_search`)

**Стоимость:** 3 кредита | **Free:** ❌ | **Требует:** `niche_table`, `goal_tree` | **Предоставляет:** `lead_list`

> Только публичные данные или предоставленные пользователем.

**Обязательное согласие перед запуском:**
```
⚠️ Этот инструмент анализирует только публично доступные данные
или текст, который ты вставляешь сам.
Продолжая, ты подтверждаешь право использовать предоставленные данные.

[Понятно, продолжить]  [Отмена]
```

**Поля для сбора:**

| Поле | Тип | Обяз. | Условие | Вопрос |
|------|-----|-------|---------|--------|
| `lead_source` | choice | ✅ | — | `[Вставлю текст / Публичные форумы / Дай стратегию]` |
| `source_content` | text | ✅ | lead_source=«Вставлю текст» | Вставь текст (до 5000 символов) |
| `search_query` | text | ✅ | lead_source=«Публичные форумы» | По какому запросу искать? |
| `target_persona` | text | ❌ | — | Уточни идеального клиента (если нужно дополнить данные из ниши) |

> `product_offer` больше не является отдельным полем: берётся автоматически из `niche_table.recommendation` и `goal_tree.smart_goal` как prefilled_fields.

**Аудит:** каждый запуск логируется с источником данных, timestamp, user_id.

**Артефакт `lead_list` (schema_version: 1.0):**
```json
{
  "leads": [{
    "identifier": "string",
    "source": "string",
    "quote": "string",
    "temperature": "hot | warm | cold",
    "suggested_message": "string"
  }],
  "search_strategy": "string",
  "search_queries": ["string"],
  "total_found": 0
}
```

**`project_fields_mapping`:** `{}`

---

## 10. Управление проектами

### 10.1 Проект — обязательная единица работы

Каждый минисервис работает внутри проекта. Проект создаётся при онбординге или автоматически перед первым запуском минисервиса.

### 10.2 Создание проекта

1. Проверка лимита: Free — max 2, Paid — max 20
2. При лимите → сообщение + предложить апгрейд
3. Оркестратор спрашивает название
4. Создание: «📁 Проект «{название}» создан. Начинаем с [минисервис]»

### 10.3 Контекст проекта в минисервисе

При запуске:
- Поля ProjectProfile → `prefilled_fields` (не задаём заново)
- `extracted_fields[miniservice_id]` → дополнительные prefilled_fields
- Существующие артефакты → `summary` в OrchestratorContext
- Оркестратор явно называет использованные данные

---

## 11. Механика артефактов

### 11.1 Версионирование схемы

Каждый артефакт хранит `artifact_schema_version`. При изменении output_schema в манифесте — инкрементируется версия. Старые артефакты читаются по старой версии. Новые создаются с новой.

### 11.2 Версионирование артефактов

- Повторный запуск: старый `is_current = False`, новый `version = prev + 1`, `is_current = True`
- История — по запросу через оркестратор

### 11.3 Экспорт

| Формат | Доступно | Примечание |
|--------|----------|-----------|
| Текст в боте | Free + Paid | Всегда |
| PDF | Free + Paid | Jinja2 → WeasyPrint → файл → отправить → удалить |
| Google Sheets | Только Paid | `niche_table`, `supplier_list`, `lead_list` |

---

## 12. Механика конфликтов контекста

### 12.1 Когда создаётся ChangeProposal

После завершения минисервиса: движок проходит по `project_fields_mapping` и сравнивает новые значения с текущими в ProjectProfile.

### 12.2 Типы изменений

| Тип | Поведение |
|-----|-----------|
| Поле было `null` | Применяется автоматически |
| Добавление в массивы (`niche_candidates`) | Мердж без уведомления |
| Изменение `goal_statement`, `chosen_niche`, `business_model` | ChangeProposal → запрос пользователю |

### 12.3 Сообщение о конфликте

```
⚠️ Обнаружено изменение в профиле проекта

Новые данные из [минисервис] отличаются от сохранённых:

📌 Ниша:
  Было: «Продажа обуви оптом»
  Стало: «Продажа кроссовок через маркетплейсы»

Это затронет 3 артефакта.

[✅ Принять изменения]  [❌ Оставить как было]
```

### 12.4 Действия

**Принять:** ProjectProfile обновляется, `is_outdated = True` у затронутых артефактов, оркестратор предлагает обновить.

**Отклонить:** ProjectProfile не меняется, новый артефакт сохраняется.

---

## 13. LLM-стратегия

### 13.1 LLMGateway

```python
@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached: bool
    duration_ms: int

class LLMGateway:
    async def complete(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        system: str | None,
        max_tokens: int,
        temperature: float,
        timeout: int,
        run_id: UUID | None,      # nullable — для оркестраторских вызовов
        cache_key: str | None
    ) -> LLMResponse: ...
```

### 13.2 Структура промпта (Prompt Caching)

```
[SYSTEM — статичный, кэшируется]
[CONTEXT — полустатичный: проекты, артефакты]
[CONVERSATION HISTORY — динамика]
[USER MESSAGE — динамика]
```

Статичное — в начало (кэшируется провайдером). Динамика — в конец.

### 13.3 Токенные лимиты

| Вызов | Max input | Max output | Модель |
|-------|-----------|------------|--------|
| Оркестратор | 6 000 | 1 000 | claude-sonnet-4-5 |
| Smart extractor | 2 000 | 800 | claude-haiku-4-5 |
| Ментор (goal_setting) | 3 000 | 800 | claude-sonnet-4-5 |
| Summary generation | 2 000 | 200 | claude-haiku-4-5 |
| niche_selection | 3 000 | 3 000 | claude-sonnet-4-5 |
| supplier_search | 4 000 | 2 000 | claude-sonnet-4-5 |
| sales_scripts | 2 000 | 2 500 | claude-sonnet-4-5 |
| ad_creation | 2 000 | 2 000 | gpt-4o-mini |
| lead_search | 5 000 | 1 500 | claude-haiku-4-5 |
| slot_filling (извлечение) | 500 | 300 | claude-haiku-4-5 |

> Smart extractor вызывается на каждом сообщении. При токене входа < 100 символов (очень короткое сообщение) — smart extractor пропускается (нечего извлекать, экономия).

### 13.4 Redis-кэш

- Ключ: `llm_cache:{sha256(model + system + user_data)}`, TTL 1 час
- **Применяется:** slot-filling (извлечение), summary generation
- **Не применяется:** оркестратор, ментор-диалог, smart extractor, генерация артефактов

### 13.5 Деградация при ошибках

| Ситуация | Поведение |
|----------|-----------|
| Smart extractor ошибка | Продолжить без извлечения, обычный поток |
| Оркестратор ошибка | Fallback: «Что-то пошло не так, попробуй ещё раз» |
| Невалидный JSON оркестратора | Повтор с `temperature=0`, затем fallback |
| LLM минисервиса таймаут | 1 retry → `failed`, без кредитов |
| Невалидный JSON минисервиса | 1 retry строгий промпт → `partially_completed` |
| Ошибка 5xx | 2 retry через 5s → `failed` |
| Rate limit 429 | Backoff: 5s → 15s → 30s |
| Tavily недоступен | Без поиска, пометка в артефакте |

---

## 14. Интеграции

### 14.1 Tavily

- В: `supplier_search`, `niche_selection`, `lead_search`
- Max 5 запросов на запуск, кэш TTL 2 часа
- При недоступности: fallback без поиска, артефакт помечается

### 14.2 Google Sheets (только Paid)

Service Account (`GOOGLE_SERVICE_ACCOUNT_JSON`). При первом экспорте показывается `GOOGLE_SERVICE_ACCOUNT_EMAIL` с инструкцией. Поток: ссылка или «создать новую» → запись → URL в `Artifact.google_sheets_url`.

### 14.3 DALL-E 3 (только Paid)

`size=1024x1024`, `quality=standard`, `n=1`. Лимит: 2 изображения на запуск `ad_creation`.

### 14.4 PDF (WeasyPrint)

Jinja2-шаблон → WeasyPrint → `/tmp/pdf/{run_id}.pdf` → отправить → удалить. PDF не хранится.

---

## 15. Биллинг

### 15.1 Тарифы

| Параметр | Free | Paid |
|----------|------|------|
| Кредиты в месяц | 3 | 30 |
| Максимум проектов | 2 | 20 |
| Google Sheets экспорт | ❌ | ✅ |
| Генерация изображений | ❌ | ✅ |
| «Поиск клиентов» | ❌ | ✅ |
| Цена | 0 ₽ | 990 ₽/мес |

### 15.2 Стоимость минисервисов

| Минисервис | Кредитов |
|------------|---------|
| Постановка целей | 1 |
| Выбор ниши | 2 |
| Поиск поставщиков | 2 |
| Скрипты продаж | 2 |
| Продающие объявления | 2 |
| Поиск клиентов | 3 |

> **Оркестраторские вызовы, smart extractor, ментор-диалог, summary generation — кредиты не расходуют.**

### 15.3 Правила списания

- `completed` → полная стоимость
- `partially_completed` → `credit_cost // 2`
- `failed` → не списывается
- Отмена → не списывается
- Сброс: 1-е число каждого месяца (Celery Beat)

**Остаток после завершения:**
```
✅ Готово! Использовано 2 кредита (остаток: 1/3 в этом месяце)
```
При остатке 1 кредит: предупреждение + ссылка на апгрейд.

### 15.4 Монетизация в v0.1 — ручная

Нет автобиллинга. При запросе апгрейда — реквизиты/ссылку. Администратор активирует через admin-команду.

### 15.5 Admin-команды (только `BOT_ADMIN_CHAT_ID`)

| Команда | Действие |
|---------|---------|
| `/admin_upgrade {telegram_id}` | Поднять до Paid на 30 дней |
| `/admin_downgrade {telegram_id}` | Вернуть на Free |
| `/admin_credits {telegram_id} {amount}` | Начислить кредиты |
| `/admin_stats` | Сводная статистика |
| `/admin_block {telegram_id}` | Заблокировать |

**Вывод `/admin_stats`:**
```
📊 Статистика за 7 дней

👥 Пользователи: 142 | Новые: 23
⚡ Запуски: 89 (✅80% / ❌7% / 🔘13%)
🔝 Топ: supplier_search 34, niche_selection 21, goal_setting 18

💳 Free: 128 | Paid: 14
   upgrade_cta CTR: 18% | credits_exhausted: 11

🤖 Оркестратор:
   calls: 1240 | avg_confidence: 0.91
   confirmation_rate: 4%
   dep_resolution: 23%
   smart_extract_rate: 89% (доля сообщений с хотя бы одним извлечённым полем)
   mentor_fallback_rate: 12%
```

---

## 16. Безопасность

### 16.1 Webhook

- Проверка `X-Telegram-Bot-Api-Secret-Token`
- HTTP 403 при несовпадении
- Только HTTPS, `allowed_updates=["message","callback_query"]`

### 16.2 Идемпотентность

`processed_update:{update_id}` в Redis, TTL 24 часа.

### 16.3 Авторизация

- Все запросы: `WHERE user_id = :current_user_id`
- Чужой объект → HTTP 404 (не 403)

### 16.4 Rate Limiting

| Уровень | Лимит | Реакция |
|---------|-------|---------|
| Telegram | 30 сообщений/мин | Игнорировать |
| Оркестратор | 1 параллельный вызов на пользователя | Следующий ждёт |
| Celery | 10 одновременных tasks на пользователя | Ждёт в очереди |
| Минисервисы | 1 активный запуск на пользователя | Оркестратор сообщает |
| LLM суммарно | 300 вызовов/день на пользователя | Сообщение об исчерпании |

> Лимит 300 (не 200): smart extractor добавляет вызов на каждое сообщение.

### 16.5 Prompt Injection

- Пользовательский текст — только в `user`-роль
- История — структурированный массив, не строка
- Санитизация: удаляются `[INST]`, `<|im_start|>`, `###`
- Allow-lists инструментов из манифеста

### 16.6 Приватность

- `conversation:{uid}`: TTL 7 дней
- `dialog:{uid}`: TTL 24 часа
- `extracted_fields:{uid}`: TTL 2 часа
- `pending_confirmation:{uid}`: TTL 10 минут
- `/delete_account`: мягкое удаление + полное через 30 дней

---

## 17. Обработка ошибок

### 17.1 Классификация

| Тип | Поведение |
|-----|-----------|
| `OrchestratorError` | Fallback, предложение переформулировать |
| `ExtractorError` | Пропустить извлечение, обычный поток |
| `UserError` | Оркестратор объясняет |
| `LLMError` | Retry → `failed`, без кредитов |
| `IntegrationError` | Fallback или сообщение |
| `SystemError` | Sentry, generic сообщение |
| `ValidationError` | Retry → `partially_completed` |

### 17.2 Celery Task

```python
@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    soft_time_limit=110,
    time_limit=120
)
def run_miniservice_task(self, run_id: str):
    try:
        ...
    except LLMRateLimitError as exc:
        raise self.retry(exc=exc, countdown=15)
    except (LLMTimeoutError, LLMAPIError) as exc:
        raise self.retry(exc=exc, countdown=5)
    except Exception as exc:
        update_run_status(run_id, "failed", str(exc))
        notify_user_about_failure(run_id)
        sentry_sdk.capture_exception(exc)
```

---

## 18. Аналитика

### 18.1 Список событий

**Онбординг:**
- `onboarding_started`, `onboarding_completed {role, primary_goal}`, `onboarding_abandoned`

**Smart extractor:**
- `smart_extract_called {message_length}`
- `smart_extract_success {fields_found_count, miniservices_enriched}`
- `smart_extract_fields_applied {miniservice_id, fields_applied}`

**Оркестратор:**
- `orchestrator_called {intent, confidence, action}`
- `orchestrator_confirmation_shown {intent, confidence}`
- `orchestrator_confirmation_accepted`, `orchestrator_confirmation_rejected`
- `orchestrator_dep_chain_initiated {target, missing_count}`
- `orchestrator_dep_chain_completed {target}`
- `orchestrator_mentor_fallback {miniservice_id, field_id, attempt_number}`
- `orchestrator_fallback`

**Минисервисы:**
- `miniservice_started {miniservice_id, mode, is_dep_chain}`
- `miniservice_field_collected {miniservice_id, field_id, was_auto_extracted}`
- `miniservice_field_autofilled {miniservice_id, field_id}` — fallback автозаполнение
- `miniservice_abandoned {miniservice_id, last_field}`
- `miniservice_completed {miniservice_id, duration_seconds, credits_spent, tokens_used}`
- `miniservice_failed {miniservice_id, error_type}`
- `miniservice_partially_completed {miniservice_id}`

**Проекты и артефакты:**
- `project_created`, `artifact_viewed`, `artifact_exported_pdf`, `artifact_exported_sheets`
- `change_proposal_shown`, `change_proposal_accepted`, `change_proposal_rejected`

**Биллинг:**
- `upgrade_cta_shown {trigger}`, `upgrade_cta_clicked`, `credits_exhausted`

### 18.2 Ключевые метрики

| Метрика | Формула |
|---------|---------|
| Completion Rate | `completed / (completed + abandoned + failed)` по `miniservice_id` |
| Onboarding Conversion | `onboarding_completed / onboarding_started` |
| Time to First Value | `first miniservice_completed - onboarding_completed` |
| Smart Extract Effectiveness | `fields_applied / fields_found_total` — доля извлечённых полей, которые реально использованы |
| Dep Chain Rate | `dep_chain_initiated / miniservice_started` |
| Mentor Depth | среднее `attempt_number` по `miniservice_mentor_probe` |
| Orchestrator Confidence | среднее по `orchestrator_called.confidence` |
| Upgrade CTA CTR | `upgrade_cta_clicked / upgrade_cta_shown` |

---

## 19. Деплой

### 19.1 docker-compose.yml

```yaml
version: '3.9'
services:
  app:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    env_file: .env
    depends_on: [postgres, redis]
    restart: unless-stopped
    ports: ["8000:8000"]

  worker:
    build: .
    command: celery -A app.workers.celery_app worker --loglevel=info --concurrency=4
    env_file: .env
    depends_on: [postgres, redis]
    restart: unless-stopped

  beat:
    build: .
    command: celery -A app.workers.celery_app beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    env_file: .env
    depends_on: [postgres, redis]
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: [postgres_data:/var/lib/postgresql/data]
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes: [redis_data:/data]
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### 19.2 Dockerfile

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 \
    libffi-dev libcairo2 libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 19.3 Nginx

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location /webhook {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 15s;
    }

    location / { return 404; }
}
```

### 19.4 Регистрация Webhook

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "'"${TELEGRAM_WEBHOOK_URL}"'",
    "allowed_updates": ["message", "callback_query"],
    "max_connections": 40,
    "secret_token": "'"${TELEGRAM_WEBHOOK_SECRET}"'"
  }'
```

### 19.5 Celery Beat расписание

```python
app.conf.beat_schedule = {
    "reset_monthly_credits": {
        "task": "app.workers.billing_tasks.reset_monthly_credits",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),
    },
    "cleanup_expired_dialogs": {
        "task": "app.workers.cleanup_tasks.cleanup_expired_dialogs",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup_tmp_pdfs": {
        "task": "app.workers.cleanup_tasks.cleanup_tmp_pdfs",
        "schedule": crontab(hour=4, minute=0),
    },
}
```

### 19.6 Миграции

```bash
docker-compose exec app alembic upgrade head
```

### 19.7 Мониторинг

- **Sentry:** все ERROR и выше
- **Алерт в `BOT_ADMIN_CHAT_ID`:** при >5 failed tasks в минуту
- **Логи:** `structlog` → JSON → stdout

---

## 20. Что явно НЕ входит в v0.1

| Функция | Когда |
|---------|-------|
| Веб-интерфейс / Mini App | v0.2 |
| Telegram Stars / автобиллинг | v0.2 |
| Клонирование проектов | v0.2 |
| Мультиязычность | v0.2+ |
| Автопарсинг Telegram-групп | v0.2+ — правовые риски |
| Командные проекты | v0.2+ |
| Аналитический дашборд | v0.2 |
| Кастомные минисервисы (маркетплейс) | v0.3+ |
| CRM-интеграции | v0.2+ |
| Email-нотификации | v0.2 |
| Уведомления о сбросе кредитов | v0.2 |
| A/B тестирование промптов | v0.2 |
| Долгосрочная память (> 7 дней) | v0.2 |
| Голосовые сообщения | v0.2+ |
| Полное удаление аккаунта (фоновая задача) | v0.2 — заготовка есть |

---

*Документ является полной и самодостаточной спецификацией для разработки v0.1.*
*Любые решения, не отражённые здесь, требуют явного обновления документа перед реализацией.*
