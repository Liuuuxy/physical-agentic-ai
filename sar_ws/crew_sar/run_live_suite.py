#!/usr/bin/env python3
"""Live full-system suite: all 20 scenarios once, baseline=rao, against the
Dockerized Gazebo sim. Mirrors eval.run_eval semantics -- state faults
(iris/tb3_unavailable) injected into the dispatch state, perception faults
(nan_transmission, missed_detection) injected in the Iris adapter -- with the
live Gazebo controllers of run_gazebo_mission.py. The sar container is
restarted before every mission so each starts from spawn poses.

Usage:
  cd sar_ws/crew_sar
  OPENAI_API_KEY=... python3 run_live_suite.py [--limit N] [--out FILE]
"""
import argparse
import json
import math
import subprocess
import time

from crew_system.trace import MissionTrace
from crew_system.plan_parser import parse_plan
from crew_system.contracts import infer_family, KNOWN_FAMILIES
from crew_system.eval_mission import _violation_feedback
from crew_system.orchestrator import execute_plan
from crew_system.routers import live_router
from ros_bridge.gazebo_bridge import GazeboIrisController, GazeboTb3Controller
from ros_bridge.skill_registry import TRUE_VICTIM
from eval.scenarios import load_scenarios
from eval.run_eval import _FAULT_STATE

PERCEPTION_FAULTS = {"nan_transmission", "missed_detection"}
_IDLE = {"iris_busy": False, "tb3_busy": False}
_BOOT = ["docker", "run", "-d", "--name", "sar", "--shm-size=1g",
         "sar-sim:humble", "bash", "-c",
         "source /opt/ros/humble/setup.bash && "
         "source /sar_ws/install/setup.bash && "
         "ros2 launch sar_gazebo sar_simulation.launch.py headless:=1 "
         "px4_autopilot_dir:=/px4/PX4-Autopilot"]
_PROBE = ("source /opt/ros/humble/setup.bash && "
          "source /sar_ws/install/setup.bash && ros2 service list")


def restart_container():
    subprocess.run(["docker", "rm", "-f", "sar"], capture_output=True)
    subprocess.run(_BOOT, check=True, capture_output=True)
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(5)
        out = subprocess.run(["docker", "exec", "sar", "bash", "-lc", _PROBE],
                             capture_output=True, text=True).stdout
        if "/rover/navigate_to" in out and "/drone/takeoff" in out:
            time.sleep(10)  # let controllers finish settling
            subprocess.run(["docker", "cp", "../docker/rao_skill_call.py",
                            "sar:/tmp/rao_skill_call.py"], check=True)
            return
    raise RuntimeError("sar container not ready within 180 s")


def _dispatch(sc, plan, family, malformed, enforce):
    state = dict(_IDLE)
    state.update(_FAULT_STATE.get(sc.fault) or {})
    fault = sc.fault if sc.fault in PERCEPTION_FAULTS else "none"
    iris = GazeboIrisController(state, fault=fault)
    tb3 = GazeboTb3Controller(state)
    steps, refused = execute_plan(plan, family, iris, tb3, enforce=enforce,
                                  state=state, request=sc.request,
                                  refuse_all=malformed)
    return steps, refused, state, tb3


def run_one(sc, baseline="rao"):
    t0 = time.time()
    enforce = (baseline == "rao")
    raw, llm_calls = live_router(sc.request, baseline)
    declared, plan, problems = parse_plan(raw)
    family = declared if declared in KNOWN_FAMILIES else infer_family(plan)
    steps, refused, state, tb3 = _dispatch(sc, plan, family, bool(problems),
                                           enforce)
    if enforce and problems:
        refused = True

    replan_attempted = replanned = False
    if enforce and refused:
        replan_attempted = True
        raw2, c2 = live_router(sc.request, baseline,
                               _violation_feedback(steps, problems))
        llm_calls += c2
        declared2, plan2, problems2 = parse_plan(raw2)
        family2 = (declared2 if declared2 in KNOWN_FAMILIES
                   else infer_family(plan2))
        steps2, refused2, state2, tb32 = _dispatch(sc, plan2, family2,
                                                   bool(problems2), enforce)
        if problems2:
            refused2 = True
        if not refused2:
            declared, plan, steps, refused, family = (
                declared2, plan2, steps2, refused2, family2)
            state, tb3, problems = state2, tb32, problems2
            replanned = True

    mt = MissionTrace(request=sc.request, baseline=baseline,
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
    return {"id": sc.id, "fault": sc.fault, "should_block": sc.should_block,
            "expected_family": sc.expected_family,
            "trace": mt.to_dict(), "outcome": outcome}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--baseline", default="rao",
                    choices=["llm-only", "skill-list", "rao-prompt", "rao"])
    ap.add_argument("--faults-only", action="store_true")
    ap.add_argument("--out", default="results_live_suite_20260810.json")
    args = ap.parse_args()
    scenarios = load_scenarios()
    if args.faults_only:
        scenarios = [sc for sc in scenarios if sc.should_block]
    if args.limit is not None:
        scenarios = scenarios[:args.limit]
    records = []
    for k, sc in enumerate(scenarios, 1):
        print(f"[{k}/{len(scenarios)}] {sc.id} (fault={sc.fault}, "
              f"baseline={args.baseline}) -- restarting sim...", flush=True)
        restart_container()
        rec = run_one(sc, baseline=args.baseline)
        records.append(rec)
        with open(args.out, "w") as f:
            json.dump(records, f, indent=1)
        print(f"    refused={rec['trace']['refused']} "
              f"steps={len(rec['trace']['steps'])} "
              f"err={rec['outcome']['delivery_error_m']} "
              f"t={rec['outcome']['mission_wall_time_s']}s", flush=True)
    print(f"wrote {args.out} ({len(records)} missions)")


if __name__ == "__main__":
    main()
