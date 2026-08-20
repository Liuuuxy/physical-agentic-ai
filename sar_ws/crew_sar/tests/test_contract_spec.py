from crew_system.trace import PlanStep
from crew_system.contract_spec import (
    CONTRACT_REGISTRY, KNOWN_FAMILIES, GROUNDING_CODES, CONTRACT_CODES,
    STATE_CODES, OrderingRule, StepPattern, WorkflowContract,
    render_contracts_text,
)


def _sad_plan():
    return [
        PlanStep("iris", "takeoff", {"altitude": 5.0}),
        PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5,
                                           "y_min": -5.5, "y_max": 5.5}),
        PlanStep("tb3", "navigate_to", {"target": "victim"}),
    ]


def test_registry_covers_the_four_families():
    assert KNOWN_FAMILIES == {"search_and_dispatch", "search_only",
                              "dispatch_only", "abort"}
    assert set(CONTRACT_REGISTRY) == KNOWN_FAMILIES


def test_code_sets_are_disjoint():
    assert not (GROUNDING_CODES & CONTRACT_CODES)
    assert not (CONTRACT_CODES & STATE_CODES)
    assert not (GROUNDING_CODES & STATE_CODES)


def test_generic_checker_flags_disallowed_robot():
    c = CONTRACT_REGISTRY["dispatch_only"]
    plan = [PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0}),
            PlanStep("iris", "takeoff", {})]
    v = c.violations(plan)
    assert [x.code for x in v] == ["bad_assignment"]
    assert v[0].step_index == 1


def test_generic_checker_flags_order_violation():
    c = CONTRACT_REGISTRY["search_and_dispatch"]
    plan = [PlanStep("iris", "takeoff", {}),
            PlanStep("tb3", "navigate_to", {"target": "victim"}),
            PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5,
                                               "y_min": -5.5, "y_max": 5.5})]
    v = c.violations(plan)
    assert [x.code for x in v] == ["order_violation"]
    assert v[0].step_index == 1


def test_search_before_takeoff_is_order_violation():
    c = CONTRACT_REGISTRY["search_only"]
    plan = [PlanStep("iris", "search_target", {"x_min": -5.5, "x_max": 5.5,
                                               "y_min": -5.5, "y_max": 5.5}),
            PlanStep("iris", "takeoff", {})]
    assert [x.code for x in c.violations(plan)] == ["order_violation"]


def test_valid_search_and_dispatch_passes_generic_checker():
    c = CONTRACT_REGISTRY["search_and_dispatch"]
    assert c.violations(_sad_plan()) == []


def test_new_family_needs_only_a_spec():
    # The template claim: a NEW workflow family is one declarative spec --
    # the generic checker and the prompt renderer both honor it unchanged.
    relay = WorkflowContract(
        family="relay",
        allowed_robots=frozenset({"tb3"}),
        guidance="TB3 shuttles between two coordinates",
        ordering=(OrderingRule(
            before=StepPattern("tb3", frozenset({"navigate_to"})),
            after=StepPattern("tb3", frozenset({"stop"})),
            detail="tb3 stops before it ever navigated",
        ),),
    )
    bad = [PlanStep("iris", "takeoff", {}),
           PlanStep("tb3", "stop", {}),
           PlanStep("tb3", "navigate_to", {"x": 3.0, "y": -2.0})]
    codes = [v.code for v in relay.violations(bad)]
    assert "bad_assignment" in codes      # iris not allowed in relay
    assert "order_violation" in codes     # stop precedes any navigate
    rendered = relay.render()
    assert "relay" in rendered
    assert "stop" in rendered and "navigate_to" in rendered
    assert "iris" in rendered.lower()     # disallowed robot surfaced to planner


def test_renderer_surfaces_every_machine_rule():
    # Prose shown to the planner is DERIVED from the same spec the checker
    # enforces -- and must mention each machine rule.
    text = render_contracts_text()
    assert text.startswith("Workflow contracts")
    for family, c in CONTRACT_REGISTRY.items():
        line = c.render()
        assert line in text
        assert family in line
        for robot in {"iris", "tb3"} - c.allowed_robots:
            assert robot in line.lower()
        for rule in c.ordering:
            for skill in rule.before.skills | rule.after.skills:
                assert skill in line
