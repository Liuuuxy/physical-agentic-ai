# crew_g1_go2/crew_system/contract_spec.py
"""Declarative workflow-contract template.

A WorkflowContract is the single source of truth for one workflow family.
The generic checker (`violations`) enforces the spec at dispatch time, and
the prompt renderer (`render`) derives the planner-facing prose from the
same spec, so the rules the LLM reads and the rules the gate runs cannot
drift. Adding a workflow family = adding one entry to CONTRACT_REGISTRY.
"""
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
MALFORMED_PLAN = "malformed_plan"  # plan-level: unparseable/incomplete LLM output
OFF_PLAN = "off_plan"              # runtime gate: dispatch not in the approved plan

GROUNDING_CODES = frozenset({UNKNOWN_SKILL, UNKNOWN_LOCATION, UNKNOWN_ROBOT,
                             MISSING_ARG})
CONTRACT_CODES = frozenset({BAD_ASSIGNMENT, ORDER_VIOLATION, SUBSTITUTED_LOCATION})
STATE_CODES = frozenset({ROBOT_BUSY})

ALL_ROBOTS = frozenset({"g1", "go2"})
_DISPLAY = {"g1": "G1", "go2": "Go2"}


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


_LOAD_SKILLS = frozenset({"grab_from_table", "place_on_table"})

# Registry order is canonical: it drives both the prompt prose and the
# JSON-schema family list shown to the planner.
CONTRACT_REGISTRY = {
    "handover": WorkflowContract(
        family="handover",
        allowed_robots=frozenset({"g1"}),
        guidance="a single G1 hand_over step",
        skill_whitelist=frozenset({"hand_over"}),
    ),
    "manipulation_only": WorkflowContract(
        family="manipulation_only",
        allowed_robots=frozenset({"g1"}),
        guidance=("a single G1 skill; for handing an object to a person "
                  "use handover"),
    ),
    "navigation_only": WorkflowContract(
        family="navigation_only",
        allowed_robots=frozenset({"go2"}),
        guidance="a single Go2 navigate_to_location step",
        skill_whitelist=frozenset({"navigate_to_location", "navigate_to_coord"}),
    ),
    "carry": WorkflowContract(
        family="carry",
        allowed_robots=frozenset({"g1", "go2"}),
        guidance=("G1 grab_from_table, then G1 place_on_table (loads onto Go2), "
                  "then Go2 navigate_to_location"),
        ordering=(OrderingRule(
            before=StepPattern("g1", _LOAD_SKILLS),
            after=StepPattern("go2", frozenset({"navigate_to_location"})),
            detail="go2 navigates before g1 loads payload"),),
        skill_whitelist=frozenset({"grab_from_table", "place_on_table",
                                   "navigate_to_location"}),
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
