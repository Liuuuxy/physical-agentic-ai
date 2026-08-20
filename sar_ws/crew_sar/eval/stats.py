"""Small, dependency-free stats for the baseline study: Wilson score CI for a
proportion and a two-sided Fisher's exact test for a 2x2 table."""
import math


def wilson_ci(k, n, z=1.96):
    """95% Wilson score interval for k successes out of n, returned as
    (low_pct, high_pct) in [0, 100]."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half) * 100, min(1.0, center + half) * 100)


def fisher_exact(a, b, c, d):
    """Two-sided p-value for the 2x2 table [[a, b], [c, d]] via summing the
    probabilities of all tables (with the same margins) no more likely than the
    observed one."""
    n = a + b + c + d
    if n == 0:
        return 1.0
    row1 = a + b
    col1 = a + c

    def prob(x):
        # P(top-left = x) under the hypergeometric with fixed margins
        return (math.comb(col1, x) * math.comb(n - col1, row1 - x)) / math.comb(n, row1)

    lo = max(0, row1 - (n - col1))
    hi = min(row1, col1)
    p_obs = prob(a)
    tol = p_obs * (1 + 1e-9)
    p = sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= tol)
    return min(1.0, p)
