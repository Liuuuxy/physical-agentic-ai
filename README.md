# Retrieval-Augmented Orchestration for Multi-Robot Task Execution

Code and recorded results for two robot systems that share one orchestration
framework: a non-actuating LLM **Mission Planner** emits a structured JSON plan
over typed skill registries; declarative **workflow contracts** render the
planner prompt *and* drive enforcement from a single spec; a procedural
**orchestrator / dispatch gate** holds sole actuation authority and may trigger
one feedback-driven replan.

| | `crew_g1_go2/` | `sar_ws/` |
|---|---|---|
| Robots | Unitree G1 humanoid + Go2 quadruped | PX4/Iris quadrotor + TurtleBot3 rover |
| Task | pick-and-deliver | air-ground search and rescue |
| Physical layer | **real hardware**, ROS 2 Humble | **Gazebo Classic 11 + PX4 SITL** |
| Evaluation | mock execution (`CREW_SIM=1`) | mock (`SAR_SIM=1`) **and** live Gazebo |

## Three execution tiers

Keeping these apart matters when reading any result in this repository.

| tier | what runs | where |
|---|---|---|
| `hardware` | real G1/Go2 over ROS 2 | `crew_g1_go2/` with `run.sh` / `go2_only.sh` |
| `live-gazebo` | real physics, PX4 SITL, real ROS 2 services | `sar_ws/crew_sar/run_live_suite.py` |
| `mock` | stub adapters, **no physics, no hardware** | `CREW_SIM=1` / `SAR_SIM=1` |

`CREW_SIM=1` is **not a simulator**. It is a stub that lets the planning and
dispatch layers be evaluated without actuating anything. The only physics
simulation in this repository is the SAR Gazebo stack. The G1+Go2 system has no
simulator, and this release contains **no recorded real-hardware runs** — every
`crew_g1_go2/results/*` artifact is mock tier.

## Quickstart

Hermetic tests — no API key, no ROS, no Gazebo:

```bash
python3 -m pip install -r requirements.txt
cd crew_g1_go2      && CREW_SIM=1 python3 -m pytest tests/ -q
cd ../sar_ws/crew_sar && SAR_SIM=1 python3 -m pytest tests/ -q
```

Mock evaluation (calls the LLM, needs `OPENAI_API_KEY`; use `--limit` first):

```bash
cd crew_g1_go2      && CREW_SIM=1 OPENAI_API_KEY=sk-... python3 -m eval.run_eval --limit 2 --latex
cd ../sar_ws/crew_sar && SAR_SIM=1 OPENAI_API_KEY=sk-... python3 -m eval.analyze
```

Live Gazebo (Docker; see `sar_ws/docker/README.md`):

```bash
cd sar_ws/docker && docker build -t sar-sim:humble .
cd ../crew_sar   && OPENAI_API_KEY=sk-... python3 run_live_suite.py --limit 1
```

Real hardware — read `crew_g1_go2/README.md` first; it moves a physical robot.
Set `ROS_WS_ROOT` if the Unitree workspaces are not directly under `$HOME`.

## How consistent are the two systems?

**Shared, byte-identical.** `crew_system/plan_parser.py`, `crew_system/trace.py`,
`eval/metrics.py`, `eval/scenarios.py`, `eval/stats.py` are the same file in both
trees (0 diff lines). Metric definitions, plan parsing, the trace schema, and the
Wilson/Fisher statistics are therefore literally shared code, which is what makes
numbers comparable across the two systems.

**Domain substitution only.** `routers.py` (6 lines), `gate.py` (26),
`orchestrator.py` (62), `eval/run_eval.py` (17), `eval/analyze.py` (12) differ by
robot names, skill names, and SAR-specific faults. Violation vocabularies match
except that SAR adds one state code, `NO_TARGET_FIX`, for the victim-fix binding
that does not exist at planning time.

**One asymmetry, stated plainly.** Enforcement is wired differently:

* `crew_g1_go2` has **two** layers — the procedural orchestrator (eval path),
  plus `ContractGate` armed in `crew_system/crew.py` and consulted by every
  dispatching tool before it touches a controller. That second layer exists
  because the hardware path runs CrewAI *execution agents* that could drift off
  the approved plan.
* `sar_ws/crew_sar` has **one** — the orchestrator. Its `crew_system/gate.py` is
  ported and fully unit-tested, but has **no production callers**: the sim
  defines only `make_task_router` (no execution agents), so plans go
  planner → orchestrator → adapters procedurally and there is no tool boundary
  for a gate to defend. `gate.py` is effectively dead code in that tree.

This is a design consequence of the sim having no execution agents, not an
unreported ablation — but it does mean the two trees mirror each other
file-for-file without mirroring each other wiring-for-wiring.

## Does mock execution predict live execution?

Yes, on the evidence here. Running the identical `eval/metrics.py` over the mock
4-arm traces and the live Gazebo suite (same 20 scenarios, `rao`):

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

Per-scenario, **0 of 20** differ on declared family, step count, grounded count,
refusal decision, or per-step violation codes. Reproduce with
`tools/compare_mock_vs_live.py`.

Two caveats, both load-bearing:

1. **`planning_latency_mean` is not comparable across tiers.** Both paths record
   `latency_s = time.time() - t0` with `t0` at *mission* start. Under mock,
   execution is a stub, so that span is effectively planning time (~1.4 s). Under
   live Gazebo it includes the drone flying and the rover driving, so it reports
   ~40 s — tracking mission wall time, not planning. Only compare latency within
   the `mock` tier.
2. **n = 1 per scenario on each side.** The exact agreement is one draw matching
   one draw, not two distributions matching. Multi-seed evidence exists only for
   the mock tier (`crew_g1_go2/results/`, four seeds).
3. **One shipped artifact carries a wrong label.**
   `results_live_ctxprompt_faults_20260815.json` records `"baseline": "rao"` in
   every trace, but it is a **`rao-prompt`** run — `run_live_suite.py` hardcoded
   the recorded label regardless of `--baseline`. Its 8 traces have plans
   identical to the `rao` suite but `refused: false`, which is the non-enforcing
   signature. The hardcode is fixed in the shipped runner; the recorded file is
   left exactly as produced and flagged here and in
   `sar_ws/crew_sar/results/README.md`.

## Layout

```
crew_g1_go2/          real G1 + Go2
  crew_system/        contract_spec, contracts, plan_parser, retrieval, routers,
                      agents, tasks, crew, orchestrator, gate, eval_mission, trace
  ros_bridge/         g1_controller, go2_controller, bridge_node (rclpy), mock_bridge
  g1_tasks/           joint configs + task sequences
  eval/  tests/  scripts/  results/
sar_ws/               air-ground SAR simulation
  crew_sar/           the same orchestration layer, SAR domain
    ros_bridge/       skill_registry, mock_bridge, gazebo_bridge (live, via docker)
    eval/  tests/  results/
  src/                ROS 2 packages: sar_gazebo, sar_msgs, sar_robot_control,
                      sar_crew (original CrewAI baseline + its Gazebo results)
  docker/             sar-sim:humble image for the full simulation
tools/                compare_mock_vs_live.py
```

Each `results/` directory has its own README labelling every artifact with the
execution tier that produced it.
