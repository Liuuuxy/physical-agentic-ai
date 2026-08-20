# crew_sar — RAO orchestration for the air–ground SAR simulation

This package restructures the search-and-dispatch simulation orchestration to
use the **same RAO framework as `crew_g1_go2`**: a non-actuating Mission
Planner that emits a structured JSON plan over typed skill registries,
declarative workflow contracts that render the planner prompt AND drive
enforcement from one spec, and a procedural orchestrator / dispatch gate with
sole actuation authority (plus one feedback-driven replan).

Layout mirrors `crew_g1_go2` file-for-file:

```
crew_system/   contract_spec, contracts, plan_parser, retrieval, routers,
               agents, tasks, orchestrator, gate, eval_mission, trace
ros_bridge/    skill_registry (Iris/TB3 skills, operational bounds),
               mock_bridge (SAR_SIM=1 adapters; no ROS or Gazebo needed)
eval/          scenarios.yaml (20 = 12 nominal + 8 fault), run_eval,
               analyze, metrics, stats
tests/         hermetic suite (fake routers; no crewai, no network)
```

The SAR-specific mechanism: the rover goal does not exist at planning time.
The plan binds it symbolically (`{"target": "victim"}`); the drone's
`search_target` publishes the fix through the state interface, and the
orchestrator re-checks the binding at dispatch time (`no_target_fix` when the
fix is absent or NaN). Non-enforcing arms dispatch anyway — a false dispatch;
`rao` refuses at the gate.

Run (mirrors the crew_g1_go2 commands):

```bash
cd sar_ws/crew_sar
SAR_SIM=1 python -m pytest tests/ -v                 # hermetic, no API key
SAR_SIM=1 OPENAI_API_KEY=... python -m eval.run_eval --limit 2 --latex   # dry run
SAR_SIM=1 OPENAI_API_KEY=... python -m eval.run_eval --latex --out results.csv
SAR_SIM=1 OPENAI_API_KEY=... python -m eval.analyze  # Wilson CIs + Fisher tests
```

The original CrewAI-context implementation (and the Gazebo stack it drives)
remains untouched under `sar_ws/src/`; this package evaluates the
planning/dispatch layer without Gazebo, the same way `CREW_SIM=1` does for the
G1+Go2 system.
