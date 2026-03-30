from enum import Enum
from dataclasses import dataclass


class OrchestratorAction(str, Enum):
    RESPOND = "RESPOND"
    ONBOARDING = "ONBOARDING"
    ENSURE_PROJECT = "ENSURE_PROJECT"
    INIT_DEP_CHAIN = "INIT_DEP_CHAIN"
    LAUNCH_MINISERVICE = "LAUNCH_MINISERVICE"
    CONTINUE_COLLECTING = "CONTINUE_COLLECTING"
    CREATE_PROJECT = "CREATE_PROJECT"
    SWITCH_PROJECT = "SWITCH_PROJECT"
    SHOW_INFO = "SHOW_INFO"
    ARTIFACT_PDF = "ARTIFACT_PDF"
    ARTIFACT_SHEETS = "ARTIFACT_SHEETS"
    SHOW_PLAN = "SHOW_PLAN"
    UPGRADE_CTA = "UPGRADE_CTA"
    CANCEL_RUN = "CANCEL_RUN"
    BUG_REPORT = "BUG_REPORT"


@dataclass
class OrchestratorDecision:
    action: OrchestratorAction
    response_text: str
    confidence: float  # 0.0-1.0
    params: dict
    needs_confirmation: bool  # True if confidence < threshold
    confirmation_text: str | None = None
