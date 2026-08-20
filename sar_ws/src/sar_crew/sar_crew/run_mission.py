#!/usr/bin/env python3
"""Entry point: run the search-and-rescue CrewAI mission against the
running Gazebo simulation.

Usage:
    source /opt/ros/humble/setup.bash
    source ~/sar_ws/install/setup.bash
    source ~/sar_ws/.venv/bin/activate
    export OPENROUTER_API_KEY=sk-...
    python3 -m sar_crew.run_mission [--runs N] [--csv FILE]
                                    [--config full|no_gate|llm_only]
                                    [--scenario a|b|c]
                                    [--fault none|corrupted_coords|nan_transmission|
                                             missed_detection|blocked_corridor|mixed]

Flags:
    --runs N      repeat the mission N times (default 1)
    --csv FILE    append one row per run to FILE (CSV)
    --config C    planner configuration: full | no_gate | llm_only  (default: full)
    --scenario S  victim/obstacle layout: a | b | c (default: a) — see scenarios.py.
                  Must match the `scenario` arg passed to run_mission.sh / ros2 launch
                  so the Gazebo world and the rover's A* obstacle map agree.
    --fault F     fault injection mode (default: none).
                  Use `mixed` to cycle randomly through all 4 non-none fault modes
                  across runs — produces the full fault-injection run set in one command.

Ablation logic
--------------
  full      Full system: tools + workflow contract (context= dependency).
  no_gate   Skill list present but NO workflow contract. The rover agent may
            dispatch before the drone confirms victim coordinates.
  llm_only  No tools executed. Crew outputs natural language. This script
            parses victim coordinates from the output and dispatches rover
            manually. Post-run tool-reference scan measures hallucination rate
            (tool names the LLM mentions that do not exist in the real registry).

Fault-injection run set
-----------------------
  mixed     Randomly selects one of {corrupted_coords, nan_transmission,
            missed_detection, blocked_corridor} per run.  Run with --runs 40
            to get ~10 samples per fault mode.  The `fault` CSV column records
            which mode was active for each run.
"""
import argparse
import csv
import math
import os
import sys
import time

from dotenv import load_dotenv

from sar_crew.crew import build_crew
from sar_crew.agents import CONFIG_LABELS
from sar_crew.fault_injection import FaultInjector, set_active_injector, FAULT_MODES
import random as _random
import sar_crew.fault_injection as _fault_module
from sar_crew.metrics import MetricsCollector
import sar_crew.metrics as _metrics_module
from sar_crew.scenarios import SCENARIOS, ROVER_SPAWN_X, ROVER_SPAWN_Y, get_scenario
import sar_crew.ros_bridge as _bridge_module


# ---------------------------------------------------------------------------
# Timing instrumentation
# ---------------------------------------------------------------------------
class _MissionTimer:
    def __init__(self):
        self.reset()

    def reset(self):
        self.t_kickoff          = None
        self.t_first_tool       = None
        self.t_takeoff_start    = None
        self.t_takeoff_end      = None
        self.t_search_start     = None
        self.t_search_end       = None
        self.t_perception_start = None
        self.t_perception_end   = None
        self.t_flyto_start      = None
        self.t_flyto_end        = None
        self.t_navigate_start   = None
        self.t_navigate_end     = None
        self.mission_success    = False
        self.victim_found       = False

    def _mark_first(self):
        if self.t_first_tool is None:
            self.t_first_tool = time.time()

    def summary(self):
        def d(a, b):
            return round(b - a, 2) if a and b else None

        return {
            'planning_latency_s':  d(self.t_kickoff, self.t_first_tool),
            'search_duration_s':   d(self.t_search_start, self.t_search_end),
            'navigate_duration_s': d(self.t_navigate_start, self.t_navigate_end),
            'total_duration_s':    d(self.t_kickoff,
                                     self.t_navigate_end or self.t_flyto_end),
            'victim_found':        self.victim_found,
            'mission_success':     self.mission_success,
        }


_timer = _MissionTimer()


