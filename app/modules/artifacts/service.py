import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.models import Artifact, MiniserviceRun


class ArtifactService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_artifact(self, **kwargs) -> Artifact:
        if kwargs.get("project_id") and kwargs.get("miniservice_id"):
            await self.session.execute(
                update(Artifact)
                .where(
                    Artifact.project_id == kwargs["project_id"],
                    Artifact.miniservice_id == kwargs["miniservice_id"],
                    Artifact.is_current == True,
                )
                .values(is_current=False)
            )
        artifact = Artifact(**kwargs)
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def get_user_artifacts(
        self, user_id: uuid.UUID, limit: int = 10
    ) -> list[Artifact]:
        stmt = (
            select(Artifact)
            .where(Artifact.user_id == user_id, Artifact.is_current == True)
            .order_by(Artifact.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_versions(
        self,
        user_id: uuid.UUID,
        miniservice_id: str,
        project_id: uuid.UUID | None,
    ) -> list[Artifact]:
        pass
