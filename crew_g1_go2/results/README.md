# Recorded results — crew_g1_go2 (G1 + Go2)

Every artifact is labelled with the **execution tier** that produced it:

* `mock` — stub adapters, no physics, no hardware. Planning-layer metrics only.
* `live-gazebo` — real Gazebo Classic 11 physics, PX4 SITL, real ROS 2 services.
* `hardware` — a real robot moved.

**Every artifact here is `mock` tier.** The G1+Go2 system has no simulator, and no real-hardware runs are recorded in this release. `planning_latency_mean` is meaningful here precisely because execution is stubbed.

Files ending `.summary.txt` were extracted by the build from the tail of the corresponding console log; the full log is kept beside them as the raw record.


| file | tier | what it is |
|---|---|---|
| `raoprompt_run.log` | `mock` | Console log of the `rao-prompt` run. |
| `results.csv` | `mock` | Earliest 3-condition sweep (llm-only / skill-list / rao). Superseded; kept for provenance. |
| `results_4arm_20260806.summary.txt` | `mock` | Metrics table extracted from `results_4arm_20260806.txt`. |
| `results_4arm_20260806.txt` | `mock` | **4-condition sweep, seed 1**, N=20. Console log; metrics table at the tail (see `.summary.txt`). |
| `results_4arm_seed2_20260810.summary.txt` | `mock` | Metrics table extracted from `results_4arm_seed2_20260810.txt`. |
| `results_4arm_seed2_20260810.txt` | `mock` | 4-condition sweep, seed 2. |
| `results_4arm_seed3_20260810.summary.txt` | `mock` | Metrics table extracted from `results_4arm_seed3_20260810.txt`. |
| `results_4arm_seed3_20260810.txt` | `mock` | 4-condition sweep, seed 3. |
| `results_4arm_seed4_20260810.summary.txt` | `mock` | Metrics table extracted from `results_4arm_seed4_20260810.txt`. |
| `results_4arm_seed4_20260810.txt` | `mock` | 4-condition sweep, seed 4. |
| `results_heldplan_20260806.summary.txt` | `mock` | Metrics table extracted from `results_heldplan_20260806.txt`. |
| `results_heldplan_20260806.txt` | `mock` | Held-plan ablation: the planner is held fixed and only enforcement varies. |
| `results_n20.txt` | `mock` | 3-condition summary at N=20 (Wilson CIs + Fisher p-values). |
| `results_n20_full.log` | `mock` | Full console log behind `results_n20.txt`. |
| `results_n20_full.summary.txt` | `mock` | Metrics table extracted from `results_n20_full.log`. |
| `results_raoprompt.csv` | `mock` | `rao-prompt` condition alone, added when the 4th rung was introduced. |
| `results_v2.csv` | `mock` | Second 3-condition sweep. Superseded. |
| `results_v3.csv` | `mock` | Third 3-condition sweep. Superseded. |
