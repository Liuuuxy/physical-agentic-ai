#!/usr/bin/env python3
"""Live Gazebo adapters for the RAO path.

Same interface and state-dict contract as the mock adapters, but each skill is
executed for real inside the sar-sim:humble container (see sar_ws/docker/):
the adapter shells in with docker exec and runs rao_skill_call.py, which calls
the corresponding ROS 2 service and prints one JSON result line. The Iris
adapter publishes the victim fix into the shared state dict exactly like the
mock -- the state interface, orchestrator checks, and gate semantics are
identical across mock and live execution.

Per-scenario perception faults (nan_transmission / missed_detection) are
injected host-side on the structured result, mirroring the mock and the
original sim's fault injector."""
import json
import math
import os
import subprocess

CONTAINER = os.environ.get("SAR_LIVE_CONTAINER", "sar")
_SETUP = ("source /opt/ros/humble/setup.bash && "
          "source /sar_ws/install/setup.bash && ")


def skill_call(skill, args=None, timeout=1900):
    payload = json.dumps(args or {})
    cmd = ["docker", "exec", CONTAINER, "bash", "-lc",
           _SETUP + f"python3 /tmp/rao_skill_call.py {skill} '{payload}'"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    return {"ok": False,
            "error": f"no JSON from skill call (rc={p.returncode}): "
                     f"{p.stderr.strip()[-300:]}"}


class GazeboIrisController:
    def __init__(self, state: dict, fault: str = "none"):
        self.state = state
        self.fault = fault

    def takeoff(self, altitude: float = 5.0) -> str:
        r = skill_call("takeoff", {"altitude": altitude})
        if r.get("success"):
            self.state["iris_airborne"] = True
        return f"[LIVE] takeoff success={r.get('success')}: {r.get('message', r.get('error'))}"

    def search_target(self, x_min: float, x_max: float, y_min: float,
                      y_max: float, altitude: float = 5.0) -> str:
        if self.fault == "missed_detection":
            # fault injected on the structured channel, as in the original sim
            self.state["victim_found"] = False
            return ("[LIVE][FAULT:missed_detection] Search area covered, "
                    "victim not detected.")
        r = skill_call("search_target", {"x_min": x_min, "x_max": x_max,
                                         "y_min": y_min, "y_max": y_max,
                                         "altitude": altitude})
        if not r.get("ok"):
            return f"[LIVE] search failed: {r.get('error')}"
        if not r.get("found"):
            self.state["victim_found"] = False
            return f"[LIVE] {r.get('message', 'victim not detected')}"
        self.state["victim_found"] = True
        if self.fault == "nan_transmission":
            self.state["victim_fix"] = (float("nan"), float("nan"))
            return ("[LIVE][FAULT:nan_transmission] Victim detected but "
                    "coordinates corrupted (NaN transmission).")
        vx, vy = r["victim_x"], r["victim_y"]
        self.state["victim_fix"] = (vx, vy)
        return f"[LIVE] VICTIM_COORDINATES: x={vx:.2f}, y={vy:.2f} (world frame)."

    def get_coordinates(self) -> str:
        fix = self.state.get("victim_fix") or (0.0, 0.0)
        r = skill_call("get_coordinates", {"drone_x": fix[0], "drone_y": fix[1]})
        return f"[LIVE] {r.get('semantic_text', r.get('error'))}"

    def fly_to(self, x: float, y: float, z: float = 5.0) -> str:
        r = skill_call("fly_to", {"x": x, "y": y, "z": z})
        return f"[LIVE] fly_to success={r.get('success')}: {r.get('message', r.get('error'))}"

    def land(self) -> str:
        r = skill_call("land")
        self.state["iris_airborne"] = False
        return f"[LIVE] land success={r.get('success')}: {r.get('message', r.get('error'))}"


class GazeboTb3Controller:
    def __init__(self, state: dict):
        self.state = state

    def navigate_to(self, target=None, x=None, y=None) -> str:
        if target is not None:
            fix = self.state.get("victim_fix")
            if fix is None:
                return ("[LIVE] TB3 navigation FAILED: no victim fix published "
                        "on the state interface.")
            x, y = fix
        try:
            xf, yf = float(x), float(y)
        except (TypeError, ValueError):
            return f"[LIVE] TB3 navigation FAILED: non-numeric goal ({x!r}, {y!r})."
        if not (math.isfinite(xf) and math.isfinite(yf)):
            return f"[LIVE] TB3 navigation FAILED: non-finite goal ({xf}, {yf})."
        r = skill_call("navigate_to", {"x": xf, "y": yf})
        return (f"[LIVE] navigate_to({xf:.2f}, {yf:.2f}) "
                f"success={r.get('success')}: {r.get('message', r.get('error'))}")

    def stop(self) -> str:
        r = skill_call("stop")
        return f"[LIVE] stop success={r.get('success')}: {r.get('message', r.get('error'))}"

    def final_position(self):
        """(x, y) from /odom, for the delivery-error metric; None if absent."""
        r = skill_call("rover_pose")
        if r.get("ok"):
            return (r["x"], r["y"])
        return None
