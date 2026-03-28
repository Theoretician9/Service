import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import UserPlan


class BillingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def reserve_credits(self, user_id: uuid.UUID, amount: int) -> bool:
        """Atomically reserve credits. Returns True if successful."""
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

    async def upgrade_to_paid(self, user_id: uuid.UUID) -> None:
        pass

    async def downgrade_to_free(self, user_id: uuid.UUID) -> None:
        pass

    async def reset_monthly_credits(self) -> int:
        """Reset credits for all users on 1st of month. Returns count."""
        pass
