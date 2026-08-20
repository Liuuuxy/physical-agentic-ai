#!/usr/bin/env python3
"""
Simulation-mode drop-in replacements for the Iris and TB3 adapters.
No rclpy, no Gazebo needed.  Set SAR_SIM=1 to activate.

Both controllers share one mutable `state` dict -- the RO state interface.
The Iris search publishes the victim fix into it exactly like the Gazebo
oracle publishes coordinates, and the TB3 resolves its "victim" binding from
it at dispatch time. The Iris mock also carries the per-scenario perception
fault (nan_transmission / missed_detection), so the fault surfaces through
the same structured channel the gate checks.
"""
import math

from ros_bridge.skill_registry import TRUE_VICTIM


class MockIrisController:
    def __init__(self, state: dict, fault: str = "none",
                 true_victim: tuple = TRUE_VICTIM):
        self.state = state
        self.fault = fault
        self.true_victim = true_victim

    def takeoff(self, altitude: float = 5.0) -> str:
        self.state["iris_airborne"] = True
        return f"[SIM] Iris airborne at {altitude:.1f} m."

    def search_target(self, x_min: float, x_max: float, y_min: float,
                      y_max: float, altitude: float = 5.0) -> str:
        if self.fault == "missed_detection":
            self.state["victim_found"] = False
            return ("[SIM][FAULT:missed_detection] Search area covered, "
                    "victim not detected.")
        vx, vy = self.true_victim
        if not (x_min <= vx <= x_max and y_min <= vy <= y_max):
            self.state["victim_found"] = False
            return "[SIM] Search area covered, victim not detected."
        self.state["victim_found"] = True
        if self.fault == "nan_transmission":
            self.state["victim_fix"] = (float("nan"), float("nan"))
            return ("[SIM][FAULT:nan_transmission] Victim detected but "
                    "coordinates corrupted (NaN transmission).")
        self.state["victim_fix"] = (vx, vy)
        return f"[SIM] VICTIM_COORDINATES: x={vx:.2f}, y={vy:.2f} (world frame)."

    def get_coordinates(self) -> str:
        fix = self.state.get("victim_fix")
        if fix is None:
            return ("[SIM perception] No human visible in current frame. "
                    "Area clear.")
        return ("[SIM perception] Target human detected, occlusion low. "
                f"Estimated world position: x={fix[0]:.2f}, y={fix[1]:.2f}.")

    def fly_to(self, x: float, y: float, z: float = 5.0) -> str:
        return f"[SIM] Iris holding at ({x:.2f}, {y:.2f}, {z:.2f})."

    def land(self) -> str:
        self.state["iris_airborne"] = False
        return "[SIM] Iris landed."


class MockTb3Controller:
    def __init__(self, state: dict):
        self.state = state

    def navigate_to(self, target=None, x=None, y=None) -> str:
        if target is not None:
            fix = self.state.get("victim_fix")
            if fix is None:
                return ("[SIM] TB3 navigation FAILED: no victim fix published "
                        "on the state interface.")
            x, y = fix
        try:
            xf, yf = float(x), float(y)
        except (TypeError, ValueError):
            return f"[SIM] TB3 navigation FAILED: non-numeric goal ({x!r}, {y!r})."
        if not (math.isfinite(xf) and math.isfinite(yf)):
            return f"[SIM] TB3 navigation FAILED: non-finite goal ({xf}, {yf})."
        return f"[SIM] TB3 arrived at ({xf:.2f}, {yf:.2f})."

    def stop(self) -> str:
        return "[SIM] TB3 stopped."
