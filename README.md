# Retrieval-Augmented Orchestration for Multi-Robot Task Execution

*Anonymous supplementary material. Code and recorded results for the submitted paper.*

An LLM **Mission Planner** emits a structured JSON plan over typed skill
registries but never actuates. Declarative **workflow contracts** render the
planner's prompt *and* drive enforcement from a single spec, so the two cannot
drift. A procedural **orchestrator** holds sole actuation authority, checks every
step against the contract at dispatch time, and may trigger one feedback-driven
replan.

The same framework is instantiated on two systems:

| | `crew_g1_go2/` | `sar_ws/` |
|---|---|---|
| Robots | Unitree G1 humanoid + Go2 quadruped | PX4/Iris quadrotor + TurtleBot3 rover |
| Task | pick-and-deliver | air–ground search and rescue |
| Physical layer | real hardware, ROS 2 Humble | Gazebo Classic 11 + PX4 SITL |
| Recorded evidence | mock execution | mock **and** live Gazebo |

## Start here

Everything below runs offline: no API key, no ROS, no Gazebo, no robot. Takes
about a minute.

```bash
python3 -m pip install -r requirements.txt

# 203 hermetic unit tests across both systems
( cd crew_g1_go2     && CREW_SIM=1 python3 -m pytest tests/ -q )
( cd sar_ws/crew_sar && SAR_SIM=1  python3 -m pytest tests/ -q )

# Re-derive the mock-vs-live agreement from the shipped artifacts
( cd sar_ws/crew_sar && SAR_SIM=1 python3 ../../tools/compare_mock_vs_live.py )
```

The last command reproduces the central methodological claim — that mock
execution is a faithful proxy for the live dispatch layer — from data in this
repository, without re-running anything.

## Execution tiers

Three tiers produce the results here. Telling them apart is necessary to read
any number in this repository correctly.

| tier | what actually runs | entry point |
|---|---|---|
| `mock` | stub adapters. No physics, no hardware. | `CREW_SIM=1` / `SAR_SIM=1` |
| `live-gazebo` | Gazebo Classic 11 physics, PX4 SITL, real ROS 2 services | `sar_ws/crew_sar/run_live_suite.py` |
| `hardware` | a real G1/Go2 over ROS 2 | `crew_g1_go2/run.sh`, `go2_only.sh` |

`CREW_SIM=1` and `SAR_SIM=1` are **not simulators**. They stub out actuation so
the planning and dispatch layers can be measured without moving anything. The
only physics simulation here is the SAR Gazebo stack; the G1+Go2 system has no
simulator.

Every artifact in a `results/` directory is labelled with its tier in that
directory's `README.md`.

## Reproducing the reported results

| claim | artifact | tier |
|---|---|---|
| G1+Go2 four-condition comparison (`tab:hw-mock-comparison`) | `crew_g1_go2/results/results_4arm_*.summary.txt` — 4 seeds | `mock` |
| Enforcement isolated from planning (held-plan ablation) | `crew_g1_go2/results/results_heldplan_20260806.summary.txt` | `mock` |
| SAR four-condition comparison (`tab:sim-comparison`, planning rows) | `sar_ws/crew_sar/results/results_mock_4arm_20260807.{csv,txt}` | `mock` |
| SAR end-to-end missions with physical outcomes | `sar_ws/crew_sar/results/results_live_suite_20260810.json` | `live-gazebo` |
| Non-enforcing arm under injected faults | `sar_ws/crew_sar/results/results_live_ctxprompt_faults_20260815.json` | `live-gazebo` |
| Original CrewAI baseline (`tab:ablation`), repeated runs | `sar_ws/src/sar_crew/*.csv`, `table_*.tex` — see `RESULTS.md` | `live-gazebo` |
| Mock predicts live | `tools/compare_mock_vs_live.py` | both |

All evaluations use 20 scenarios (12 nominal + 8 fault) per condition. The four
conditions isolate one ingredient per rung:

| condition | registry in prompt | contracts in prompt | dispatch gate + replan |
|---|:--:|:--:|:--:|
| `llm-only` | – | – | – |
| `skill-list` | ✓ | – | – |
| `rao-prompt` | ✓ | ✓ | – |
| `rao` | ✓ | ✓ | ✓ |

`rao-prompt` vs `rao` separates what *prompted* contracts buy from what
*enforcing* them buys.

## Re-running from scratch

**Mock evaluation.** Calls a paid LLM API. Use `--limit` for a cheap dry run
before any full sweep.

```bash
( cd crew_g1_go2     && CREW_SIM=1 OPENAI_API_KEY=sk-... python3 -m eval.run_eval --limit 2 --latex )
( cd sar_ws/crew_sar && SAR_SIM=1  OPENAI_API_KEY=sk-... python3 -m eval.analyze )
```

**Live Gazebo.** Docker is the supported path; the image builds PX4 and takes
20–40+ minutes the first time. See `sar_ws/docker/README.md`.

```bash
( cd sar_ws/docker   && docker build -t sar-sim:humble . )
( cd sar_ws/crew_sar && OPENAI_API_KEY=sk-... python3 run_live_suite.py --limit 1 )
```

**Real hardware.** Read `crew_g1_go2/README.md` first — these commands move a
physical robot. Requires ROS 2 Humble, the Unitree workspaces, and the Go2
autonomy stack. Set `ROS_WS_ROOT` if those are not directly under `$HOME`.

