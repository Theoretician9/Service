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
        """Update a single field on the Project profile."""
        # Validate the field exists on the model to prevent arbitrary setattr
        valid_fields = {
            "goal_statement", "point_a", "point_b", "goal_deadline",
            "success_metrics", "constraints", "niche_candidates",
            "chosen_niche", "hypothesis_table", "geography",
            "budget_range", "business_model",
        }
        if field not in valid_fields:
            raise ValueError(f"Invalid project profile field: {field}")

        stmt = select(Project).where(Project.id == project_id)
        result = await self.session.execute(stmt)
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        setattr(project, field, value)
        await self.session.commit()

    async def archive(self, project_id: uuid.UUID) -> None:
        pass
