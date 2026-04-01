"""Registry mapping miniservice_id to its conversation agent."""
from app.miniservices.agents.base_agent import BaseAgent

_AGENTS: dict[str, type[BaseAgent]] = {}


def register_agent(miniservice_id: str, agent_class: type[BaseAgent]):
    _AGENTS[miniservice_id] = agent_class


def get_agent(miniservice_id: str) -> BaseAgent | None:
    cls = _AGENTS.get(miniservice_id)
    return cls() if cls else None


# Register all agents
from app.miniservices.agents.goal_setting_agent import GoalSettingAgent
from app.miniservices.agents.niche_selection_agent import NicheSelectionAgent

register_agent("goal_setting", GoalSettingAgent)
register_agent("niche_selection", NicheSelectionAgent)
