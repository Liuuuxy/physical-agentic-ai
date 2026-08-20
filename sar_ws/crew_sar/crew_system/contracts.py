# crew_sar/crew_system/contracts.py
"""Contract checking: grounds a plan against the skill registries and
interprets the declarative WorkflowContract specs in contract_spec.py.
This module is the public checking API; the specs themselves (and the
violation codes) live in contract_spec so prompt rendering, enforcement,
and metrics all read one source."""
import math
import re

from crew_system.contract_spec import (  # noqa: F401  (re-exported)
    Violation, CONTRACT_REGISTRY, KNOWN_FAMILIES,
    GROUNDING_CODES, CONTRACT_CODES, STATE_CODES,
    UNKNOWN_SKILL, UNKNOWN_LOCATION, UNKNOWN_ROBOT, MISSING_ARG,
    BAD_ASSIGNMENT, ORDER_VIOLATION, ROBOT_BUSY, SUBSTITUTED_LOCATION,
    NO_TARGET_FIX, MALFORMED_PLAN, OFF_PLAN,
)
from ros_bridge.skill_registry import (
    IRIS_SKILL_REGISTRY, TB3_SKILL_REGISTRY, OPERATIONAL_BOUNDS,
    REQUIRED_ARGS, VICTIM_TARGET,
)

IRIS_SKILLS = set(IRIS_SKILL_REGISTRY.keys())
TB3_SKILLS = set(TB3_SKILL_REGISTRY.keys())


def infer_family(plan) -> str:
    """Fallback classifier when the LLM's declared family is missing or
    invalid: derive the applicable contract from the plan's shape."""
    iris = [s for s in plan if s.robot == "iris"]
    tb3 = [s for s in plan if s.robot == "tb3"]
    if plan and all(s.skill in ("land", "stop") for s in plan):
        return "abort"
    if iris and tb3:
        return "search_and_dispatch"
    if tb3 and not iris:
        return "dispatch_only"
    return "search_only"


def _num(v) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


def _in_bounds(x, y) -> bool:
    x_min, x_max, y_min, y_max = OPERATIONAL_BOUNDS
    return x_min <= x <= x_max and y_min <= y <= y_max


def _iris_arg_violations(s, i):
    out = []
    _, argspec = IRIS_SKILL_REGISTRY[s.skill]
    required = REQUIRED_ARGS.get(s.skill, ())
    for name, _default in argspec:
        v = s.args.get(name)
        if v is None:
            if name in required:
                out.append(Violation(MISSING_ARG, i, f"{s.skill} needs '{name}'"))
        elif not _num(v):
            out.append(Violation(UNKNOWN_LOCATION, i,
                                 f"non-numeric {name} {v!r}"))
    if out:
        return out
    # All supplied args are numeric; check the geometry against the map.
    if s.skill == "search_target":
        x_min, x_max = s.args.get("x_min"), s.args.get("x_max")
        y_min, y_max = s.args.get("y_min"), s.args.get("y_max")
        if None not in (x_min, x_max, y_min, y_max):
            if not (x_min < x_max and y_min < y_max):
                out.append(Violation(UNKNOWN_LOCATION, i, "degenerate search zone"))
            elif not (_in_bounds(x_min, y_min) and _in_bounds(x_max, y_max)):
                out.append(Violation(UNKNOWN_LOCATION, i,
                                     "search zone outside the operational area"))
    elif s.skill == "fly_to":
        x, y = s.args.get("x"), s.args.get("y")
        if None not in (x, y) and not _in_bounds(x, y):
            out.append(Violation(UNKNOWN_LOCATION, i,
                                 f"({x}, {y}) outside the operational area"))
    return out


def _tb3_navigate_violations(s, i):
    target = s.args.get("target")
    x, y = s.args.get("x"), s.args.get("y")
    if target is not None:
        if not (isinstance(target, str)
                and target.lower().strip() == VICTIM_TARGET):
            return [Violation(UNKNOWN_LOCATION, i,
                              f"unknown navigation target {target!r}")]
        return []
    if x is not None or y is not None:
        if x is None or y is None:
            missing = "y" if y is None else "x"
            return [Violation(MISSING_ARG, i, f"navigate_to needs '{missing}'")]
        if not (_num(x) and _num(y)):
            return [Violation(UNKNOWN_LOCATION, i,
                              f"non-numeric coordinates ({x!r}, {y!r})")]
        if not _in_bounds(x, y):
            return [Violation(UNKNOWN_LOCATION, i,
                              f"({x}, {y}) outside the operational area")]
        return []
    return [Violation(MISSING_ARG, i,
                      'navigate_to needs {"target": "victim"} or numeric x, y')]


