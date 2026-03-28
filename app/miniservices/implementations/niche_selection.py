from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult


class NicheSelectionService(MiniserviceBase):
    """Выбор ниши + декомпозиция — niche analysis with Tavily search.
    LLM: claude-sonnet + Tavily.
    project_fields_written: niche_candidates, hypothesis_table, geography, budget_range, business_model
    """

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        raise NotImplementedError
