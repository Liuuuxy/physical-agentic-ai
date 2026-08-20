from crew_system.trace import PlanStep, StepTrace, MissionTrace


def test_mission_trace_to_dict_roundtrips():
    step = PlanStep(robot="go2", skill="navigate_to_location", args={"location": "room_b"})
    st = StepTrace(step=step, dispatched=True, grounded=True, result="[SIM] arrived", violations=[])
    mt = MissionTrace(
        request="bring me the cube", baseline="rao", declared_family="carry",
        plan=[step], steps=[st], refused=False, replanned=False, llm_calls=2, latency_s=1.3,
    )
    d = mt.to_dict()
    assert d["baseline"] == "rao"
    assert d["plan"][0]["skill"] == "navigate_to_location"
    assert d["steps"][0]["dispatched"] is True
    assert d["llm_calls"] == 2
    import json
    json.dumps(d)  # must be JSON-serializable
