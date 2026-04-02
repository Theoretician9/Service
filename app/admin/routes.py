import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select, case, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.modules.users.models import User
from app.modules.billing.models import UserPlan
from app.modules.artifacts.models import MiniserviceRun

router = APIRouter(prefix="/admin")

# ── Token store (in-memory, survives until restart) ──────────────────────

_active_tokens: dict[str, datetime] = {}
TOKEN_TTL_HOURS = 24


def _generate_token() -> str:
    return secrets.token_urlsafe(48)


def _cleanup_tokens():
    now = datetime.now(timezone.utc)
    expired = [t for t, exp in _active_tokens.items() if exp < now]
    for t in expired:
        del _active_tokens[t]


def _verify_token(token: str) -> bool:
    _cleanup_tokens()
    return token in _active_tokens


async def require_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth[7:]
    if not _verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Auth endpoint ────────────────────────────────────────────────────────

@router.post("/api/login")
async def admin_login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    if username == settings.admin_username and password == settings.admin_password:
        token = _generate_token()
        _active_tokens[token] = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
        return {"token": token}
    raise HTTPException(status_code=401, detail="Invalid credentials")


# ── Dashboard stats ──────────────────────────────────────────────────────

@router.get("/api/dashboard", dependencies=[Depends(require_auth)])
async def dashboard_stats(session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Total users
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0

    # Active users 7d (users who have runs started in last 7 days)
    active_users_7d = (await session.execute(
        select(func.count(func.distinct(MiniserviceRun.user_id)))
        .where(MiniserviceRun.started_at >= week_ago)
    )).scalar() or 0

    # Run stats
    total_runs = (await session.execute(select(func.count(MiniserviceRun.id)))).scalar() or 0
    completed_runs = (await session.execute(
        select(func.count(MiniserviceRun.id)).where(MiniserviceRun.status == "completed")
    )).scalar() or 0
    failed_runs = (await session.execute(
        select(func.count(MiniserviceRun.id)).where(MiniserviceRun.status == "failed")
    )).scalar() or 0

    # Aggregates
    total_credits_spent = (await session.execute(
        select(func.coalesce(func.sum(MiniserviceRun.credits_spent), 0))
    )).scalar() or 0
    total_tokens_used = (await session.execute(
        select(func.coalesce(func.sum(MiniserviceRun.llm_tokens_used), 0))
    )).scalar() or 0
    total_searches_used = (await session.execute(
        select(func.coalesce(func.sum(MiniserviceRun.web_searches_used), 0))
    )).scalar() or 0

    # Runs by miniservice
    by_ms_rows = (await session.execute(
        select(MiniserviceRun.miniservice_id, func.count(MiniserviceRun.id))
        .group_by(MiniserviceRun.miniservice_id)
    )).all()
    runs_by_miniservice = {row[0]: row[1] for row in by_ms_rows}

    # Runs by status
    by_status_rows = (await session.execute(
        select(MiniserviceRun.status, func.count(MiniserviceRun.id))
        .group_by(MiniserviceRun.status)
    )).all()
    runs_by_status = {row[0]: row[1] for row in by_status_rows}

    return {
        "total_users": total_users,
        "active_users_7d": active_users_7d,
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "total_credits_spent": int(total_credits_spent),
        "total_tokens_used": int(total_tokens_used),
        "total_searches_used": int(total_searches_used),
        "runs_by_miniservice": runs_by_miniservice,
        "runs_by_status": runs_by_status,
    }


# ── Users list ───────────────────────────────────────────────────────────

@router.get("/api/users", dependencies=[Depends(require_auth)])
async def list_users(session: AsyncSession = Depends(get_session)):
    # Subquery: per-user run stats
    run_stats = (
        select(
            MiniserviceRun.user_id,
            func.count(MiniserviceRun.id).label("total_runs"),
            func.count(case((MiniserviceRun.status == "completed", 1))).label("completed_runs"),
            func.coalesce(func.sum(MiniserviceRun.llm_tokens_used), 0).label("total_tokens"),
            func.coalesce(func.sum(MiniserviceRun.credits_spent), 0).label("total_credits_spent"),
            func.max(MiniserviceRun.started_at).label("last_activity"),
        )
        .group_by(MiniserviceRun.user_id)
        .subquery()
    )

    query = (
        select(
            User.id,
            User.telegram_id,
            User.username,
            User.first_name,
            User.onboarding_completed,
            User.created_at,
            UserPlan.plan_type,
            UserPlan.credits_remaining,
            UserPlan.credits_monthly_limit,
            run_stats.c.total_runs,
            run_stats.c.completed_runs,
            run_stats.c.total_tokens,
            run_stats.c.total_credits_spent,
            run_stats.c.last_activity,
        )
        .outerjoin(UserPlan, User.id == UserPlan.user_id)
        .outerjoin(run_stats, User.id == run_stats.c.user_id)
        .order_by(User.created_at.desc())
    )

    rows = (await session.execute(query)).all()
    users = []
    for r in rows:
        users.append({
            "id": str(r[0]),
            "telegram_id": r[1],
            "username": r[2] or "",
            "first_name": r[3] or "",
            "plan_type": r[6] or "free",
            "credits_remaining": r[7] if r[7] is not None else 0,
            "credits_monthly_limit": r[8] if r[8] is not None else 3,
            "total_runs": r[9] or 0,
            "completed_runs": r[10] or 0,
            "total_tokens": int(r[11] or 0),
            "total_credits_spent": int(r[12] or 0),
            "onboarding_completed": r[4] or False,
            "created_at": r[5].isoformat() if r[5] else "",
            "last_activity": r[13].isoformat() if r[13] else "",
        })
    return users


# ── Runs list ────────────────────────────────────────────────────────────

@router.get("/api/runs", dependencies=[Depends(require_auth)])
async def list_runs(session: AsyncSession = Depends(get_session)):
    query = (
        select(
            MiniserviceRun.id,
            MiniserviceRun.miniservice_id,
            MiniserviceRun.status,
            MiniserviceRun.credits_spent,
            MiniserviceRun.llm_tokens_used,
            MiniserviceRun.web_searches_used,
            MiniserviceRun.started_at,
            MiniserviceRun.completed_at,
            User.username,
            User.first_name,
            User.telegram_id,
        )
        .join(User, MiniserviceRun.user_id == User.id)
        .order_by(MiniserviceRun.started_at.desc())
    )

    rows = (await session.execute(query)).all()
    runs = []
    for r in rows:
        user_name = r[8] or r[9] or f"id:{r[10]}"
        runs.append({
            "id": str(r[0]),
            "user_name": user_name,
            "telegram_id": r[10],
            "miniservice_id": r[1],
            "status": r[2],
            "credits_spent": r[3] or 0,
            "llm_tokens_used": r[4] or 0,
            "web_searches_used": r[5] or 0,
            "started_at": r[6].isoformat() if r[6] else "",
            "completed_at": r[7].isoformat() if r[7] else "",
        })
    return runs


# ── Cost breakdown ───────────────────────────────────────────────────────

# Approximate costs per 1M tokens (input+output blended estimate)
MODEL_COSTS_PER_1M = {
    "claude-sonnet-4-5": 9.0,
    "claude-haiku-4-5": 1.0,
    "gpt-4o-mini": 0.6,
}


def _parse_log_tokens(log_path: str = "/app/logs/conversations.jsonl") -> dict:
    """Parse JSONL logs to get token usage by model (agents + orchestrator + generation)."""
    import json
    from pathlib import Path

    by_model: dict[str, dict] = {}
    p = Path(log_path)
    if not p.exists():
        return by_model

    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line.strip())
                event = d.get("event", "")
                if event in ("agent_llm_call", "llm_call"):
                    model = d.get("model", "unknown")
                    tokens_in = d.get("tokens_in", 0) or d.get("input_tokens", 0)
                    tokens_out = d.get("tokens_out", 0) or d.get("output_tokens", 0)
                    total = tokens_in + tokens_out
                    if model not in by_model:
                        by_model[model] = {"tokens": 0, "calls": 0, "tokens_in": 0, "tokens_out": 0}
                    by_model[model]["tokens"] += total
                    by_model[model]["tokens_in"] += tokens_in
                    by_model[model]["tokens_out"] += tokens_out
                    by_model[model]["calls"] += 1
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception:
        pass

    return by_model