def _patch_bridge(timer: _MissionTimer):
    from sar_crew.ros_bridge import RosBridge

    _orig_takeoff    = RosBridge.drone_takeoff
    _orig_search     = RosBridge.drone_search_area
    _orig_perception = RosBridge.drone_perception_query
    _orig_flyto      = RosBridge.drone_fly_to
    _orig_navigate   = RosBridge.rover_navigate_to

    def _timed_takeoff(self, *a, **kw):
        timer._mark_first()
        timer.t_takeoff_start = time.time()
        r = _orig_takeoff(self, *a, **kw)
        timer.t_takeoff_end = time.time()
        return r

    def _timed_search(self, *a, **kw):
        timer._mark_first()
        timer.t_search_start = time.time()
        r = _orig_search(self, *a, **kw)
        timer.t_search_end = time.time()
        timer.victim_found = r[0]
        return r

    def _timed_perception(self, *a, **kw):
        timer._mark_first()
        timer.t_perception_start = time.time()
        r = _orig_perception(self, *a, **kw)
        timer.t_perception_end = time.time()
        return r

    def _timed_flyto(self, *a, **kw):
        timer._mark_first()
        timer.t_flyto_start = time.time()
        r = _orig_flyto(self, *a, **kw)
        timer.t_flyto_end = time.time()
        return r

    def _timed_navigate(self, *a, **kw):
        timer._mark_first()
        timer.t_navigate_start = time.time()
        r = _orig_navigate(self, *a, **kw)
        timer.t_navigate_end = time.time()
        timer.mission_success = r[0]
        return r

    RosBridge.drone_takeoff          = _timed_takeoff
    RosBridge.drone_search_area      = _timed_search
    RosBridge.drone_perception_query = _timed_perception
    RosBridge.drone_fly_to           = _timed_flyto
    RosBridge.rover_navigate_to      = _timed_navigate


# ---------------------------------------------------------------------------
# LLM call counter via CrewAI step callback
# ---------------------------------------------------------------------------
def _make_step_callback():
    def _cb(step_output):
        MetricsCollector.instance().increment_llm_calls()
    return _cb


# ---------------------------------------------------------------------------
# llm_only post-processing: hallucination detection + coord parse + dispatch
# ---------------------------------------------------------------------------
_NON_NONE_FAULTS = [f for f in FAULT_MODES if f != 'none']


def _llm_only_dispatch(crew_result_text: str, timer: _MissionTimer,
                       true_vx: float, true_vy: float) -> bool:
    """Parse victim coordinates from LLM crew output and manually dispatch rover.

    Also scans the output for tool-call references and records how many are
    hallucinated (not in REAL_TOOL_NAMES) vs real.
    Returns True if rover was successfully dispatched and arrived.
    """
    from sar_crew.ros_bridge import RosBridge
    from sar_crew.fault_injection import get_active_injector
    from sar_crew.metrics import REAL_TOOL_NAMES

    mc = MetricsCollector.instance()

    # --- Tool hallucination detection ---
    total_refs, hallu_count, hallu_names = MetricsCollector.detect_tool_refs(crew_result_text)
    mc.tool_ref_count = total_refs
    mc.tool_hallucination_count = hallu_count
    if total_refs > 0:
        hallu_rate = 100.0 * hallu_count / total_refs
        print(f'  [llm_only] Tool refs: {total_refs} total, '
              f'{hallu_count} hallucinated ({hallu_rate:.0f}%)')
        if hallu_names:
            print(f'  [llm_only] Hallucinated names: {hallu_names}')
    else:
        print('  [llm_only] No tool-call references detected in output')

    # --- Coordinate grounding ---
    vx, vy = MetricsCollector.parse_coords_from_text(crew_result_text)

    if math.isnan(vx) or math.isnan(vy):
        print('  [llm_only] Grounding FAILED — no coordinates found in crew output')
        mc.grounding_ok = False
        mc.assignment_ok = False
        return False

    print(f'  [llm_only] Grounding OK — parsed victim coords: x={vx:.2f}, y={vy:.2f}')
    # Use record_localization so _victim_confirmed=True is set before record_navigate,
    # preventing a spurious false_dispatch flag in the llm_only path.
    mc.record_localization(vx, vy, detected=True)

    # Apply fault injection to the parsed coords
    fi = get_active_injector()
    if fi.fault == 'corrupted_coords':
        if fi.bounds:
            x_min, x_max, y_min, y_max = fi.bounds
        else:
            x_min, x_max, y_min, y_max = -50.0, 50.0, -50.0, 50.0
        vx = max(x_min, min(x_max, vx + _random.gauss(0, 5.0)))
        vy = max(y_min, min(y_max, vy + _random.gauss(0, 5.0)))
        print(f'  [llm_only][FAULT:corrupted_coords] coords perturbed to x={vx:.2f}, y={vy:.2f}')
    elif fi.fault in ('nan_transmission', 'missed_detection'):
        print(f'  [llm_only][FAULT:{fi.fault}] navigation suppressed')
        return False
    elif fi.fault == 'blocked_corridor':
        print(f'  [llm_only][FAULT:blocked_corridor] navigation blocked')
        mc.record_navigate(vx, vy)
        return False

    # Dispatch rover manually
    mc.record_navigate(vx, vy)
    timer.t_navigate_start = time.time()
    bridge = RosBridge.instance()
    try:
        success, message = bridge.rover_navigate_to(vx, vy)
    except RuntimeError as e:
        success, message = False, str(e)
    timer.t_navigate_end = time.time()
    timer.mission_success = success

    print(f'  [llm_only] rover_navigate_to({vx:.2f},{vy:.2f}) → success={success}: {message}')
    return success


