#!/usr/bin/env python3
"""RAO live mission runner against the Dockerized Gazebo simulation.

Same pipeline as crew_system/eval_mission.py, with the mock adapters swapped
for the GazeboIris/GazeboTb3 controllers: planner (live LLM or --plan JSON)
-> parse -> contract check -> enforce-and-dispatch one skill at a time via
the real ROS 2 services, with one feedback-driven replan under rao. Prints
the MissionTrace plus physical outcomes (victim fix, rover final pose,
delivery error, wall time).

Prerequisite: the sar container is up (see sar_ws/docker/README.md) and
rao_skill_call.py has been copied in:
  docker cp sar_ws/docker/rao_skill_call.py sar:/tmp/rao_skill_call.py

Usage:
  cd sar_ws/crew_sar
  python run_gazebo_mission.py --request "..." [--baseline rao]
      [--fault none|nan_transmission|missed_detection] [--plan plan.json]
"""
import argparse
import json
import math
import time

from crew_system.trace import MissionTrace
from crew_system.plan_parser import parse_plan
from crew_system.contracts import infer_family, KNOWN_FAMILIES
from crew_system.orchestrator import execute_plan
from crew_system.eval_mission import _violation_feedback
from ros_bridge.gazebo_bridge import GazeboIrisController, GazeboTb3Controller
from ros_bridge.skill_registry import TRUE_VICTIM

_IDLE = {"iris_busy": False, "tb3_busy": False}


def _family_of(declared, plan):
    return declared if declared in KNOWN_FAMILIES else infer_family(plan)


def _run_once(plan, family, enforce, request, fault, malformed=False):
    state = dict(_IDLE)
    iris = GazeboIrisController(state, fault=fault)
    tb3 = GazeboTb3Controller(state)
    steps, refused = execute_plan(plan, family, iris, tb3, enforce=enforce,
                                  state=state, request=request,
                                  refuse_all=malformed)
    return steps, refused, state, tb3


def run_live_mission(request, baseline="rao", router=None, fault="none"):
    if router is None:
        from crew_system.routers import live_router
        router = live_router
    t0 = time.time()
    enforce = (baseline == "rao")

    raw, llm_calls = router(request, baseline)
    declared, plan, problems = parse_plan(raw)
    family = _family_of(declared, plan)
    steps, refused, state, tb3 = _run_once(plan, family, enforce, request,
                                           fault, malformed=bool(problems))
    if enforce and problems:
        refused = True

    replan_attempted = replanned = False
    if enforce and refused:
        replan_attempted = True
        raw2, calls2 = router(request, baseline, _violation_feedback(steps, problems))
        llm_calls += calls2
        declared2, plan2, problems2 = parse_plan(raw2)
        family2 = _family_of(declared2, plan2)
        steps2, refused2, state2, tb3_2 = _run_once(
            plan2, family2, enforce, request, fault, malformed=bool(problems2))
        if problems2:
            refused2 = True
        if not refused2:
            declared, plan, steps, refused, family, problems = (
                declared2, plan2, steps2, refused2, family2, problems2)
            state, tb3 = state2, tb3_2
            replanned = True

    mt = MissionTrace(request=request, baseline=baseline,
                      declared_family=declared, plan=plan, steps=steps,
                      refused=refused, replanned=replanned,
                      llm_calls=llm_calls, latency_s=time.time() - t0,
                      replan_attempted=replan_attempted,
                      parse_problems=list(problems))

    pose = tb3.final_position()
    fix = state.get("victim_fix")
    outcome = {
        "victim_fix": None if fix is None else list(fix),
        "rover_final_pose": None if pose is None else list(pose),
        "delivery_error_m": (math.hypot(pose[0] - TRUE_VICTIM[0],
                                        pose[1] - TRUE_VICTIM[1])
                             if pose is not None else None),
        "mission_wall_time_s": round(time.time() - t0, 1),
    }
    return mt, outcome


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--baseline", default="rao",
                    choices=["llm-only", "skill-list", "rao-prompt", "rao"])
    ap.add_argument("--fault", default="none",
                    choices=["none", "nan_transmission", "missed_detection"])
    ap.add_argument("--plan", default=None,
                    help="path to a raw planner-output file (skips the LLM)")
    args = ap.parse_args()

    router = None
    if args.plan:
        raw = open(args.plan).read()
        router = lambda request, baseline, feedback=None: (raw, 0)  # noqa: E731

    mt, outcome = run_live_mission(args.request, baseline=args.baseline,
                                   router=router, fault=args.fault)
    print(json.dumps({"trace": mt.to_dict(), "outcome": outcome}, indent=2))


if __name__ == "__main__":
    main()
