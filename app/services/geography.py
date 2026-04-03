"""Geography normalization — deterministic mapping from city/region to country."""

# City/region → country mapping
GEOGRAPHY_ALIASES: dict[str, str] = {
    # Russia
    "москва": "Россия", "питер": "Россия", "санкт-петербург": "Россия",
    "новосибирск": "Россия", "екатеринбург": "Россия", "казань": "Россия",
    "нижний новгород": "Россия", "красноярск": "Россия", "самара": "Россия",
    "ростов": "Россия", "уфа": "Россия", "краснодар": "Россия",
    "омск": "Россия", "челябинск": "Россия", "пермь": "Россия",
    "волгоград": "Россия", "воронеж": "Россия", "тюмень": "Россия",
    "рф": "Россия", "россия": "Россия", "российская": "Россия",
    # Kazakhstan
    "алматы": "Казахстан", "астана": "Казахстан", "нур-султан": "Казахстан",
    "шымкент": "Казахстан", "караганда": "Казахстан", "актобе": "Казахстан",
    "тараз": "Казахстан", "павлодар": "Казахстан", "костанай": "Казахстан",
    "кз": "Казахстан", "казахстан": "Казахстан",
    # Belarus
    "минск": "Беларусь", "гомель": "Беларусь", "витебск": "Беларусь",
    "брест": "Беларусь", "гродно": "Беларусь", "могилёв": "Беларусь",
    "рб": "Беларусь", "беларусь": "Беларусь", "белоруссия": "Беларусь",
}


def normalize_geography(user_text: str) -> str | None:
    """Try to normalize user input to a standard geography value.

    Returns "Россия", "Казахстан", "Беларусь", or None if can't determine.
    """
    lower = user_text.strip().lower()

    # Direct lookup
    if lower in GEOGRAPHY_ALIASES:
        return GEOGRAPHY_ALIASES[lower]

    # Check if any alias is a substring of user input
    for alias, country in GEOGRAPHY_ALIASES.items():
        if alias in lower:
            return country

    return None
