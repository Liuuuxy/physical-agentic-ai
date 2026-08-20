"""The dispatching CrewAI tools must consult the contract gate before touching
a controller. Needs crewai (tool base classes) and CREW_SIM=1 (mock bridge)."""
import pytest

pytest.importorskip("crewai")

from crew_system.gate import GATE  # noqa: E402

NAV_PLAN = ('{"workflow_family":"navigation_only","steps":['
            '{"robot":"go2","skill":"navigate_to_location","args":{"location":"room_b"}}]}')


@pytest.fixture(autouse=True)
def disarm_after():
    yield
    GATE.disarm()


def test_g1_tool_refuses_off_plan_dispatch():
    from crew_system.tools.g1_tools import G1ExecuteTaskTool
    assert GATE.arm(NAV_PLAN, request="go to room_b").ok
    out = G1ExecuteTaskTool()._run(task_name="wave")
    assert "off_plan" in out


def test_go2_tool_dispatches_approved_step():
    from crew_system.tools.go2_tools import Go2NavigateToLocationTool
    assert GATE.arm(NAV_PLAN, request="go to room_b").ok
    out = Go2NavigateToLocationTool()._run(location="room_b")
    assert "[SIM]" in out          # reached the (mock) controller


def test_go2_tool_refuses_unapproved_destination():
    from crew_system.tools.go2_tools import Go2NavigateToLocationTool
    assert GATE.arm(NAV_PLAN, request="go to room_b").ok
    out = Go2NavigateToLocationTool()._run(location="charging")
    assert "off_plan" in out


def test_execution_tasks_embed_the_approved_plan():
    # The execution agents receive the contract-checked plan verbatim in
    # their task description (no cross-crew context resolution needed).
    from crew_system.agents import make_g1_agent, make_go2_agent
    from crew_system.tasks import make_g1_execution_task, make_go2_execution_task
    plan_text = '{"workflow_family": "carry", "steps": []}'
    t1 = make_g1_execution_task(make_g1_agent(), plan_text=plan_text)
    t2 = make_go2_execution_task(make_go2_agent(), plan_text=plan_text)
    assert plan_text in t1.description
    assert plan_text in t2.description
