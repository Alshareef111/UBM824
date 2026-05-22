"""
src/signals.py — Opening range, cluster detection, candidates, and signals.

Builds on processed bars from data.py. Per-session pipeline:
    1. Compute OR (09:30-09:44 ET) → or_high, or_low
    2. Build cluster pool from trailing 200 sessions' ORs
    3. Filter clusters to candidates within today's OR
    4. Generate breakout entry signals (next step)

Run from project root:
    python -m src.signals or-stats     # OR distribution stats
    python -m src.signals clusters     # Inspect cluster pool
    python -m src.signals candidates   # Inspect per-session candidates
"""

import statistics
import sys

import pandas as pd

from src.data import load_processed_bars

LOOKBACK_SESSIONS = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3


# ─── Opening range ────────────────────────────────────────────────────────

def compute_opening_range(bars, or_start="09:30", or_end="09:44"):
    or_bars = bars.between_time(or_start, or_end, inclusive="both")
    return or_bars.groupby("session_date").agg(
        or_high=("high", "max"),
        or_low=("low", "min"),
    )


def compute_or_close(bars, or_close_time="09:44"):
    """Per-session close at the final bar of the OR window.

    Used as the reference price for proximity gates (within_100, within_200).
    Returned as a Series indexed by session_date.
    """
    or_close_bars = bars.between_time(or_close_time, or_close_time,
                                       inclusive="both")
    return or_close_bars.groupby("session_date")["close"].last()


# ─── Cluster pool ─────────────────────────────────────────────────────────

def _cluster_levels(levels, gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE):
    if not levels:
        return []
    levels = sorted(levels)
    clusters = []
    current = [levels[0]]
    for x in levels[1:]:
        if x - current[-1] <= gap:
            current.append(x)
        else:
            if len(current) >= min_size:
                clusters.append(current)
            current = [x]
    if len(current) >= min_size:
        clusters.append(current)
    return clusters


def build_cluster_pool(or_levels, lookback=LOOKBACK_SESSIONS,
                       gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE):
    """For each session, derive clusters from trailing `lookback` ORs."""
    sessions = or_levels.index.tolist()
    rows = []
    for i, session in enumerate(sessions):
        if i < lookback:
            continue
        window = or_levels.iloc[i - lookback:i]
        levels = window["or_high"].tolist() + window["or_low"].tolist()
        clusters = _cluster_levels(levels, gap=gap, min_size=min_size)
        for j, cluster in enumerate(clusters):
            rows.append({
                "session_date": session,
                "cluster_id": j,
                "center": sum(cluster) / len(cluster),
                "median": statistics.median(cluster),
                "n_levels": len(cluster),
                "low": min(cluster),
                "high": max(cluster),
            })
    return pd.DataFrame(rows)


# ─── Candidates (clusters within today's OR) ──────────────────────────────

CANDIDATE_COLS = ["session_date", "cluster_id", "center", "median", "n_levels",
                  "low", "high", "or_low", "or_high"]


def build_candidates(or_levels, cluster_pool, gate="inside_OR", or_close=None):
    """
    Per-session candidates: clusters that pass the gate.

    Gates:
      inside_OR  — center in [or_low, or_high]  (original behavior)
      within_100 — |center - or_close| <= 100   (proximity to 09:45 price)
      within_200 — |center - or_close| <= 200   (locked-config gate)
      no_gate    — all clusters (sanity / max-density)

    For proximity gates, `or_close` (Series indexed by session_date, from
    compute_or_close) is required. Sessions missing or_close drop out.

    Returns DataFrame with columns: session_date, cluster_id, center, median,
    n_levels, low, high, or_low, or_high.
    """
    base = or_levels.reset_index()[["session_date", "or_low", "or_high"]]
    needs_close = gate in ("within_100", "within_200")
    if needs_close:
        if or_close is None:
            raise ValueError(f"gate={gate!r} requires or_close (from "
                             f"compute_or_close)")
        base = base.merge(or_close.rename("or_close").reset_index(),
                          on="session_date", how="left")

    merged = cluster_pool.merge(base, on="session_date", how="inner")

    if gate == "inside_OR":
        mask = ((merged["center"] >= merged["or_low"])
                & (merged["center"] <= merged["or_high"]))
    elif gate == "no_gate":
        mask = pd.Series(True, index=merged.index)
    elif gate == "within_100":
        mask = ((merged["center"] - merged["or_close"]).abs() <= 100.0) \
               & merged["or_close"].notna()
    elif gate == "within_200":
        mask = ((merged["center"] - merged["or_close"]).abs() <= 200.0) \
               & merged["or_close"].notna()
    else:
        raise ValueError(f"Unknown gate: {gate!r}")

    return merged[mask][CANDIDATE_COLS].reset_index(drop=True)


# ─── CLI commands ─────────────────────────────────────────────────────────

def or_stats():
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    or_levels["or_range"] = or_levels["or_high"] - or_levels["or_low"]
    print(f"Sessions with RTH data: {len(or_levels):,}")
    print(f"\nOR range distribution (points):")
    print(or_levels["or_range"].describe().to_string())
    print(f"\n5 narrowest:")
    print(or_levels.nsmallest(5, "or_range").to_string())
    print(f"\n5 widest:")
    print(or_levels.nlargest(5, "or_range").to_string())


def clusters():
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    pool = build_cluster_pool(or_levels)
    n_trading = len(or_levels) - LOOKBACK_SESSIONS
    print(f"Total clusters: {len(pool):,}")
    print(f"Sessions with clusters: {pool['session_date'].nunique():,} / "
          f"{n_trading:,}")
    print(f"\nClusters per session:")
    print(pool.groupby("session_date").size().describe().to_string())


def candidates():
    print("Loading processed bars...")
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    print(f"OR computed for {len(or_levels):,} sessions")

    print("Building cluster pool...")
    pool = build_cluster_pool(or_levels)
    print(f"Pool: {len(pool):,} clusters")

    print("Filtering to candidates (clusters within day's OR)...")
    cands = build_candidates(or_levels, pool)

    n_trading = len(or_levels) - LOOKBACK_SESSIONS
    n_with_cands = cands["session_date"].nunique()

    print(f"\nTotal candidates: {len(cands):,}")
    print(f"Sessions with >=1 candidate: {n_with_cands:,} / {n_trading:,} "
          f"({n_with_cands / n_trading * 100:.1f}%)")
    print(f"Sessions with 0 candidates (no trade): "
          f"{n_trading - n_with_cands:,} ({(n_trading - n_with_cands) / n_trading * 100:.1f}%)")

    per_session = cands.groupby("session_date").size()
    print(f"\nCandidates-per-session distribution (sessions with any):")
    print(per_session.describe().to_string())

    # Show a session with multiple candidates as a sample
    if len(per_session) > 0:
        busy = per_session.idxmax()
        print(f"\nSample: busiest session ({busy}, "
              f"{per_session.loc[busy]} candidates):")
        print(cands[cands["session_date"] == busy].to_string())

    # Yearly breakdown
    cands_with_year = cands.copy()
    cands_with_year["year"] = pd.to_datetime(cands_with_year["session_date"]).dt.year
    print(f"\nCandidates per year:")
    yearly = cands_with_year.groupby("year").agg(
        candidates=("cluster_id", "count"),
        trading_sessions=("session_date", "nunique"),
    )
    print(yearly.to_string())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "or-stats"
    cmd = cmd.replace("-", "_")
    {"or_stats": or_stats, "clusters": clusters, "candidates": candidates}.get(
        cmd, lambda: print(f"Unknown: {cmd}\n"
                           f"Usage: or-stats | clusters | candidates")
    )()