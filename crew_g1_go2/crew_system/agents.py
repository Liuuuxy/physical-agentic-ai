#!/usr/bin/env python3
"""CrewAI agent definitions for the dual-robot system."""

import os
from crewai import Agent, LLM

from crew_system.tools.g1_tools import (
    G1ExecuteTaskTool,
    G1StatusTool,
    G1ListTasksTool,
)
from crew_system.tools.go2_tools import (
    Go2NavigateToLocationTool,
    Go2NavigateToCoordTool,
    Go2StatusTool,
    Go2StopTool,
    Go2ListLocationsTool,
)

# Use GPT-5 as the backbone for all agents.
# Set OPENAI_API_KEY in your shell before running.
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
    tools = [G1ListTasksTool(), Go2ListLocationsTool()] if with_tools else []
    return Agent(
        role="Task Router",
        goal=(
            "Understand the human's request and decide which robot (G1 humanoid "
            "or Go2 quadruped) handles which part of the task, and in what order. "
            "Output a clear numbered plan: each step must name the robot and the "
            "exact action (e.g. 'G1: grab_from_table', 'Go2: navigate to table_a')."
        ),
        backstory=(
            "You are the mission planner for a dual-robot system. "
            "The G1 humanoid specialises in close-range arm manipulation: "
            "grabbing, placing, waving, and handing over objects. "
            "The Go2 quadruped specialises in autonomous navigation: carrying "
            "items between locations across a room or building. "
            "Typical collaborative workflow: G1 grabs an object → Go2 carries "
            "it to the destination → G1 places it down. "
            "You must produce an unambiguous, executable plan before any robot moves."
        ),
        tools=tools,
        llm=_llm,
        verbose=True,
        allow_delegation=False,
    )


def make_g1_agent() -> Agent:
    """Executes manipulation tasks on the G1 humanoid."""
    return Agent(
        role="G1 Manipulation Specialist",
        goal=(
            "Execute the G1 humanoid's arm manipulation tasks exactly as instructed "
            "in the plan. Report success or failure for each step."
        ),
        backstory=(
            "You control the Unitree G1 humanoid robot. "
            "Your commands publish joint-level motor targets to /user_lowcmd "
            "at 500 Hz, interpolated through hard-coded keyframe sequences. "
            "You must only use available task names and confirm completion "
            "before declaring the step done."
        ),
        tools=[G1ExecuteTaskTool(), G1StatusTool(), G1ListTasksTool()],
        llm=_llm,
        verbose=True,
        allow_delegation=False,
    )


def make_go2_agent() -> Agent:
    """Executes navigation tasks on the Go2 quadruped."""
    return Agent(
        role="Go2 Navigation Specialist",
        goal=(
            "Navigate the Go2 quadruped to the locations specified in the plan. "
            "Confirm arrival before reporting success. "
            "Stop the robot if an emergency is declared."
        ),
        backstory=(
            "You control the Unitree Go2 quadruped dog. "
            "Goals are published as geometry_msgs/PointStamped to /goal_point "
            "and processed by the FAR Planner autonomy stack. "
            "You must only navigate to known locations or explicit coordinates "
            "and always verify arrival before proceeding."
        ),
        tools=[
            Go2NavigateToLocationTool(),
            Go2NavigateToCoordTool(),
            Go2StatusTool(),
            Go2StopTool(),
            Go2ListLocationsTool(),
        ],
        llm=_llm,
        verbose=True,
        allow_delegation=False,
    )
