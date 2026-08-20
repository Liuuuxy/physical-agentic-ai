#!/usr/bin/env python3
"""CrewAI task definitions for the air--ground SAR crew."""

from crewai import Task
from crewai import Agent


def make_routing_task(router: Agent, human_request: str, extra_instructions: str = "") -> Task:
    base_description = (
        f"A human has given the following request:\n\n"
        f'  "{human_request}"\n\n'
        "Analyse it and produce an ordered plan. For each step specify:\n"
        "  - which robot (Iris or TB3)\n"
        "  - the exact skill (use the iris_list_skills and tb3_list_skills "
        "    tools to check available options)\n"
        "  - any relevant parameters (search zone bounds, coordinates, "
        "    target binding)\n\n"
        "If the request cannot be fulfilled with the available skills, "
        "explain why."
    )
    description = base_description + ("\n\n" + extra_instructions if extra_instructions else "")
    return Task(
        description=description,
        expected_output=(
            "An ordered plan of robot actions derived from the human request, "
            "using only valid skill names and arguments."
        ),
        agent=router,
    )
