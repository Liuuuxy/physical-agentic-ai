#!/usr/bin/env python3
"""CrewAI tools that drive the G1 humanoid robot."""

from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from ros_bridge.bridge_node import get_bridge
from crew_system.gate import GATE


_G1_DISABLED = "G1 is disabled (running in GO2_ONLY mode)."

def _g1():
    g1, _ = get_bridge()
    return g1


# ---------------------------------------------------------------------------

class _TaskNameInput(BaseModel):
    task_name: str = Field(
        description=(
            "Name of the G1 manipulation task to execute. "
            "Available: grab_from_table, place_on_table, wave, hand_over."
        )
    )


class G1ExecuteTaskTool(BaseTool):
    name: str = "g1_execute_task"
    description: str = (
        "Execute a hard-coded arm manipulation task on the G1 humanoid robot. "
        "The call blocks until the motion sequence is complete. "
        "Use task_name='grab_from_table' to grab an object from a table in front, "
        "'place_on_table' to set an object down, "
        "'wave' to wave the right arm (safe test), "
        "'hand_over' to extend both arms forward."
    )
    args_schema: Type[BaseModel] = _TaskNameInput

    def _run(self, task_name: str) -> str:
        ok, why = GATE.authorize("g1", task_name)
        if not ok:
            return f"[REFUSED by contract gate] {why}"
        g1 = _g1()
        return _G1_DISABLED if g1 is None else g1.execute_task(task_name)


# ---------------------------------------------------------------------------

class _EmptyInput(BaseModel):
    pass


class G1StatusTool(BaseTool):
    name: str = "g1_status"
    description: str = (
        "Return the current status of the G1 humanoid: "
        "idle or executing (with current frame info)."
    )
    args_schema: Type[BaseModel] = _EmptyInput

    def _run(self) -> str:
        g1 = _g1()
        return _G1_DISABLED if g1 is None else g1.get_status()


class G1ListTasksTool(BaseTool):
    name: str = "g1_list_tasks"
    description: str = "List all available hard-coded G1 manipulation tasks."
    args_schema: Type[BaseModel] = _EmptyInput

    def _run(self) -> str:
        g1 = _g1()
        if g1 is None:
            return _G1_DISABLED
        return "Available G1 tasks: " + ", ".join(g1.available_tasks())