# ---------------------------------------------------------------------------
# Per-run printing
# ---------------------------------------------------------------------------
def _print_summary(run_idx: int, config: str, fault: str, s: dict, ms: dict):
    label = CONFIG_LABELS.get(config, config)
    print(f'\n{"="*58}')
    print(f'  Run {run_idx} | {label} | fault={fault}')
    print(f'{"="*58}')
    print(f'  Mission success      : {s["mission_success"]}')
    print(f'  Victim found         : {s["victim_found"]}')
    print(f'  LLM planning latency : {s["planning_latency_s"]} s')
    print(f'  Drone search time    : {s["search_duration_s"]} s')
    print(f'  Rover navigate time  : {s["navigate_duration_s"]} s')
    print(f'  Total mission time   : {s["total_duration_s"]} s')
    print(f'  --- Ablation metrics ---')
    print(f'  Grounding OK         : {bool(ms["grounding_ok"])}')
    print(f'  Assignment OK        : {bool(ms["assignment_ok"])}')
    print(f'  Plan executability   : {bool(ms["plan_executability"])}')
    print(f'  False dispatch       : {bool(ms["false_dispatch"])}')
    print(f'  Localisation error   : {ms["localization_error"]:.2f} m'
          if not math.isnan(ms["localization_error"]) else
          '  Localisation error   : N/A')
    print(f'  Delivery error       : {ms["delivery_error"]:.2f} m'
          if not math.isnan(ms["delivery_error"]) else
          '  Delivery error       : N/A')
    print(f'  LLM call count       : {ms["llm_call_count"]}')
    if ms['tool_ref_count'] > 0:
        print(f'  Tool refs            : {ms["tool_ref_count"]} '
              f'({ms["tool_hallucination_count"]} hallucinated, '
              f'{ms["tool_hallucination_rate"]*100:.0f}%)')
    print(f'{"="*58}\n')


