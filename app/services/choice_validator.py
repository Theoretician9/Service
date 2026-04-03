"""Strict choice field matching — replaces fuzzy matching in message_handler.

Rules:
- Exact match (case-insensitive): always accepted
- Numeric selection (1, 2, 3): accepted if in valid range
- No partial/substring matching — too error-prone
- Multi-choice: each item must be exact match or number
"""


def match_choice(user_text: str, choices: list[str]) -> str | None:
    """Match user input to a single choice option.

    Returns matched option string or None if no match.
    """
    text = user_text.strip().lower()

    if not choices:
        return None

    # Exact match (case-insensitive)
    for c in choices:
        if text == c.lower():
            return c

    # Numeric selection: "1", "2", etc.
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(choices):
            return choices[idx]

    return None


def match_yes_no(user_text: str) -> str | None:
    """Match user input to yes/no."""
    text = user_text.strip().lower()
    yes_words = {"да", "yes", "ага", "угу", "конечно", "разумеется", "+", "ок", "давай"}
    no_words = {"нет", "no", "не", "нее", "неа", "-"}
    if text in yes_words:
        return "да"
    if text in no_words:
        return "нет"
    return None


def match_multi_choice(user_text: str, choices: list[str]) -> str | None:
    """Match user input to multiple choice options.

    Supports: "1, 3", "Услуги, Товары", "всё", numbers.
    Returns comma-separated matched options or None.
    """
    text = user_text.strip().lower()

    # "всё" / "все" / "all" — select all
    if text in ("всё", "все", "all"):
        return ", ".join(choices)

    matched = []

    # Try splitting by comma, semicolon, or "и"
    parts = [p.strip() for p in text.replace(";", ",").replace(" и ", ",").split(",")]

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Exact match
        for c in choices:
            if part == c.lower() and c not in matched:
                matched.append(c)
                break
        else:
            # Number match
            if part.isdigit():
                idx = int(part) - 1
                if 0 <= idx < len(choices) and choices[idx] not in matched:
                    matched.append(choices[idx])

    return ", ".join(matched) if matched else None


def match_choice_field(user_text: str, field: dict) -> str | None:
    """Universal choice matcher — dispatches to correct handler by field type."""
    field_type = field.get("type", "")
    choices = field.get("choices", [])

    if field_type == "yes_no":
        return match_yes_no(user_text)
    elif field_type == "multi_choice":
        return match_multi_choice(user_text, choices)
    elif field_type == "choice":
        return match_choice(user_text, choices)
    return None
