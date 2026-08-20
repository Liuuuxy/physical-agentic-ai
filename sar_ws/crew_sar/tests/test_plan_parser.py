from crew_system.plan_parser import parse_plan


def test_parses_fenced_json():
    raw = '''here is the plan:
```json
{"workflow_family": "search_and_dispatch",
 "steps": [{"robot":"iris","skill":"takeoff","args":{"altitude":5.0}},
           {"robot":"tb3","skill":"navigate_to","args":{"target":"victim"}}]}
```'''
    family, plan, problems = parse_plan(raw)
    assert problems == []
    assert family == "search_and_dispatch"
    assert len(plan) == 2
    assert plan[1].args["target"] == "victim"


def test_no_json_is_reported_as_malformed():
    family, plan, problems = parse_plan("Step 1 - Iris: take off")
    assert family is None
    assert plan == []
    assert problems  # the gate must see a problem, not a clean empty plan


def test_empty_steps_is_reported_as_malformed():
    family, plan, problems = parse_plan(
        '{"workflow_family": "search_only", "steps": []}')
    assert plan == []
    assert problems


def test_step_missing_required_keys_is_reported():
    raw = '{"workflow_family": "search_only", "steps": [{"robot": "iris"}]}'
    family, plan, problems = parse_plan(raw)
    assert len(plan) == 1              # step still recorded for the trace
    assert any("skill" in p for p in problems)


def test_non_dict_args_reported_and_coerced():
    raw = ('{"workflow_family": "dispatch_only", "steps": '
           '[{"robot": "tb3", "skill": "navigate_to", "args": "victim"}]}')
    family, plan, problems = parse_plan(raw)
    assert problems                    # must surface, never crash downstream
    assert plan[0].args == {}


def test_non_string_robot_or_skill_reported_and_coerced():
    raw = ('{"workflow_family": "search_only", "steps": '
           '[{"robot": "iris", "skill": ["takeoff"], "args": {}}]}')
    family, plan, problems = parse_plan(raw)
    assert problems
    assert plan[0].skill == ""         # hashable/checkable downstream


def test_non_string_family_reported_and_dropped():
    raw = ('{"workflow_family": {"name": "abort"}, "steps": '
           '[{"robot": "iris", "skill": "land", "args": {}}]}')
    family, plan, problems = parse_plan(raw)
    assert family is None              # never an unhashable value
    assert problems


def test_trailing_prose_with_braces_does_not_break_a_valid_plan():
    raw = ('{"workflow_family": "abort", "steps": '
           '[{"robot": "iris", "skill": "land", "args": {}}]}\n'
           "Note: I left the optional args object empty {} on purpose.")
    family, plan, problems = parse_plan(raw)
    assert problems == []
    assert family == "abort"
    assert len(plan) == 1
