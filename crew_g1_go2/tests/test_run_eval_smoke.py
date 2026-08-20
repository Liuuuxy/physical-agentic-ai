from eval.run_eval import run, to_latex


def fake_router(request, baseline, feedback=None):
    # always returns a valid navigation plan
    raw = ('{"workflow_family":"navigation_only",'
           '"steps":[{"robot":"go2","skill":"navigate_to_location","args":{"location":"room_b"}}]}')
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
