import math

from crew_system.trace import StepTrace
from crew_system.contracts import check, substitution_violations, GROUNDING_CODES
from crew_system.contract_spec import NO_TARGET_FIX
from ros_bridge.skill_registry import (IRIS_SKILL_REGISTRY, TB3_SKILL_REGISTRY,
                                       VICTIM_TARGET)


def _coerce(value, default):
    """Fall back to the registry default when the planner emitted null or a
    wrong-typed value (non-enforcing arms still dispatch such steps)."""
    if isinstance(default, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return float(value) if ok else default
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    return default if value is None else value


def _dispatch(step, iris, tb3):
    if step.robot == "iris" and step.skill in IRIS_SKILL_REGISTRY:
        method, argspec = IRIS_SKILL_REGISTRY[step.skill]
        return getattr(iris, method)(
            *(_coerce(step.args.get(name), default) for name, default in argspec))
    if step.robot == "tb3":
        if step.skill == "navigate_to":
            # Special-cased: the goal is either the victim binding (resolved
            # against the state interface) or literal coordinates.
            return tb3.navigate_to(target=step.args.get("target"),
                                   x=step.args.get("x"), y=step.args.get("y"))
        if step.skill in TB3_SKILL_REGISTRY:
            method, argspec = TB3_SKILL_REGISTRY[step.skill]
            return getattr(tb3, method)(
                *(_coerce(step.args.get(name), default) for name, default in argspec))
    return f"[REFUSED] no adapter for {step.robot}:{step.skill}"


def _fix_missing(state):
    fix = state.get("victim_fix")
    if fix is None:
        return True
    try:
        return not (math.isfinite(float(fix[0])) and math.isfinite(float(fix[1])))
    except (TypeError, ValueError, IndexError):
        return True


def _dynamic_codes(step, state):
    """Dispatch-time state checks that static plan checking cannot decide:
    the rover's victim binding resolves against the state interface only
    after the drone's search has (or has not) published a finite fix."""
    if (step.robot == "tb3" and step.skill == "navigate_to"
            and isinstance(step.args.get("target"), str)
            and step.args["target"].lower().strip() == VICTIM_TARGET
            and _fix_missing(state)):
        return [NO_TARGET_FIX]
    return []


def execute_plan(plan, family, iris, tb3, enforce, state=None, request=None,
                 refuse_all=False):
    """refuse_all: plan-level fault (e.g. malformed planner output) -- when
    enforcing, no step may dispatch even if the step itself checks clean.

    `state` is the shared state-interface dict: the adapters write the victim
    fix into it during execution, and each step's dispatch-time checks read
    it at that step's turn."""
    if state is None:
        state = {"iris_busy": False, "tb3_busy": False}
    violations = check(plan, family, state)
    if request is not None:
        violations = violations + substitution_violations(plan, request)
    by_index = {}
    for v in violations:
        by_index.setdefault(v.step_index, []).append(v.code)

    steps = []
    refused = False
    for i, step in enumerate(plan):
        codes = by_index.get(i, []) + _dynamic_codes(step, state)
        grounded = not any(c in GROUNDING_CODES for c in codes)
        if enforce and (codes or refuse_all):
            steps.append(StepTrace(step, dispatched=False, grounded=grounded,
                                   result="[REFUSED] " + (", ".join(codes) or "malformed_plan"),
                                   violations=codes))
            refused = True
            continue
        result = _dispatch(step, iris, tb3)
        steps.append(StepTrace(step, dispatched=True, grounded=grounded,
                               result=result, violations=codes))
    return steps, refused
