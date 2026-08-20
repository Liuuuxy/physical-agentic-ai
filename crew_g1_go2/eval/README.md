# Mock-mode baseline evaluation

Runs the four planning conditions on the G1+Go2 pick-and-deliver task in
mock-execution mode (`CREW_SIM=1`, no robot hardware). Execution is mocked, so
the metrics are **planning-layer only** (workflow selection, skill grounding,
contract/safety-gate behavior, latency) — no physical outcomes are reported.

The ablation ladder isolates one ingredient per rung:

| condition    | registry in prompt | contracts in prompt | dispatch gate + replan |
|--------------|:--:|:--:|:--:|
| `llm-only`   | – | – | – |
| `skill-list` | ✓ | – | – |
| `rao-prompt` | ✓ | ✓ | – |
| `rao`        | ✓ | ✓ | ✓ |

`rao-prompt` vs `rao` separates what the *prompted* contracts buy from what
*enforcing* them buys. The contract prose shown to the planner is rendered from
`crew_system/contract_spec.py` — the same specs the gate enforces — so the two
cannot drift.

The CLI drives the live LLM router, so it **requires `OPENAI_API_KEY` and makes
API calls**. Use `--limit` for a small, cheap dry run before the full sweep.

Dry run (first 2 scenarios):

    cd crew_g1_go2
    CREW_SIM=1 OPENAI_API_KEY=sk-... python -m eval.run_eval --limit 2 --latex

Full sweep (all 20 scenarios, all four conditions):

    CREW_SIM=1 OPENAI_API_KEY=sk-... python -m eval.run_eval --latex --out results.csv

Outputs `results.csv` plus paste-ready LaTeX cells for the
`tab:hw-mock-comparison` table in `paper/paper.tex`. Note: the paper table is
currently three method columns; add a fourth (`rao-prompt`, between
`skill-list` and `rao`) before pasting.

The unit tests are hermetic — they inject a fake router and need no API key
(`crewai` is needed only by the tool-gate wiring tests, which skip without it):

    CREW_SIM=1 python -m pytest tests/ -v
