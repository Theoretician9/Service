"""Robust JSON parsing for LLM responses with retry support.

Centralizes JSON extraction logic used across all miniservice implementations.
"""
import json
import re

import structlog

logger = structlog.get_logger()


def parse_llm_json(raw_content: str, context: str = "") -> dict | list | None:
    """Parse JSON from LLM response, handling markdown wrapping.

    Returns parsed JSON or None if parsing fails completely.
    Does NOT return empty defaults — caller decides how to handle failure.

    Args:
        raw_content: Raw LLM response text
        context: Description for logging (e.g. "goal_setting generation")
    """
    content = raw_content.strip()

    # Strip markdown code block if present
    if "```" in content:
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
        else:
            lines = content.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            content = "\n".join(lines)

    # Try direct JSON parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try to find JSON array in text
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.error("llm_json_parse_failed", context=context, raw_preview=content[:300])
    return None


async def parse_llm_json_with_retry(
    llm_gateway,
    provider: str,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    context: str = "",
    run_id=None,
    max_retries: int = 1,
) -> tuple[dict | list, int]:
    """Call LLM and parse JSON response, retrying on parse failure.

    Returns (parsed_json, total_tokens_used).
    Raises ValueError if all retries fail.
    """
    total_tokens = 0

    for attempt in range(1 + max_retries):
        response = await llm_gateway.complete(
            provider=provider,
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            run_id=run_id,
        )
        total_tokens += response.input_tokens + response.output_tokens

        parsed = parse_llm_json(response.content, context)
        if parsed is not None:
            return parsed, total_tokens

        if attempt < max_retries:
            logger.warning(
                "llm_json_retry",
                context=context,
                attempt=attempt + 1,
            )
            # Add instruction to return valid JSON
            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": "Ответ не в формате JSON. Верни ТОЛЬКО валидный JSON без текста вокруг."},
            ]

    raise ValueError(f"Failed to get valid JSON from LLM after {1 + max_retries} attempts ({context})")
