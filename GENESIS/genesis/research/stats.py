"""Small, dependency-free statistics for paired comparisons on the same dataset items."""

from __future__ import annotations

import math
import random
from typing import Sequence


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar test on discordant pairs (A right/B wrong vs A wrong/B right)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def bootstrap_diff_ci(pairs: Sequence[tuple[int, int]], seed: int = 0, rounds: int = 2000,
                      alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap CI of mean(b - a) over paired 0/1 outcomes. Seeded: reproducible."""
    if not pairs:
        return (0.0, 0.0)
    rng, n = random.Random(seed), len(pairs)
    diffs = sorted(sum(pairs[j][1] - pairs[j][0] for j in (rng.randrange(n) for _ in range(n))) / n
                   for _ in range(rounds))
    lo = diffs[int(alpha / 2 * rounds)]
    hi = diffs[min(rounds - 1, int((1 - alpha / 2) * rounds))]
    return (round(lo, 4), round(hi, 4))


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]
