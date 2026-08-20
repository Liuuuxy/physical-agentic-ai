from crew_system.eval_mission import run_eval_mission

VALID_SAD = ('{"workflow_family":"search_and_dispatch","steps":['
             '{"robot":"iris","skill":"takeoff","args":{"altitude":5.0}},'
             '{"robot":"iris","skill":"search_target","args":'
             '{"x_min":-5.5,"x_max":5.5,"y_min":-5.5,"y_max":5.5}},'
             '{"robot":"tb3","skill":"navigate_to","args":{"target":"victim"}}]}')
SAD_REQUEST = ("A hiker is missing in the search zone x from -5.5 to 5.5, "
               "y from -5.5 to 5.5. Send the rover to the victim once located.")


def fake_router(request, baseline, feedback=None):
    raw = ('{"workflow_family":"dispatch_only",'
           '"steps":[{"robot":"tb3","skill":"navigate_to","args":{"x":40.0,"y":45.0}}]}')
    return raw, 1


def test_rao_refuses_bad_plan_when_replan_also_bad():
    # fake_router returns the same out-of-bounds plan on retry, so the replan
    # fails and the mission stays refused.
    mt = run_eval_mission("drive the rover to x 40.0, y 45.0",
                          baseline="rao", router=fake_router)
    assert mt.baseline == "rao"
    assert mt.refused is True
    assert mt.replan_attempted is True
    assert mt.replanned is False
    assert mt.steps[0].dispatched is False


def test_skill_list_does_not_enforce():
    mt = run_eval_mission("drive the rover to x 40.0, y 45.0",
                          baseline="skill-list", router=fake_router)
    assert mt.refused is False
    assert mt.replan_attempted is False
    assert mt.steps[0].dispatched is True


def malformed_router(request, baseline, feedback=None):
    return "I cannot produce a plan for that request.", 1


def test_rao_refuses_malformed_plan_and_attempts_replan():
    # Unparseable LLM output must NOT become a silently successful empty
    # mission: the gate refuses it and triggers the feedback replan.
    mt = run_eval_mission(SAD_REQUEST, baseline="rao", router=malformed_router)
    assert mt.refused is True
    assert mt.replan_attempted is True
    assert mt.replanned is False
    assert mt.parse_problems
    assert mt.steps == []


def test_rao_dispatches_nothing_from_partially_malformed_plan():
    # A plan with SOME well-formed steps but structural problems must fail
    # closed: no step dispatches, then the replan fires.
    def router(request, baseline, feedback=None):
        raw = ('{"workflow_family":"dispatch_only","steps":['
               '{"robot":"tb3"},'
               '{"robot":"tb3","skill":"navigate_to","args":{"x":3.0,"y":-2.0}}]}')
        return raw, 1

    mt = run_eval_mission("Drive the rover to position x 3.0, y -2.0.",
                          baseline="rao", router=router)
    assert mt.refused is True
    assert mt.replan_attempted is True
    assert all(st.dispatched is False for st in mt.steps)


def test_skill_list_records_malformed_but_does_not_refuse():
    mt = run_eval_mission(SAD_REQUEST, baseline="skill-list",
                          router=malformed_router)
    assert mt.refused is False
    assert mt.parse_problems


def test_rao_recovers_from_malformed_plan_via_replan():
    def stateful_router(request, baseline, feedback=None):
        if feedback is None:
            return "no JSON here, sorry", 1
        assert "malformed_plan" in feedback
        return VALID_SAD, 1

    mt = run_eval_mission(SAD_REQUEST, baseline="rao", router=stateful_router)
    assert mt.replanned is True
    assert mt.refused is False
    assert mt.parse_problems == []      # the adopted plan parsed cleanly
    assert all(st.dispatched for st in mt.steps)


def test_rao_replans_to_success():
    # First call returns an out-of-bounds plan; the feedback-driven retry
    # returns a valid one. RAO should recover: refused False, replanned True.
    calls = {"n": 0}

    def stateful_router(request, baseline, feedback=None):
        calls["n"] += 1
        if feedback is None:
            return ('{"workflow_family":"dispatch_only","steps":'
                    '[{"robot":"tb3","skill":"navigate_to","args":{"x":40.0,"y":45.0}}]}'), 1
        return ('{"workflow_family":"dispatch_only","steps":'
                '[{"robot":"tb3","skill":"navigate_to","args":{"x":3.0,"y":-2.0}}]}'), 1

    mt = run_eval_mission("Drive the rover to position x 3.0, y -2.0.",
                          baseline="rao", router=stateful_router)
    assert mt.replan_attempted is True
    assert mt.replanned is True
    assert mt.refused is False
    assert mt.steps[0].dispatched is True
    assert calls["n"] == 2          # one retry
    assert mt.llm_calls == 2


def sad_router(request, baseline, feedback=None):
    return VALID_SAD, 1


def test_rao_blocks_nan_fix_at_the_rover_dispatch():
    # The perception fault is invisible to the planner AND to static plan
    # checks; it surfaces on the state interface at dispatch time. RAO must
    # refuse the rover step, attempt a replan, and stay refused (the fault
    # is unrecoverable by design).
    mt = run_eval_mission(SAD_REQUEST, baseline="rao", router=sad_router,
                          mock_fault="nan_transmission")
    assert mt.refused is True
    assert mt.replan_attempted is True
    assert mt.replanned is False
    tb3_step = mt.steps[2]
    assert tb3_step.dispatched is False
    assert "no_target_fix" in tb3_step.violations


def test_skill_list_dispatches_on_nan_fix():
    mt = run_eval_mission(SAD_REQUEST, baseline="skill-list", router=sad_router,
                          mock_fault="nan_transmission")
    assert mt.refused is False
    tb3_step = mt.steps[2]
    assert tb3_step.dispatched is True
    assert "no_target_fix" in tb3_step.violations


def test_nominal_sad_mission_succeeds_under_rao():
    mt = run_eval_mission(SAD_REQUEST, baseline="rao", router=sad_router)
    assert mt.refused is False
    assert mt.replan_attempted is False
    assert all(st.dispatched for st in mt.steps)
    assert "arrived at (5.00, 5.00)" in mt.steps[2].result
