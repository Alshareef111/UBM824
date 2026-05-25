"""Cluster detection.

Pure function: given a list of price levels, return clusters where every
adjacent pair (after sorting) is within `max_gap` points and the cluster
contains at least `min_size` levels. The algorithm is a single greedy walk
of the sorted levels — chains break only when a sorted gap exceeds max_gap.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Cluster:
    low: float
    high: float
    levels: tuple
    size: int


def find_clusters(
    levels: list[float],
    max_gap: float = 3.0,
    min_size: int = 3,
) -> list[Cluster]:
    """Group sorted levels into clusters by the chain rule.

    Sorts ``levels`` ascending and walks the sorted sequence, extending the
    current chain when the next level is within ``max_gap`` of the previous
    one. A chain becomes a Cluster only if it has at least ``min_size``
    levels; shorter chains are dropped. The gap test is inclusive
    (``next - prev <= max_gap``).

    Args:
        levels:   Unsorted iterable of price levels. Duplicates are kept.
        max_gap:  Maximum allowed gap between adjacent sorted levels.
        min_size: Minimum levels required to emit a Cluster.

    Returns:
        List of Cluster, in ascending order by low.
    """
    if not levels:
        return []

    sorted_levels = sorted(levels)
    clusters: list[Cluster] = []
    current: list[float] = [sorted_levels[0]]

    for lvl in sorted_levels[1:]:
        if lvl - current[-1] <= max_gap:
            current.append(lvl)
        else:
            if len(current) >= min_size:
                clusters.append(_build(current))
            current = [lvl]

    if len(current) >= min_size:
        clusters.append(_build(current))

    return clusters


def _build(sorted_chain: list[float]) -> Cluster:
    return Cluster(
        low=sorted_chain[0],
        high=sorted_chain[-1],
        levels=tuple(sorted_chain),
        size=len(sorted_chain),
    )


if __name__ == "__main__":

    def show(label, result):
        print(f"{label}")
        if not result:
            print("  (no clusters)")
        for c in result:
            print(f"  size={c.size}  low={c.low}  high={c.high}  levels={c.levels}")
        print()

    # 1. Tight cluster of exactly 3
    r = find_clusters([100.0, 101.0, 102.0])
    show("Test 1: tight 3 levels [100, 101, 102]", r)
    assert len(r) == 1 and r[0].size == 3 and r[0].low == 100.0 and r[0].high == 102.0

    # 2. Chain of 5 levels at 2.5pt spacing, total span 10pt
    r = find_clusters([100.0, 102.5, 105.0, 107.5, 110.0])
    show("Test 2: chain of 5 at 2.5pt spacing (span 10pt)", r)
    assert len(r) == 1 and r[0].size == 5 and (r[0].high - r[0].low) == 10.0

    # 3. No cluster (all gaps > 3)
    r = find_clusters([100.0, 110.0, 120.0])
    show("Test 3: gaps too wide [100, 110, 120]", r)
    assert r == []

    # 4. Multiple separate clusters in one input
    r = find_clusters([100.0, 101.0, 102.0, 200.0, 201.0, 202.5, 300.0, 305.0])
    show("Test 4: two clusters + 2 isolated levels", r)
    assert len(r) == 2 and r[0].size == 3 and r[1].size == 3

    # 5. Boundary: exactly 3.0 apart counts (<=, not <)
    r = find_clusters([100.0, 103.0, 106.0])
    show("Test 5: boundary spacing of exactly 3.0", r)
    assert len(r) == 1 and r[0].size == 3

    print("All assertions passed.")
