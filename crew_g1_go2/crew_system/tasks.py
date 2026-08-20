#!/usr/bin/env python3
"""CrewAI task definitions for the dual-robot system."""

from crewai import Task
from crewai import Agent


def make_routing_task(router: Agent, human_request: str, extra_instructions: str = "") -> Task:
    base_description = (
        f"A human has given the following request:\n\n"
        f'  "{human_request}"\n\n'
        "Analyse it and produce an ordered plan. For each step specify:\n"
        "  - which robot (G1 or Go2)\n"
        "  - the exact action (use g1_list_tasks and go2_list_locations "
        "    tools to check available options)\n"
        "  - any relevant parameters (location name, task name)\n\n"
        "Format:\n"
        "  Step 1 – <Robot>: <action>\n"
        "  Step 2 – <Robot>: <action>\n"
        "  ...\n"
        "If the request cannot be fulfilled with the available actions, "
        "explain why."
    )
    description = base_description + ("\n\n" + extra_instructions if extra_instructions else "")
    return Task(
        description=description,
        expected_output=(
            "A numbered list of robot actions derived from the human request, "
            "using only valid task names and location names."
        ),
        agent=router,
    )


def _plan_prefix(plan_text: str) -> str:
    if not plan_text:
        return ""
    return (
        "The contract-checked APPROVED plan for this mission is:\n"
        f"{plan_text}\n"
        "Execute ONLY the steps assigned to your robot, in order. Any "
        "robot-dispatching tool call outside this plan will be refused by "
        "the contract gate; status/list/stop tools remain available.\n\n"
    )


def make_g1_execution_task(g1_agent: Agent, context_tasks: list = None,
                           plan_text: str = "") -> Task:
    return Task(
        description=_plan_prefix(plan_text) + (
            "Execute all G1 humanoid steps from the routing plan. "
            "For each G1 step:\n"
            "  1. Call g1_execute_task with the correct task_name.\n"
            "  2. Call g1_status to confirm completion.\n"
            "  3. Report the result.\n"
            "Do not proceed to the next step until the current one is confirmed."
        ),
        expected_output=(
            "A summary of each G1 step: task name, outcome (success/failure), "
            "and any errors encountered."
        ),
        agent=g1_agent,
        context=context_tasks or None,
    )


def make_go2_execution_task(go2_agent: Agent, context_tasks: list = None,
                            plan_text: str = "") -> Task:
    return Task(
        description=_plan_prefix(plan_text) + (
            "Execute all Go2 navigation steps from the routing plan. "
            "For each Go2 step:\n"
            "  1. Call go2_navigate_to_location (or go2_navigate_to_coord "
            "     for explicit coordinates).\n"
            "  2. The tool blocks until arrival – report the result.\n"
            "  3. Call go2_status to confirm the final position.\n"
            "If navigation fails or times out, call go2_stop and report the error."
        ),
        expected_output=(
            "A summary of each Go2 navigation step: destination, "
            "outcome (arrived/timeout/error), and final position."
        ),
        agent=go2_agent,
        context=context_tasks or None,
    )
