from crew_system.trace import PlanStep
from crew_system.contract_spec import (
    CONTRACT_REGISTRY, KNOWN_FAMILIES, GROUNDING_CODES, CONTRACT_CODES,
    STATE_CODES, OrderingRule, StepPattern, WorkflowContract,
    render_contracts_text,
)


def test_registry_covers_the_four_families():
    assert KNOWN_FAMILIES == {"handover", "carry", "navigation_only", "manipulation_only"}
    assert set(CONTRACT_REGISTRY) == KNOWN_FAMILIES


def test_code_sets_are_disjoint():
    assert not (GROUNDING_CODES & CONTRACT_CODES)
    assert not (CONTRACT_CODES & STATE_CODES)
    assert not (GROUNDING_CODES & STATE_CODES)


def test_generic_checker_flags_disallowed_robot():
    c = CONTRACT_REGISTRY["handover"]
    plan = [PlanStep("g1", "hand_over", {}),
            PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    v = c.violations(plan)
    assert [x.code for x in v] == ["bad_assignment"]
    assert v[0].step_index == 1


def test_generic_checker_flags_order_violation():
    c = CONTRACT_REGISTRY["carry"]
    plan = [PlanStep("go2", "navigate_to_location", {"location": "room_b"}),
            PlanStep("g1", "grab_from_table", {}),
            PlanStep("g1", "place_on_table", {})]
    v = c.violations(plan)
    assert [x.code for x in v] == ["order_violation"]
    assert v[0].step_index == 0


def test_valid_carry_passes_generic_checker():
    c = CONTRACT_REGISTRY["carry"]
    plan = [PlanStep("g1", "grab_from_table", {}),
            PlanStep("g1", "place_on_table", {}),
            PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    assert c.violations(plan) == []


def test_new_family_needs_only_a_spec():
    # The template claim: a NEW workflow family is one declarative spec --
    # the generic checker and the prompt renderer both honor it unchanged.
    patrol = WorkflowContract(
        family="patrol",
        allowed_robots=frozenset({"go2"}),
        guidance="Go2 visits a sequence of named locations",
        ordering=(OrderingRule(
            before=StepPattern("go2", frozenset({"navigate_to_location"})),
            after=StepPattern("go2", frozenset({"stop"})),
            detail="go2 stops before it ever navigated",
        ),),
    )
    bad = [PlanStep("g1", "wave", {}),
           PlanStep("go2", "stop", {}),
           PlanStep("go2", "navigate_to_location", {"location": "room_b"})]
    codes = [v.code for v in patrol.violations(bad)]
    assert "bad_assignment" in codes      # g1 not allowed in patrol
    assert "order_violation" in codes     # stop precedes any navigate
    rendered = patrol.render()
    assert "patrol" in rendered
    assert "stop" in rendered and "navigate_to_location" in rendered
    assert "g1" in rendered.lower()       # disallowed robot surfaced to planner


def test_renderer_surfaces_every_machine_rule():
    # Prose shown to the planner is DERIVED from the same spec the checker
    # enforces -- and must mention each machine rule.
    text = render_contracts_text()
    assert text.startswith("Workflow contracts")
    for family, c in CONTRACT_REGISTRY.items():
        line = c.render()
        assert line in text
        assert family in line
        for robot in {"g1", "go2"} - c.allowed_robots:
            assert robot in line.lower()
        for rule in c.ordering:
            for skill in rule.before.skills | rule.after.skills:
                assert skill in line
