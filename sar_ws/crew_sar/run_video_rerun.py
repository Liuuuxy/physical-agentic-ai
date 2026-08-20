#!/usr/bin/env python3
"""Re-run selected fault missions under Contract-prompt (rao-prompt) with
video capture (Xvfb + gzclient + ffmpeg inside the sar-sim:video container)
and ground-truth trajectory logging (/model_states -> CSV).

Usage:
  cd sar_ws/crew_sar
  OPENAI_API_KEY=... python3 run_video_rerun.py [scenario_id ...]
"""
import json
import subprocess
import sys
import time

from run_live_suite import run_one, _PROBE
from eval.scenarios import load_scenarios

IMAGE = "sar-sim:video"
LAUNCH = ("source /opt/ros/humble/setup.bash && "
          "source /sar_ws/install/setup.bash && "
          "ros2 launch sar_gazebo sar_simulation.launch.py headless:=1 "
          "px4_autopilot_dir:=/px4/PX4-Autopilot")
SRC = ("source /opt/ros/humble/setup.bash && "
       "source /sar_ws/install/setup.bash && ")


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True)


def exd(cmd):
    return sh("docker", "exec", "-d", "sar", "bash", "-lc", cmd)


def boot():
    sh("docker", "rm", "-f", "sar")
    subprocess.run(["docker", "run", "-d", "--name", "sar", "--shm-size=1g",
                    IMAGE, "bash", "-c", LAUNCH],
                   check=True, capture_output=True)
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(5)
        out = sh("docker", "exec", "sar", "bash", "-lc", _PROBE).stdout
        if "/rover/navigate_to" in out and "/drone/takeoff" in out:
            time.sleep(10)
            sh("docker", "cp", "../docker/rao_skill_call.py",
               "sar:/tmp/rao_skill_call.py")
            sh("docker", "cp", "traj_logger.py", "sar:/tmp/traj_logger.py")
            return
    raise RuntimeError("sar container not ready within 180 s")


def start_capture(tag):
    exd("Xvfb :1 -screen 0 1280x720x24 &> /tmp/xvfb.log")
    time.sleep(3)
    exd("DISPLAY=:1 gzclient &> /tmp/gzclient.log")
    time.sleep(12)
    # follow the rover; try both classic user-camera names
    sh("docker", "exec", "sar", "bash", "-lc",
       SRC + "gz camera -c user_camera -f waffle || "
             "gz camera -c gzclient_camera -f waffle")
    exd(SRC + f"python3 /tmp/traj_logger.py /tmp/traj_{tag}.csv")
    exd(f"ffmpeg -y -f x11grab -r 10 -s 1280x720 -i :1 -c:v libx264 "
        f"-preset veryfast -pix_fmt yuv420p /tmp/clip_{tag}.mp4 "
        f"&> /tmp/ffmpeg.log")
    time.sleep(2)


def stop_capture(tag):
    sh("docker", "exec", "sar", "bash", "-lc",
       "pkill -INT -f x11grab || true")
    time.sleep(4)
    sh("docker", "exec", "sar", "bash", "-lc",
       "pkill -f traj_logger || true; pkill -f gzclient || true")
    sh("docker", "cp", f"sar:/tmp/clip_{tag}.mp4", f"clip_{tag}.mp4")
    sh("docker", "cp", f"sar:/tmp/traj_{tag}.csv", f"traj_{tag}.csv")


def main():
    ids = sys.argv[1:] or ["fault_out_of_bounds_1", "fault_tb3_unavailable_1"]
    by_id = {sc.id: sc for sc in load_scenarios()}
    records = []
    for sid in ids:
        sc = by_id[sid]
        print(f"=== {sid}: booting fresh sim...", flush=True)
        boot()
        start_capture(sid)
        rec = run_one(sc, baseline="rao-prompt")
        stop_capture(sid)
        records.append(rec)
        print(f"    refused={rec['trace']['refused']} "
              f"rover_final={rec['outcome']['rover_final_pose']} "
              f"t={rec['outcome']['mission_wall_time_s']}s", flush=True)
        with open("results_video_rerun_20260815.json", "w") as f:
            json.dump(records, f, indent=1)
    print("done")


if __name__ == "__main__":
    main()
