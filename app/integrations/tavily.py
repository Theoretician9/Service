import hashlib
import json

import structlog

from app.config import settings
from app.redis_client import redis

logger = structlog.get_logger()

TAVILY_CACHE_TTL = 7200  # 2 hours
MAX_SEARCHES_PER_RUN = 5


class TavilySearch:
    """Tavily web search integration."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from tavily import TavilyClient
            self._client = TavilyClient(api_key=settings.tavily_api_key)
        return self._client

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        cache_key = f"tavily:{hashlib.sha256(query.encode()).hexdigest()}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        try:
            response = self.client.search(query=query, max_results=max_results)
            results = response.get("results", [])
            await redis.set(cache_key, json.dumps(results), ex=TAVILY_CACHE_TTL)
            return results
        except Exception as e:
            logger.error("tavily_error", query=query, error=str(e))
            return []


tavily_search = TavilySearch()
