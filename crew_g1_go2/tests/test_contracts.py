from crew_system.trace import PlanStep
from crew_system.contracts import check, infer_family, substitution_violations


def test_substitution_flags_unrequested_valid_location():
    plan = [PlanStep("go2", "navigate_to_location", {"location": "dropoff"})]
    codes = [v.code for v in substitution_violations(plan, "carry the cube to the rooftop helipad")]
    assert codes == ["substituted_location"]


def test_no_substitution_when_location_is_in_request():
    plan = [PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    assert substitution_violations(plan, "bring the cube to room_b") == []
    # underscore/space normalization
    assert substitution_violations(plan, "bring the cube to room b") == []


def test_substitution_ignores_invalid_location_names():
    # invalid names are grounding's job (unknown_location), not substitution
    plan = [PlanStep("go2", "navigate_to_location", {"location": "rooftop_helipad"})]
    assert substitution_violations(plan, "go to the rooftop helipad") == []


IDLE = {"g1_busy": False, "go2_busy": False}


def _carry_plan():
    return [
        PlanStep("g1", "grab_from_table", {}),
        PlanStep("g1", "place_on_table", {}),
        PlanStep("go2", "navigate_to_location", {"location": "room_b"}),
    ]


def test_infer_family_from_shape():
    assert infer_family([PlanStep("g1", "hand_over", {})]) == "handover"
    assert infer_family([PlanStep("g1", "wave", {})]) == "manipulation_only"
    assert infer_family([PlanStep("go2", "navigate_to_location", {"location": "room_b"})]) == "navigation_only"
    assert infer_family(_carry_plan()) == "carry"


def test_valid_carry_has_no_violations():
    assert check(_carry_plan(), "carry", IDLE) == []


def test_carry_go2_before_load_is_order_violation():
    plan = [
        PlanStep("go2", "navigate_to_location", {"location": "room_b"}),
        PlanStep("g1", "grab_from_table", {}),
        PlanStep("g1", "place_on_table", {}),
    ]
    codes = [v.code for v in check(plan, "carry", IDLE)]
    assert "order_violation" in codes


def test_unknown_skill_and_location():
    plan = [PlanStep("g1", "teleport", {}),
            PlanStep("go2", "navigate_to_location", {"location": "mars"})]
    codes = [v.code for v in check(plan, "carry", IDLE)]
    assert "unknown_skill" in codes
    assert "unknown_location" in codes


def test_handover_must_not_use_go2():
    plan = [PlanStep("g1", "hand_over", {}),
            PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    codes = [v.code for v in check(plan, "handover", IDLE)]
    assert "bad_assignment" in codes


def test_busy_robot_blocks_dispatch():
    plan = [PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    codes = [v.code for v in check(plan, "navigation_only", {"g1_busy": False, "go2_busy": True})]
    assert "robot_busy" in codes


def test_non_string_location_is_refused_not_crashed():
    plan = [PlanStep("go2", "navigate_to_location", {"location": 3})]
    codes = [v.code for v in check(plan, "navigation_only", IDLE)]
    assert codes == ["unknown_location"]
    assert substitution_violations(plan, "go somewhere") == []


def test_unknown_robot_is_a_grounding_violation():
    from crew_system.contract_spec import UNKNOWN_ROBOT, GROUNDING_CODES
    plan = [PlanStep("drone", "fly", {})]
    codes = [v.code for v in check(plan, "navigation_only", IDLE)]
    assert codes == [UNKNOWN_ROBOT]
    assert UNKNOWN_ROBOT in GROUNDING_CODES   # counts as ungrounded in metrics


def test_family_skill_whitelist_is_enforced():
    # The guidance ('a single navigate step') is now machine-enforced, not
    # free text: padding steps like status/stop violate the contract.
    plan = [PlanStep("go2", "navigate_to_location", {"location": "room_b"}),
            PlanStep("go2", "status", {})]
    codes = [v.code for v in check(plan, "navigation_only", IDLE)]
    assert codes == ["bad_assignment"]


def test_substitution_matches_spaced_location_names():
    plan = [PlanStep("go2", "navigate_to_location", {"location": "dropoff"})]
    assert substitution_violations(plan, "Go2, drop off point please") == []


def test_navigate_to_coord_requires_x_and_y():
    plan = [PlanStep("go2", "navigate_to_coord", {"x": 1.0})]
    codes = [v.code for v in check(plan, "navigation_only", IDLE)]
    assert codes == ["missing_arg"]


def test_go2_skill_registry_matches_both_controllers():
    # Grounding and dispatch share GO2_SKILL_REGISTRY; every entry must be
    # callable on the real controller and its mock.
    from ros_bridge.go2_controller import GO2_SKILL_REGISTRY, Go2Controller
    from ros_bridge.mock_bridge import MockGo2Controller
    assert set(GO2_SKILL_REGISTRY) == {"navigate_to_location", "navigate_to_coord",
                                       "stop", "status"}
    for method, _argspec in GO2_SKILL_REGISTRY.values():
        assert callable(getattr(Go2Controller, method))
        assert callable(getattr(MockGo2Controller, method))
