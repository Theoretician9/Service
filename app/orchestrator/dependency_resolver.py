"""Resolves miniservice dependency chains."""

from uuid import UUID

DEPENDENCY_GRAPH = {
    "goal_setting": [],
    "niche_selection": ["goal_tree"],
    "decomposition_hypothesis": ["goal_tree", "niche_table"],
    "supplier_search": ["niche_table"],
    "sales_scripts": ["goal_tree", "niche_table"],
    "ad_creation": ["niche_table"],
    "lead_search": ["niche_table", "goal_tree"],
}

ARTIFACT_TO_MINISERVICE = {
    "goal_tree": "goal_setting",
    "niche_table": "niche_selection",
    "decomposition_hypothesis_report": "decomposition_hypothesis",
    "supplier_list": "supplier_search",
    "sales_script": "sales_scripts",
    "ad_set": "ad_creation",
    "lead_list": "lead_search",
}


# Deterministic chain: which miniservice to suggest next based on completed artifacts
NEXT_STEP_CHAIN = [
    ([], "goal_setting"),
    (["goal_tree"], "niche_selection"),
    (["goal_tree", "niche_table"], "decomposition_hypothesis"),
    (["goal_tree", "niche_table", "decomposition_hypothesis_report"], "supplier_search"),
]


def get_next_miniservice(existing_artifact_types: list[str]) -> str | None:
    """Deterministically compute the next recommended miniservice.

    Returns miniservice_id or None if all main chain steps are done.
    """
    existing = set(existing_artifact_types)
    for required_artifacts, next_ms in NEXT_STEP_CHAIN:
        if all(a in existing for a in required_artifacts):
            # Check if this miniservice's artifact already exists
            ms_artifact = None
            for art, ms in ARTIFACT_TO_MINISERVICE.items():
                if ms == next_ms:
                    ms_artifact = art
                    break
            if ms_artifact and ms_artifact not in existing:
                return next_ms
    return None


def resolve_missing(miniservice_id: str, existing_artifact_types: list[str]) -> list[str]:
    """Return ordered list of miniservice_ids that need to run first.

    Only includes miniservices whose artifacts don't exist yet.
    """
    required = DEPENDENCY_GRAPH.get(miniservice_id, [])
    missing = []
    for artifact_type in required:
        if artifact_type not in existing_artifact_types:
            dep_ms = ARTIFACT_TO_MINISERVICE[artifact_type]
            # Recursively resolve dependencies of the dependency
            sub_missing = resolve_missing(dep_ms, existing_artifact_types)
            for sm in sub_missing:
                if sm not in missing:
                    missing.append(sm)
            if dep_ms not in missing:
                missing.append(dep_ms)
    return missing
