"""Unit tests for src.signals (build_cluster_pool, build_candidates).

Tiny hand-built fixtures with no data dependency. Each test asserts exact
expected output: row counts, cluster bounds, gate decisions.

Run:
    .venv/bin/python -m tests.test_signals
"""

import datetime as dt
import sys

import pandas as pd

from src.signals import build_candidates, build_cluster_pool

# ───────────────────────── build_cluster_pool ─────────────────────────────


def _or_levels(rows):
    """rows: list of (session_date, or_high, or_low). Returns DataFrame
    indexed by session_date, sorted (build_cluster_pool walks positionally)."""
    df = pd.DataFrame(rows, columns=["session_date", "or_high", "or_low"])
    return df.set_index("session_date").sort_index()


def test_build_cluster_pool_windowing_and_chains():
    # 5 sessions, lookback=2, gap=2, min_size=2.
    # i=0,1 skipped (i < lookback).
    # i=2 (s3): trailing window = s1, s2 → ORs [100, 99, 98, 97]
    #   sorted=[97,98,99,100], gaps≤2 → one cluster of 4.
    # i=3 (s4): trailing window = s2, s3 → ORs [99, 200, 97, 199]
    #   sorted=[97,99,199,200] → cluster [97,99], gap 100 break,
    #   cluster [199,200] → two clusters.
    # i=4 (s5): trailing window = s3, s4 → ORs [200, 201, 199, 198]
    #   sorted=[198,199,200,201] → one cluster of 4.
    or_levels = _or_levels(
        [
            (dt.date(2024, 1, 2), 100.0, 98.0),
            (dt.date(2024, 1, 3), 99.0, 97.0),
            (dt.date(2024, 1, 4), 200.0, 199.0),
            (dt.date(2024, 1, 5), 201.0, 198.0),
            (dt.date(2024, 1, 8), 300.0, 299.0),
        ]
    )
    pool = build_cluster_pool(or_levels, lookback=2, gap=2.0, min_size=2)

    assert len(pool) == 4, f"expected 4 rows (1 + 2 + 1), got {len(pool)}\n{pool}"

    # s3 (i=2): one cluster spanning 97..100, n=4, center=98.5, median=98.5
    s3 = pool[pool["session_date"] == dt.date(2024, 1, 4)].reset_index(drop=True)
    assert len(s3) == 1, f"s3 should have 1 cluster, got {len(s3)}"
    assert s3.loc[0, "cluster_id"] == 0
    assert s3.loc[0, "low"] == 97.0 and s3.loc[0, "high"] == 100.0
    assert s3.loc[0, "n_levels"] == 4
    assert s3.loc[0, "center"] == 98.5
    assert s3.loc[0, "median"] == 98.5

    # s4 (i=3): two clusters, [97,99] and [199,200]
    s4 = pool[pool["session_date"] == dt.date(2024, 1, 5)].reset_index(drop=True)
    assert len(s4) == 2, f"s4 should have 2 clusters, got {len(s4)}"
    # cluster_id is the within-session ordinal in sorted level order
    assert list(s4["cluster_id"]) == [0, 1]
    assert s4.loc[0, "low"] == 97.0 and s4.loc[0, "high"] == 99.0
    assert s4.loc[0, "n_levels"] == 2 and s4.loc[0, "center"] == 98.0
    assert s4.loc[1, "low"] == 199.0 and s4.loc[1, "high"] == 200.0
    assert s4.loc[1, "n_levels"] == 2 and s4.loc[1, "center"] == 199.5

    # s5 (i=4): one cluster 198..201, n=4, center=199.5
    s5 = pool[pool["session_date"] == dt.date(2024, 1, 8)].reset_index(drop=True)
    assert len(s5) == 1
    assert s5.loc[0, "low"] == 198.0 and s5.loc[0, "high"] == 201.0
    assert s5.loc[0, "n_levels"] == 4 and s5.loc[0, "center"] == 199.5

    # No rows for sessions inside the warm-up window (i < lookback).
    assert dt.date(2024, 1, 2) not in pool["session_date"].values
    assert dt.date(2024, 1, 3) not in pool["session_date"].values
    print("  OK  windowing + chain output (lookback=2, gap=2, min=2)")


