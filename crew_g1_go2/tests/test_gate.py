from crew_system.gate import ContractGate

RAW_CARRY = ('{"workflow_family":"carry","steps":['
             '{"robot":"g1","skill":"grab_from_table","args":{}},'
             '{"robot":"g1","skill":"place_on_table","args":{}},'
             '{"robot":"go2","skill":"navigate_to_location","args":{"location":"room_b"}}]}')
CARRY_REQUEST = "bring the red cube to room_b"


def test_arm_accepts_valid_plan():
    g = ContractGate()
    res = g.arm(RAW_CARRY, request=CARRY_REQUEST)
    assert res.ok
    assert res.family == "carry"
    assert len(res.plan) == 3


def test_armed_gate_enforces_ordering_incrementally():
    g = ContractGate()
    assert g.arm(RAW_CARRY, request=CARRY_REQUEST).ok
    # Go2 tries to leave before G1 loaded the payload -- even though the
    # plan itself is valid, the runtime order is not.
    ok, why = g.authorize("go2", "navigate_to_location", {"location": "room_b"})
    assert ok is False
    assert "order_violation" in why
    assert g.authorize("g1", "grab_from_table")[0] is True
    assert g.authorize("g1", "place_on_table")[0] is True
    ok, _ = g.authorize("go2", "navigate_to_location", {"location": "room_b"})
    assert ok is True


def test_armed_gate_refuses_off_plan_dispatch():
    g = ContractGate()
    assert g.arm(RAW_CARRY, request=CARRY_REQUEST).ok
    ok, why = g.authorize("go2", "navigate_to_location", {"location": "charging"})
    assert ok is False
    assert "off_plan" in why
    # a consumed step cannot be dispatched twice
    assert g.authorize("g1", "grab_from_table")[0] is True
    ok, why = g.authorize("g1", "grab_from_table")
    assert ok is False
    assert "off_plan" in why


def test_arm_refuses_ungrounded_plan_with_feedback():
    g = ContractGate()
    raw = ('{"workflow_family":"navigation_only","steps":['
           '{"robot":"go2","skill":"navigate_to_location","args":{"location":"mars"}}]}')
    res = g.arm(raw, request="go to mars")
    assert res.ok is False
    assert "unknown_location" in res.feedback()
    # failed arm leaves the gate disarmed; no execution crew will launch
    assert g.armed is False


def test_arm_refuses_malformed_routing_output():
    g = ContractGate()
    res = g.arm("Step 1 - G1: grab the cube")
    assert res.ok is False
    assert "malformed_plan" in res.feedback()


def test_arm_refuses_when_required_robot_unavailable():
    g = ContractGate()
    res = g.arm(RAW_CARRY, request=CARRY_REQUEST,
                state={"g1_busy": True, "go2_busy": False})
    assert res.ok is False
    assert "robot_busy" in res.feedback()


def test_gate_matches_coordinates_numerically():
    g = ContractGate()
    raw = ('{"workflow_family":"navigation_only","steps":['
           '{"robot":"go2","skill":"navigate_to_coord","args":{"x":2.0,"y":0.0}}]}')
    assert g.arm(raw).ok
    ok, why = g.authorize("go2", "navigate_to_coord", {"x": 99.0, "y": -1.0})
    assert ok is False                 # coordinate drift is off-plan
    assert "off_plan" in why
    ok, _ = g.authorize("go2", "navigate_to_coord", {"x": 2.0, "y": 0.0})
    assert ok is True


def test_gate_enforces_within_robot_plan_order():
    g = ContractGate()
    assert g.arm(RAW_CARRY, request=CARRY_REQUEST).ok
    # place before grab is within the plan but out of the approved order
    ok, why = g.authorize("g1", "place_on_table")
    assert ok is False
    assert "off_plan" in why
    assert g.authorize("g1", "grab_from_table")[0] is True
    assert g.authorize("g1", "place_on_table")[0] is True


def test_disarmed_gate_passes_through():
    # Outside an armed mission (manual REPL commands), tools stay usable.
    g = ContractGate()
    assert g.authorize("g1", "wave")[0] is True


def test_disarm_after_mission():
    g = ContractGate()
    assert g.arm(RAW_CARRY, request=CARRY_REQUEST).ok
    g.disarm()
    assert g.armed is False
    assert g.authorize("go2", "navigate_to_location", {"location": "charging"})[0] is True