@router.get("/api/costs", dependencies=[Depends(require_auth)])
async def cost_breakdown(session: AsyncSession = Depends(get_session)):
    # DB tokens (generation only — stored in MiniserviceRun)
    total_db_tokens = (await session.execute(
        select(func.coalesce(func.sum(MiniserviceRun.llm_tokens_used), 0))
    )).scalar() or 0

    # By miniservice from DB
    by_ms_rows = (await session.execute(
        select(
            MiniserviceRun.miniservice_id,
            func.coalesce(func.sum(MiniserviceRun.llm_tokens_used), 0),
            func.count(MiniserviceRun.id),
        )
        .group_by(MiniserviceRun.miniservice_id)
    )).all()

    by_miniservice = {}
    for row in by_ms_rows:
        by_miniservice[row[0]] = {"tokens": int(row[1]), "runs": row[2]}

    # Real token usage by model from logs (agents + orchestrator + generation)
    log_by_model = _parse_log_tokens()

    # If logs available — use real data; otherwise estimate from DB
    if log_by_model:
        by_model = {}
        for model, data in log_by_model.items():
            cost_per_m = MODEL_COSTS_PER_1M.get(model, 9.0)
            by_model[model] = {
                "tokens": data["tokens"],
                "tokens_in": data["tokens_in"],
                "tokens_out": data["tokens_out"],
                "calls": data["calls"],
                "cost": round(data["tokens"] / 1_000_000 * cost_per_m, 4),
            }
        total_tokens = sum(d["tokens"] for d in by_model.values())
    else:
        # Fallback: estimate from DB (generation tokens only)
        by_model = {}
        ms_model_map = {
            "goal_setting": "claude-sonnet-4-5",
            "niche_selection": "claude-sonnet-4-5",
            "supplier_search": "claude-sonnet-4-5",
            "sales_scripts": "claude-sonnet-4-5",
            "ad_creation": "gpt-4o-mini",
            "lead_search": "claude-sonnet-4-5",
        }
        for ms_id, data in by_miniservice.items():
            model = ms_model_map.get(ms_id, "claude-sonnet-4-5")
            if model not in by_model:
                by_model[model] = {"tokens": 0, "cost": 0.0}
            by_model[model]["tokens"] += data["tokens"]
            cost_per_m = MODEL_COSTS_PER_1M.get(model, 9.0)
            by_model[model]["cost"] += round(data["tokens"] / 1_000_000 * cost_per_m, 4)
        total_tokens = int(total_db_tokens)

    estimated_cost_usd = sum(m["cost"] for m in by_model.values())

    # Daily tokens (last 30 days) from DB
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    daily_rows = (await session.execute(
        select(
            cast(MiniserviceRun.started_at, Date).label("day"),
            func.coalesce(func.sum(MiniserviceRun.llm_tokens_used), 0),
        )
        .where(MiniserviceRun.started_at >= thirty_days_ago)
        .group_by("day")
        .order_by("day")
    )).all()

    daily_tokens = [{"date": str(row[0]), "tokens": int(row[1])} for row in daily_rows]

    return {
        "total_tokens": int(total_tokens),
        "estimated_cost_usd": round(estimated_cost_usd, 4),
        "by_model": by_model,
        "by_miniservice": by_miniservice,
        "daily_tokens": daily_tokens,
    }


# ── Serve admin HTML ────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def admin_page():
    from pathlib import Path
    html_path = Path(__file__).parent.parent.parent / "templates" / "admin" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
