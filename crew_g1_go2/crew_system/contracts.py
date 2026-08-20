# crew_g1_go2/crew_system/contracts.py
"""Contract checking: grounds a plan against the skill registries and
interprets the declarative WorkflowContract specs in contract_spec.py.
This module is the public checking API; the specs themselves (and the
violation codes) live in contract_spec so prompt rendering, enforcement,
and metrics all read one source."""
from crew_system.contract_spec import (  # noqa: F401  (re-exported)
    Violation, CONTRACT_REGISTRY, KNOWN_FAMILIES,
    GROUNDING_CODES, CONTRACT_CODES, STATE_CODES,
    UNKNOWN_SKILL, UNKNOWN_LOCATION, UNKNOWN_ROBOT, MISSING_ARG,
    BAD_ASSIGNMENT, ORDER_VIOLATION, ROBOT_BUSY, SUBSTITUTED_LOCATION,
    MALFORMED_PLAN, OFF_PLAN,
)
from g1_tasks.sequences import TASK_REGISTRY
from ros_bridge.go2_controller import GO2_SKILL_REGISTRY, NAMED_LOCATIONS

G1_SKILLS = set(TASK_REGISTRY.keys())
GO2_SKILLS = set(GO2_SKILL_REGISTRY.keys())


def infer_family(plan) -> str:
    """Fallback classifier when the LLM's declared family is missing or
    invalid: derive the applicable contract from the plan's shape."""
    g1 = [s for s in plan if s.robot == "g1"]
    go2 = [s for s in plan if s.robot == "go2"]
    if g1 and go2:
        return "carry"
    if go2 and not g1:
        return "navigation_only"
    if any(s.skill == "hand_over" for s in g1):
        return "handover"
    return "manipulation_only"


def _grounding_violations(plan):
    out = []
    for i, s in enumerate(plan):
        if s.robot == "g1":
            if s.skill not in G1_SKILLS:
                out.append(Violation(UNKNOWN_SKILL, i, f"g1 has no skill '{s.skill}'"))
        elif s.robot == "go2":
            if s.skill not in GO2_SKILL_REGISTRY:
                out.append(Violation(UNKNOWN_SKILL, i, f"go2 has no skill '{s.skill}'"))
                continue
            _, argspec = GO2_SKILL_REGISTRY[s.skill]
            for name, _default in argspec:
                if s.args.get(name) is None:
                    out.append(Violation(MISSING_ARG, i, f"{s.skill} needs '{name}'"))
            loc = s.args.get("location")
            if s.skill == "navigate_to_location" and loc is not None:
                if not isinstance(loc, str):
                    out.append(Violation(UNKNOWN_LOCATION, i,
                                         f"non-string location {loc!r}"))
                elif loc.lower().strip() not in NAMED_LOCATIONS:
                    out.append(Violation(UNKNOWN_LOCATION, i,
                                         f"unknown location '{loc}'"))
        else:
            out.append(Violation(UNKNOWN_ROBOT, i, f"unknown robot '{s.robot}'"))
    return out


def _family_violations(plan, family):
    contract = CONTRACT_REGISTRY.get(family)
    return contract.violations(plan) if contract else []


def _state_violations(plan, state):
    out = []
    for i, s in enumerate(plan):
        if s.robot == "g1" and state.get("g1_busy"):
            out.append(Violation(ROBOT_BUSY, i, "g1 is busy"))
        if s.robot == "go2" and state.get("go2_busy"):
            out.append(Violation(ROBOT_BUSY, i, "go2 is busy"))
    return out


def check(plan, family, state):
    return (_grounding_violations(plan)
            + _family_violations(plan, family)
            + _state_violations(plan, state))


def _squash(text):
    """Normalize for containment: lowercase alphanumerics only, so that
    'room_b', 'room b', and 'dropoff' vs 'drop off' all compare equal."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def substitution_violations(plan, request):
    """Flag navigate steps whose destination is a *valid* location that was never
    named in the request -- i.e., the planner silently substituted a destination
    (laundering an unsatisfiable request into a plausible-but-wrong one). This
    catches semantic errors the name/ordering gate cannot. Invalid location names
    are left to grounding (`unknown_location`)."""
    req = _squash(request or "")
    out = []
    for i, s in enumerate(plan):
        if s.robot == "go2" and s.skill == "navigate_to_location":
            loc = s.args.get("location")
            if not isinstance(loc, str):
                continue  # non-string values are grounding's job
            loc = loc.lower().strip()
            if loc in NAMED_LOCATIONS and _squash(loc) not in req:
                out.append(Violation(SUBSTITUTED_LOCATION, i,
                                     f"navigates to '{loc}', not named in the request"))
    return out
