# Original CrewAI baseline — recorded Gazebo runs

Tier: **`live-gazebo`** for all files below. These are the paper's first
recorded results, produced by the pre-RAO CrewAI-context implementation in
`sar_crew/` driving the Gazebo stack directly. Each row is one real mission,
with wall-clock `search_duration_s` / `navigate_duration_s` and a measured
`delivery_error` in metres.

Config names here predate the 4-condition ladder and are not consistent
across files: `full` and `ours` correspond to `rao`; `no_gate` and
`skill_list` to `skill-list`; `llm_only` to `llm-only`; `text_only` is a
further variant with no counterpart in the ladder. See the `configs` column
below for what each file actually contains. These names are **not**
interchangeable with the `results_mock_4arm_*` condition names.

Regenerate the plots with `python3 plot_results.py` (writes to `./figures/`,
or `$SAR_FIG_OUT`).

The two `table_*.tex` files here are the paper tables generated from these
CSVs (`tab:ablation`, `tab:sim-comparison`). They use the older config names
and N values recorded above, not the 4-condition ladder.

| file | runs | configs | scenarios | faults |
|---|---:|---|---|---|
| `ablation_nominal.csv` | 80 | ours, skill_list | - | none |
| `fault_full_a.csv` | 20 | full | a | blocked_corridor, corrupted_coords, missed_detection, nan_transmission |
| `fault_full_a_cc.csv` | 5 | full | a | corrupted_coords |
| `fault_full_a_md.csv` | 5 | full | a | missed_detection |
| `fault_llm_only_a.csv` | 10 | llm_only | a | blocked_corridor, corrupted_coords, missed_detection, nan_transmission |
| `fault_no_gate_a.csv` | 10 | no_gate | a | blocked_corridor, corrupted_coords, missed_detection, nan_transmission |
| `nominal_full_a.csv` | 10 | full | a | none |
| `nominal_llm_only_a.csv` | 10 | llm_only | a | none |
| `nominal_no_gate_a.csv` | 10 | no_gate | a | none |
| `results_full.csv` | 30 | full | - | none |
| `results_full_a.csv` | 13 | full | a | none |
| `results_full_b.csv` | 20 | full | b | none |
| `results_full_c.csv` | 10 | full | c | none |
| `results_no_gate.csv` | 18 | no_gate | - | none |
| `results_no_gate_a.csv` | 10 | no_gate | a | none |
| `results_no_gate_b.csv` | 10 | no_gate | b | none |
| `results_no_gate_c.csv` | 10 | no_gate | c | none |
| `results_text_only.csv` | 20 | text_only | - | none |
| `results_text_only_a.csv` | 10 | text_only | a | none |
| `results_text_only_b.csv` | 10 | text_only | b | none |
| `results_text_only_c.csv` | 10 | text_only | c | none |
