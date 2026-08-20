"""Push-based retrieval context injected into the planner prompt.

This is the 'retrieval-augmented' half of RAO: instead of relying on the agent
to *call* list-tools (which the eval showed it often skips), the available
skills, the operational area, and -- for rao / rao-prompt -- the workflow
contracts are placed directly into the planner's context. The ladder is:
  llm-only   -> no registry (must guess; hallucinates)
  skill-list -> skill registry + operational area injected (grounded, but no contracts)
  rao-prompt -> registry + contracts injected, but NO dispatch gate
  rao        -> registry + contracts injected AND enforced at dispatch
"""
from ros_bridge.skill_registry import (IRIS_PLANNER_SKILLS, TB3_PLANNER_SKILLS,
                                       OPERATIONAL_BOUNDS, DEFAULT_ALTITUDE)
from crew_system.contract_spec import render_contracts_text

# Generic format example with PLACEHOLDER names -- safe to show every baseline
# (including llm-only) because it teaches JSON shape without leaking any real
# skill or argument name from the registry.
FORMAT_EXAMPLE = (
    "Example of the required JSON shape (placeholder names, do not copy them):\n"
    '{"workflow_family": "search_and_dispatch", "steps": ['
    '{"robot": "iris", "skill": "<iris_skill>", "args": {}}, '
    '{"robot": "tb3", "skill": "<tb3_skill>", "args": {"<arg_name>": "<value>"}}]}'
)

# Rendered from CONTRACT_REGISTRY -- the same specs the dispatch gate
# enforces -- so prompt prose and machine checks cannot drift.
CONTRACTS_TEXT = render_contracts_text()


def _registry_text():
    x_min, x_max, y_min, y_max = OPERATIONAL_BOUNDS
    return (
        "Available Iris drone skills (use these EXACT names, do not invent "
        f"others): {', '.join(IRIS_PLANNER_SKILLS)}. "
        "search_target takes args x_min, x_max, y_min, y_max (and optional "
        f"altitude, default {DEFAULT_ALTITUDE}).\n"
        f"TB3 rover skills: {', '.join(TB3_PLANNER_SKILLS)}. navigate_to takes "
        'either {"target": "victim"} to drive to the drone-published victim '
        'fix, or explicit numeric "x" and "y" stated in the request.\n'
        "Operational area (world frame): "
        f"x in [{x_min}, {x_max}], y in [{y_min}, {y_max}]."
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
