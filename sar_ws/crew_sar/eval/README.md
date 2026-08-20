# Mock-mode baseline evaluation (SAR simulation)

Runs the four planning conditions on the air–ground Search-and-Dispatch task
in mock-execution mode (`SAR_SIM=1`, no Gazebo). Execution is mocked, so the
metrics are **planning-layer only** (workflow selection, skill grounding,
contract/safety-gate behavior, latency) — no physical outcomes are reported.

The ablation ladder isolates one ingredient per rung (identical to
`crew_g1_go2/eval`):

| condition    | registry in prompt | contracts in prompt | dispatch gate + replan |
|--------------|:--:|:--:|:--:|
| `llm-only`   | – | – | – |
| `skill-list` | ✓ | – | – |
| `rao-prompt` | ✓ | ✓ | – |
| `rao`        | ✓ | ✓ | ✓ |

Faults (8 of 20 scenarios): robot-unavailable state faults the planner cannot
see (`iris_unavailable`, `tb3_unavailable`), out-of-bounds destinations a
retrieval-equipped planner might silently substitute (`out_of_bounds`), and
perception faults injected in the mock Iris adapter (`nan_transmission`,
`missed_detection`) that surface only at the rover's dispatch through the
state interface — the SAR analogue of the structured-channel bypass measured
on the old implementation.

The CLI drives the live LLM router (model `gpt-5.4-mini`, temperature 0.1 —
same as the G1+Go2 eval), so it **requires `OPENAI_API_KEY` and makes API
calls**. Use `--limit` for a small, cheap dry run before the full sweep.

    cd sar_ws/crew_sar
    SAR_SIM=1 OPENAI_API_KEY=sk-... python -m eval.run_eval --limit 2 --latex
    SAR_SIM=1 OPENAI_API_KEY=sk-... python -m eval.run_eval --latex --out results.csv
    SAR_SIM=1 OPENAI_API_KEY=sk-... python -m eval.analyze

`--latex` emits paste-ready rows for the planning-layer block of
`tab:sim-comparison` in the paper (add a `rao-prompt` column to match the
four-arm ladder). The unit tests are hermetic — they inject a fake router and
need no API key:

    SAR_SIM=1 python -m pytest tests/ -v
