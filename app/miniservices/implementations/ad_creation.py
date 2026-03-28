from app.miniservices.base import MiniserviceBase, MiniserviceContext, MiniserviceResult


class AdCreationService(MiniserviceBase):
    """Продающие объявления — ad copy + DALL-E images (Paid only).
    LLM text: gpt-4o-mini. LLM images: DALL-E 3 (Paid only).
    """

    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        raise NotImplementedError
