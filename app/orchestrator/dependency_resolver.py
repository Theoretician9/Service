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