def test_build_cluster_pool_gap_param_breaks_tight_chain():
    # Same 5 sessions, but gap=0.5 → every adjacent pair is >0.5 apart, so
    # NO chain of length >=2 survives. Pool is empty.
    or_levels = _or_levels(
        [
            (dt.date(2024, 1, 2), 100.0, 98.0),
            (dt.date(2024, 1, 3), 99.0, 97.0),
            (dt.date(2024, 1, 4), 200.0, 199.0),
            (dt.date(2024, 1, 5), 201.0, 198.0),
            (dt.date(2024, 1, 8), 300.0, 299.0),
        ]
    )
    pool = build_cluster_pool(or_levels, lookback=2, gap=0.5, min_size=2)
    assert len(pool) == 0, f"gap=0.5 should produce no clusters, got {len(pool)}"
    print("  OK  gap parameter (0.5) breaks all chains")


def test_build_cluster_pool_min_size_filter():
    # Same 5 sessions; lookback=2, gap=2, but min_size=5 → no cluster
    # has 5 levels (largest is 4) → empty pool.
    or_levels = _or_levels(
        [
            (dt.date(2024, 1, 2), 100.0, 98.0),
            (dt.date(2024, 1, 3), 99.0, 97.0),
            (dt.date(2024, 1, 4), 200.0, 199.0),
            (dt.date(2024, 1, 5), 201.0, 198.0),
            (dt.date(2024, 1, 8), 300.0, 299.0),
        ]
    )
    pool = build_cluster_pool(or_levels, lookback=2, gap=2.0, min_size=5)
    assert len(pool) == 0, f"min_size=5 should produce no clusters, got {len(pool)}"
    print("  OK  min_size filter (5) drops all 4-level clusters")


def test_build_cluster_pool_warmup_skips_when_too_few_sessions():
    # lookback=10, only 3 sessions → every i < lookback → empty pool.
    or_levels = _or_levels(
        [
            (dt.date(2024, 1, 2), 100.0, 98.0),
            (dt.date(2024, 1, 3), 99.0, 97.0),
            (dt.date(2024, 1, 4), 101.0, 99.0),
        ]
    )
    pool = build_cluster_pool(or_levels, lookback=10, gap=2.0, min_size=2)
    assert len(pool) == 0
    print("  OK  warm-up skip (lookback > available sessions) → empty")


# ───────────────────────── build_candidates ────────────────────────────────


def _candidate_fixture():
    """Two-session OR + a 5-row cluster pool that exercises every gate."""
    or_levels = _or_levels(
        [
            (dt.date(2024, 1, 2), 110.0, 100.0),  # OR [100, 110]
            (dt.date(2024, 1, 3), 210.0, 200.0),  # OR [200, 210]
        ]
    )
    pool = pd.DataFrame(
        [
            # session_date, cluster_id, center, median, n_levels, low, high
            # s1 #0: inside OR, ±0 from close (passes every non-empty gate)
            (dt.date(2024, 1, 2), 0, 105.0, 105.0, 3, 104.0, 106.0),
            # s1 #1: outside OR (center=120 > or_high=110), within_100 (diff=15)
            (dt.date(2024, 1, 2), 1, 120.0, 120.0, 3, 119.0, 121.0),
            # s1 #2: outside OR, within_200 only (diff=110 > 100, ≤ 200)
            (dt.date(2024, 1, 2), 2, 215.0, 215.0, 3, 214.0, 216.0),
            # s2 #0: inside OR but or_close is NaN → fails proximity gates
            (dt.date(2024, 1, 3), 0, 205.0, 205.0, 3, 204.0, 206.0),
            # s2 #1: outside OR, also fails proximity gates (NaN close)
            (dt.date(2024, 1, 3), 1, 400.0, 400.0, 3, 399.0, 401.0),
        ],
        columns=["session_date", "cluster_id", "center", "median", "n_levels", "low", "high"],
    )
    or_close = pd.Series(
        {dt.date(2024, 1, 2): 105.0, dt.date(2024, 1, 3): float("nan")},
        name="or_close",
    )
    or_close.index.name = "session_date"
    return or_levels, pool, or_close


