import structlog

from app.config import settings

logger = structlog.get_logger()

MAX_IMAGES_PER_RUN = 2


class ImageGenerator:
    """DALL-E 3 image generation for ad_creation (Paid only)."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def generate(self, prompt: str) -> str | None:
        try:
            response = await self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            return response.data[0].url
        except Exception as e:
            logger.error("image_gen_error", error=str(e))
            return None


image_gen = ImageGenerator()
