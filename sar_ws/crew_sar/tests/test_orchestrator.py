from crew_system.trace import PlanStep
from crew_system.orchestrator import execute_plan
from ros_bridge.mock_bridge import MockIrisController, MockTb3Controller

IDLE = {"iris_busy": False, "tb3_busy": False}


def _ctrls(fault="none", state=None):
    state = dict(state) if state else dict(IDLE)
    return MockIrisController(state, fault=fault), MockTb3Controller(state), state


def _sad_plan():
    return [
        PlanStep("iris", "takeoff", {"altitude": 5.0}),
        PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5,
                                           "y_min": -5.5, "y_max": 5.5}),
        PlanStep("tb3", "navigate_to", {"target": "victim"}),
    ]

SAD_REQUEST = ("A hiker is missing in the search zone x from -5.5 to 5.5, "
               "y from -5.5 to 5.5. Send the rover to the victim once located.")


def test_rao_executes_valid_search_and_dispatch_end_to_end():
    iris, tb3, state = _ctrls()
    steps, refused = execute_plan(_sad_plan(), "search_and_dispatch", iris, tb3,
                                  enforce=True, state=state, request=SAD_REQUEST)
    assert refused is False
    assert all(s.dispatched for s in steps)
    # the rover goal came from the state interface, not the plan
    assert "arrived at (5.00, 5.00)" in steps[2].result


def test_rao_refuses_rover_dispatch_on_nan_fix():
    iris, tb3, state = _ctrls(fault="nan_transmission")
    steps, refused = execute_plan(_sad_plan(), "search_and_dispatch", iris, tb3,
                                  enforce=True, state=state, request=SAD_REQUEST)
    assert refused is True
    assert steps[0].dispatched and steps[1].dispatched   # search still ran
    assert steps[2].dispatched is False
    assert "no_target_fix" in steps[2].violations


def test_rao_refuses_rover_dispatch_on_missed_detection():
    iris, tb3, state = _ctrls(fault="missed_detection")
    steps, refused = execute_plan(_sad_plan(), "search_and_dispatch", iris, tb3,
                                  enforce=True, state=state, request=SAD_REQUEST)
    assert refused is True
    assert steps[2].dispatched is False
    assert "no_target_fix" in steps[2].violations


def test_skill_list_dispatches_nan_fix_but_records_it():
    # Without the gate the corrupted fix reaches the rover: a false dispatch.
    iris, tb3, state = _ctrls(fault="nan_transmission")
    steps, refused = execute_plan(_sad_plan(), "search_and_dispatch", iris, tb3,
                                  enforce=False, state=state, request=SAD_REQUEST)
    assert refused is False
    assert steps[2].dispatched is True
    assert "no_target_fix" in steps[2].violations
    assert "non-finite goal" in steps[2].result


def test_rao_blocks_victim_binding_without_search():
    iris, tb3, state = _ctrls()
    plan = [PlanStep("tb3", "navigate_to", {"target": "victim"})]
    steps, refused = execute_plan(plan, "dispatch_only", iris, tb3,
                                  enforce=True, state=state)
    assert refused is True
    assert "no_target_fix" in steps[0].violations


def test_rao_blocks_out_of_bounds_goal_no_dispatch():
    iris, tb3, state = _ctrls()
    plan = [PlanStep("tb3", "navigate_to", {"x": 40.0, "y": 45.0})]
    steps, refused = execute_plan(plan, "dispatch_only", iris, tb3,
                                  enforce=True, state=state)
    assert refused is True
    assert steps[0].dispatched is False
    assert "unknown_location" in steps[0].violations


def test_rao_blocks_substituted_coordinates():
    iris, tb3, state = _ctrls()
    plan = [PlanStep("tb3", "navigate_to", {"x": 2.0, "y": 1.0})]
    steps, refused = execute_plan(plan, "dispatch_only", iris, tb3, enforce=True,
                                  state=state,
                                  request="drive the rover to x 40.0, y 45.0")
    assert refused is True
    assert "substituted_location" in steps[0].violations


def test_rao_blocks_when_required_robot_unavailable():
    iris, tb3, state = _ctrls(state={"iris_busy": False, "tb3_busy": True})
    plan = [PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0})]
    steps, refused = execute_plan(plan, "dispatch_only", iris, tb3, enforce=True,
                                  state=state,
                                  request="Drive the rover to position x 3.0, y -2.0.")
    assert refused is True
    assert "robot_busy" in steps[0].violations


def test_skill_list_dispatches_even_when_ungrounded():
    iris, tb3, state = _ctrls()
    plan = [PlanStep("tb3", "navigate_to", {"x": 40.0, "y": 45.0})]
    steps, refused = execute_plan(plan, "dispatch_only", iris, tb3,
                                  enforce=False, state=state)
    assert refused is False
    assert steps[0].dispatched is True          # no gate
    assert steps[0].grounded is False            # but recorded as ungrounded


def test_unknown_skill_dispatch_is_refused_by_adapter_lookup():
    iris, tb3, state = _ctrls()
    plan = [PlanStep("iris", "teleport", {})]
    steps, refused = execute_plan(plan, "search_only", iris, tb3,
                                  enforce=False, state=state)
    assert steps[0].dispatched is True
    assert "no adapter" in steps[0].result
