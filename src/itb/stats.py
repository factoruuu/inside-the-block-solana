"""Small, dependency-free statistics used by the analyzer.

Implemented by hand so the analysis is reproducible in a minimal container
and every number in the report can be traced to code in this repo.
"""

from __future__ import annotations

import math
import random


def pairwise_concordance(xs: list[float], ys: list[float]) -> dict:
    """For all pairs i<j: does the order of x agree with the order of y?

    Used with (fee, -landing_index) or (send_seq, -landing_index): a pair is
    concordant when the transaction that should land earlier under the
    hypothesis actually did. Ties in either variable are excluded from the
    denominator and reported. Returns counts plus the concordance fraction
    (0.5 = no relationship).
    """
    concordant = discordant = tied = 0
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            dx = (xs[i] > xs[j]) - (xs[i] < xs[j])
            dy = (ys[i] > ys[j]) - (ys[i] < ys[j])
            if dx == 0 or dy == 0:
                tied += 1
            elif dx == dy:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return {
        "concordant": concordant,
        "discordant": discordant,
        "tied": tied,
        "fraction": (concordant / total) if total else None,
    }


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # average rank, 1-based
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation; None when undefined (n<2 or no variance)."""
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    if den == 0:
        return None
    return num / den


def bootstrap_ci_fraction(
    pairs: list[tuple[float, float]], iterations: int = 1000, seed: int = 1234
) -> tuple[float, float] | None:
    """Bootstrap 95% CI for pairwise concordance fraction over (x, y) pairs.

    Resamples pairs with replacement. Pairs are (hypothesis value, outcome
    value) as passed to pairwise_concordance.
    """
    if len(pairs) < 4:
        return None
    rng = random.Random(seed)
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    fracs: list[float] = []
    n = len(pairs)
    for _ in range(iterations):
        idx = [rng.randrange(n) for _ in range(n)]
        res = pairwise_concordance([xs[i] for i in idx], [ys[i] for i in idx])
        if res["fraction"] is not None:
            fracs.append(res["fraction"])
    if not fracs:
        return None
    fracs.sort()
    lo = fracs[int(0.025 * len(fracs))]
    hi = fracs[min(len(fracs) - 1, int(0.975 * len(fracs)))]
    return (lo, hi)


def mean(values: list[float]) -> float | None:
    return (sum(values) / len(values)) if values else None
