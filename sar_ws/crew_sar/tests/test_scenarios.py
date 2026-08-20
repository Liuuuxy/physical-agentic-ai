from eval.scenarios import load_scenarios

_FAMS = {"search_and_dispatch", "search_only", "dispatch_only", "abort"}
_FAULTS = {"none", "iris_unavailable", "tb3_unavailable", "out_of_bounds",
           "nan_transmission", "missed_detection"}


def test_scenarios_load_and_validate():
    scen = load_scenarios()
    assert len(scen) == 20
    for s in scen:
        assert s.expected_family in _FAMS
        assert s.fault in _FAULTS
        assert isinstance(s.should_block, bool)
        assert s.should_block == (s.fault != "none")
        assert set(s.expected_robots) <= {"iris", "tb3"}


def test_scenario_ids_are_unique():
    scen = load_scenarios()
    ids = [s.id for s in scen]
    assert len(ids) == len(set(ids))


def test_has_both_nominal_and_fault_cases():
    scen = load_scenarios()
    assert sum(1 for s in scen if s.fault == "none") == 12
    assert sum(1 for s in scen if s.fault != "none") == 8


def test_every_family_has_nominal_coverage():
    scen = load_scenarios()
    for fam in _FAMS:
        assert sum(1 for s in scen
                   if s.fault == "none" and s.expected_family == fam) == 3
