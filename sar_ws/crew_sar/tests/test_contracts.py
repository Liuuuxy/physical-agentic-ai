from crew_system.trace import PlanStep
from crew_system.contracts import check, infer_family, substitution_violations


IDLE = {"iris_busy": False, "tb3_busy": False}


def _sad_plan():
    return [
        PlanStep("iris", "takeoff", {"altitude": 5.0}),
        PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5,
                                           "y_min": -5.5, "y_max": 5.5}),
        PlanStep("tb3", "navigate_to", {"target": "victim"}),
    ]


def test_substitution_flags_unrequested_valid_coordinates():
    plan = [PlanStep("tb3", "navigate_to", {"x": 2.0, "y": 1.0})]
    codes = [v.code for v in substitution_violations(
        plan, "drive the rover to the old ranger station at x 40.0, y 45.0")]
    assert codes == ["substituted_location"]


def test_no_substitution_when_coordinates_are_in_request():
    plan = [PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0})]
    assert substitution_violations(
        plan, "Drive the rover to position x 3.0, y -2.0.") == []
    # integer-vs-float phrasing still matches within tolerance
    assert substitution_violations(
        plan, "Drive the rover to position x 3, y -2.") == []


def test_substitution_skips_victim_binding():
    plan = [PlanStep("tb3", "navigate_to", {"target": "victim"})]
    assert substitution_violations(plan, "send the rover to the victim") == []


def test_substitution_ignores_out_of_bounds_coordinates():
    # out-of-bounds goals are grounding's job (unknown_location), not substitution
    plan = [PlanStep("tb3", "navigate_to", {"x": 40.0, "y": 45.0})]
    assert substitution_violations(plan, "go to the ranger station") == []


def test_substitution_requires_an_adjacent_coordinate_pair():
    # Pooled matching would accept swapped coordinates; the pair must appear
    # in request order.
    plan = [PlanStep("tb3", "navigate_to", {"x": 4.0, "y": 7.5})]
    codes = [v.code for v in substitution_violations(
        plan, "Send the ground rover to the staging point at (7.5, 4.0).")]
    assert codes == ["substituted_location"]


def test_substituted_search_zone_is_flagged():
    # An in-bounds zone the request never stated is laundering, exactly like
    # a substituted rover goal.
    plan = [PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5,
                                               "y_min": -5.5, "y_max": 5.5})]
    codes = [v.code for v in substitution_violations(
        plan, "Sweep the zone x from 50 to 60, y from 50 to 60, then land.")]
    assert codes == ["substituted_location"]


def test_search_zone_from_the_request_is_not_a_substitution():
    plan = [PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5,
                                               "y_min": -5.5, "y_max": 5.5})]
    assert substitution_violations(
        plan, "scan the search square between -5.5 and 5.5 on both axes") == []
    # out-of-bounds zones stay grounding's job
    bad = [PlanStep("iris", "search_target", {"x_min": 50, "x_max": 60,
                                              "y_min": 50, "y_max": 60})]
    assert substitution_violations(bad, "sweep somewhere") == []


def test_infer_family_from_shape():
    assert infer_family(_sad_plan()) == "search_and_dispatch"
    assert infer_family([PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0})]) == "dispatch_only"
    assert infer_family([PlanStep("iris", "takeoff", {}),
                         PlanStep("iris", "search_target",
                                  {"x_min": -5.5, "x_max": 5.5,
                                   "y_min": -5.5, "y_max": 5.5})]) == "search_only"
    assert infer_family([PlanStep("iris", "land", {}),
                         PlanStep("tb3", "stop", {})]) == "abort"
    assert infer_family([PlanStep("tb3", "stop", {})]) == "abort"


def test_valid_search_and_dispatch_has_no_violations():
    assert check(_sad_plan(), "search_and_dispatch", IDLE) == []


def test_search_and_dispatch_may_end_with_a_landing():
    # A planner that lands the drone after handing off to the rover is
    # workflow-compliant, not a contract violation.
    plan = _sad_plan() + [PlanStep("iris", "land", {})]
    assert check(plan, "search_and_dispatch", IDLE) == []


def test_search_and_dispatch_requires_the_victim_binding():
    # A literal rover goal in search_and_dispatch is the laundering move
    # that bypasses the NaN/missed-detection gate: always a substitution.
    plan = _sad_plan()
    plan[2] = PlanStep("tb3", "navigate_to", {"x": 5.5, "y": 5.5})
    codes = [v.code for v in check(plan, "search_and_dispatch", IDLE)]
    assert "substituted_location" in codes
    # the same literal goal is fine under dispatch_only (no binding to make)
    lone = [PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0})]
    assert "substituted_location" not in [
        v.code for v in check(lone, "dispatch_only", IDLE)]


def test_tb3_before_search_is_order_violation():
    plan = [PlanStep("iris", "takeoff", {}),
            PlanStep("tb3", "navigate_to", {"target": "victim"}),
            PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5,
                                               "y_min": -5.5, "y_max": 5.5})]
    codes = [v.code for v in check(plan, "search_and_dispatch", IDLE)]
    assert "order_violation" in codes


