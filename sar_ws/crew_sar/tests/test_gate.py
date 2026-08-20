from crew_system.gate import ContractGate

RAW_SAD = ('{"workflow_family":"search_and_dispatch","steps":['
           '{"robot":"iris","skill":"takeoff","args":{"altitude":5.0}},'
           '{"robot":"iris","skill":"search_target","args":'
           '{"x_min":-5.5,"x_max":5.5,"y_min":-5.5,"y_max":5.5}},'
           '{"robot":"tb3","skill":"navigate_to","args":{"target":"victim"}}]}')
SAD_REQUEST = ("A hiker is missing in the search zone x from -5.5 to 5.5, "
               "y from -5.5 to 5.5. Send the rover to the victim once located.")


def test_arm_accepts_valid_plan():
    g = ContractGate()
    res = g.arm(RAW_SAD, request=SAD_REQUEST)
    assert res.ok
    assert res.family == "search_and_dispatch"
    assert len(res.plan) == 3


def test_armed_gate_enforces_ordering_incrementally():
    g = ContractGate()
    assert g.arm(RAW_SAD, request=SAD_REQUEST).ok
    # TB3 tries to leave before the drone localized the victim -- even though
    # the plan itself is valid, the runtime order is not.
    ok, why = g.authorize("tb3", "navigate_to", {"target": "victim"})
    assert ok is False
    assert "order_violation" in why
    assert g.authorize("iris", "takeoff", {"altitude": 5.0})[0] is True
    assert g.authorize("iris", "search_target",
                       {"x_min": -5.5, "x_max": 5.5,
                        "y_min": -5.5, "y_max": 5.5})[0] is True
    ok, _ = g.authorize("tb3", "navigate_to", {"target": "victim"})
    assert ok is True


def test_armed_gate_refuses_off_plan_dispatch():
    g = ContractGate()
    assert g.arm(RAW_SAD, request=SAD_REQUEST).ok
    ok, why = g.authorize("tb3", "navigate_to", {"x": 2.0, "y": 1.0})
    assert ok is False
    assert "off_plan" in why
    # a consumed step cannot be dispatched twice
    assert g.authorize("iris", "takeoff", {"altitude": 5.0})[0] is True
    ok, why = g.authorize("iris", "takeoff", {"altitude": 5.0})
    assert ok is False
    assert "off_plan" in why


def test_arm_refuses_ungrounded_plan_with_feedback():
    g = ContractGate()
    raw = ('{"workflow_family":"dispatch_only","steps":['
           '{"robot":"tb3","skill":"navigate_to","args":{"x":40.0,"y":45.0}}]}')
    res = g.arm(raw, request="drive the rover to x 40.0, y 45.0")
    assert res.ok is False
    assert "unknown_location" in res.feedback()
    # failed arm leaves the gate disarmed; no execution crew will launch
    assert g.armed is False


def test_arm_refuses_malformed_routing_output():
    g = ContractGate()
    res = g.arm("Step 1 - Iris: take off and search")
    assert res.ok is False
    assert "malformed_plan" in res.feedback()


def test_arm_refuses_when_required_robot_unavailable():
    g = ContractGate()
    res = g.arm(RAW_SAD, request=SAD_REQUEST,
                state={"iris_busy": True, "tb3_busy": False})
    assert res.ok is False
    assert "robot_busy" in res.feedback()


def test_gate_matches_coordinates_numerically():
    g = ContractGate()
    raw = ('{"workflow_family":"dispatch_only","steps":['
           '{"robot":"tb3","skill":"navigate_to","args":{"x":3.0,"y":-2.0}}]}')
    assert g.arm(raw, request="Drive the rover to position x 3.0, y -2.0.").ok
    ok, why = g.authorize("tb3", "navigate_to", {"x": 99.0, "y": -1.0})
    assert ok is False                 # coordinate drift is off-plan
    assert "off_plan" in why
    ok, _ = g.authorize("tb3", "navigate_to", {"x": 3.0, "y": -2.0})
    assert ok is True


def test_gate_enforces_within_robot_plan_order():
    g = ContractGate()
    assert g.arm(RAW_SAD, request=SAD_REQUEST).ok
    # search before takeoff is within the plan but out of the approved order
    ok, why = g.authorize("iris", "search_target",
                          {"x_min": -5.5, "x_max": 5.5,
                           "y_min": -5.5, "y_max": 5.5})
    assert ok is False
    assert "off_plan" in why
    assert g.authorize("iris", "takeoff", {"altitude": 5.0})[0] is True


def test_disarmed_gate_passes_through():
    # Outside an armed mission (manual REPL commands), tools stay usable.
    g = ContractGate()
    assert g.authorize("iris", "land")[0] is True


def test_disarm_after_mission():
    g = ContractGate()
    assert g.arm(RAW_SAD, request=SAD_REQUEST).ok
    g.disarm()
    assert g.armed is False
    assert g.authorize("tb3", "navigate_to", {"x": 3.0, "y": -2.0})[0] is True
