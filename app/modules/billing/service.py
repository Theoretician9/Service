import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.billing.models import UserPlan


class BillingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def reserve_credits(self, user_id: uuid.UUID, amount: int, telegram_id: int | None = None) -> bool:
        """Atomically reserve credits. Returns True if successful.
        Admins have unlimited credits — always returns True without deducting."""
        if telegram_id and settings.is_admin(telegram_id):
            return True

        result = await self.session.execute(
            update(UserPlan)
            .where(UserPlan.user_id == user_id, UserPlan.credits_remaining >= amount)
            .values(credits_remaining=UserPlan.credits_remaining - amount)
            .returning(UserPlan.credits_remaining)
        )
        await self.session.commit()
        return result.scalar_one_or_none() is not None

    async def refund_credits(self, user_id: uuid.UUID, amount: int) -> None:
        """Return credits on failure or cancel."""
        await self.session.execute(
            update(UserPlan)
            .where(UserPlan.user_id == user_id)
            .values(credits_remaining=UserPlan.credits_remaining + amount)
        )
        await self.session.commit()

    async def get_plan(self, user_id: uuid.UUID) -> UserPlan | None:
        stmt = select(UserPlan).where(UserPlan.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_plan(self, user_id: uuid.UUID) -> UserPlan:
        """Get existing plan or create a free plan for new users."""
        plan = await self.get_plan(user_id)
        if plan:
            return plan

        now = datetime.now(timezone.utc)
        # Credits reset on the 1st of next month
        if now.month == 12:
            reset_at = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            reset_at = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

        plan = UserPlan(
            user_id=user_id,
            plan_type="free",
            credits_remaining=settings.free_plan_monthly_credits,
            credits_monthly_limit=settings.free_plan_monthly_credits,
            credits_reset_at=reset_at,
        )
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        return plan

    async def upgrade_to_paid(self, user_id: uuid.UUID) -> None:
        pass

    async def downgrade_to_free(self, user_id: uuid.UUID) -> None:
        pass

    async def reset_monthly_credits(self) -> int:
        """Reset credits for all users on 1st of month. Returns count."""
        pass
