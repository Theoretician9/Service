import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

MANIFESTS_DIR = Path(__file__).parent / "manifests"

_manifest_cache: dict[str, dict] = {}


def load_manifest(miniservice_id: str) -> dict:
    """Load and cache a miniservice manifest."""
    if miniservice_id not in _manifest_cache:
        path = MANIFESTS_DIR / f"{miniservice_id}.json"
        with open(path) as f:
            _manifest_cache[miniservice_id] = json.load(f)
    return _manifest_cache[miniservice_id]


def get_all_manifests() -> dict[str, dict]:
    """Load all manifests."""
    for path in MANIFESTS_DIR.glob("*.json"):
        ms_id = path.stem
        if ms_id not in _manifest_cache:
            with open(path) as f:
                _manifest_cache[ms_id] = json.load(f)
    return _manifest_cache


def get_next_question(miniservice_id: str, collected_fields: dict[str, Any]) -> dict | None:
    """Determine next question based on manifest question_plan and collected fields.
    Returns field definition dict or None if all required fields collected."""
    manifest = load_manifest(miniservice_id)
    fields_map = {f["id"]: f for f in manifest["input_schema"]["fields"]}

    for step in manifest["question_plan"]:
        field_id = step["field_id"]
        if field_id in collected_fields:
            continue

        field_def = fields_map[field_id]

        condition = step.get("condition")
        if condition:
            dep_field = condition["field"]
            dep_value = condition["value"]
            if collected_fields.get(dep_field) != dep_value:
                continue

        if field_def.get("required", False) or field_id not in collected_fields:
            return field_def

    return None


def all_required_collected(miniservice_id: str, collected_fields: dict[str, Any]) -> bool:
    """Check if all required fields are collected."""
    manifest = load_manifest(miniservice_id)
    fields_map = {f["id"]: f for f in manifest["input_schema"]["fields"]}

    for step in manifest["question_plan"]:
        field_id = step["field_id"]
        field_def = fields_map[field_id]

        if not field_def.get("required", False):
            continue

        condition = step.get("condition")
        if condition:
            dep_field = condition["field"]
            dep_value = condition["value"]
            if collected_fields.get(dep_field) != dep_value:
                continue

        if field_id not in collected_fields:
            return False

    return True
