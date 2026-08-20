from crew_system.eval_mission import run_eval_mission


def fake_router(request, baseline, feedback=None):
    raw = ('{"workflow_family":"navigation_only",'
           '"steps":[{"robot":"go2","skill":"navigate_to_location","args":{"location":"mars"}}]}')
    return raw, 1


def test_rao_refuses_bad_plan_when_replan_also_bad():
    # fake_router returns the same invalid plan on retry, so the replan fails
    # and the mission stays refused.
    mt = run_eval_mission("go to mars", baseline="rao", router=fake_router)
    assert mt.baseline == "rao"
    assert mt.refused is True
    assert mt.replan_attempted is True
    assert mt.replanned is False
    assert mt.steps[0].dispatched is False


def test_skill_list_does_not_enforce():
    mt = run_eval_mission("go to mars", baseline="skill-list", router=fake_router)
    assert mt.refused is False
    assert mt.replan_attempted is False
    assert mt.steps[0].dispatched is True


def malformed_router(request, baseline, feedback=None):
    return "I cannot produce a plan for that request.", 1


def test_rao_refuses_malformed_plan_and_attempts_replan():
    # Unparseable LLM output must NOT become a silently successful empty
    # mission: the gate refuses it and triggers the feedback replan.
    mt = run_eval_mission("go to room_b", baseline="rao", router=malformed_router)
    assert mt.refused is True
    assert mt.replan_attempted is True
    assert mt.replanned is False
    assert mt.parse_problems
    assert mt.steps == []


def test_rao_dispatches_nothing_from_partially_malformed_plan():
    # A plan with SOME well-formed steps but structural problems must fail
    # closed: no step dispatches, then the replan fires.
    def router(request, baseline, feedback=None):
        raw = ('{"workflow_family":"navigation_only","steps":['
               '{"robot":"go2"},'
               '{"robot":"go2","skill":"navigate_to_location","args":{"location":"room_b"}}]}')
        return raw, 1

    mt = run_eval_mission("go to room_b", baseline="rao", router=router)
    assert mt.refused is True
    assert mt.replan_attempted is True
    assert all(st.dispatched is False for st in mt.steps)


def test_skill_list_records_malformed_but_does_not_refuse():
    mt = run_eval_mission("go to room_b", baseline="skill-list", router=malformed_router)
    assert mt.refused is False
    assert mt.parse_problems


def test_rao_recovers_from_malformed_plan_via_replan():
    def stateful_router(request, baseline, feedback=None):
        if feedback is None:
            return "no JSON here, sorry", 1
        assert "malformed_plan" in feedback
        return ('{"workflow_family":"navigation_only","steps":'
                '[{"robot":"go2","skill":"navigate_to_location","args":{"location":"room_b"}}]}'), 1

    mt = run_eval_mission("go to room_b", baseline="rao", router=stateful_router)
    assert mt.replanned is True
    assert mt.refused is False
    assert mt.parse_problems == []      # the adopted plan parsed cleanly
    assert mt.steps[0].dispatched is True


def test_rao_replans_to_success():
    # First call returns an invalid plan; the feedback-driven retry returns a
    # valid one. RAO should recover: refused False, replanned True.
    calls = {"n": 0}

    def stateful_router(request, baseline, feedback=None):
        calls["n"] += 1
        if feedback is None:
            return ('{"workflow_family":"navigation_only","steps":'
                    '[{"robot":"go2","skill":"navigate_to_location","args":{"location":"mars"}}]}'), 1
        return ('{"workflow_family":"navigation_only","steps":'
                '[{"robot":"go2","skill":"navigate_to_location","args":{"location":"room_b"}}]}'), 1

    mt = run_eval_mission("go to room_b", baseline="rao", router=stateful_router)
    assert mt.replan_attempted is True
    assert mt.replanned is True
    assert mt.refused is False
    assert mt.steps[0].dispatched is True
    assert calls["n"] == 2          # one retry
    assert mt.llm_calls == 2