def _key_set(cands):
    return set(zip(cands["session_date"], cands["cluster_id"]))


def test_build_candidates_inside_OR():
    or_levels, pool, _ = _candidate_fixture()
    cands = build_candidates(or_levels, pool, gate="inside_OR")
    # s1#0 (center=105 in [100,110]) ✓; s2#0 (center=205 in [200,210]) ✓.
    expected = {(dt.date(2024, 1, 2), 0), (dt.date(2024, 1, 3), 0)}
    assert _key_set(cands) == expected, f"inside_OR: expected {expected}, got {_key_set(cands)}"
    # Check or_low/or_high columns are merged correctly.
    row = cands[cands["session_date"] == dt.date(2024, 1, 2)].iloc[0]
    assert row["or_low"] == 100.0 and row["or_high"] == 110.0
    print("  OK  gate=inside_OR (2 candidates)")


def test_build_candidates_no_gate_passes_everything():
    or_levels, pool, _ = _candidate_fixture()
    cands = build_candidates(or_levels, pool, gate="no_gate")
    assert len(cands) == 5, f"no_gate should pass all 5, got {len(cands)}"
    print("  OK  gate=no_gate (5 candidates, all pass)")


def test_build_candidates_within_100():
    or_levels, pool, or_close = _candidate_fixture()
    cands = build_candidates(or_levels, pool, gate="within_100", or_close=or_close)
    # s1#0 (|105-105|=0) ✓, s1#1 (|120-105|=15) ✓, s1#2 (|215-105|=110) ✗.
    # s2 sessions ✗ because or_close is NaN.
    expected = {(dt.date(2024, 1, 2), 0), (dt.date(2024, 1, 2), 1)}
    assert _key_set(cands) == expected, f"within_100: expected {expected}, got {_key_set(cands)}"
    print("  OK  gate=within_100 (2 candidates; NaN close drops s2)")


def test_build_candidates_within_200():
    or_levels, pool, or_close = _candidate_fixture()
    cands = build_candidates(or_levels, pool, gate="within_200", or_close=or_close)
    # s1#0 ✓, s1#1 ✓, s1#2 (110 ≤ 200) ✓.  s2 ✗ (NaN close).
    expected = {(dt.date(2024, 1, 2), 0), (dt.date(2024, 1, 2), 1), (dt.date(2024, 1, 2), 2)}
    assert _key_set(cands) == expected, f"within_200: expected {expected}, got {_key_set(cands)}"
    print("  OK  gate=within_200 (3 candidates; NaN close drops s2)")


def test_build_candidates_within_gates_require_or_close():
    or_levels, pool, _ = _candidate_fixture()
    for gate in ("within_100", "within_200"):
        try:
            build_candidates(or_levels, pool, gate=gate)
        except ValueError:
            pass
        else:
            raise AssertionError(f"gate={gate} without or_close should raise")
    print("  OK  within_* gates raise without or_close")


def test_build_candidates_unknown_gate_raises():
    or_levels, pool, _ = _candidate_fixture()
    try:
        build_candidates(or_levels, pool, gate="bogus_gate")
    except ValueError:
        print("  OK  unknown gate raises ValueError")
    else:
        raise AssertionError("unknown gate should raise ValueError")


def main():
    print("Running tests.test_signals ...\n")
    test_build_cluster_pool_windowing_and_chains()
    test_build_cluster_pool_gap_param_breaks_tight_chain()
    test_build_cluster_pool_min_size_filter()
    test_build_cluster_pool_warmup_skips_when_too_few_sessions()

    test_build_candidates_inside_OR()
    test_build_candidates_no_gate_passes_everything()
    test_build_candidates_within_100()
    test_build_candidates_within_200()
    test_build_candidates_within_gates_require_or_close()
    test_build_candidates_unknown_gate_raises()
    print("\nPASS — all signals tests green")


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except AssertionError as e:
        print(f"\nFAIL — {e}", file=sys.stderr)
        sys.exit(1)
