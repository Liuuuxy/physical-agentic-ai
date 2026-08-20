"""CrewAI tools wrapping the SAR ROS 2 services.

Skill libraries match the typed action spaces defined in the system architecture:

  Iris Drone Skills  : iris_takeoff, iris_search_target, iris_get_coordinates,
                       iris_fly_to, iris_land
  TurtleBot3 Skills  : tb3_navigate_to, tb3_stop

Each tool is a thin wrapper around ros_bridge.RosBridge that returns a short
structured text description which the CrewAI agents read as observation.

For ablation experiments, IrisSearchTargetTool, IrisGetCoordinatesTool, and
Tb3NavigateToTool check the module-level FaultInjector and MetricsCollector
singletons set by run_mission.py before each run.
"""
import math
from typing import Type

from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from sar_crew.ros_bridge import RosBridge
from sar_crew.fault_injection import get_active_injector
from sar_crew.metrics import MetricsCollector


# ──────────────────────────────────────────────────────────────────────────────
# Iris Drone Skill Library
# ──────────────────────────────────────────────────────────────────────────────

class TakeoffInput(BaseModel):
    altitude: float = Field(..., description='Target altitude in meters above ground')


class IrisTakeoffTool(BaseTool):
    name: str = 'iris_takeoff'
    description: str = (
        'Arm the IRIS drone, switch it to OFFBOARD mode and climb to the '
        'given altitude (meters). Must be called before any search or flight.'
    )
    args_schema: Type[BaseModel] = TakeoffInput

    def _run(self, altitude: float) -> str:
        success, message = RosBridge.instance().drone_takeoff(altitude)
        return f'iris_takeoff success={success}: {message}'


class SearchAreaInput(BaseModel):
    x_min: float = Field(..., description='Minimum X of the search rectangle (world frame, meters)')
    x_max: float = Field(..., description='Maximum X of the search rectangle (world frame, meters)')
    y_min: float = Field(..., description='Minimum Y of the search rectangle (world frame, meters)')
    y_max: float = Field(..., description='Maximum Y of the search rectangle (world frame, meters)')
    altitude: float = Field(..., description='Search altitude in meters above ground')


class IrisSearchTargetTool(BaseTool):
    name: str = 'iris_search_target'
    description: str = (
        'Fly a lawnmower search pattern over the rectangle '
        '[x_min, x_max] × [y_min, y_max] at the given altitude, '
        'continuously querying the onboard perception bridge at each waypoint. '
        'Returns whether the victim was found and their world-frame coordinates. '
        'This is a long-running operation.'
    )
    args_schema: Type[BaseModel] = SearchAreaInput

    def _run(self, x_min: float, x_max: float, y_min: float, y_max: float,
             altitude: float) -> str:
        found, message, vx, vy, vz = RosBridge.instance().drone_search_area(
            x_min, x_max, y_min, y_max, altitude)

        # fault injection
        fi = get_active_injector()
        found, message, vx, vy, vz = fi.inject_search(found, message, vx, vy, vz)

        # metrics — localization quality
        MetricsCollector.instance().record_localization(vx, vy, found)

        if found:
            if math.isnan(vx) or math.isnan(vy):
                return (f'iris_search_target: victim signal detected but coordinates '
                        f'corrupted (NaN transmission error). {message}')
            return (
                f'iris_search_target: victim located. {message}. '
                f'VICTIM_COORDINATES: x={vx:.2f}, y={vy:.2f}, z={vz:.2f} (world frame)'
            )
        return f'iris_search_target: victim not found. {message}'


class PerceptionQueryInput(BaseModel):
    drone_x: float = Field(..., description='Current drone X position in world frame (meters)')
    drone_y: float = Field(..., description='Current drone Y position in world frame (meters)')


