#!/usr/bin/env python3
"""Recompute the mock-vs-live-Gazebo consistency table from shipped artifacts.

Applies the SAME eval/metrics.py functions to (a) the mock 4-arm traces and
(b) the live Gazebo suite, then diffs them per scenario. This is the evidence
that the mock harness is a faithful proxy for the live dispatch layer.

Usage:
    cd sar_ws/crew_sar && SAR_SIM=1 python3 ../../tools/compare_mock_vs_live.py
"""
import csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CREW_SAR = os.path.join(HERE, os.pardir, 'sar_ws', 'crew_sar')
sys.path.insert(0, os.path.abspath(CREW_SAR))
os.environ.setdefault('SAR_SIM', '1')
RES = os.path.join(os.path.abspath(CREW_SAR), 'results')

from eval.metrics import compute_metrics  # noqa: E402


class Step:
    def __init__(self, d):
        self.grounded = d.get('grounded', False)
        self.dispatched = d.get('dispatched', False)
        self.violations = d.get('violations') or []


class MT:
    def __init__(self, t):
        self.declared_family = t.get('declared_family')
        self.plan = t.get('plan') or []
        self.steps = [Step(x) for x in t.get('steps', [])]
        self.refused = t.get('refused')
        self.replanned = t.get('replanned')
        self.replan_attempted = t.get('replan_attempted', False)
        self.latency_s = t.get('latency_s', 0.0)
        self.llm_calls = t.get('llm_calls', 0)


class SC:
    def __init__(self, r):
        self.expected_family = r['expected_family']
        self.should_block = r['should_block']


live = json.load(open(os.path.join(RES, 'results_live_suite_20260810.json')))
mock_tr = json.load(open(os.path.join(RES, 'results_mock_4arm_20260807_traces.json')))['rao']
mock_row = {r['baseline']: r for r in csv.DictReader(
    open(os.path.join(RES, 'results_mock_4arm_20260807.csv')))}['rao']

live_m = compute_metrics([(SC(r), MT(r['trace'])) for r in live])

KEYS = ['workflow_accuracy', 'skill_grounding', 'tool_hallucination',
        'plan_executability', 'contract_violation', 'false_dispatch',
        'safety_recall', 'safety_precision', 'planning_latency_mean']
print(f"{'metric':26}{'MOCK(rao)':>11}{'LIVE(rao)':>11}   note")
print('-' * 66)
for k in KEYS:
    a, b = float(mock_row[k]), float(live_m[k])
    note = ''
    if k == 'planning_latency_mean':
        note = 'NOT COMPARABLE - see results/README.md'
    elif round(a, 2) != round(b, 2):
        note = 'DIFFERS'
    print(f'{k:26}{a:11.2f}{b:11.2f}   {note}')

mi = {r['scenario']: r['trace'] for r in mock_tr}
li = {r['id']: r['trace'] for r in live}


def profile(t):
    steps = t.get('steps', [])
    return (t.get('declared_family'), len(steps),
            sum(1 for s in steps if s.get('grounded')), bool(t.get('refused')),
            tuple(tuple(sorted(s.get('violations') or [])) for s in steps))


assert set(mi) == set(li), 'scenario sets differ'
diff = [k for k in sorted(mi) if profile(mi[k]) != profile(li[k])]
print(f'\nper-scenario trace profiles differing: {len(diff)}/{len(mi)}'
      + (f' -> {diff}' if diff else ''))
