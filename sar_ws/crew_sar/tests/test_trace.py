from crew_system.trace import PlanStep, StepTrace, MissionTrace


def test_mission_trace_to_dict_roundtrips():
    step = PlanStep(robot="tb3", skill="navigate_to", args={"target": "victim"})
    st = StepTrace(step=step, dispatched=True, grounded=True,
                   result="[SIM] arrived", violations=[])
    mt = MissionTrace(
        request="send the rover to the victim", baseline="rao",
        declared_family="search_and_dispatch",
        plan=[step], steps=[st], refused=False, replanned=False,
        llm_calls=2, latency_s=1.3,
    )
    d = mt.to_dict()
    assert d["baseline"] == "rao"
    assert d["plan"][0]["skill"] == "navigate_to"
    assert d["steps"][0]["dispatched"] is True
    assert d["llm_calls"] == 2
    import json
    json.dumps(d)  # must be JSON-serializable
