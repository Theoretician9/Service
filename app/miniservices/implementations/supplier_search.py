from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult


class SupplierSearchService(MiniserviceBase):
    """Поиск поставщиков — supplier discovery via Tavily + LLM analysis.
    1. Tavily: 3-5 search queries
    2. LLM (Haiku): structure search results
    3. LLM (Sonnet): generate email templates + verification checklist
    """

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        raise NotImplementedError
