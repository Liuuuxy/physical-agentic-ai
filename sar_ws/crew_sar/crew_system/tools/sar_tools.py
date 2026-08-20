#!/usr/bin/env python3
"""CrewAI list-tools for the SAR crew's Task Router (retrieval arms only)."""

from crewai.tools import BaseTool


class IrisListSkillsTool(BaseTool):
    name: str = "iris_list_skills"
    description: str = "List the executable skills of the Iris drone."

    def _run(self) -> str:
        from ros_bridge.skill_registry import IRIS_PLANNER_SKILLS, DEFAULT_ALTITUDE
        return (
            "Iris skills: " + ", ".join(IRIS_PLANNER_SKILLS) + ". "
            "search_target takes x_min, x_max, y_min, y_max "
            f"(optional altitude, default {DEFAULT_ALTITUDE})."
        )


class Tb3ListSkillsTool(BaseTool):
    name: str = "tb3_list_skills"
    description: str = ("List the executable skills of the TB3 ground rover "
                        "and the operational area.")

    def _run(self) -> str:
        from ros_bridge.skill_registry import TB3_PLANNER_SKILLS, OPERATIONAL_BOUNDS
        x_min, x_max, y_min, y_max = OPERATIONAL_BOUNDS
        return (
            "TB3 skills: " + ", ".join(TB3_PLANNER_SKILLS) + ". "
            'navigate_to takes {"target": "victim"} or explicit numeric x, y. '
            f"Operational area: x in [{x_min}, {x_max}], y in [{y_min}, {y_max}]."
        )
