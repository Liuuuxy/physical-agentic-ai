"""Push-based retrieval context injected into the planner prompt.

This is the 'retrieval-augmented' half of RAO: instead of relying on the agent
to *call* list-tools (which the eval showed it often skips), the available
skills, locations, and -- for rao / rao-prompt -- the workflow contracts are
placed directly into the planner's context. The ladder is:
  llm-only   -> no registry (must guess; hallucinates)
  skill-list -> skill/location registry injected (grounded, but no contracts)
  rao-prompt -> registry + contracts injected, but NO dispatch gate
  rao        -> registry + contracts injected AND enforced at dispatch
"""
from g1_tasks.sequences import TASK_REGISTRY
from ros_bridge.go2_controller import GO2_PLANNER_SKILLS, NAMED_LOCATIONS
from crew_system.contract_spec import render_contracts_text

G1_SKILL_NAMES = sorted(TASK_REGISTRY.keys())
LOCATION_NAMES = sorted(NAMED_LOCATIONS.keys())

# Generic format example with PLACEHOLDER names -- safe to show every baseline
# (including llm-only) because it teaches JSON shape without leaking any real
# skill or argument name from the registry.
FORMAT_EXAMPLE = (
    "Example of the required JSON shape (placeholder names, do not copy them):\n"
    '{"workflow_family": "carry", "steps": ['
    '{"robot": "g1", "skill": "<g1_skill>", "args": {}}, '
    '{"robot": "go2", "skill": "<go2_skill>", "args": {"<arg_name>": "<value>"}}]}'
)

# Rendered from CONTRACT_REGISTRY -- the same specs the dispatch gate
# enforces -- so prompt prose and machine checks cannot drift.
CONTRACTS_TEXT = render_contracts_text()


def _registry_text():
    return (
        "Available G1 skills (use these EXACT names, do not invent others): "
        f"{', '.join(G1_SKILL_NAMES)}.\n"
        f"Go2 skill: {', '.join(GO2_PLANNER_SKILLS)}.\n"
        "Valid Go2 location names (use these EXACT names): "
        f"{', '.join(LOCATION_NAMES)}."
    )


def retrieval_context(baseline: str) -> str:
    """Context injected for a baseline. llm-only: none; skill-list: registry;
    rao / rao-prompt: registry + workflow contracts."""
    if baseline == "llm-only":
        return ""
    if baseline == "skill-list":
        return _registry_text()
    if baseline in ("rao-prompt", "rao"):
        return _registry_text() + "\n" + CONTRACTS_TEXT
    raise ValueError(f"unknown baseline '{baseline}'")
