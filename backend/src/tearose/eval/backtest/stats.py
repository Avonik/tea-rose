"""Small, dependency-free statistics for the back-test (stdlib only; no numpy/scipy).

- average_ranks: 1-based ranks, ties get the mean of the positions they occupy.
- spearman: Pearson correlation of the average ranks (the tie-correct Spearman rho).
- auc: Mann-Whitney AUC = P(score_pos > score_neg) + 0.5 * P(score_pos == score_neg).
- bootstrap_ci: percentile bootstrap over cases (pairs resampled with replacement), fixed seed.

All functions return None when the statistic is undefined (fewer than 3 points, zero variance
in either vector, or a class missing for AUC) instead of raising.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence

BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 20260101  # fixed so a report is reproducible byte for byte


def average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # positions i..j (0-based) -> mean 1-based rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    n = len(x)
    if n != len(y) or n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 1e-15 or syy <= 1e-15:
        return None
    return sxy / math.sqrt(sxx * syy)


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rho with average ranks for ties (= Pearson on the ranks)."""
    if len(x) != len(y) or len(x) < 3:
        return None
    return pearson(average_ranks(x), average_ranks(y))


def auc(scores: Sequence[float], positive: Sequence[bool]) -> float | None:
    """Mann-Whitney AUC; ties between a positive and a negative count one half."""
    pos = [s for s, p in zip(scores, positive, strict=True) if p]
    neg = [s for s, p in zip(scores, positive, strict=True) if not p]
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for q in neg:
            wins += 1.0 if p > q else 0.5 if p == q else 0.0
    return wins / (len(pos) * len(neg))


def percentile(sorted_xs: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile (q in [0, 1]) of an ascending list."""
    if not sorted_xs:
        raise ValueError("empty")
    pos = q * (len(sorted_xs) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def bootstrap_ci[T](
    data: Sequence[T],
    stat: Callable[[list[T]], float | None],
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> tuple[float | None, float | None, int]:
    """Percentile bootstrap CI over cases. Returns (low, high, n_valid_resamples).

    Resamples where the statistic is undefined (e.g. all labels equal) are skipped and
    counted out; with fewer than 100 valid resamples the CI is reported as undefined.
    """
    if len(data) < 3:
        return None, None, 0
    rng = random.Random(seed)
    n = len(data)
    vals: list[float] = []
    for _ in range(iterations):
        sample = [data[rng.randrange(n)] for _ in range(n)]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    if len(vals) < 100:
        return None, None, len(vals)
    vals.sort()
    return percentile(vals, alpha / 2), percentile(vals, 1 - alpha / 2), len(vals)
