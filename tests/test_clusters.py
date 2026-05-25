"""Unit tests for src.clusters.find_clusters.

Tiny hand-built fixtures with no data dependency. Each test asserts the
exact expected output of the chain-rule grouping logic at known gap
boundaries — the core invariant the locked pipeline relies on when
building per-session cluster pools.

Run:
    .venv/bin/python -m tests.test_clusters
"""

import sys

from src.clusters import Cluster, find_clusters


def _check(label, result, expected_clusters):
    """expected_clusters: list of tuples (low, high, levels_tuple)."""
    assert len(result) == len(expected_clusters), (
        f"{label}: expected {len(expected_clusters)} cluster(s), got {len(result)} → {result}"
    )
    for i, (c, (lo, hi, levels)) in enumerate(zip(result, expected_clusters)):
        assert isinstance(c, Cluster), f"{label}[{i}]: not a Cluster: {c}"
        assert c.low == lo, f"{label}[{i}].low: expected {lo}, got {c.low}"
        assert c.high == hi, f"{label}[{i}].high: expected {hi}, got {c.high}"
        assert c.levels == levels, f"{label}[{i}].levels: expected {levels}, got {c.levels}"
        assert c.size == len(levels), f"{label}[{i}].size: expected {len(levels)}, got {c.size}"
    print(f"  OK  {label}")


def test_empty_input():
    r = find_clusters([])
    assert r == [], f"empty input should return [], got {r}"
    print("  OK  empty input → []")


def test_single_chain_within_gap():
    # All adjacent gaps == 1.0 < max_gap=3.0 → one cluster of 4.
    r = find_clusters([10.0, 11.0, 12.0, 13.0], max_gap=3.0, min_size=3)
    _check("single chain of 4 within gap", r, [(10.0, 13.0, (10.0, 11.0, 12.0, 13.0))])


def test_chain_breaks_at_gap_boundary():
    # 100 → 102 (gap 2 OK), 102 → 105 (gap 3, exactly == max_gap, still OK),
    # 105 → 109 (gap 4 > max_gap → break). First chain qualifies (3 levels),
    # remainder is a singleton and is dropped by min_size.
    r = find_clusters([100.0, 102.0, 105.0, 109.0], max_gap=3.0, min_size=3)
    _check("chain breaks past gap, singleton dropped", r, [(100.0, 105.0, (100.0, 102.0, 105.0))])


def test_two_clusters_separated_by_wide_gap():
    # First chain [10, 11, 12] (3 levels), then gap 88 > 3 → break,
    # then second chain [100, 101, 102] (3 levels). Both qualify min_size=3.
    r = find_clusters([10.0, 11.0, 12.0, 100.0, 101.0, 102.0], max_gap=3.0, min_size=3)
    _check(
        "two clusters split by wide gap",
        r,
        [
            (10.0, 12.0, (10.0, 11.0, 12.0)),
            (100.0, 102.0, (100.0, 101.0, 102.0)),
        ],
    )


def test_min_size_drops_short_chain():
    # Two levels within gap, but min_size=3 demands at least 3.
    r = find_clusters([10.0, 11.0], max_gap=3.0, min_size=3)
    assert r == [], f"min_size should drop chain of 2, got {r}"
    print("  OK  chain shorter than min_size → []")


def test_unsorted_input_is_sorted_internally():
    # Caller passes reverse-sorted; find_clusters sorts before chaining.
    r = find_clusters([12.0, 10.0, 11.0], max_gap=3.0, min_size=3)
    _check("unsorted input sorted internally", r, [(10.0, 12.0, (10.0, 11.0, 12.0))])


def test_boundary_gap_equals_max_gap_inclusive():
    # 100 → 103 → 106: every gap is exactly max_gap=3.0. The rule is "<="
    # so this counts as one chain of 3.
    r = find_clusters([100.0, 103.0, 106.0], max_gap=3.0, min_size=3)
    _check("gap == max_gap counts (inclusive)", r, [(100.0, 106.0, (100.0, 103.0, 106.0))])


def test_min_size_two_allows_pairs():
    # With min_size=2 we keep adjacent pairs that survived the gap rule.
    r = find_clusters([10.0, 11.0, 100.0, 101.0], max_gap=3.0, min_size=2)
    _check(
        "min_size=2 keeps pair clusters",
        r,
        [
            (10.0, 11.0, (10.0, 11.0)),
            (100.0, 101.0, (100.0, 101.0)),
        ],
    )


def test_duplicate_levels_preserved():
    # find_clusters does not dedupe — duplicates appear in cluster.levels.
    r = find_clusters([10.0, 10.0, 11.0], max_gap=3.0, min_size=3)
    _check("duplicates preserved (no dedupe)", r, [(10.0, 11.0, (10.0, 10.0, 11.0))])


def main():
    print("Running tests.test_clusters ...\n")
    test_empty_input()
    test_single_chain_within_gap()
    test_chain_breaks_at_gap_boundary()
    test_two_clusters_separated_by_wide_gap()
    test_min_size_drops_short_chain()
    test_unsorted_input_is_sorted_internally()
    test_boundary_gap_equals_max_gap_inclusive()
    test_min_size_two_allows_pairs()
    test_duplicate_levels_preserved()
    print("\nPASS — all find_clusters tests green")


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except AssertionError as e:
        print(f"\nFAIL — {e}", file=sys.stderr)
        sys.exit(1)
