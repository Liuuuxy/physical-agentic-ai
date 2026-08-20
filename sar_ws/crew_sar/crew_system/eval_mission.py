# crew_sar/crew_system/eval_mission.py
"""Mock-execution entry point for the baseline study. Independent of the
live-Gazebo path so unit tests need neither crewai nor rclpy.

`mock_fault` carries the per-scenario perception fault into the mock Iris
adapter (nan_transmission / missed_detection); the resulting bad fix then
surfaces at the rover's dispatch through the state interface -- the same
channel the gate checks."""
import time

from ros_bridge.mock_bridge import MockIrisController, MockTb3Controller
from crew_system.trace import MissionTrace
from crew_system.plan_parser import parse_plan
from crew_system.contracts import infer_family, KNOWN_FAMILIES, MALFORMED_PLAN
from crew_system.orchestrator import execute_plan

_IDLE = {"iris_busy": False, "tb3_busy": False}


def _family_of(declared, plan):
    return declared if declared in KNOWN_FAMILIES else infer_family(plan)


def _violation_feedback(steps, problems=()):
    codes = sorted({c for st in steps for c in st.violations})
    if problems:
        codes.append(MALFORMED_PLAN + " (" + "; ".join(problems) + ")")
    return "violations: " + ", ".join(codes) if codes else "plan was refused"


def _run_once(plan, family, enforce, initial_state, request, malformed=False,
              mock_fault="none"):
    state = dict(initial_state) if initial_state else dict(_IDLE)
    iris = MockIrisController(state, fault=mock_fault)
    tb3 = MockTb3Controller(state)
    return execute_plan(plan, family, iris, tb3, enforce=enforce, state=state,
                        request=request, refuse_all=malformed)


def run_eval_mission(request, baseline="rao", router=None, initial_state=None,
                     mock_fault="none"):
    if router is None:
        from crew_system.routers import live_router
        router = live_router
    t0 = time.time()
    enforce = (baseline == "rao")

    raw, llm_calls = router(request, baseline)
    declared_family, plan, problems = parse_plan(raw)
    family = _family_of(declared_family, plan)
    steps, refused = _run_once(plan, family, enforce, initial_state, request,
                               malformed=bool(problems), mock_fault=mock_fault)
    if enforce and problems:  # malformed output fails closed, not silently open
        refused = True

    replan_attempted = replanned = False
    # RAO recovers from a refused plan with a single feedback-driven retry.
    if enforce and refused:
        replan_attempted = True
        raw2, calls2 = router(request, baseline, _violation_feedback(steps, problems))
        llm_calls += calls2
        declared2, plan2, problems2 = parse_plan(raw2)
        family2 = _family_of(declared2, plan2)
        steps2, refused2 = _run_once(plan2, family2, enforce, initial_state, request,
                                     malformed=bool(problems2), mock_fault=mock_fault)
        if problems2:
            refused2 = True
        if not refused2:  # recovered
            declared_family, plan, steps, refused, family, problems = (
                declared2, plan2, steps2, refused2, family2, problems2)
            replanned = True

    return MissionTrace(
        request=request, baseline=baseline,
        declared_family=declared_family, plan=plan, steps=steps,
        refused=refused, replanned=replanned, llm_calls=llm_calls,
        latency_s=time.time() - t0, replan_attempted=replan_attempted,
        parse_problems=list(problems),
    )