def _grounding_violations(plan):
    out = []
    for i, s in enumerate(plan):
        if s.robot == "iris":
            if s.skill not in IRIS_SKILL_REGISTRY:
                out.append(Violation(UNKNOWN_SKILL, i, f"iris has no skill '{s.skill}'"))
                continue
            out.extend(_iris_arg_violations(s, i))
        elif s.robot == "tb3":
            if s.skill not in TB3_SKILL_REGISTRY:
                out.append(Violation(UNKNOWN_SKILL, i, f"tb3 has no skill '{s.skill}'"))
                continue
            if s.skill == "navigate_to":
                out.extend(_tb3_navigate_violations(s, i))
        else:
            out.append(Violation(UNKNOWN_ROBOT, i, f"unknown robot '{s.robot}'"))
    return out


def _family_violations(plan, family):
    contract = CONTRACT_REGISTRY.get(family)
    return contract.violations(plan) if contract else []


def _binding_violations(plan, family):
    """In search_and_dispatch the rover goal exists only at execution time,
    so the plan must bind it to the drone-published fix. A literal
    coordinate here is by construction not the victim's location -- and is
    the exact laundering move that bypasses the NaN/missed-detection gate."""
    if family != "search_and_dispatch":
        return []
    return [Violation(SUBSTITUTED_LOCATION, i,
                      "rover goal must bind to the drone-published victim fix "
                      '({"target": "victim"}), not literal coordinates')
            for i, s in enumerate(plan)
            if s.robot == "tb3" and s.skill == "navigate_to"
            and s.args.get("target") is None]


def _state_violations(plan, state):
    out = []
    for i, s in enumerate(plan):
        if s.robot == "iris" and state.get("iris_busy"):
            out.append(Violation(ROBOT_BUSY, i, "iris is busy"))
        if s.robot == "tb3" and state.get("tb3_busy"):
            out.append(Violation(ROBOT_BUSY, i, "tb3 is busy"))
    return out


def check(plan, family, state):
    return (_grounding_violations(plan)
            + _family_violations(plan, family)
            + _binding_violations(plan, family)
            + _state_violations(plan, state))


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_TOL = 0.25


def _request_numbers(request):
    return [float(t) for t in _NUM_RE.findall(request or "")]


def _near(a, b):
    return abs(a - b) <= _TOL


def substitution_violations(plan, request):
    """Flag steps whose *valid* literal geometry was never stated in the
    request -- the planner invented or substituted a destination/zone instead
    of copying the request (laundering an unsatisfiable request into a
    plausible-but-wrong one). This catches semantic errors the bounds and
    ordering checks cannot. Out-of-bounds or non-numeric values are left to
    grounding (`unknown_location`).

    Rover goals must match an ADJACENT number pair in the request (pooled
    matching would let '(4.0, 7.5)' pass against a request naming (7.5, 4.0));
    search-zone bounds match pooled, since zone phrasings like 'between -5.5
    and 5.5 on both axes' state shared values once."""
    nums = _request_numbers(request)
    pairs = list(zip(nums, nums[1:]))
    out = []
    for i, s in enumerate(plan):
        if s.robot == "tb3" and s.skill == "navigate_to":
            if s.args.get("target") is not None:
                continue  # the victim binding is never a substitution
            x, y = s.args.get("x"), s.args.get("y")
            if not (_num(x) and _num(y)) or not _in_bounds(x, y):
                continue  # invalid coordinates are grounding's job
            if not any(_near(x, a) and _near(y, b) for a, b in pairs):
                out.append(Violation(SUBSTITUTED_LOCATION, i,
                                     f"navigates to ({x}, {y}), not stated in the request"))
        elif s.robot == "iris" and s.skill == "search_target":
            bounds = [s.args.get(k) for k in ("x_min", "x_max", "y_min", "y_max")]
            if not all(_num(b) for b in bounds):
                continue  # missing/non-numeric bounds are grounding's job
            if not (bounds[0] < bounds[1] and bounds[2] < bounds[3]
                    and _in_bounds(bounds[0], bounds[2])
                    and _in_bounds(bounds[1], bounds[3])):
                continue  # invalid zones are grounding's job
            if not all(any(_near(b, v) for v in nums) for b in bounds):
                out.append(Violation(SUBSTITUTED_LOCATION, i,
                                     "search zone not stated in the request"))
    return out
