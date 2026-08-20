"""Run the full scenario set once per baseline and report, for the headline
metrics, each method's rate with a 95% Wilson CI plus a two-sided Fisher's exact
test of RAO vs each baseline. Latency is mean +/- std. No scipy required.

Usage:
  cd sar_ws/crew_sar
  export OPENAI_API_KEY=...
  SAR_SIM=1 python -m eval.analyze
"""
import statistics

from eval.scenarios import load_scenarios
from eval.run_eval import _FAULT_STATE, _MOCK_FAULTS
from crew_system.eval_mission import run_eval_mission
from eval.metrics import compute_counts, compute_metrics
from eval.stats import wilson_ci, fisher_exact

BASELINES = ["llm-only", "skill-list", "rao-prompt", "rao"]

# (key, label, arrow) -- the metrics whose contrast is the paper's claim.
HEADLINE = [
    ("workflow_accuracy", "Workflow-selection acc.", "up"),
    ("skill_grounding", "Skill grounding", "up"),
    ("plan_executability", "Plan executability", "up"),
    ("contract_violation", "Contract violation", "down"),
    ("false_dispatch", "False dispatch", "down"),
    ("safety_recall", "Safety-gate recall", "up"),
    ("safety_precision", "Safety-gate precision", "up"),
]


def run_records(baselines, router=None):
    scen = load_scenarios()
    return {
        b: [(sc, run_eval_mission(
                sc.request, baseline=b, router=router,
                initial_state=_FAULT_STATE.get(sc.fault),
                mock_fault=sc.fault if sc.fault in _MOCK_FAULTS else "none"))
            for sc in scen]
        for b in baselines
    }


def _cell(counts, key):
    k, nn = counts[key]
    rate = 100.0 * k / nn if nn else 0.0
    lo, hi = wilson_ci(k, nn)
    return f"{rate:4.0f} [{lo:3.0f},{hi:3.0f}]"


def _fisher(counts_a, counts_b, key):
    a, na = counts_a[key]
    b, nb = counts_b[key]
    return fisher_exact(a, na - a, b, nb - b)


def report(records):
    baselines = [b for b in BASELINES if b in records]
    others = [b for b in baselines if b != "rao"]
    counts = {b: compute_counts(records[b]) for b in baselines}
    n = len(next(iter(records.values())))
    print(f"N = {n} distinct scenarios per method "
          f"({sum(1 for sc, _ in records['rao'] if sc.fault == 'none')} nominal + "
          f"{sum(1 for sc, _ in records['rao'] if sc.fault != 'none')} fault)\n")

    hdr = (f"{'metric':<24}" + "".join(f"{b:>16}" for b in baselines)
           + "".join(f"{'p:' + b[:8]:>11}" for b in others))
    print(hdr)
    print("-" * len(hdr))
    for key, label, _ in HEADLINE:
        cells = "".join(f"{_cell(counts[b], key):>16}" for b in baselines)
        pvals = "".join(f"{_fisher(counts['rao'], counts[b], key):>11.1e}"
                        for b in others)
        print(f"{label:<24}{cells}{pvals}")

    print("\nrate [95% Wilson CI]; p = two-sided Fisher's exact (RAO vs baseline)\n")
    for b in baselines:
        lat = [mt.latency_s for _, mt in records[b]]
        print(f"latency {b:<11}: {statistics.fmean(lat):.2f} +/- {statistics.pstdev(lat):.2f} s")


def main():
    records = run_records(BASELINES)
    report(records)


if __name__ == "__main__":
    main()
