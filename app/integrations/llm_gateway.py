import json
import time
import uuid
from dataclasses import dataclass

import structlog

from app.config import settings
from app.redis_client import redis

logger = structlog.get_logger()

LLM_CACHE_TTL = 3600  # 1 hour


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached: bool
    duration_ms: int


class LLMGateway:
    """Unified LLM gateway. All LLM calls go through this class."""

    def __init__(self):
        self._anthropic_client = None
        self._openai_client = None

    @property
    def anthropic_client(self):
        if self._anthropic_client is None:
            import anthropic
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._anthropic_client

    @property
    def openai_client(self):
        if self._openai_client is None:
            import openai
            self._openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    async def complete(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        timeout: int | None = None,
        run_id: uuid.UUID | None = None,
        cache_key: str | None = None,
    ) -> LLMResponse:
        timeout = timeout or settings.llm_request_timeout_seconds

        if cache_key:
            cached = await redis.get(f"llm_cache:{cache_key}")
            if cached:
                data = json.loads(cached)
                return LLMResponse(**data, cached=True)

        start = time.monotonic()

        if provider == "anthropic":
            response = await self._call_anthropic(model, messages, system, max_tokens, temperature)
        elif provider == "openai":
            response = await self._call_openai(model, messages, system, max_tokens, temperature)
        else:
            raise ValueError(f"Unknown provider: {provider}")

        duration_ms = int((time.monotonic() - start) * 1000)
        result = LLMResponse(
            content=response["content"],
            provider=provider,
            model=model,
            input_tokens=response["input_tokens"],
            output_tokens=response["output_tokens"],
            cached=False,
            duration_ms=duration_ms,
        )

        logger.info(
            "llm_call",
            provider=provider,
            model=model,
            run_id=str(run_id) if run_id else None,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            duration_ms=duration_ms,
        )

        if cache_key:
            cache_data = {
                "content": result.content,
                "provider": result.provider,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "duration_ms": result.duration_ms,
            }
            await redis.set(f"llm_cache:{cache_key}", json.dumps(cache_data), ex=LLM_CACHE_TTL)

        return result

    async def _call_anthropic(self, model, messages, system, max_tokens, temperature) -> dict:
        kwargs = {
            "model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        response = await self.anthropic_client.messages.create(**kwargs)
        return {
            "content": response.content[0].text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

    async def _call_openai(self, model, messages, system, max_tokens, temperature) -> dict:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = await self.openai_client.chat.completions.create(
            model=model, messages=msgs, max_tokens=max_tokens, temperature=temperature,
        )
        return {
            "content": response.choices[0].message.content,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }


llm_gateway = LLMGateway()
