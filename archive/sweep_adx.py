"""Phase 1 — ADX solo sweep.

49 configs (7 N values x 7 thresholds) evaluated via the walk-forward harness:
  N        ∈ {15, 30, 60, 120, 240, 390, 780}   (1-min bars)
  threshold ∈ {15, 20, 25, 30, 35, 40, 45}

For each config:
  - Build AdxClassifier with pre-computed lookup
  - Run simulator_v2 over the full 7-year dataset
  - Compute per-window OOS P&L across the 7 walk-forward windows
  - Score: median(OOS), stdev, sharpe_like = median/stdev, sign-stability count
  - Qualification gates (#5, #6a): >= 6/7 windows positive AND median > 0

Output: results/archive/sweep_adx_YYYYMMDD/
  - sweep_results.parquet   — one row per config
  - top5_by_sharpe.md       — top-5 surface (and any qualifying)
  - report.md               — full breakdown
  - trades/                 — per-config trade outputs (skipped to save disk;
                              only top configs persisted)
"""
from __future__ import annotations

import sys
import time
from datetime import date

import numpy as np
import pandas as pd

from regime_indicators.adx import AdxClassifier, precompute_lookup
from regime_indicators.base import Label
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs
from simulator_v2 import POINT_VALUE_USD, run_backtest, trades_to_dataframe
import walk_forward as wf

N_VALUES = [15, 30, 60, 120, 240, 390, 780]
THRESHOLDS = [15, 20, 25, 30, 35, 40, 45]

TODAY = date.today().strftime("%Y%m%d")
SWEEP_DIR = ARCHIVE_DIR / f"sweep_adx_{TODAY}"
TRADES_SUBDIR = SWEEP_DIR / "trades"


def run_one(bars, orb_table, lookup, n, thr, windows):
    clf = AdxClassifier(lookup, n=n, threshold=thr)
    trades = run_backtest(bars, orb_table, clf)
    df = trades_to_dataframe(trades)
    pw_oos = wf.per_window_pnl(df, windows, slice_="oos")
    pw_is = wf.per_window_pnl(df, windows, slice_="is")
    total_pnl = float(df["pnl_dollars"].sum()) if len(df) else 0.0
    label_split = df["cluster_label"].value_counts().to_dict() if len(df) else {}
    return {
        "n": n,
        "threshold": thr,
        "n_trades": len(df),
        "n_fade": int(label_split.get("FADE", 0)),
        "n_trend": int(label_split.get("TREND", 0)),
        "total_pnl": total_pnl,
        "is_pnl_sum": float(sum(pw_is.values())),
        "oos_pnl_sum": float(sum(pw_oos.values())),
        "oos_median": wf.median_pnl(pw_oos),
        "oos_sharpe_like": wf.sharpe_like_score(pw_oos),
        "oos_sign_count": wf.sign_stability_count(pw_oos),
        "qualifies": wf.qualifies(pw_oos),
        **{f"oos_{w.name}": pw_oos[w.name] for w in windows},
    }, df


def main():
    ensure_dirs()
    SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    TRADES_SUBDIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions", flush=True)

    print("Pre-computing ADX(N) series for each N (vectorized)...", flush=True)
    lookups = {}
    for n in N_VALUES:
        t_pre = time.time()
        lookups[n] = precompute_lookup(bars, n)
        print(f"  ADX(N={n}) ready in {time.time()-t_pre:.1f}s ({len(lookups[n]):,} entries)", flush=True)
    print(f"  Pre-compute total: {time.time()-t0:.1f}s", flush=True)

    windows = wf.make_windows()
    rows = []
    qualifying_dfs = {}  # save full trade dfs for qualifying configs

    print(f"\nSweeping {len(N_VALUES)*len(THRESHOLDS)} configs:", flush=True)
    for n in N_VALUES:
        for thr in THRESHOLDS:
            t_one = time.time()
            row, df = run_one(bars, orb_table, lookups[n], n, thr, windows)
            elapsed = time.time() - t_one
            qual_marker = "QUAL" if row["qualifies"] else "    "
            print(
                f"  {qual_marker}  N={n:>4} thr={thr:>2}  trades={row['n_trades']:>4} "
                f"(F={row['n_fade']:>4} T={row['n_trend']:>4})  "
                f"OOS median=${row['oos_median']:>7.0f}  sharpe={row['oos_sharpe_like']:>6.2f}  "
                f"sign={row['oos_sign_count']}/7  [{elapsed:.1f}s]",
                flush=True,
            )
            rows.append(row)
            if row["qualifies"]:
                qualifying_dfs[(n, thr)] = df

    results_df = pd.DataFrame(rows)
    results_df.to_parquet(SWEEP_DIR / "sweep_results.parquet", index=False)
    print(f"\nWrote sweep_results.parquet ({len(results_df)} rows)", flush=True)

    # Save trades for qualifying configs + top-5 by sharpe (whichever larger set)
    top5 = results_df.sort_values("oos_sharpe_like", ascending=False).head(5)
    keep_keys = set(qualifying_dfs.keys()) | {(r.n, r.threshold) for r in top5.itertuples()}
    for (n, thr) in keep_keys:
        if (n, thr) in qualifying_dfs:
            df = qualifying_dfs[(n, thr)]
        else:
            # Re-run to get trades for top-5-but-not-qualifying configs
            print(f"  Re-running ADX(N={n},thr={thr}) for trade output...", flush=True)
            clf = AdxClassifier(lookups[n], n=n, threshold=thr)
            trades = run_backtest(bars, orb_table, clf)
            df = trades_to_dataframe(trades)
        out = TRADES_SUBDIR / f"trades_adx_n{n}_thr{thr}.parquet"
        df.to_parquet(out, index=False)

    write_report(results_df, windows)
    print(f"\nTotal elapsed: {(time.time()-t0)/60:.1f} min", flush=True)
    print(f"Artifacts: {SWEEP_DIR}", flush=True)


