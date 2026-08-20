import json
import re

from crew_system.trace import PlanStep

_BRACE = re.compile(r"\{")
_DECODER = json.JSONDecoder()


def _extract_object(raw):
    """First JSON object decodable from any '{' in the text; tolerates
    fenced blocks and trailing prose (even prose containing braces)."""
    s = raw or ""
    err = None
    for m in _BRACE.finditer(s):
        try:
            obj, _ = _DECODER.raw_decode(s, m.start())
        except json.JSONDecodeError as e:
            err = err or e
            continue
        if isinstance(obj, dict):
            return obj, None
    return None, err


def parse_plan(raw):
    """Extract (workflow_family, steps, problems) from raw planner output.

    `problems` is non-empty when the output is malformed (no/invalid JSON,
    empty plan, wrong-typed family/robot/skill/args). Wrong-typed values are
    coerced to safe defaults so every downstream checker sees only strings
    and dicts -- the gate treats a malformed plan as a refusable violation,
    never as a crash and never as a clean empty plan."""
    data, err = _extract_object(raw)
    if data is None:
        msg = ("no JSON object in planner output" if err is None
               else f"invalid JSON in planner output: {err.msg}")
        return None, [], [msg]

    problems = []
    family = data.get("workflow_family")
    if family is not None and not isinstance(family, str):
        problems.append("workflow_family is not a string")
        family = None
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        return family, [], problems + ["'steps' missing or not a list"]

    plan = []
    for i, s in enumerate(raw_steps):
        if not isinstance(s, dict):
            problems.append(f"step {i} is not an object")
            continue
        fields = {}
        for key in ("robot", "skill"):
            v = s.get(key)
            if not isinstance(v, str) or not v:
                problems.append(f"step {i} missing '{key}'" if not v
                                else f"step {i} '{key}' is not a string")
                v = ""
            fields[key] = v
        args = s.get("args")
        if args is None:
            args = {}
        elif not isinstance(args, dict):
            problems.append(f"step {i} 'args' is not an object")
            args = {}
        plan.append(PlanStep(robot=fields["robot"], skill=fields["skill"], args=args))
    if not plan:
        problems.append("empty plan")
    return family, plan, problems
