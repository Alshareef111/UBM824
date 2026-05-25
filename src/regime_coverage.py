"""
src/regime_coverage.py — Regime-coverage scan.

For every session with a full 200-session OR pool, classify the regime:
  OR_ABOVE_POOL  (today's or_low  >  pool max)
  OR_BELOW_POOL  (today's or_high <  pool min)
  OR_IN_POOL     (otherwise — any overlap)

Under the live C config (gap=7, min_size=2), record per session:
  - n_candidates       clusters whose center is inside today's OR
  - nearest_dist       min(|center - OR|), 0 if a center is inside
  - within_30pts       True if nearest_dist <= 30
  - within_100pts      True if nearest_dist <= 100

Output:
  results/regime_coverage.csv  — per-session rows
  printed per-year aggregate
  printed longest + most-recent zero-candidate streak

Run:
    python -m src.regime_coverage
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src.data import load_processed_bars
from src.signals import (
    LOOKBACK_SESSIONS,
    _cluster_levels,
    compute_opening_range,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "results"

C_GAP = 7.0
C_MIN_SIZE = 2


def classify(or_low, or_high, pool_min, pool_max):
    if or_low > pool_max:
        return "OR_ABOVE_POOL"
    if or_high < pool_min:
        return "OR_BELOW_POOL"
    return "OR_IN_POOL"


def nearest_distance(centers, or_low, or_high):
    if not centers:
        return float("nan")
    s = pd.Series(centers)
    dist = (or_low - s).clip(lower=0) + (s - or_high).clip(lower=0)
    return float(dist.min())


def find_runs(flags):
    """Return list of (start_idx, end_idx, length) for True-runs in flags."""
    runs = []
    cur_start = None
    for i, f in enumerate(flags):
        if f:
            if cur_start is None:
                cur_start = i
        else:
            if cur_start is not None:
                runs.append((cur_start, i - 1, i - cur_start))
                cur_start = None
    if cur_start is not None:
        runs.append((cur_start, len(flags) - 1, len(flags) - cur_start))
    return runs


def main():
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)

    sessions = or_levels.index.tolist()
    rows = []
    for i, sess in enumerate(sessions):
        if i < LOOKBACK_SESSIONS:
            continue
        window = or_levels.iloc[i - LOOKBACK_SESSIONS : i]
        levels = window["or_high"].tolist() + window["or_low"].tolist()
        pool_min = float(min(levels))
        pool_max = float(max(levels))
        or_low = float(or_levels.iloc[i]["or_low"])
        or_high = float(or_levels.iloc[i]["or_high"])

        clusters = _cluster_levels(levels, gap=C_GAP, min_size=C_MIN_SIZE)
        centers = [sum(c) / len(c) for c in clusters]

        cand_count = sum(1 for c in centers if or_low <= c <= or_high)
        nd = nearest_distance(centers, or_low, or_high)

        rows.append(
            {
                "session_date": sess,
                "or_low": or_low,
                "or_high": or_high,
                "pool_min": pool_min,
                "pool_max": pool_max,
                "regime": classify(or_low, or_high, pool_min, pool_max),
                "n_clusters_C": len(clusters),
                "n_candidates_C": cand_count,
                "zero_candidate": cand_count == 0,
                "nearest_dist": nd,
                "within_30pts": (not np.isnan(nd)) and nd <= 30,
                "within_100pts": (not np.isnan(nd)) and nd <= 100,
            }
        )

    df = pd.DataFrame(rows)
    df["session_date"] = pd.to_datetime(df["session_date"])
    df = df.sort_values("session_date").reset_index(drop=True)

    RESULTS.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS / "regime_coverage.csv"
    df.to_csv(out_path, index=False)

    # ── Per-year aggregate ───────────────────────────────────────────────
    df["year"] = df["session_date"].dt.year
    yearly = (
        df.groupby("year")
        .agg(
            n_sessions=("session_date", "size"),
            pct_OR_ABOVE_POOL=("regime", lambda s: (s == "OR_ABOVE_POOL").mean() * 100),
            pct_OR_IN_POOL=("regime", lambda s: (s == "OR_IN_POOL").mean() * 100),
            pct_OR_BELOW_POOL=("regime", lambda s: (s == "OR_BELOW_POOL").mean() * 100),
            pct_zero_candidate=("zero_candidate", lambda s: s.mean() * 100),
            median_nearest_dist=("nearest_dist", "median"),
        )
        .round(2)
    )

    print("Per-year regime coverage:")
    print(yearly.to_string())

    # ── Zero-candidate streaks ───────────────────────────────────────────
    flags = df["zero_candidate"].tolist()
    runs = find_runs(flags)
    sess_arr = df["session_date"].tolist()

    if runs:
        longest = max(runs, key=lambda r: r[2])
        ls_i, le_i, ll = longest
        print(
            f"\nLongest zero-candidate streak: {ll} sessions  "
            f"({pd.Timestamp(sess_arr[ls_i]).date()} → "
            f"{pd.Timestamp(sess_arr[le_i]).date()})"
        )

        recent = runs[-1]
        rs_i, re_i, rl = recent
        tag = "TRAILING (still active)" if re_i == len(flags) - 1 else "ended earlier"
        print(
            f"Most recent zero-candidate streak: {rl} sessions  "
            f"({pd.Timestamp(sess_arr[rs_i]).date()} → "
            f"{pd.Timestamp(sess_arr[re_i]).date()})  [{tag}]"
        )
    else:
        print("\nNo zero-candidate sessions in the scanned range.")

    print(f"\nSaved {len(df):,} rows to {out_path}")
    print("REGIME SCAN DONE")


if __name__ == "__main__":
    main()
