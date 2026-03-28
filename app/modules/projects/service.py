import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, user_id: uuid.UUID, name: str, description: str | None = None
    ) -> Project:
        project = Project(user_id=user_id, name=name, description=description)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_user_projects(self, user_id: uuid.UUID) -> list[Project]:
        stmt = select(Project).where(Project.user_id == user_id, Project.status == "active")
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Project)
            .where(Project.user_id == user_id, Project.status == "active")
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update_profile_field(self, project_id: uuid.UUID, field: str, value) -> None:
        pass

    async def archive(self, project_id: uuid.UUID) -> None:
        pass
