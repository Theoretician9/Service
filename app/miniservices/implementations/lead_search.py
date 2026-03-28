from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult


class LeadSearchService(MiniserviceBase):
    """Поиск клиентов — lead discovery (Paid only).
    LLM: claude-haiku (structuring) + Tavily + claude-sonnet (analysis).
    """

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        raise NotImplementedError