def write_report(results_df, windows):
    qualifying = results_df[results_df["qualifies"]].sort_values("oos_sharpe_like", ascending=False)
    top5_sharpe = results_df.sort_values("oos_sharpe_like", ascending=False).head(5)

    lines: list[str] = []
    lines.append("# Phase 1 — ADX solo sweep")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Sweep:** {len(N_VALUES)} N × {len(THRESHOLDS)} thresholds = {len(N_VALUES)*len(THRESHOLDS)} configs")
    lines.append(f"**N values:** {N_VALUES}  (1-min bars)")
    lines.append(f"**Thresholds:** {THRESHOLDS}  (ADX value)")
    lines.append("")
    lines.append("## Decision rule")
    lines.append("")
    lines.append("Per cluster touch at bar T: look up ADX(N) at T-1.")
    lines.append("- ADX(N) at T-1 ≥ threshold → TREND (invert direction)")
    lines.append("- ADX(N) at T-1 < threshold → FADE (locked-baseline direction)")
    lines.append("")
    lines.append("Warm-up (NaN) → FADE default.")
    lines.append("")
    lines.append("## Qualification gates")
    lines.append("")
    lines.append(f"- median(per-window OOS P&L) > 0")
    lines.append(f"- ≥ 6 of 7 OOS windows positive")
    lines.append("")

    lines.append(f"## Qualifying configs: {len(qualifying)}")
    lines.append("")
    if len(qualifying) > 0:
        lines.append("| N | thr | trades | median OOS | sharpe_like | sign | total_pnl |")
        lines.append("|---:|---:|---:|---:|---:|:---:|---:|")
        for r in qualifying.itertuples():
            lines.append(
                f"| {r.n} | {r.threshold} | {r.n_trades} | "
                f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.3f} | "
                f"{r.oos_sign_count}/7 | ${r.total_pnl:,.0f} |"
            )
    else:
        lines.append("**No configs qualify** — none clear both the median>0 AND 6/7-positive gates.")
    lines.append("")

    lines.append("## Top 5 by Sharpe-like score (regardless of qualification)")
    lines.append("")
    lines.append("| N | thr | trades | median OOS | sharpe_like | sign | qualifies | total_pnl |")
    lines.append("|---:|---:|---:|---:|---:|:---:|:---:|---:|")
    for r in top5_sharpe.itertuples():
        q = "✓" if r.qualifies else " "
        lines.append(
            f"| {r.n} | {r.threshold} | {r.n_trades} | "
            f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.3f} | "
            f"{r.oos_sign_count}/7 | {q} | ${r.total_pnl:,.0f} |"
        )
    lines.append("")

    lines.append("## Full surface (N × threshold)")
    lines.append("")
    lines.append("Per-config Sharpe-like score:")
    lines.append("")
    pivot = results_df.pivot(index="n", columns="threshold", values="oos_sharpe_like")
    lines.append("| N \\ thr | " + " | ".join(str(t) for t in pivot.columns) + " |")
    lines.append("|---:|" + "|".join(["---:"] * len(pivot.columns)) + "|")
    for n_val in pivot.index:
        row = pivot.loc[n_val]
        cells = [f"{v:.2f}" if not pd.isna(v) else "—" for v in row.values]
        lines.append(f"| **{n_val}** | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("Per-config median OOS P&L:")
    lines.append("")
    pivot2 = results_df.pivot(index="n", columns="threshold", values="oos_median")
    lines.append("| N \\ thr | " + " | ".join(str(t) for t in pivot2.columns) + " |")
    lines.append("|---:|" + "|".join(["---:"] * len(pivot2.columns)) + "|")
    for n_val in pivot2.index:
        row = pivot2.loc[n_val]
        cells = [f"${v:.0f}" if not pd.isna(v) else "—" for v in row.values]
        lines.append(f"| **{n_val}** | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("Per-config sign-stability count (k/7):")
    lines.append("")
    pivot3 = results_df.pivot(index="n", columns="threshold", values="oos_sign_count")
    lines.append("| N \\ thr | " + " | ".join(str(t) for t in pivot3.columns) + " |")
    lines.append("|---:|" + "|".join(["---:"] * len(pivot3.columns)) + "|")
    for n_val in pivot3.index:
        row = pivot3.loc[n_val]
        cells = [f"{int(v)}" if not pd.isna(v) else "—" for v in row.values]
        lines.append(f"| **{n_val}** | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Per-window OOS P&L for top-5 by Sharpe-like")
    lines.append("")
    lines.append("| Config | " + " | ".join(w.name for w in windows) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(windows)) + "|")
    for r in top5_sharpe.itertuples():
        cells = [f"${getattr(r, f'oos_{w.name}'):,.0f}" for w in windows]
        lines.append(f"| ADX(N={r.n},thr={r.threshold}) | " + " | ".join(cells) + " |")
    lines.append("")

    report = SWEEP_DIR / "report.md"
    report.write_text("\n".join(lines))
    print(f"Wrote {report}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