class IrisGetCoordinatesTool(BaseTool):
    name: str = 'iris_get_coordinates'
    description: str = (
        'Query the drone\'s onboard perception bridge at the current position. '
        'The bridge evaluates the live camera feed through a Vision-Language Model '
        'and returns a structured semantic description of the scene, including '
        'victim detection status, estimated world-frame coordinates, and '
        'environmental occlusion level. '
        'Use this to verify or refine victim localisation reported by iris_search_target, '
        'or to query perception at a specific hover position.'
    )
    args_schema: Type[BaseModel] = PerceptionQueryInput

    def _run(self, drone_x: float, drone_y: float) -> str:
        detected, text, vx, vy = RosBridge.instance().drone_perception_query(drone_x, drone_y)

        # fault injection
        fi = get_active_injector()
        detected, text, vx, vy = fi.inject_perception(detected, text, vx, vy)

        # metrics
        MetricsCollector.instance().record_localization(vx, vy, detected)

        if detected:
            if math.isnan(vx) or math.isnan(vy):
                return f'iris_get_coordinates: {text} (coordinates unavailable — NaN)'
            return (
                f'iris_get_coordinates: {text} '
                f'VICTIM_COORDINATES: x={vx:.2f}, y={vy:.2f} (world frame)'
            )
        return f'iris_get_coordinates: {text}'


class FlyToInput(BaseModel):
    x: float = Field(..., description='Target X (world frame, meters)')
    y: float = Field(..., description='Target Y (world frame, meters)')
    z: float = Field(..., description='Target altitude above ground (meters)')


class IrisFlyToTool(BaseTool):
    name: str = 'iris_fly_to'
    description: str = (
        'Fly the IRIS drone to a specific (x, y, z) waypoint in world-frame '
        'coordinates — e.g. to hover over the victim for air support or to '
        'reposition for a clearer perception query.'
    )
    args_schema: Type[BaseModel] = FlyToInput

    def _run(self, x: float, y: float, z: float) -> str:
        success, message = RosBridge.instance().drone_fly_to(x, y, z)
        return f'iris_fly_to success={success}: {message}'


class IrisLandTool(BaseTool):
    name: str = 'iris_land'
    description: str = 'Switch the IRIS drone to AUTO.LAND so it descends and lands at its current position.'

    def _run(self) -> str:
        success, message = RosBridge.instance().drone_land()
        return f'iris_land success={success}: {message}'


# ──────────────────────────────────────────────────────────────────────────────
# TurtleBot3 Ground Skill Library
# ──────────────────────────────────────────────────────────────────────────────

class NavigateToInput(BaseModel):
    x: float = Field(..., description='Target X (world frame, meters)')
    y: float = Field(..., description='Target Y (world frame, meters)')


class Tb3NavigateToTool(BaseTool):
    name: str = 'tb3_navigate_to'
    description: str = (
        'Drive the TurtleBot3 rover to the given (x, y) world-frame coordinates '
        '(same frame that iris_search_target and iris_get_coordinates report). '
        'Uses A* path planning to route around known obstacles and reactive '
        'LiDAR avoidance as a safety net. Blocks until arrival or timeout.'
    )
    args_schema: Type[BaseModel] = NavigateToInput

    def _run(self, x: float, y: float) -> str:
        # metrics — before dispatch
        MetricsCollector.instance().record_navigate(x, y)

        # fault injection — false dispatch check
        fi = get_active_injector()
        fi.check_navigate_dispatch(x, y)

        success, message = RosBridge.instance().rover_navigate_to(x, y)

        # fault injection — navigation outcome
        success, message = fi.inject_navigate(success, message)

        return f'tb3_navigate_to success={success}: {message}'


class Tb3StopTool(BaseTool):
    name: str = 'tb3_stop'
    description: str = (
        'Immediately halt the TurtleBot3 rover, cancelling any ongoing navigation. '
        'Use this if a navigation must be aborted — for example, if the victim '
        'coordinates need to be updated before the rover arrives.'
    )

    def _run(self) -> str:
        success, message = RosBridge.instance().rover_stop()
        return f'tb3_stop success={success}: {message}'
