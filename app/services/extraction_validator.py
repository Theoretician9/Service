"""Validates that smart_extractor output comes from actual user message.

Prevents LLM hallucinations in field extraction by checking that
extracted values are grounded in the original message text.
"""


def validate_extraction(extracted_value: str, original_message: str) -> bool:
    """Check that extracted value is grounded in the original message.

    Returns True if value appears to come from the message.
    Uses case-insensitive substring check with word boundary awareness.
    """
    if not extracted_value or not original_message:
        return False

    value_lower = extracted_value.lower().strip()
    message_lower = original_message.lower()

    # Direct substring match — most reliable
    if value_lower in message_lower:
        return True

    # Check if key words from extracted value appear in message
    # (handles reformulation by LLM while preserving core data)
    value_words = set(value_lower.split())
    message_words = set(message_lower.split())

    if not value_words:
        return False

    # At least 50% of extracted words must appear in message
    overlap = value_words & message_words
    overlap_ratio = len(overlap) / len(value_words)

    return overlap_ratio >= 0.5


def validate_extractions(
    extracted: dict[str, dict[str, str]],
    original_message: str,
) -> dict[str, dict[str, str]]:
    """Filter extracted fields, keeping only grounded ones.

    Args:
        extracted: {miniservice_id: {field_id: value}}
        original_message: The user's original message text

    Returns:
        Filtered dict with only validated extractions.
    """
    validated = {}
    for ms_id, fields in extracted.items():
        valid_fields = {}
        for field_id, value in fields.items():
            if validate_extraction(str(value), original_message):
                valid_fields[field_id] = value
        if valid_fields:
            validated[ms_id] = valid_fields
    return validated
