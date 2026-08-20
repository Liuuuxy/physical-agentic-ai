#!/usr/bin/env python3
"""Entry point: run the dual-capable platform-selection demo.

Both the IRIS drone and the TurtleBot3 rover can physically reach every
target in this experiment. Unlike the main search-and-dispatch mission
(sar_crew.run_mission), there is no fixed drone-then-rover pipeline here —
a single Mission Commander agent must call assess_reachability and then
choose which ONE platform to dispatch. This script records which platform
was actually dispatched per run and compares it against the
efficiency-optimal expectation defined in targets.py.

Usage:
    source /opt/ros/humble/setup.bash
    source ~/sar_ws/install/setup.bash
    source ~/sar_ws/.venv/bin/activate
    export OPENROUTER_API_KEY=sk-...
    cd ~/sar_ws/src/sar_crew
    python3 -m sar_crew.experiments.dual_capable.run_mission \\
        --target rover_easy|drone_easy|ambiguous [--runs N] [--csv FILE]

Launch the simulation first with the matching world/obstacle:
    ./src/sar_crew/sar_crew/experiments/dual_capable/run_dual_mission.sh \\
        --target rover_easy --runs 5 --csv dual_rover_easy.csv
"""
import argparse
import csv
import os
import sys
import time

from dotenv import load_dotenv

from sar_crew.experiments.dual_capable.crew import build_crew
from sar_crew.experiments.dual_capable.targets import get_target, TARGETS


class _Timer:
    def __init__(self):
        self.reset()

    def reset(self):
        self.t_kickoff = None
        self.t_dispatch_start = None
        self.t_dispatch_end = None
        self.platform_dispatched = None   # 'drone' | 'rover' | None
        self.dispatch_success = False

    def summary(self):
        d = (round(self.t_dispatch_end - self.t_kickoff, 2)
             if self.t_kickoff and self.t_dispatch_end else None)
        return {
            'platform_dispatched': self.platform_dispatched,
            'dispatch_success':    self.dispatch_success,
            'total_duration_s':    d,
        }


_timer = _Timer()


def _patch_bridge(timer: _Timer):
    from sar_crew.ros_bridge import RosBridge

    _orig_flyto    = RosBridge.drone_fly_to
    _orig_navigate = RosBridge.rover_navigate_to

    def _timed_flyto(self, *a, **kw):
        timer.platform_dispatched = 'drone'
        timer.t_dispatch_start = timer.t_dispatch_start or time.time()
        r = _orig_flyto(self, *a, **kw)
        timer.t_dispatch_end = time.time()
        timer.dispatch_success = r[0]
        return r

    def _timed_navigate(self, *a, **kw):
        timer.platform_dispatched = 'rover'
        timer.t_dispatch_start = timer.t_dispatch_start or time.time()
        r = _orig_navigate(self, *a, **kw)
        timer.t_dispatch_end = time.time()
        timer.dispatch_success = r[0]
        return r

    RosBridge.drone_fly_to      = _timed_flyto
    RosBridge.rover_navigate_to = _timed_navigate


def _make_step_callback(counter: dict):
    def _cb(step_output):
        counter['llm_calls'] = counter.get('llm_calls', 0) + 1
    return _cb


def _append_csv(path: str, run_idx: int, target_name: str, expected: str, s: dict):
    match = (expected is None) or (s['platform_dispatched'] == expected)
    combined = {'run': run_idx, 'target': target_name, 'expected_platform': expected,
               'matches_expected': int(match), **s}
    write_header = not os.path.exists(path)
    with open(path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(combined.keys()))
        if write_header:
            w.writeheader()
        w.writerow(combined)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=str, required=True,
                        choices=tuple(TARGETS.keys()),
                        help='Which test target to dispatch to')
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--csv', type=str, default=None)
    args = parser.parse_args()

    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', '.env')
    load_dotenv(os.path.abspath(env_path))
    if not os.environ.get('OPENROUTER_API_KEY') or \
            os.environ['OPENROUTER_API_KEY'] == 'sk-your-key-here':
        print('ERROR: OPENROUTER_API_KEY is not set.', file=sys.stderr)
        sys.exit(1)

    _patch_bridge(_timer)
    target = get_target(args.target)
    expected = target['expected_platform']

    print(f'\n>>> Dual-capable demo | target={args.target} '
         f'({target["x"]},{target["y"]}) | expected={expected} | runs={args.runs}')

    summaries = []
    for run in range(1, args.runs + 1):
        print(f'\n>>> Run {run}/{args.runs}')
        _timer.reset()
        counter = {}

        crew = build_crew(target['x'], target['y'], target['description'],
                          step_callback=_make_step_callback(counter))
        _timer.t_kickoff = time.time()
        result = crew.kickoff()
        print('\n=== Result ===')
        print(result.raw if hasattr(result, 'raw') else str(result))

        s = _timer.summary()
        s['llm_calls'] = counter.get('llm_calls', 0)
        match = (expected is None) or (s['platform_dispatched'] == expected)
        print(f'  Platform dispatched : {s["platform_dispatched"]}')
        print(f'  Expected platform   : {expected}')
        print(f'  Matches expected    : {match}')
        print(f'  Dispatch success    : {s["dispatch_success"]}')
        print(f'  Total duration      : {s["total_duration_s"]} s')
        summaries.append(s)

        if args.csv:
            _append_csv(args.csv, run, args.target, expected, s)

        if run < args.runs:
            from sar_crew.ros_bridge import RosBridge
            print('Resetting for next run...')
            RosBridge.instance().reset_for_next_run(settle_secs=8.0)

    if args.runs > 1:
        n = len(summaries)
        matches = sum(1 for s in summaries
                     if expected is None or s['platform_dispatched'] == expected)
        drone_count = sum(1 for s in summaries if s['platform_dispatched'] == 'drone')
        rover_count = sum(1 for s in summaries if s['platform_dispatched'] == 'rover')
        print(f'\n=== Aggregate: target={args.target}, n={n} ===')
        print(f'  Drone dispatched : {drone_count}/{n}')
        print(f'  Rover dispatched : {rover_count}/{n}')
        if expected is not None:
            print(f'  Matches expected ({expected}): {matches}/{n} = {100*matches/n:.0f}%')


if __name__ == '__main__':
    main()
