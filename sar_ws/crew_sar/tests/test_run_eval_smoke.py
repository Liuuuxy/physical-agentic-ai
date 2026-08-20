from eval.run_eval import run, to_latex


def fake_router(request, baseline, feedback=None):
    # always returns a valid search-and-dispatch plan with the victim binding
    raw = ('{"workflow_family":"search_and_dispatch","steps":['
           '{"robot":"iris","skill":"takeoff","args":{"altitude":5.0}},'
           '{"robot":"iris","skill":"search_target","args":'
           '{"x_min":-5.5,"x_max":5.5,"y_min":-5.5,"y_max":5.5}},'
           '{"robot":"tb3","skill":"navigate_to","args":{"target":"victim"}}]}')
    return raw, 1


def test_run_returns_metrics_per_baseline():
    res = run(["skill-list", "rao"], router=fake_router, limit=2)
    assert set(res.keys()) == {"skill-list", "rao"}
    assert "workflow_accuracy" in res["rao"]


def test_to_latex_emits_rows():
    res = run(["llm-only", "skill-list", "rao"], router=fake_router, limit=1)
    tex = to_latex(res)
    assert "Workflow-selection accuracy" in tex
    assert "&" in tex


def test_unknown_baseline_name_raises():
    import pytest
    with pytest.raises(ValueError):
        run(["rao_prompt"], router=fake_router, limit=1)


def test_rao_prompt_arm_is_a_first_class_column():
    # rao-prompt (contracts in prompt, no gate) must run and land in the
    # LaTeX ladder between skill-list and rao.
    res = run(["llm-only", "skill-list", "rao-prompt", "rao"],
              router=fake_router, limit=1)
    assert set(res) == {"llm-only", "skill-list", "rao-prompt", "rao"}
    first_row = to_latex(res).splitlines()[0]
    assert first_row.count("&") == 4    # row label + 4 baseline cells


def test_mock_faults_reach_the_adapters():
    # Under the full scenario set the nan_transmission scenario must produce
    # a no_target_fix somewhere for a non-enforcing arm (dispatched) and a
    # gate block for rao.
    res = run(["skill-list", "rao"], router=fake_router)
    assert res["skill-list"]["false_dispatch"] > 0.0
    assert res["rao"]["false_dispatch"] == 0.0
    assert res["rao"]["safety_recall"] > 0.0
