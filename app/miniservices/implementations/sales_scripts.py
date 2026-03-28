from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult


class SalesScriptsService(MiniserviceBase):
    """Скрипты продаж — sales script generation.
    LLM: claude-sonnet.
    """

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        raise NotImplementedError
