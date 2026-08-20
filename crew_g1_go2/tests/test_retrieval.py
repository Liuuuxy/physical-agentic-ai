from crew_system.retrieval import retrieval_context


def test_llm_only_gets_no_registry():
    assert retrieval_context("llm-only") == ""


def test_skill_list_lists_real_skills_and_locations_but_no_contracts():
    ctx = retrieval_context("skill-list")
    assert "grab_from_table" in ctx       # real G1 skill
    assert "room_b" in ctx                # real Go2 location
    assert "Workflow contracts" not in ctx


def test_rao_includes_registry_and_contracts():
    ctx = retrieval_context("rao")
    assert "grab_from_table" in ctx
    assert "Workflow contracts" in ctx
    assert "carry:" in ctx


# build_instructions is pure (imports retrieval lazily; no crewai at import).
from crew_system.routers import build_instructions  # noqa: E402


def test_build_instructions_injects_registry_and_contracts_for_rao():
    instr = build_instructions("rao")
    assert "grab_from_table" in instr     # retrieval injected
    assert "Workflow contracts" in instr
    assert "JSON" in instr                # schema present


def test_build_instructions_llm_only_has_schema_but_no_registry():
    instr = build_instructions("llm-only")
    assert "grab_from_table" not in instr
    assert "JSON" in instr


def test_build_instructions_appends_feedback():
    instr = build_instructions("rao", feedback="violations: unknown_location")
    assert "REJECTED" in instr
    assert "unknown_location" in instr


def test_contracts_text_is_derived_from_registry():
    # The prose the planner reads is GENERATED from the same specs the gate
    # enforces -- no second hand-written copy to drift.
    from crew_system.retrieval import CONTRACTS_TEXT
    from crew_system.contract_spec import render_contracts_text
    assert CONTRACTS_TEXT == render_contracts_text()


def test_rao_prompt_arm_gets_registry_and_contracts():
    # rao-prompt: contracts in the prompt but NO dispatch gate; isolates
    # prompt knowledge from enforcement in the ablation ladder.
    ctx = retrieval_context("rao-prompt")
    assert "grab_from_table" in ctx
    assert "Workflow contracts" in ctx


def test_llm_only_sees_no_real_skill_names_anywhere():
    # The bottom rung of the ablation must not be contaminated: no real g1
    # OR go2 skill name may leak through the schema or format example.
    instr = build_instructions("llm-only")
    assert "grab_from_table" not in instr
    assert "navigate_to_location" not in instr


def test_registry_advertises_only_planner_facing_go2_skills():
    # status/stop/navigate_to_coord are dispatchable but not advertised:
    # the planner is only told about skills the contracts actually use.
    ctx = retrieval_context("skill-list")
    assert "navigate_to_location" in ctx
    assert "status" not in ctx
    assert "stop" not in ctx
    assert "navigate_to_coord" not in ctx


def test_unknown_baseline_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        retrieval_context("rao_prompt")   # typo must not silently become an arm


def test_plan_schema_lists_registry_families():
    from crew_system.routers import PLAN_SCHEMA, router_config
    from crew_system.contract_spec import KNOWN_FAMILIES
    for fam in KNOWN_FAMILIES:
        assert fam in PLAN_SCHEMA
    assert router_config("rao-prompt")[0] is True   # retrieval tools enabled
