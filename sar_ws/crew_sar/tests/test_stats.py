from eval.stats import wilson_ci, fisher_exact


def test_wilson_zero_n():
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_all_success_upper_is_100():
    lo, hi = wilson_ci(20, 20)
    assert hi == 100.0
    assert 80.0 < lo < 100.0       # not absurdly wide for n=20


def test_wilson_midpoint_brackets_50():
    lo, hi = wilson_ci(10, 20)
    assert lo < 50.0 < hi


def test_fisher_strong_effect_is_significant():
    # rao 0/20 false-dispatch vs llm-only 18/20 -> tiny p
    p = fisher_exact(0, 20, 18, 2)
    assert p < 0.001


def test_fisher_no_effect_is_nonsignificant():
    p = fisher_exact(10, 10, 10, 10)
    assert p > 0.9


def test_fisher_symmetric_in_rows():
    assert abs(fisher_exact(2, 8, 7, 3) - fisher_exact(7, 3, 2, 8)) < 1e-12
