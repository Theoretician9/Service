"""Pre-agent field validation — enforces data quality before LLM sees data.

Called in agent's handle_message BEFORE sending to LLM.
Ensures collected_fields contain valid data that won't mislead the agent.
"""
from app.services.currency import has_money_amount


def validate_collected_fields(miniservice_id: str, collected_fields: dict) -> dict:
    """Validate and clean collected_fields before agent call.

    Returns cleaned dict (may remove invalid entries).
    Modifies in place AND returns for convenience.
    """
    if miniservice_id == "goal_setting":
        _validate_goal_setting(collected_fields)
    return collected_fields


def _validate_goal_setting(fields: dict) -> None:
    """Goal setting specific validations."""
    # point_b must contain a concrete income amount
    point_b = fields.get("point_b", "")
    if point_b and not has_money_amount(str(point_b)):
        # Remove point_b — force agent to ask for target income
        del fields["point_b"]


def field_has_required_quality(field_id: str, value: str, miniservice_id: str) -> bool:
    """Check if a field value meets quality requirements.

    Used to validate smart_extractor output before auto-filling.
    """
    if not value or not str(value).strip():
        return False

    if miniservice_id == "goal_setting":
        if field_id == "point_b":
            # point_b must contain a money amount
            return has_money_amount(str(value))

    return True
