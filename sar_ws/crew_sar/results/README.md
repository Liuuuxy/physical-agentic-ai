# Recorded results — crew_sar (air-ground SAR)

Every artifact is labelled with the **execution tier** that produced it:

* `mock` — stub adapters, no physics, no hardware. Planning-layer metrics only.
* `live-gazebo` — real Gazebo Classic 11 physics, PX4 SITL, real ROS 2 services.
* `hardware` — a real robot moved.

Mock and live-Gazebo results for the **same 20 scenarios** sit side by side here. `tools/compare_mock_vs_live.py` recomputes the agreement between them (8/8 planning metrics equal; 0/20 per-scenario trace profiles differ).

> **`planning_latency_mean` is not comparable across tiers.** Both paths record `latency_s = time.time() - t0` from *mission* start. Under mock, execution is a stub, so it reads as planning time (~1.4 s). Under live Gazebo it includes the drone flying and rover driving (~40 s) and tracks mission wall time. Compare latency only within the `mock` tier.


| file | tier | what it is |
|---|---|---|
| `live_ctxprompt_progress.log` | `live-gazebo` | Progress log for the live fault re-run. |
| `live_suite_progress.log` | `live-gazebo` | Progress log streamed during the live suite. |
| `results_live_ctxprompt_faults_20260815.json` | `live-gazebo` | 8 fault scenarios re-run live under the **`rao-prompt`** condition (contracts in the prompt, no dispatch gate). **The `baseline` field inside every trace in this file reads `"rao"` and is wrong** -- `run_live_suite.py` hardcoded the recorded label regardless of `--baseline`. The data is genuine rao-prompt data: the plans are identical to `results_live_suite_20260810.json` but `refused` is `false` for all 8 (no enforcement), where enforcing `rao` refused all 8. Read the file as `rao-prompt`; do not read it as `rao` failing to refuse. The hardcode is fixed in the shipped `run_live_suite.py`, but the recorded artifact is left byte-for-byte as produced. |
| `results_live_missions_20260807.json` | `live-gazebo` | Two individual live missions (`nominal_rao`, `nan_transmission_rao`). |
| `results_live_suite_20260810.json` | `live-gazebo` | **Primary live evidence.** All 20 scenarios, `rao`, against the Dockerized Gazebo sim; the container is restarted before each mission. Carries physical outcomes: `victim_fix`, `rover_final_pose`, `delivery_error_m`, `mission_wall_time_s`. |
| `results_mock_4arm_20260807.csv` | `mock` | 4-condition comparison table. **Renamed** from `results_sim_4arm_*`: the original name said "sim" but this is mock output (`SAR_SIM=1`), not Gazebo. |
| `results_mock_4arm_20260807.txt` | `mock` | Summary table with Wilson CIs and Fisher p-values for the above. |
| `results_mock_4arm_20260807_full.log` | `mock` | Full console log behind the mock 4-condition sweep. |
| `results_mock_4arm_20260807_full.summary.txt` | `mock` | Metrics table extracted from `results_mock_4arm_20260807_full.log`. |
| `results_mock_4arm_20260807_traces.json` | `mock` | Per-scenario traces for all four conditions. Input to `tools/compare_mock_vs_live.py`. |
| `video_rerun_progress.log` | `live-gazebo` | Progress log for the video re-run. |