def _print_aggregate(summaries: list, config: str, fault: str):
    import statistics
    label = CONFIG_LABELS.get(config, config)
    n = len(summaries)
    timing_keys  = ['planning_latency_s', 'search_duration_s',
                    'navigate_duration_s', 'total_duration_s']
    timing_labels = ['LLM planning latency',
                     'Drone search time   ',
                     'Rover navigate time ',
                     'Total mission time  ']
    metric_keys  = ['grounding_ok', 'assignment_ok', 'plan_executability',
                    'false_dispatch', 'localization_error', 'delivery_error',
                    'llm_call_count', 'tool_ref_count',
                    'tool_hallucination_count', 'tool_hallucination_rate']

    successes = sum(1 for s in summaries if s['mission_success'])

    print(f'\n{"="*68}')
    print(f'  Aggregate | {label} | fault={fault} | n={n}')
    print(f'{"="*68}')
    print(f'  Mission success rate : {successes}/{n} = {100*successes/n:.0f}%')

    for key, label in zip(timing_keys, timing_labels):
        vals = [s[key] for s in summaries if s[key] is not None]
        if not vals:
            print(f'  {label}: N/A')
        elif len(vals) == 1:
            print(f'  {label}: {vals[0]:.1f} s')
        else:
            print(f'  {label}: {statistics.mean(vals):.1f} ± '
                  f'{statistics.stdev(vals):.1f} s')

    print(f'  --- Ablation metrics ---')
    for key in metric_keys:
        raw_vals = [s.get(key) for s in summaries]
        if key in ('grounding_ok', 'assignment_ok', 'false_dispatch'):
            rate = 100.0 * sum(1 for v in raw_vals if v) / n
            print(f'  {key:25s}: {rate:.0f}%')
        else:
            vals = [v for v in raw_vals
                    if v is not None and not (isinstance(v, float) and math.isnan(v))]
            if not vals:
                print(f'  {key:25s}: N/A')
            elif len(vals) == 1:
                print(f'  {key:25s}: {vals[0]:.2f}')
            else:
                print(f'  {key:25s}: {statistics.mean(vals):.2f} ± '
                      f'{statistics.stdev(vals):.2f}')
    print(f'{"="*68}')

    # LaTeX paste block
    print(f'\n  === LaTeX rows ({label}, fault={fault}) ===')
    print(f'  Mission success rate        & {100*successes/n:.0f}\\% \\\\')
    for key, label in zip(timing_keys, timing_labels):
        vals = [s[key] for s in summaries if s[key] is not None]
        if vals and len(vals) > 1:
            print(f'  {label.strip():35s} & '
                  f'${statistics.mean(vals):.1f} \\pm {statistics.stdev(vals):.1f}$\\,s \\\\')
        elif vals:
            print(f'  {label.strip():35s} & ${vals[0]:.1f}$\\,s \\\\')
    for key in ('grounding_ok', 'assignment_ok', 'plan_executability', 'false_dispatch'):
        raw_vals = [s.get(key) for s in summaries]
        rate = 100.0 * sum(1 for v in raw_vals if v) / n
        print(f'  {key:35s} & {rate:.0f}\\% \\\\')
    for key in ('localization_error', 'delivery_error', 'llm_call_count',
                'tool_hallucination_rate'):
        vals = [s.get(key) for s in summaries
                if s.get(key) is not None and not (
                    isinstance(s.get(key), float) and math.isnan(s.get(key)))]
        if vals and len(vals) > 1:
            print(f'  {key:35s} & '
                  f'${statistics.mean(vals):.2f} \\pm {statistics.stdev(vals):.2f}$ \\\\')
        elif vals:
            print(f'  {key:35s} & ${vals[0]:.2f}$ \\\\')


