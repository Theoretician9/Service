"""Smart extractor: extracts useful fields from EVERY incoming message using Haiku."""

import json

import structlog

from app.integrations.llm_gateway import llm_gateway
from app.miniservices.engine import get_all_manifests
from app.services.extraction_validator import validate_extractions

logger = structlog.get_logger()

# Minimum message length to trigger extraction (optimization from spec)
MIN_MESSAGE_LENGTH = 100


def _build_extractable_fields() -> dict[str, list[dict]]:
    """Build a mapping of miniservice_id -> list of extractable field defs.

    Only includes fields where extract_from_free_text=true.
    """
    manifests = get_all_manifests()
    result: dict[str, list[dict]] = {}
    for ms_id, manifest in manifests.items():
        extractable = []
        for field_def in manifest["input_schema"]["fields"]:
            if field_def.get("extract_from_free_text", False):
                extractable.append({
                    "id": field_def["id"],
                    "label": field_def["label"],
                    "type": field_def["type"],
                    "question": field_def["question"],
                })
        if extractable:
            result[ms_id] = extractable
    return result


def _build_extraction_prompt(
    message_text: str,
    extractable_fields: dict[str, list[dict]],
    active_miniservice_id: str | None,
) -> str:
    """Build the extraction prompt listing all extractable fields."""
    lines = [
        "Проанализируй сообщение пользователя и извлеки из него значения полей для минисервисов.",
        "Извлекай ТОЛЬКО то, что явно содержится в тексте. Не придумывай данные.",
        "",
        "Доступные поля для извлечения:",
    ]

    # If there's an active miniservice, list it first for priority
    ordered_ids = list(extractable_fields.keys())
    if active_miniservice_id and active_miniservice_id in ordered_ids:
        ordered_ids.remove(active_miniservice_id)
        ordered_ids.insert(0, active_miniservice_id)

    for ms_id in ordered_ids:
        fields = extractable_fields[ms_id]
        lines.append(f"\n## {ms_id}:")
        for f in fields:
            lines.append(f"  - {f['id']} ({f['label']}): {f['question']}")

    lines.extend([
        "",
        "Ответь ТОЛЬКО валидным JSON без markdown-обёртки.",
        'Формат: {"miniservice_id": {"field_id": "извлечённое_значение"}}',
        "Если для минисервиса нечего извлечь — не включай его в ответ.",
        "Если ничего не извлечено — ответь пустым объектом: {}",
    ])

    return "\n".join(lines)


async def extract_fields(message_text: str, context: dict) -> dict:
    """Extract fields from user message for all miniservices.

    Returns {miniservice_id: {field_id: value}}.
    On error, returns empty dict (extraction is best-effort).

    Args:
        message_text: The user's message text.
        context: Dict with optional keys:
            - active_miniservice_id: str | None — currently active miniservice
    """
    if len(message_text) < MIN_MESSAGE_LENGTH:
        return {}  # Too short, skip extraction to save tokens

    try:
        extractable_fields = _build_extractable_fields()
        if not extractable_fields:
            return {}

        active_miniservice_id = context.get("active_miniservice_id")

        system_prompt = (
            "Ты — экстрактор данных. Извлекай структурированную информацию "
            "из свободного текста пользователя. Отвечай только JSON."
        )
        user_prompt = _build_extraction_prompt(
            message_text, extractable_fields, active_miniservice_id
        )

        response = await llm_gateway.complete(
            provider="anthropic",
            model="claude-haiku-4-5",
            messages=[
                {"role": "user", "content": f"Сообщение пользователя:\n\n{message_text}\n\n{user_prompt}"},
            ],
            system=system_prompt,
            max_tokens=800,
            temperature=0,
        )

        # Parse JSON from response
        content = response.content.strip()
        # Handle potential markdown code block wrapping
        if content.startswith("```"):
            # Remove ```json and ``` wrappers
            lines = content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines).strip()

        result = json.loads(content)

        if not isinstance(result, dict):
            logger.warning("smart_extractor_invalid_type", type=type(result).__name__)
            return {}

        # Validate structure: {str: {str: str}}
        validated: dict[str, dict[str, str]] = {}
        for ms_id, fields in result.items():
            if not isinstance(fields, dict):
                continue
            if ms_id not in extractable_fields:
                continue
            valid_field_ids = {f["id"] for f in extractable_fields[ms_id]}
            valid_fields = {}
            for field_id, value in fields.items():
                if field_id in valid_field_ids and isinstance(value, str) and value.strip():
                    valid_fields[field_id] = value.strip()
            if valid_fields:
                validated[ms_id] = valid_fields

        # Before returning extracted fields, validate they come from the message
        validated = validate_extractions(validated, message_text)

        logger.info(
            "smart_extractor_result",
            extracted_count=sum(len(v) for v in validated.values()),
            miniservices=list(validated.keys()),
        )
        return validated

    except json.JSONDecodeError:
        logger.warning("smart_extractor_json_error", message_len=len(message_text))
        return {}
    except Exception:
        logger.exception("smart_extractor_error")
        return {}
