from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult


class GoalSettingService(MiniserviceBase):
    """Постановка целей — SMART goal tree generation.
    LLM: claude-sonnet for generation.
    project_fields_written: goal_statement, success_metrics, constraints, timeline
    """

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        raise NotImplementedError
