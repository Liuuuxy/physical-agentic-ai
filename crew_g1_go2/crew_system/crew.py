#!/usr/bin/env python3
"""Assembles and runs the dual-robot CrewAI crew behind the contract gate."""

import json
from dataclasses import asdict

from crewai import Crew, Process

from crew_system.agents import make_task_router, make_g1_agent, make_go2_agent
from crew_system.gate import GATE
from crew_system.routers import build_instructions
from crew_system.tasks import (
    make_routing_task,
    make_g1_execution_task,
    make_go2_execution_task,
)
from ros_bridge.bridge_node import get_bridge


def _plan_once(router, human_request: str, feedback=None) -> str:
    task = make_routing_task(router, human_request,
                             extra_instructions=build_instructions("rao", feedback))
    crew = Crew(agents=[router], tasks=[task], process=Process.sequential, verbose=True)
    return str(crew.kickoff())


def run_mission(human_request: str) -> str:
    """
    Full pipeline for one human command, mirroring the eval path:
      1. The router plans with retrieved skills, locations, and workflow
         contracts in context.
      2. The contract gate parses and checks the plan; a refused plan gets
         ONE feedback-driven replan, then a structured refusal -- no robot
         action is dispatched from a plan that failed its contract.
      3. Execution agents run with the gate armed: every dispatching tool
         call must match a pending step of the approved plan and satisfy
         the family's ordering rules.
    """
    router = make_task_router()
    g1_ctrl, _ = get_bridge()
    state = {"g1_busy": g1_ctrl is None, "go2_busy": False}  # GO2_ONLY => no G1

    raw = _plan_once(router, human_request)
    res = GATE.arm(raw, request=human_request, state=state)
    if not res.ok:
        raw = _plan_once(router, human_request, feedback=res.feedback())
        res = GATE.arm(raw, request=human_request, state=state)
        if not res.ok:
            GATE.disarm()
            return ("[MISSION REFUSED] plan violates the workflow contract "
                    f"({res.feedback()}); no robot action was dispatched.")

    try:
        plan_text = json.dumps({"workflow_family": res.family,
                                "steps": [asdict(s) for s in res.plan]})
        agents, tasks = [], []
        if any(s.robot == "g1" for s in res.plan):
            g1_agent = make_g1_agent()
            agents.append(g1_agent)
            tasks.append(make_g1_execution_task(g1_agent, plan_text=plan_text))
        if any(s.robot == "go2" for s in res.plan):
            go2_agent = make_go2_agent()
            agents.append(go2_agent)
            tasks.append(make_go2_execution_task(go2_agent, plan_text=plan_text))

        crew = Crew(agents=agents, tasks=tasks, process=Process.sequential,
                    verbose=True)
        result = crew.kickoff()
    finally:
        GATE.disarm()  # nothing between arm and here may leave the gate armed
    return str(result)
