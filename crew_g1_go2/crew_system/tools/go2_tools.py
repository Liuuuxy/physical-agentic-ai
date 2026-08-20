#!/usr/bin/env python3
"""CrewAI tools that drive the Go2 quadruped robot."""

from typing import Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from ros_bridge.bridge_node import get_bridge
from ros_bridge.go2_controller import NAMED_LOCATIONS
from crew_system.gate import GATE


def _go2():
    _, go2 = get_bridge()
    return go2


# ---------------------------------------------------------------------------

class _LocationInput(BaseModel):
    location: str = Field(
        description=(
            "Named destination for the Go2 robot. "
            "Available locations: " + ", ".join(NAMED_LOCATIONS.keys()) + ". "
            "Use 'list_locations' tool if unsure."
        )
    )


class Go2NavigateToLocationTool(BaseTool):
    name: str = "go2_navigate_to_location"
    description: str = (
        "Send the Go2 quadruped to a named location using its autonomy stack. "
        "The call blocks until Go2 arrives (or times out after 120 s). "
        "Provide a location name such as 'table_a', 'room_b', 'charging', etc."
    )
    args_schema: Type[BaseModel] = _LocationInput

    def _run(self, location: str) -> str:
        ok, why = GATE.authorize("go2", "navigate_to_location", {"location": location})
        if not ok:
            return f"[REFUSED by contract gate] {why}"
        return _go2().navigate_to_location(location)


# ---------------------------------------------------------------------------

class _CoordInput(BaseModel):
    x: float = Field(description="Goal X coordinate in the map frame (metres).")
    y: float = Field(description="Goal Y coordinate in the map frame (metres).")


class Go2NavigateToCoordTool(BaseTool):
    name: str = "go2_navigate_to_coord"
    description: str = (
        "Send the Go2 quadruped to an arbitrary (x, y) coordinate in the map frame. "
        "Blocks until arrival or 120 s timeout."
    )
    args_schema: Type[BaseModel] = _CoordInput

    def _run(self, x: float, y: float) -> str:
        ok, why = GATE.authorize("go2", "navigate_to_coord", {"x": x, "y": y})
        if not ok:
            return f"[REFUSED by contract gate] {why}"
        return _go2().navigate_to(x, y)


# ---------------------------------------------------------------------------

class _EmptyInput(BaseModel):
    pass


class Go2StatusTool(BaseTool):
    name: str = "go2_status"
    description: str = (
        "Return the current navigation status of the Go2 robot: "
        "whether it is navigating, its current position, and distance to goal."
    )
    args_schema: Type[BaseModel] = _EmptyInput

    def _run(self) -> str:
        return _go2().get_status()


class Go2StopTool(BaseTool):
    name: str = "go2_stop"
    description: str = "Immediately cancel any active Go2 navigation goal."
    args_schema: Type[BaseModel] = _EmptyInput

    def _run(self) -> str:
        return _go2().stop()


class Go2ListLocationsTool(BaseTool):
    name: str = "go2_list_locations"
    description: str = "List all named locations the Go2 robot can navigate to."
    args_schema: Type[BaseModel] = _EmptyInput

    def _run(self) -> str:
        locs = _go2().available_locations()
        return "Available Go2 locations: " + ", ".join(locs)
