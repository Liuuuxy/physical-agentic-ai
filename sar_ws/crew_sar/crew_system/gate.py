# crew_sar/crew_system/gate.py
"""Runtime contract gate for the live-simulation (Gazebo) path.

The mock-eval path checks plans inside orchestrator.execute_plan; this module
brings the same contract checks to the live pipeline: a runner arms the gate
with the checked routing plan, and every dispatching adapter asks authorize()
before touching a controller -- so no unchecked action reaches a robot even
if an execution agent drifts off the approved plan. (The Gazebo runner that
wires this up is not part of the mock eval; until it lands, the gate's
callers are the tests and the mock path's semantics live in execute_plan.)

The gate is per-mission: armed by run_mission, disarmed when the mission
ends. Disarmed, it passes through so manual REPL commands keep working."""
from dataclasses import dataclass, field

from crew_system.contract_spec import (CONTRACT_REGISTRY, MALFORMED_PLAN,
                                       OFF_PLAN, ORDER_VIOLATION)
from crew_system.contracts import (check, infer_family, substitution_violations,
                                   KNOWN_FAMILIES)
from crew_system.plan_parser import parse_plan

_IDLE = {"iris_busy": False, "tb3_busy": False}


@dataclass
class ArmResult:
    family: str | None
    plan: list
    problems: list = field(default_factory=list)
    violations: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and not self.violations

    def feedback(self) -> str:
        """Replan feedback, same shape the eval path feeds the router."""
        codes = sorted({v.code for v in self.violations})
        if self.problems:
            codes.append(MALFORMED_PLAN + " (" + "; ".join(self.problems) + ")")
        return "violations: " + ", ".join(codes) if codes else "plan was refused"


class ContractGate:
    def __init__(self):
        self._family = None
        self._plan = []
        self._done = []      # indices of consumed plan steps
        self.armed = False

    def disarm(self):
        self._family, self._plan, self._done, self.armed = None, [], [], False

    def arm(self, raw_planner_output, request=None, state=None) -> ArmResult:
        """Parse and contract-check the routing output. Arms the gate only
        when the plan is clean; a refused plan leaves the gate disarmed."""
        self.disarm()
        declared, plan, problems = parse_plan(raw_planner_output)
        family = declared if declared in KNOWN_FAMILIES else infer_family(plan)
        violations = check(plan, family, state or dict(_IDLE))
        if request is not None:
            violations = violations + substitution_violations(plan, request)
        result = ArmResult(family, plan, problems, violations)
        if result.ok:
            self._family, self._plan, self.armed = family, plan, True
        return result

    def authorize(self, robot, skill, args=None):
        """(ok, message) for one dispatch. A dispatch must match the robot's
        NEXT pending step of the approved plan (within-robot plan order is
        enforced), and every ordering rule whose 'after' pattern it matches
        must already have an executed 'before' step. A step is consumed on
        authorization: failed dispatches are not retried -- the mission halts
        and reports, matching the prototype's no-autonomous-recovery policy."""
        if not self.armed:
            return True, "gate disarmed (no mission armed)"
        args = args or {}
        idx = next((i for i, s in enumerate(self._plan)
                    if i not in self._done and s.robot == robot), None)
        if idx is None:
            return False, f"{OFF_PLAN}: no pending {robot} step in the approved plan"
        step = self._plan[idx]
        if step.skill != skill or not self._args_match(step, skill, args):
            return False, (f"{OFF_PLAN}: next approved {robot} step is "
                           f"{step.skill} {step.args}, not {skill} {args}")
        contract = CONTRACT_REGISTRY.get(self._family)
        if contract:
            for rule in contract.ordering:
                if rule.after.matches(step) and not any(
                        rule.before.matches(self._plan[j]) for j in self._done):
                    return False, f"{ORDER_VIOLATION}: {rule.detail}"
        self._done.append(idx)
        return True, "authorized"

    @staticmethod
    def _args_match(step, skill, args):
        if skill == "navigate_to":
            want_t, got_t = step.args.get("target"), args.get("target")
            if want_t is not None or got_t is not None:
                return (isinstance(want_t, str) and isinstance(got_t, str)
                        and want_t.lower().strip() == got_t.lower().strip())
            try:
                return (abs(float(step.args.get("x")) - float(args.get("x"))) < 1e-6
                        and abs(float(step.args.get("y")) - float(args.get("y"))) < 1e-6)
            except (TypeError, ValueError):
                return False
        return True


# Process-wide gate shared by run_mission and the dispatching tools.
GATE = ContractGate()
