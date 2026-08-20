#!/usr/bin/env python3
"""Go2 quadruped navigation controller."""

import math
import threading
import time
from typing import Optional


# Named locations in the world frame (x, y) in meters.
# Adjust these to match the actual physical environment.
NAMED_LOCATIONS: dict[str, tuple[float, float]] = {
    "start":     (0.0,  0.0),
    "table_a":   (2.0,  0.0),
    "table_b":   (2.0,  1.0),
    "room_a":    (1.0,  0.0),
    "room_b":    (0.0, -1.0),
    "charging":  (-1.0, 0.0),
    "pickup":    (1.0,  1.0),
    "dropoff":   (0.0,  1.5),
}

ARRIVAL_THRESHOLD = 0.5   # metres – considered arrived within this radius

# Planner-facing skill registry: skill name -> (controller method,
# ((arg name, dispatch default), ...)). Contract grounding checks and the
# orchestrator's dispatch adapter both derive from this single table, so a
# skill added here is automatically known to both.
GO2_SKILL_REGISTRY: dict[str, tuple[str, tuple]] = {
    "navigate_to_location": ("navigate_to_location", (("location", ""),)),
    "navigate_to_coord":    ("navigate_to",          (("x", 0.0), ("y", 0.0))),
    "stop":                 ("stop",                 ()),
    "status":               ("get_status",           ()),
}

# Skills advertised to the LLM planner. The rest stay dispatchable (and
# contract-checkable) but are not suggested, so the planner cannot launder a
# request into unrequested status/stop/coordinate steps.
GO2_PLANNER_SKILLS: tuple[str, ...] = ("navigate_to_location",)


class Go2Controller:
    """
    Tracks Go2 navigation state and exposes a navigate_to() API for
    CrewAI tools.  The ROS bridge publishes the goal and feeds odometry.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._arrived = threading.Event()

        self._current_x: float = 0.0
        self._current_y: float = 0.0
        self._goal_x:    Optional[float] = None
        self._goal_y:    Optional[float] = None
        self._navigating: bool = False
        self._pose_received: bool = False   # guard against false arrival at (0,0)

        # Injected by bridge_node once the publisher is ready
        self._publish_goal_fn = None

    def set_publish_fn(self, fn) -> None:
        self._publish_goal_fn = fn

    # ------------------------------------------------------------------
    # Called by the ROS pose subscriber (background thread)
    # Accepts geometry_msgs/PoseStamped from /utlidar/robot_pose
    # ------------------------------------------------------------------
    def update_pose(self, msg) -> None:
        with self._lock:
            self._current_x = msg.pose.position.x
            self._current_y = msg.pose.position.y
            self._pose_received = True
            if self._navigating and self._goal_x is not None:
                dx = self._current_x - self._goal_x
                dy = self._current_y - self._goal_y
                if math.hypot(dx, dy) <= ARRIVAL_THRESHOLD:
                    self._navigating = False
                    self._arrived.set()

    # ------------------------------------------------------------------
    # Public API for CrewAI tools (caller thread)
    # ------------------------------------------------------------------
    def navigate_to(
        self,
        x: float,
        y: float,
        block: bool = True,
        timeout: float = 120.0,
    ) -> str:
        if self._publish_goal_fn is None:
            return "ROS bridge not ready – cannot publish navigation goal."

        with self._lock:
            if self._navigating:
                return "Go2 is already navigating. Use go2_stop or wait."
            self._goal_x = x
            self._goal_y = y
            self._navigating = True

        self._arrived.clear()
        self._publish_goal_fn(x, y)

        if not block:
            return f"Navigation goal ({x:.2f}, {y:.2f}) sent (non-blocking)."

        # Republish the goal every second so the local planner keeps
        # receiving it (a single message can be dropped during startup).
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            arrived = self._arrived.wait(timeout=min(1.0, remaining))
            if arrived:
                return f"Go2 arrived at ({x:.2f}, {y:.2f})."
            with self._lock:
                still_going = self._navigating
            if not still_going:
                break
            self._publish_goal_fn(x, y)   # heartbeat republish

        with self._lock:
            self._navigating = False
        return f"Navigation to ({x:.2f}, {y:.2f}) timed out after {timeout}s."

    def navigate_to_location(self, location_name: str, **kwargs) -> str:
        name = location_name.lower().strip()
        if name not in NAMED_LOCATIONS:
            return (
                f"Unknown location '{location_name}'. "
                f"Available: {list(NAMED_LOCATIONS)}"
            )
        x, y = NAMED_LOCATIONS[name]
        return self.navigate_to(x, y, **kwargs)

    def stop(self) -> str:
        with self._lock:
            was_navigating = self._navigating
            self._navigating = False
            self._goal_x = None
            self._goal_y = None
        self._arrived.set()
        return "Go2 navigation stopped." if was_navigating else "Go2 was not navigating."

    def get_status(self) -> str:
        with self._lock:
            pos = f"pos=({self._current_x:.2f}, {self._current_y:.2f})"
            if self._navigating and self._goal_x is not None:
                dx = self._current_x - self._goal_x
                dy = self._current_y - self._goal_y
                dist = math.hypot(dx, dy)
                return (
                    f"Go2 navigating to ({self._goal_x:.2f}, {self._goal_y:.2f}), "
                    f"{dist:.2f}m remaining. {pos}"
                )
            return f"Go2 idle. {pos}"

    @staticmethod
    def available_locations() -> list[str]:
        return list(NAMED_LOCATIONS.keys())