def _append_csv(path: str, run_idx: int, config: str, fault: str,
                s: dict, ms: dict, scenario: str):
    combined = {'run': run_idx, 'config': config, 'scenario': scenario,
               'fault': fault, **s, **ms}
    write_header = not os.path.exists(path)
    with open(path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(combined.keys()))
        if write_header:
            w.writeheader()
        w.writerow(combined)


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=1,
                        help='Number of mission runs (default: 1)')
    parser.add_argument('--csv', type=str, default=None,
                        help='Append per-run metrics to this CSV file')
    parser.add_argument('--config', type=str, default='full',
                        choices=('full', 'no_gate', 'llm_only'),
                        help='Planner configuration: full | no_gate | llm_only  (default: full)')
    parser.add_argument('--fault', type=str, default='none',
                        choices=list(FAULT_MODES) + ['mixed'],
                        help='Fault injection mode (default: none). '
                             'Use "mixed" to randomly cycle through all 4 '
                             'non-none fault modes across runs.')
    parser.add_argument('--scenario', type=str, default='a',
                        choices=tuple(SCENARIOS.keys()),
                        help='Victim/obstacle scenario: a | b | c (default: a). '
                            'Must match the scenario the simulation was launched '
                            'with (run_mission.sh --scenario X).')
    args = parser.parse_args()

    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    load_dotenv(os.path.abspath(env_path))

    if not os.environ.get('OPENROUTER_API_KEY') or \
            os.environ['OPENROUTER_API_KEY'] == 'sk-your-key-here':
        print('ERROR: OPENROUTER_API_KEY is not set.', file=sys.stderr)
        sys.exit(1)

    _patch_bridge(_timer)

    scenario = get_scenario(args.scenario)
    search_bounds = scenario['search_bounds']
    true_vx, true_vy = scenario['victim_x'], scenario['victim_y']
    _metrics_module.set_true_victim(true_vx, true_vy)
    _fault_module.set_true_victim(true_vx, true_vy)
    summaries = []

    label = CONFIG_LABELS.get(args.config, args.config)
    print(f'\n>>> Setup: {label}  |  {scenario["label"]}  |  '
          f'Fault: {args.fault}  |  Runs: {args.runs}')

    for run in range(1, args.runs + 1):
        print(f'\n>>> Starting run {run}/{args.runs}')

        # Reset per-run state
        _timer.reset()
        mc = MetricsCollector.reset_instance()
        # resolve 'mixed' → random non-none fault mode each run
        effective_fault = (
            _random.choice(_NON_NONE_FAULTS)
            if args.fault == 'mixed' else args.fault
        )
        sb = search_bounds
        fi = FaultInjector(effective_fault,
                           bounds=(sb['x_min'], sb['x_max'], sb['y_min'], sb['y_max']))
        set_active_injector(fi)

        crew, inputs = build_crew(search_bounds, search_altitude=5.0,
                                  config=args.config, scenario=args.scenario,
                                  step_callback=_make_step_callback())

        _timer.t_kickoff = time.time()
        result = crew.kickoff(inputs=inputs)
        # Concatenate ALL task outputs so llm_only coordinate parsing can find
        # the drone agent's output (result.raw is only the last task's output).
        if hasattr(result, 'tasks_output') and result.tasks_output:
            raw_text = '\n'.join(t.raw for t in result.tasks_output if t.raw)
        else:
            raw_text = result.raw if hasattr(result, 'raw') else str(result)

        # llm_only: scan for hallucinations, parse coords, dispatch rover manually
        if args.config == 'llm_only':
            _llm_only_dispatch(raw_text, _timer, true_vx, true_vy)
        else:
            # Update timer.mission_success from mc if needed
            if not _timer.mission_success:
                _timer.mission_success = mc.assignment_ok

        # Collect delivery error from /odom
        from sar_crew.ros_bridge import RosBridge
        bridge = RosBridge.instance()
        rx, ry = bridge.rover_final_position()
        mc.record_delivery(rx, ry)

        # Also propagate false_dispatch count from FaultInjector
        if fi.false_dispatches > 0:
            mc.false_dispatch = True

        s  = _timer.summary()
        ms = mc.summary()
        summaries.append({**s, **ms, '_effective_fault': effective_fault})

        print('\n=== Mission result ===')
        print(raw_text)
        _print_summary(run, args.config, effective_fault, s, ms)

        if args.csv:
            # record the actually-applied fault mode (not 'mixed') in the CSV
            _append_csv(args.csv, run, args.config, effective_fault, s, ms, args.scenario)
            print(f'  → metrics appended to {args.csv}')

        if run < args.runs:
            print(f'\nResetting simulation for run {run+1}...')
            bridge.reset_for_next_run(rover_spawn_x=ROVER_SPAWN_X,
                                      rover_spawn_y=ROVER_SPAWN_Y,
                                      drone_spawn_x=1.01, drone_spawn_y=0.98,
                                      drone_spawn_z=5.0, settle_secs=8.0)

    if args.runs > 1:
        _print_aggregate(summaries, args.config,
                         args.fault if args.fault != 'mixed' else 'mixed')


if __name__ == '__main__':
    main()
