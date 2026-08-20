#!/usr/bin/env python3
"""CrewAI agent definitions for the air--ground SAR crew."""

import os
from crewai import Agent, LLM

from crew_system.tools.sar_tools import IrisListSkillsTool, Tb3ListSkillsTool

# Same backbone as the crew_g1_go2 eval so the paper reports one model
# across both testbeds. Set OPENAI_API_KEY in your shell before running.
_llm = LLM(
    model="gpt-5.4-mini",
    api_key=os.environ.get("OPENAI_API_KEY", ""),
    temperature=0.1,   # low temp for deterministic robot control decisions
)


def make_task_router(with_tools: bool = True) -> Agent:
    """
    Analyses the human request and produces a step-by-step plan that
    specifies which robot performs which action in what order.
    Does not execute anything – it only plans.
    """
    tools = [IrisListSkillsTool(), Tb3ListSkillsTool()] if with_tools else []
    return Agent(
        role="Task Router",
        goal=(
            "Understand the human's request and decide which robot (Iris "
            "quadcopter or TB3 ground rover) handles which part of the "
            "mission, and in what order. Output a clear plan: each step must "
            "name the robot and the exact skill with its arguments."
        ),
        backstory=(
            "You are the mission planner for a heterogeneous air--ground "
            "search-and-rescue crew. The Iris quadcopter provides aerial "
            "coverage: it takes off, sweeps a requested search zone, and "
            "publishes the located victim's world coordinates through the "
            "state interface. The TB3 ground rover provides ground "
            "transport: it navigates to published coordinates to deliver "
            "aid. Typical collaborative workflow: Iris takes off → sweeps "
            "the zone → publishes the victim fix → TB3 drives to the fix. "
            "You must produce an unambiguous, executable plan before any "
            "robot moves."
        ),
        tools=tools,
        llm=_llm,
        verbose=True,
        allow_delegation=False,
    )
