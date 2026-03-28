import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.models import AnalyticsEvent, BugReport


class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def track(
        self,
        event_type: str,
        user_id: uuid.UUID | None = None,
        properties: dict | None = None,
    ) -> None:
        event = AnalyticsEvent(
            event_type=event_type, user_id=user_id, properties=properties or {}
        )
        self.session.add(event)
        await self.session.commit()

    async def create_bug_report(self, user_id: uuid.UUID, text: str) -> BugReport:
        report = BugReport(user_id=user_id, text=text)
        self.session.add(report)
        await self.session.commit()
        return report

    async def get_stats(self, days: int = 7) -> dict:
        """Aggregate stats for /admin_stats."""
        pass
