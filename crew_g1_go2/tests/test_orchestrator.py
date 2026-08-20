from crew_system.trace import PlanStep
from crew_system.orchestrator import execute_plan
from ros_bridge.mock_bridge import MockG1Controller, MockGo2Controller


def _ctrls():
    return MockG1Controller(), MockGo2Controller()


def test_rao_blocks_substituted_location():
    g1, go2 = _ctrls()
    plan = [PlanStep("go2", "navigate_to_location", {"location": "dropoff"})]
    steps, refused = execute_plan(plan, "navigation_only", g1, go2, enforce=True,
                                  request="go to the rooftop helipad")
    assert refused is True
    assert steps[0].dispatched is False
    assert "substituted_location" in steps[0].violations


def test_rao_blocks_when_required_robot_unavailable():
    g1, go2 = _ctrls()
    plan = [PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    steps, refused = execute_plan(plan, "navigation_only", g1, go2, enforce=True,
                                  state={"g1_busy": False, "go2_busy": True},
                                  request="go to room_b")
    assert refused is True
    assert "robot_busy" in steps[0].violations


def test_skill_list_dispatches_substitution_but_records_it():
    g1, go2 = _ctrls()
    plan = [PlanStep("go2", "navigate_to_location", {"location": "dropoff"})]
    steps, refused = execute_plan(plan, "navigation_only", g1, go2, enforce=False,
                                  request="go to the rooftop helipad")
    assert refused is False
    assert steps[0].dispatched is True
    assert "substituted_location" in steps[0].violations


def test_rao_blocks_unknown_location_no_dispatch():
    g1, go2 = _ctrls()
    plan = [PlanStep("go2", "navigate_to_location", {"location": "mars"})]
    steps, refused = execute_plan(plan, "navigation_only", g1, go2, enforce=True)
    assert refused is True
    assert steps[0].dispatched is False
    assert "unknown_location" in steps[0].violations


def test_skill_list_dispatches_even_when_ungrounded():
    g1, go2 = _ctrls()
    plan = [PlanStep("go2", "navigate_to_location", {"location": "mars"})]
    steps, refused = execute_plan(plan, "navigation_only", g1, go2, enforce=False)
    assert refused is False
    assert steps[0].dispatched is True          # no gate
    assert steps[0].grounded is False            # but recorded as ungrounded


def test_explicit_null_arg_dispatches_with_default_when_not_enforcing():
    # JSON null for a required arg must not crash the non-enforcing arms.
    g1, go2 = _ctrls()
    plan = [PlanStep("go2", "navigate_to_location", {"location": None})]
    steps, refused = execute_plan(plan, "navigation_only", g1, go2, enforce=False)
    assert steps[0].dispatched is True
    assert "Unknown location" in steps[0].result


def test_rao_dispatches_valid_carry():
    g1, go2 = _ctrls()
    plan = [PlanStep("g1", "grab_from_table", {}),
            PlanStep("g1", "place_on_table", {}),
            PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    steps, refused = execute_plan(plan, "carry", g1, go2, enforce=True)
    assert refused is False
    assert all(s.dispatched for s in steps)
