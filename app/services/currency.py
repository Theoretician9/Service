"""Currency detection, normalization and validation.

Single source of truth for all currency-related logic across agents.
"""
import re

# Currency markers for detection in text
CURRENCY_SYMBOLS = {"₽", "₸", "$", "€"}
CURRENCY_WORDS = {"руб", "рубл", "тенге", "byn", "долл", "rub", "kzt"}

# Geography → default currency (used only as suggestion, not auto-assignment)
GEOGRAPHY_CURRENCY = {
    "Россия": "₽",
    "Казахстан": "₸",
    "Беларусь": "BYN",
    "Весь СНГ": None,  # Must ask
}

# User input → normalized currency
CURRENCY_ALIASES = {
    "рубли": "₽", "рублей": "₽", "рублях": "₽", "руб": "₽", "₽": "₽", "rub": "₽",
    "тенге": "₸", "₸": "₸", "kzt": "₸",
    "бын": "BYN", "byn": "BYN", "белорусских": "BYN", "белорусские": "BYN",
    "доллар": "$", "долларов": "$", "$": "$", "usd": "$",
}


def has_currency(text: str) -> bool:
    """Check if text contains any currency marker."""
    lower = text.lower()
    for symbol in CURRENCY_SYMBOLS:
        if symbol in text:  # symbols are case-sensitive
            return True
    for word in CURRENCY_WORDS:
        if word in lower:
            return True
    return False


def has_money_amount(text: str) -> bool:
    """Check if text contains a money amount (digits + multiplier or large number)."""
    return bool(re.search(
        r'\d+\s*[кkКK]'          # 100к, 200K
        r'|\d{4,}'               # 10000+
        r'|\d+\s*(?:тыс|млн|миллион)'  # 100 тыс, 1 млн
        r'|\d+\s*(?:руб|тенге)',  # 100 руб, 5000 тенге
        text
    ))


def detect_currency(text: str) -> str | None:
    """Detect currency from user's text. Returns symbol or None."""
    lower = text.lower()
    for alias, symbol in CURRENCY_ALIASES.items():
        if alias in lower:
            return symbol
    return None


def needs_currency_clarification(collected_fields: dict, money_fields: tuple = ("point_a", "point_b")) -> bool:
    """Check if any money-containing field lacks currency info."""
    if "currency" in collected_fields:
        return False
    for field_id in money_fields:
        value = str(collected_fields.get(field_id, ""))
        if value and has_money_amount(value) and not has_currency(value):
            return True
    return False


def format_currency_question() -> str:
    """Standard currency clarification question."""
    return "В какой валюте считаем — рубли (₽), тенге (₸) или белорусские рубли (BYN)?"