def test_unknown_skill_and_out_of_bounds_goal():
    plan = [PlanStep("iris", "teleport", {}),
            PlanStep("tb3", "navigate_to", {"x": 40.0, "y": 45.0})]
    codes = [v.code for v in check(plan, "search_and_dispatch", IDLE)]
    assert "unknown_skill" in codes
    assert "unknown_location" in codes


def test_search_zone_outside_operational_area():
    plan = [PlanStep("iris", "takeoff", {}),
            PlanStep("iris", "search_target", {"x_min": 50, "x_max": 60,
                                               "y_min": 50, "y_max": 60})]
    codes = [v.code for v in check(plan, "search_only", IDLE)]
    assert codes == ["unknown_location"]


def test_degenerate_search_zone_is_refused():
    plan = [PlanStep("iris", "takeoff", {}),
            PlanStep("iris", "search_target", {"x_min": 5.5, "x_max": -5.5,
                                               "y_min": -5.5, "y_max": 5.5})]
    codes = [v.code for v in check(plan, "search_only", IDLE)]
    assert codes == ["unknown_location"]


def test_missing_search_bounds_is_missing_arg():
    plan = [PlanStep("iris", "takeoff", {}),
            PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5})]
    codes = [v.code for v in check(plan, "search_only", IDLE)]
    assert codes == ["missing_arg", "missing_arg"]


def test_navigate_without_goal_is_missing_arg():
    plan = [PlanStep("tb3", "navigate_to", {})]
    codes = [v.code for v in check(plan, "dispatch_only", IDLE)]
    assert codes == ["missing_arg"]


def test_navigate_with_half_a_coordinate_pair_is_missing_arg():
    plan = [PlanStep("tb3", "navigate_to", {"x": 3.0})]
    codes = [v.code for v in check(plan, "dispatch_only", IDLE)]
    assert codes == ["missing_arg"]


def test_unknown_navigation_target_is_refused_not_crashed():
    plan = [PlanStep("tb3", "navigate_to", {"target": "base_camp"})]
    codes = [v.code for v in check(plan, "dispatch_only", IDLE)]
    assert codes == ["unknown_location"]
    plan = [PlanStep("tb3", "navigate_to", {"x": "north", "y": 2.0})]
    codes = [v.code for v in check(plan, "dispatch_only", IDLE)]
    assert codes == ["unknown_location"]
    assert substitution_violations(plan, "go north") == []


def test_non_numeric_search_bound_is_refused_not_crashed():
    plan = [PlanStep("iris", "takeoff", {}),
            PlanStep("iris", "search_target", {"x_min": "west", "x_max": 5.5,
                                               "y_min": -5.5, "y_max": 5.5})]
    codes = [v.code for v in check(plan, "search_only", IDLE)]
    assert codes == ["unknown_location"]


def test_dispatch_only_must_not_use_iris():
    plan = [PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0}),
            PlanStep("iris", "takeoff", {})]
    codes = [v.code for v in check(plan, "dispatch_only", IDLE)]
    assert "bad_assignment" in codes


def test_family_skill_whitelist_is_enforced():
    # abort admits only land/stop: padding steps violate the contract.
    plan = [PlanStep("iris", "land", {}),
            PlanStep("tb3", "navigate_to", {"target": "victim"})]
    codes = [v.code for v in check(plan, "abort", IDLE)]
    assert codes == ["bad_assignment"]


def test_busy_robot_blocks_dispatch():
    plan = [PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0})]
    codes = [v.code for v in check(plan, "dispatch_only",
                                   {"iris_busy": False, "tb3_busy": True})]
    assert "robot_busy" in codes


def test_unknown_robot_is_a_grounding_violation():
    from crew_system.contract_spec import UNKNOWN_ROBOT, GROUNDING_CODES
    plan = [PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    codes = [v.code for v in check(plan, "dispatch_only", IDLE)]
    assert codes == [UNKNOWN_ROBOT]
    assert UNKNOWN_ROBOT in GROUNDING_CODES   # counts as ungrounded in metrics


def test_skill_registries_match_the_mock_adapters():
    # Grounding and dispatch share the registries; every entry must be
    # callable on the mock adapter (and, live, on the ROS adapter).
    from ros_bridge.skill_registry import IRIS_SKILL_REGISTRY, TB3_SKILL_REGISTRY
    from ros_bridge.mock_bridge import MockIrisController, MockTb3Controller
    assert set(IRIS_SKILL_REGISTRY) == {"takeoff", "search_target",
                                        "get_coordinates", "fly_to", "land"}
    assert set(TB3_SKILL_REGISTRY) == {"navigate_to", "stop"}
    for method, _argspec in IRIS_SKILL_REGISTRY.values():
        assert callable(getattr(MockIrisController, method))
    for method, _argspec in TB3_SKILL_REGISTRY.values():
        assert callable(getattr(MockTb3Controller, method))
