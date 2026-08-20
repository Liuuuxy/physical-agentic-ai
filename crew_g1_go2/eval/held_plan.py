# crew_g1_go2/eval/held_plan.py
"""Held-plan ablation: sample the planner ONCE per scenario, then dispatch the
IDENTICAL plan with enforcement off and on. Planner variance is removed
entirely, so any difference between the two arms is attributable to the
dispatch gate alone.

The planner sample uses the rao-prompt context (same knowledge as rao, no
gate in the loop), and neither arm replans -- a held plan has exactly one
planner sample by construction.

Usage:
  CREW_SIM=1 OPENAI_API_KEY=... python -m eval.held_plan [--limit N]
"""
import argparse
import time

from ros_bridge.mock_bridge import MockG1Controller, MockGo2Controller
from crew_system.trace import MissionTrace
from crew_system.plan_parser import parse_plan
from crew_system.contracts import infer_family, KNOWN_FAMILIES
from crew_system.orchestrator import execute_plan
from eval.scenarios import load_scenarios
from eval.run_eval import _FAULT_STATE
from eval.metrics import compute_counts
from eval.stats import wilson_ci, fisher_exact

SAMPLING_BASELINE = "rao-prompt"
SAFETY_KEYS = ("false_dispatch", "safety_recall", "safety_precision")


def _family_of(declared, plan):
    return declared if declared in KNOWN_FAMILIES else infer_family(plan)


def _dispatch(plan, family, enforce, state, request, malformed):
    g1, go2 = MockG1Controller(), MockGo2Controller()
    return execute_plan(plan, family, g1, go2, enforce=enforce, state=state,
                        request=request, refuse_all=malformed)


def run_held(router=None, limit=None):
    """{arm: [(scenario, MissionTrace), ...]} for arms 'no-gate' and 'gate'."""
    if router is None:
        from crew_system.routers import live_router
        router = live_router
    scenarios = load_scenarios()
    if limit is not None:
        scenarios = scenarios[:limit]
    records = {"no-gate": [], "gate": []}
    for sc in scenarios:
        t0 = time.time()
        raw, llm_calls = router(sc.request, SAMPLING_BASELINE)
        latency = time.time() - t0
        declared, plan, problems = parse_plan(raw)
        family = _family_of(declared, plan)
        state = _FAULT_STATE.get(sc.fault)
        for arm, enforce in (("no-gate", False), ("gate", True)):
            steps, refused = _dispatch(plan, family, enforce, state,
                                       sc.request, bool(problems))
            if enforce and problems:  # malformed output fails closed under the gate
                refused = True
            records[arm].append((sc, MissionTrace(
                request=sc.request, baseline=arm,
                declared_family=declared, plan=plan, steps=steps,
                refused=refused, replanned=False, llm_calls=llm_calls,
                latency_s=latency, replan_attempted=False,
                parse_problems=list(problems),
            )))
    return records


def report(records):
    n = len(records["gate"])
    print(f"Held-plan ablation: one {SAMPLING_BASELINE} planner sample per "
          f"scenario, identical plans dispatched both ways (N={n})")
    for key in SAFETY_KEYS:
        cells = []
        for arm in ("no-gate", "gate"):
            k, d = compute_counts(records[arm])[key]
            lo, hi = wilson_ci(k, d)
            pct = 100.0 * k / d if d else 0.0
            cells.append(f"{arm} {pct:5.1f}% ({k}/{d}) [{lo:.0f},{hi:.0f}]")
        k1, d1 = compute_counts(records["no-gate"])[key]
        k2, d2 = compute_counts(records["gate"])[key]
        p = fisher_exact(k1, d1 - k1, k2, d2 - k2)
        print(f"{key:<17} " + "   ".join(cells) + f"   p={p:.2e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    report(run_held(limit=args.limit))


if __name__ == "__main__":
    main()
