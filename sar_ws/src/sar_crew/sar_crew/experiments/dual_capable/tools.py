"""
Tools for the dual-capable platform-selection demo.

assess_reachability gives the Mission Commander agent grounded numbers to
reason over (straight-line drone distance vs. obstacle-aware rover path
distance) instead of having a fixed pipeline pick the platform for it.
dispatch_drone / dispatch_rover are the two mutually-exclusive actions —
the agent should call exactly one per mission.
"""
import math
from typing import Type

from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from sar_crew.ros_bridge import RosBridge
from sar_crew.experiments.dual_capable.targets import (
    DRONE_SPAWN_X, DRONE_SPAWN_Y, DRONE_ALTITUDE, WALL_RUBBLE,
)

# Reuse the rover's own A* planner so the path-cost estimate matches what
# tb3_navigate_to will actually drive.
from sar_robot_control.rover_controller_node import _astar


class AssessReachabilityInput(BaseModel):
    x: float = Field(..., description='Target X (world frame, meters)')
    y: float = Field(..., description='Target Y (world frame, meters)')


class AssessReachabilityTool(BaseTool):
    name: str = 'assess_reachability'
    description: str = (
        'Compare how efficiently each platform can reach a target (x, y). '
        'Returns the drone\'s direct flight distance (always unobstructed) '
        'and the rover\'s obstacle-aware ground path distance/time (via A*). '
        'Call this BEFORE dispatching either platform.'
    )
    args_schema: Type[BaseModel] = AssessReachabilityInput

    def _run(self, x: float, y: float) -> str:
        drone_dist = math.sqrt(
            (x - DRONE_SPAWN_X) ** 2 + (y - DRONE_SPAWN_Y) ** 2 + DRONE_ALTITUDE ** 2)
        drone_eta = drone_dist / 3.0   # rough cruise speed estimate, m/s

        rx, ry = RosBridge.instance().rover_final_position()
        if math.isnan(rx) or math.isnan(ry):
            rx, ry = -2.0, -2.0   # fall back to nominal spawn if /odom not yet seen

        path = _astar(rx, ry, x, y, WALL_RUBBLE)
        pts = [(rx, ry)] + list(path)
        rover_dist = sum(
            math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            for i in range(len(pts) - 1))
        rover_eta = rover_dist / 0.15   # rover linear_speed, m/s

        return (
            f'assess_reachability(x={x:.1f}, y={y:.1f}): '
            f'DRONE direct distance={drone_dist:.2f}m, ETA~{drone_eta:.0f}s, no obstacles. '
            f'ROVER ground path distance={rover_dist:.2f}m '
            f'({len(path)} waypoints, detour ratio={rover_dist / max(0.01, math.hypot(x-rx, y-ry)):.2f}), '
            f'ETA~{rover_eta:.0f}s.'
        )


class DispatchInput(BaseModel):
    x: float = Field(..., description='Target X (world frame, meters)')
    y: float = Field(..., description='Target Y (world frame, meters)')


class DispatchDroneTool(BaseTool):
    name: str = 'dispatch_drone'
    description: str = (
        'Send the IRIS drone to directly reach the target (x, y): arms, climbs '
        'to cruise altitude, and flies straight to the target. Use this only '
        'after assess_reachability shows the drone is the more efficient choice.'
    )
    args_schema: Type[BaseModel] = DispatchInput

    def _run(self, x: float, y: float) -> str:
        bridge = RosBridge.instance()
        ok1, msg1 = bridge.drone_takeoff(DRONE_ALTITUDE)
        if not ok1:
            return f'dispatch_drone FAILED at takeoff: {msg1}'
        ok2, msg2 = bridge.drone_fly_to(x, y, DRONE_ALTITUDE)
        return f'dispatch_drone success={ok2}: {msg2}'


class DispatchRoverTool(BaseTool):
    name: str = 'dispatch_rover'
    description: str = (
        'Send the TurtleBot3 rover to directly reach the target (x, y), using '
        'A* path planning around known obstacles. Use this only after '
        'assess_reachability shows the rover is the more efficient choice.'
    )
    args_schema: Type[BaseModel] = DispatchInput

    def _run(self, x: float, y: float) -> str:
        success, message = RosBridge.instance().rover_navigate_to(x, y)
        return f'dispatch_rover success={success}: {message}'
