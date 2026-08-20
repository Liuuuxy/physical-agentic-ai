import argparse
import csv
import json

from eval.scenarios import load_scenarios
from eval.metrics import compute_metrics
from crew_system.eval_mission import run_eval_mission

_ROWS = [
    ("Workflow-selection accuracy (\\%)", "workflow_accuracy"),
    ("Skill-grounding rate (\\%)", "skill_grounding"),
    ("Tool-hallucination rate (\\%)", "tool_hallucination"),
    ("Plan executability (\\%)", "plan_executability"),
    ("Contract-violation rate (\\%)", "contract_violation"),
    ("False-dispatch rate (\\%)", "false_dispatch"),
    ("Safety-gate recall (\\%)", "safety_recall"),
    ("Safety-gate precision (\\%)", "safety_precision"),
    ("Replan success rate (\\%)", "replan_success"),
    ("Planning latency (s, mock)", "planning_latency_mean"),
    # NOTE: llm_calls_mean is intentionally NOT reported -- it counts router
    # invocations (1, or 2 when RAO replans), not true LLM calls.
    # compute_metrics still returns it; see eval/EVAL_REPORT.md.
]


# State faults the planner cannot see or launder: the required robot is down.
_FAULT_STATE = {
    "go2_unavailable": {"g1_busy": False, "go2_busy": True},
    "g1_unavailable": {"g1_busy": True, "go2_busy": False},
}

# Ablation ladder. rao-prompt separates prompt knowledge from enforcement:
# it sees the same contracts as rao but nothing gates its dispatches.
_LADDER = ("llm-only", "skill-list", "rao-prompt", "rao")


def run(baselines, router=None, limit=None):
    unknown = [b for b in baselines if b not in _LADDER]
    if unknown:
        raise ValueError(f"unknown baseline(s) {unknown}; valid: {list(_LADDER)}")
    scenarios = load_scenarios()
    if limit is not None:
        scenarios = scenarios[:limit]
    results = {}
    for b in baselines:
        records = [
            (sc, run_eval_mission(sc.request, baseline=b, router=router,
                                  initial_state=_FAULT_STATE.get(sc.fault)))
            for sc in scenarios
        ]
        results[b] = compute_metrics(records)
    return results


def to_latex(results):
    order = [b for b in _LADDER if b in results]
    lines = []
    for label, key in _ROWS:
        cells = " & ".join(f"{results[b][key]:.1f}" for b in order)
        lines.append(f"\\quad {label} & {cells} \\\\")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baselines", nargs="+", default=list(_LADDER))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--latex", action="store_true")
    ap.add_argument("--out", default="results.csv")
    args = ap.parse_args()

    results = run(args.baselines, router=None, limit=args.limit)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["baseline"] + [k for _, k in _ROWS])
        for b, m in results.items():
            w.writerow([b] + [f"{m[k]:.2f}" for _, k in _ROWS])
    print(json.dumps(results, indent=2))
    if args.latex:
        print("\n% --- paste into tab:hw-mock-comparison ---")
        print(to_latex(results))


if __name__ == "__main__":
    main()
