from eval.scenarios import load_scenarios


def test_scenarios_load_and_validate():
    scen = load_scenarios()
    assert len(scen) >= 8
    fams = {"handover", "carry", "navigation_only", "manipulation_only"}
    for s in scen:
        assert s.expected_family in fams
        assert s.fault in {"none", "invalid_location", "go2_unavailable", "g1_unavailable"}
        if s.fault != "none":
            assert isinstance(s.should_block, bool)


def test_has_both_nominal_and_fault_cases():
    scen = load_scenarios()
    assert any(s.fault == "none" for s in scen)
    assert any(s.fault != "none" for s in scen)
