#!/usr/bin/env python3
"""
Simulation-mode drop-in replacements for G1Controller and Go2Controller.
No rclpy, no robot hardware needed.  Set CREW_SIM=1 to activate.
"""

from g1_tasks.sequences import TASK_REGISTRY
from ros_bridge.go2_controller import NAMED_LOCATIONS


class MockG1Controller:
    def execute_task(self, task_name: str, timeout: float = 60.0) -> str:
        if task_name not in TASK_REGISTRY:
            return (
                f"[SIM] Unknown G1 task '{task_name}'. "
                f"Available: {list(TASK_REGISTRY)}"
            )
        seq = TASK_REGISTRY[task_name]
        total = sum(f["duration"] for f in seq)
        frames = " → ".join(f["label"] for f in seq)
        return (
            f"[SIM] G1 executed '{task_name}' successfully.\n"
            f"      Frames: {frames}\n"
            f"      Total duration: {total:.1f} s"
        )

    def get_status(self) -> str:
        return "[SIM] G1 is idle (simulation mode — no hardware)."

    def available_tasks(self) -> list[str]:
        return list(TASK_REGISTRY.keys())


class MockGo2Controller:
    def navigate_to_location(self, location_name: str, **kwargs) -> str:
        name = location_name.lower().strip()
        if name not in NAMED_LOCATIONS:
            return (
                f"[SIM] Unknown location '{location_name}'. "
                f"Available: {list(NAMED_LOCATIONS)}"
            )
        x, y = NAMED_LOCATIONS[name]
        return f"[SIM] Go2 arrived at '{name}' (x={x:.1f}, y={y:.1f})."

    def navigate_to(self, x: float, y: float, **kwargs) -> str:
        return f"[SIM] Go2 arrived at ({x:.2f}, {y:.2f})."

    def stop(self) -> str:
        return "[SIM] Go2 navigation stopped."

    def get_status(self) -> str:
        return "[SIM] Go2 idle at (0.00, 0.00) (simulation mode — no hardware)."

    def set_publish_fn(self, fn) -> None:
        pass  # no-op

    @staticmethod
    def available_locations() -> list[str]:
        return list(NAMED_LOCATIONS.keys())