Requirements: Python 3.10–3.13 for the planning layer (no ROS needed). The
hardware path additionally needs the system Python 3.10 that provides `rclpy`,
and `numpy<2.0`.

## Shared code across the two systems

Five modules are **byte-identical** in both trees (0 diff lines):
`crew_system/plan_parser.py`, `crew_system/trace.py`, `eval/metrics.py`,
`eval/scenarios.py`, `eval/stats.py`. Metric definitions, plan parsing, the trace
schema, and the Wilson/Fisher statistics are therefore literally the same code,
which is what makes numbers comparable across systems.

The remaining differences are domain substitution — robot names, skill names,
SAR-specific faults:

| module | diff lines | nature of the difference |
|---|---:|---|
| `crew_system/routers.py` | 6 | robot identifiers in the plan schema |
| `crew_system/gate.py` | 26 | robot and skill names |
| `crew_system/orchestrator.py` | 62 | robot names + SAR victim-fix binding check |
| `eval/run_eval.py` | 17 | fault names, perception faults |
| `eval/analyze.py` | 12 | fault names |

Violation vocabularies are identical except that SAR adds one state code,
`NO_TARGET_FIX`, for a goal that does not exist at planning time (the rover's
target is bound symbolically and resolved from the drone's search at dispatch).

**Enforcement is wired differently in the two trees.** `crew_g1_go2` has two
layers: the procedural orchestrator, plus a `ContractGate` armed in
`crew_system/crew.py` and consulted by every dispatching tool before it touches a
controller. That second layer exists because the hardware path runs CrewAI
*execution agents* that could drift from the approved plan. `sar_ws/crew_sar` has
only the orchestrator: it defines no execution agents, so plans flow
planner → orchestrator → adapters procedurally and there is no tool boundary for
a gate to defend. Its `crew_system/gate.py` is ported and unit-tested but has no
production callers.

## Does mock execution predict live execution?

Applying the identical `eval/metrics.py` to the mock traces and the live Gazebo
suite over the same 20 scenarios (`rao`):

| metric | mock | live Gazebo |
|---|---:|---:|
| workflow_accuracy | 100.00 | 100.00 |
| skill_grounding | 95.74 | 95.74 |
| tool_hallucination | 0.00 | 0.00 |
| plan_executability | 90.00 | 90.00 |
| contract_violation | 0.00 | 0.00 |
| false_dispatch | 0.00 | 0.00 |
| safety_recall | 100.00 | 100.00 |
| safety_precision | 100.00 | 100.00 |

Per scenario, **0 of 20** differ on declared family, step count, grounded count,
refusal decision, or per-step violation codes. Reproduce with
`tools/compare_mock_vs_live.py`.

## Scope and limitations

1. **No hardware runs are recorded here.** Every `crew_g1_go2/results/*` artifact
   is `mock` tier. The hardware code path is included and documented, but this
   release reports no measurements from a physical robot.
2. **`planning_latency_mean` is not comparable across tiers.** Both paths record
   `latency_s = time.time() - t0` from *mission* start. Under mock, execution is
   a stub, so the span is effectively planning time (~1.4 s). Under live Gazebo it
   includes the drone flying and the rover driving (~40 s), tracking mission wall
   time rather than planning. Compare latency only within the `mock` tier.
3. **The mock/live agreement is n = 1 per scenario on each side.** Exact agreement
   here is one draw matching one draw, not two distributions matching. Multi-seed
   evidence exists only for the `mock` tier (`crew_g1_go2/results/`, 4 seeds).
4. **One shipped artifact carries a wrong internal label.**
   `results_live_ctxprompt_faults_20260815.json` records `"baseline": "rao"` in
   every trace, but it is a `rao-prompt` run: `run_live_suite.py` hardcoded the
   recorded label regardless of `--baseline`. Its traces have plans identical to
   the `rao` suite but `refused: false`, the non-enforcing signature. The hardcode
   is fixed in the shipped runner; the recorded file is left exactly as produced
   and flagged in `sar_ws/crew_sar/results/README.md`.

## Layout

```
README.md  LICENSE  requirements.txt  .env.example
tools/                compare_mock_vs_live.py

crew_g1_go2/          real G1 + Go2
  crew_system/        contract_spec, contracts, plan_parser, retrieval, routers,
                      agents, tasks, crew, orchestrator, gate, eval_mission, trace
  crew_system/tools/  CrewAI tools; each calls GATE.authorize() before dispatch
  ros_bridge/         g1_controller (unitree_hg LowCmd @500 Hz), go2_controller,
                      bridge_node (rclpy), mock_bridge
  g1_tasks/           joint configs + task frame sequences
  eval/  tests/  scripts/  results/

sar_ws/               air-ground SAR simulation
  crew_sar/           the same orchestration layer, SAR domain
    ros_bridge/       skill_registry, mock_bridge, gazebo_bridge (live, via docker)
    eval/  tests/  results/
  src/                ROS 2 packages: sar_gazebo, sar_msgs, sar_robot_control,
                      and sar_crew (original CrewAI baseline + its Gazebo results)
  docker/             sar-sim:humble image for the full simulation
```

## License

MIT. See `LICENSE`.
