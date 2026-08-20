from crew_system.trace import StepTrace
from crew_system.contracts import check, substitution_violations, GROUNDING_CODES
from ros_bridge.go2_controller import GO2_SKILL_REGISTRY


def _coerce(value, default):
    """Fall back to the registry default when the planner emitted null or a
    wrong-typed value (non-enforcing arms still dispatch such steps)."""
    if isinstance(default, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return float(value) if ok else default
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    return default if value is None else value


def _dispatch(step, g1, go2):
    if step.robot == "g1":
        return g1.execute_task(step.skill)
    if step.robot == "go2" and step.skill in GO2_SKILL_REGISTRY:
        method, argspec = GO2_SKILL_REGISTRY[step.skill]
        return getattr(go2, method)(
            *(_coerce(step.args.get(name), default) for name, default in argspec))
    return f"[REFUSED] no adapter for {step.robot}:{step.skill}"


def execute_plan(plan, family, g1, go2, enforce, state=None, request=None,
                 refuse_all=False):
    """refuse_all: plan-level fault (e.g. malformed planner output) -- when
    enforcing, no step may dispatch even if the step itself checks clean."""
    if state is None:
        state = {"g1_busy": False, "go2_busy": False}
    violations = check(plan, family, state)
    if request is not None:
        violations = violations + substitution_violations(plan, request)
    by_index = {}
    for v in violations:
        by_index.setdefault(v.step_index, []).append(v.code)

    steps = []
    refused = False
    for i, step in enumerate(plan):
        codes = by_index.get(i, [])
        grounded = not any(c in GROUNDING_CODES for c in codes)
        if enforce and (codes or refuse_all):
            steps.append(StepTrace(step, dispatched=False, grounded=grounded,
                                   result="[REFUSED] " + (", ".join(codes) or "malformed_plan"),
                                   violations=codes))
            refused = True
            continue
        result = _dispatch(step, g1, go2)
        steps.append(StepTrace(step, dispatched=True, grounded=grounded,
                               result=result, violations=codes))
    return steps, refused
