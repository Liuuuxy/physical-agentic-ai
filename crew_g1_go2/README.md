# crew_g1_go2 — Unitree G1 + Go2, real hardware

RAO orchestration for a pick-and-deliver task on a real Unitree G1 humanoid and
Go2 quadruped over ROS 2 Humble.

```
crew_system/   contract_spec, contracts, plan_parser, retrieval, routers,
               agents, tasks, crew, orchestrator, gate, eval_mission, trace
crew_system/tools/  CrewAI tools; every dispatching tool calls GATE.authorize()
ros_bridge/    g1_controller (unitree_hg LowCmd @500 Hz + CRC),
               go2_controller (/way_point goals, /utlidar/robot_pose),
               bridge_node (single rclpy node, background thread),
               mock_bridge (CREW_SIM=1 stubs -- no ROS, no hardware)
g1_tasks/      joint configs and task frame sequences
eval/ tests/ scripts/ results/
```

## Run

Mock tier — no ROS, no robot, no API key for the tests:

```bash
CREW_SIM=1 python3 -m pytest tests/ -q
CREW_SIM=1 OPENAI_API_KEY=sk-... python3 -m eval.run_eval --limit 2 --latex
CREW_SIM=1 ./sim.sh "grab from table_a then go to room_b"
```

Real hardware — **this moves a physical robot.** Prerequisites in separate
terminals: source ROS 2 Humble, the Unitree workspaces, and the Go2 autonomy
stack (`system_real_robot.sh`). Then:

```bash
export ROS_WS_ROOT=$HOME     # if the workspaces are not directly under $HOME
export OPENAI_API_KEY=sk-...
./run.sh                     # G1 + Go2
./go2_only.sh                # Go2 only; G1 publishers fully disabled
```

`GO2_ONLY=1` skips G1 initialisation entirely, so no `/user_lowcmd` publisher is
created — the safe mode when the G1 is absent or powered off.

## Evaluation

Four conditions isolate one ingredient per rung:

| condition | registry in prompt | contracts in prompt | dispatch gate + replan |
|---|:--:|:--:|:--:|
| `llm-only` | – | – | – |
| `skill-list` | ✓ | – | – |
| `rao-prompt` | ✓ | ✓ | – |
| `rao` | ✓ | ✓ | ✓ |

`rao-prompt` vs `rao` separates what *prompted* contracts buy from what
*enforcing* them buys. The contract prose shown to the planner is rendered from
`crew_system/contract_spec.py` — the same specs the gate enforces — so the two
cannot drift.

Execution is mocked, so these metrics are **planning-layer only** (workflow
selection, skill grounding, contract/gate behaviour, latency). No physical
outcome is measured, and this release contains no recorded hardware runs.
