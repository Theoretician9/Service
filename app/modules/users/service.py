import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(
        self, telegram_id: int, first_name: str, username: str | None = None
    ) -> User:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            user = User(telegram_id=telegram_id, first_name=first_name, username=username)
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_onboarding(
        self, user_id: uuid.UUID, role: str, primary_goal: str
    ) -> None:
        pass

    async def mark_deleted(self, user_id: uuid.UUID) -> None:
        pass
