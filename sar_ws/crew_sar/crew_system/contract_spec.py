# crew_sar/crew_system/contract_spec.py
"""Declarative workflow-contract template for the air--ground SAR crew.

A WorkflowContract is the single source of truth for one workflow family.
The generic checker (`violations`) enforces the spec at dispatch time, and
the prompt renderer (`render`) derives the planner-facing prose from the
same spec, so the rules the LLM reads and the rules the gate runs cannot
drift. Adding a workflow family = adding one entry to CONTRACT_REGISTRY.

Same template and violation vocabulary as crew_g1_go2, plus one SAR-specific
state code: no_target_fix (the rover's victim binding has no finite fix on
the state interface at dispatch time)."""
from dataclasses import dataclass

# --- Violation codes: single source for the checker, orchestrator, gate,
# --- and metrics. Never re-type these strings elsewhere.
UNKNOWN_SKILL = "unknown_skill"
UNKNOWN_LOCATION = "unknown_location"
UNKNOWN_ROBOT = "unknown_robot"
MISSING_ARG = "missing_arg"
BAD_ASSIGNMENT = "bad_assignment"
ORDER_VIOLATION = "order_violation"
SUBSTITUTED_LOCATION = "substituted_location"
ROBOT_BUSY = "robot_busy"
NO_TARGET_FIX = "no_target_fix"    # dispatch-time: victim binding unresolved
MALFORMED_PLAN = "malformed_plan"  # plan-level: unparseable/incomplete LLM output
OFF_PLAN = "off_plan"              # runtime gate: dispatch not in the approved plan

GROUNDING_CODES = frozenset({UNKNOWN_SKILL, UNKNOWN_LOCATION, UNKNOWN_ROBOT,
                             MISSING_ARG})
CONTRACT_CODES = frozenset({BAD_ASSIGNMENT, ORDER_VIOLATION, SUBSTITUTED_LOCATION})
STATE_CODES = frozenset({ROBOT_BUSY, NO_TARGET_FIX})

ALL_ROBOTS = frozenset({"iris", "tb3"})
_DISPLAY = {"iris": "Iris", "tb3": "TB3"}


@dataclass
class Violation:
    code: str
    step_index: int
    detail: str


@dataclass(frozen=True)
class StepPattern:
    robot: str
    skills: frozenset | None = None  # None = any skill on that robot

    def matches(self, step) -> bool:
        return step.robot == self.robot and (
            self.skills is None or step.skill in self.skills)

    def describe(self) -> str:
        name = _DISPLAY.get(self.robot, self.robot)
        if self.skills is None:
            return f"any {name} step"
        return f"{name} {'/'.join(sorted(self.skills))}"


@dataclass(frozen=True)
class OrderingRule:
    """Every step matching `after` must be preceded by one matching `before`."""
    before: StepPattern
    after: StepPattern
    detail: str  # violation message shown in traces and replan feedback

    def first_offender(self, plan):
        a = next((i for i, s in enumerate(plan) if self.after.matches(s)), None)
        b = next((i for i, s in enumerate(plan) if self.before.matches(s)), None)
        if a is not None and (b is None or a < b):
            return a
        return None

    def render(self) -> str:
        return f"{self.after.describe()} must NOT come before {self.before.describe()}"


@dataclass(frozen=True)
class WorkflowContract:
    family: str
    allowed_robots: frozenset
    guidance: str  # free-text planner hint (canonical step sequence)
    ordering: tuple = ()
    skill_whitelist: frozenset | None = None  # None = any skill of an allowed robot

    def violations(self, plan) -> list:
        out, flagged = [], set()
        for i, s in enumerate(plan):
            if (s.robot in ALL_ROBOTS and s.robot not in self.allowed_robots
                    and s.robot not in flagged):
                flagged.add(s.robot)
                out.append(Violation(BAD_ASSIGNMENT, i,
                                     f"{self.family} must not use {s.robot}"))
            elif (self.skill_whitelist is not None
                    and s.robot in self.allowed_robots
                    and s.skill not in self.skill_whitelist):
                out.append(Violation(BAD_ASSIGNMENT, i,
                                     f"{self.family} does not include {s.robot}:{s.skill}"))
        for rule in self.ordering:
            idx = rule.first_offender(plan)
            if idx is not None:
                out.append(Violation(ORDER_VIOLATION, idx, rule.detail))
        return out

    def render(self) -> str:
        parts = [self.guidance]
        for r in sorted(ALL_ROBOTS - self.allowed_robots):
            parts.append(f"NO {_DISPLAY[r]} step")
        line = f"- {self.family}: " + "; ".join(parts) + "."
        for rule in self.ordering:
            line += " " + rule.render() + "."
        return line


_SEARCH_SKILLS = frozenset({"search_target", "get_coordinates"})

# Registry order is canonical: it drives both the prompt prose and the
# JSON-schema family list shown to the planner.
CONTRACT_REGISTRY = {
    "search_and_dispatch": WorkflowContract(
        family="search_and_dispatch",
        allowed_robots=frozenset({"iris", "tb3"}),
        guidance=("Iris takeoff, then Iris search_target over the exact zone "
                  'stated in the request, then TB3 navigate_to with args '
                  '{"target": "victim"} once the fix is published (the rover '
                  "goal must bind to the fix, never literal coordinates)"),
        ordering=(
            OrderingRule(
                before=StepPattern("iris", frozenset({"takeoff"})),
                after=StepPattern("iris", _SEARCH_SKILLS),
                detail="iris searches before takeoff (drone not airborne)"),
            OrderingRule(
                before=StepPattern("iris", _SEARCH_SKILLS),
                after=StepPattern("tb3", frozenset({"navigate_to"})),
                detail="tb3 dispatched before iris localizes the victim"),
        ),
        skill_whitelist=frozenset({"takeoff", "search_target", "get_coordinates",
                                   "fly_to", "land", "navigate_to"}),
    ),
    "search_only": WorkflowContract(
        family="search_only",
        allowed_robots=frozenset({"iris"}),
        guidance=("an Iris-only aerial survey: takeoff, search_target over "
                  "the exact zone stated in the request, then land"),
        ordering=(OrderingRule(
            before=StepPattern("iris", frozenset({"takeoff"})),
            after=StepPattern("iris", _SEARCH_SKILLS),
            detail="iris searches before takeoff (drone not airborne)"),),
        skill_whitelist=frozenset({"takeoff", "search_target",
                                   "get_coordinates", "fly_to", "land"}),
    ),
    "dispatch_only": WorkflowContract(
        family="dispatch_only",
        allowed_robots=frozenset({"tb3"}),
        guidance=("a single TB3 navigate_to step with explicit numeric x, y "
                  "taken from the request"),
        skill_whitelist=frozenset({"navigate_to"}),
    ),
    "abort": WorkflowContract(
        family="abort",
        allowed_robots=frozenset({"iris", "tb3"}),
        guidance="stand down: Iris land and/or TB3 stop, nothing else",
        skill_whitelist=frozenset({"land", "stop"}),
    ),
}

KNOWN_FAMILIES = frozenset(CONTRACT_REGISTRY)


def render_contracts_text() -> str:
    """Planner-prompt prose derived from the registry (never hand-written)."""
    return ("Workflow contracts (choose exactly ONE family and follow its "
            "ordering):\n"
            + "\n".join(c.render() for c in CONTRACT_REGISTRY.values()))


def families_json_list() -> str:
    """JSON array of family names for the plan-schema prompt."""
    return "[" + ",".join(f'"{f}"' for f in CONTRACT_REGISTRY) + "]"
