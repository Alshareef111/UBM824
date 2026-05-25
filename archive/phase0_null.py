"""Phase 0 supplement — null-distribution baseline.

50 RandomBinary classifiers (seeds 1-50) through the walk-forward harness.
Each produces a trades dataset; harness scores it across 7 OOS windows.

Becomes the control comparison for every indicator from Phase 1 forward.
A qualifying indicator should clearly exceed the null distribution, not just
clear the gates — a single random seed can game them by chance (as Phase 0
showed with seed=0 qualifying 7/7).

Output: results/archive/phase0_null_20260512/
  - null_stats.parquet      — per-seed scoring
  - per_seed_pnl.parquet    — per-seed × per-window OOS P&L
  - report.md               — distribution stats + percentile bands
"""
from __future__ import annotations

import sys
import time
from datetime import date

import numpy as np
import pandas as pd

from indicators.base import RandomBinary
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs
from simulator_v2 import run_backtest, trades_to_dataframe
import walk_forward as wf

N_SEEDS = 50
TODAY = date.today().strftime("%Y%m%d")
NULL_DIR = ARCHIVE_DIR / f"phase0_null_{TODAY}"


def percentile_row(label: str, values: np.ndarray) -> dict:
    return {
        "stat": label,
        "min": float(np.min(values)),
        "p5":  float(np.percentile(values, 5)),
        "p25": float(np.percentile(values, 25)),
        "p50": float(np.median(values)),
        "p75": float(np.percentile(values, 75)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "stdev": float(np.std(values, ddof=1)) if len(values) > 1 else float("nan"),
    }


def main():
    ensure_dirs()
    NULL_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions", flush=True)

    windows = wf.make_windows()
    rows = []
    per_seed_oos = []

    print(f"\nRunning {N_SEEDS} RandomBinary seeds:", flush=True)
    for seed in range(1, N_SEEDS + 1):
        t_one = time.time()
        clf = RandomBinary(seed=seed)
        trades = run_backtest(bars, orb_table, clf)
        df = trades_to_dataframe(trades)
        pw = wf.per_window_pnl(df, windows, slice_="oos")
        labels = df["cluster_label"].value_counts().to_dict() if len(df) else {}
        n_fade = int(labels.get("FADE", 0))
        n_trend = int(labels.get("TREND", 0))

        rows.append({
            "seed": seed,
            "n_trades": len(df),
            "fade_frac": n_fade / max(1, n_fade + n_trend),
            "total_pnl": float(df["pnl_dollars"].sum()) if len(df) else 0.0,
            "oos_median": wf.median_pnl(pw),
            "oos_sharpe_like": wf.sharpe_like_score(pw),
            "oos_sign_count": wf.sign_stability_count(pw),
            "qualifies": wf.qualifies(pw),
        })
        per_seed_oos.append({"seed": seed, **{w.name: pw[w.name] for w in windows}})

        elapsed = time.time() - t_one
        q = "QUAL" if rows[-1]["qualifies"] else "    "
        print(
            f"  seed={seed:>3}  {q}  trades={rows[-1]['n_trades']}  "
            f"fade_frac={rows[-1]['fade_frac']:.1%}  "
            f"median=${rows[-1]['oos_median']:>7.0f}  sharpe={rows[-1]['oos_sharpe_like']:>6.2f}  "
            f"sign={rows[-1]['oos_sign_count']}/7  [{elapsed:.1f}s]",
            flush=True,
        )

    stats_df = pd.DataFrame(rows)
    pnl_df = pd.DataFrame(per_seed_oos)
    stats_df.to_parquet(NULL_DIR / "null_stats.parquet", index=False)
    pnl_df.to_parquet(NULL_DIR / "per_seed_pnl.parquet", index=False)
    print(f"\nWrote null_stats.parquet  ({len(stats_df)} seeds)", flush=True)

    # Percentile breakdown
    pct_sharpe = percentile_row("sharpe_like", stats_df["oos_sharpe_like"].to_numpy())
    pct_sign = percentile_row("sign_count", stats_df["oos_sign_count"].to_numpy().astype(float))
    pct_median = percentile_row("median_oos", stats_df["oos_median"].to_numpy())
    qualifying_rate = float(stats_df["qualifies"].sum()) / len(stats_df)

    write_report(stats_df, pnl_df, [pct_sharpe, pct_sign, pct_median], qualifying_rate, windows)
    print(f"\nQualification rate: {stats_df['qualifies'].sum()}/{N_SEEDS} = {qualifying_rate:.1%}", flush=True)
    print(f"Total elapsed: {(time.time()-t0)/60:.1f} min", flush=True)
    print(f"Artifacts: {NULL_DIR}", flush=True)


def write_report(stats_df, pnl_df, percentiles, qualifying_rate, windows):
    lines: list[str] = []
    lines.append("# Phase 0 supplement — null-distribution baseline")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Seeds:** 1–{N_SEEDS}")
    lines.append(f"**Classifier:** RandomBinary (per-cluster 50/50 FADE/TREND, hash-keyed)")
    lines.append("")
    lines.append("Random labeling per cluster, deterministic via seed. Acts as the null")
    lines.append("comparison — any real indicator must clearly exceed this distribution,")
    lines.append("not just clear the qualification gates.")
    lines.append("")

    lines.append("## Qualification rate under null")
    lines.append("")
    lines.append(f"**{int(stats_df['qualifies'].sum())} of {N_SEEDS} = {qualifying_rate:.1%}** seeds qualify under the spec gates")
    lines.append(f"(>=6/7 OOS windows positive AND median OOS > 0).")
    lines.append("")
    lines.append("If this rate is non-trivial (say > 5%), then 'qualifies = true' for a")
    lines.append("real indicator is by itself weak evidence of edge — the indicator's")
    lines.append("score must beat the null's percentile distribution.")
    lines.append("")

    lines.append("## Distribution of scores")
    lines.append("")
    lines.append("| Statistic | min | p5 | p25 | median | p75 | p95 | max | mean | stdev |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for p in percentiles:
        def fmt(v):
            return f"{v:.2f}" if abs(v) < 100 else f"{v:,.0f}"
        lines.append(
            f"| {p['stat']} | {fmt(p['min'])} | {fmt(p['p5'])} | {fmt(p['p25'])} | "
            f"{fmt(p['p50'])} | {fmt(p['p75'])} | {fmt(p['p95'])} | {fmt(p['max'])} | "
            f"{fmt(p['mean'])} | {fmt(p['stdev'])} |"
        )
    lines.append("")

    lines.append("## How to use this in Phase 1+")
    lines.append("")
    lines.append("For an indicator parameter config X with score (sharpe_like, sign_count, median_oos):")
    lines.append("")
    lines.append("- **Weak evidence:** X qualifies under the gates. (Some non-trivial fraction of random")
    lines.append("  seeds also qualify, so qualifying alone is not strong.)")
    lines.append("- **Moderate evidence:** X's sharpe_like exceeds the null distribution's 75th percentile.")
    lines.append("- **Strong evidence:** X's sharpe_like exceeds the null's 95th percentile AND median_oos")
    lines.append("  exceeds null's 95th percentile.")
    lines.append("- **Almost certainly noise:** X scores below the null's median across all three stats.")
    lines.append("")

    lines.append("## Top 5 seeds by Sharpe-like")
    lines.append("")
    top5 = stats_df.sort_values("oos_sharpe_like", ascending=False).head(5)
    lines.append("| Seed | trades | fade_frac | median OOS | sharpe_like | sign | qualifies | total |")
    lines.append("|---:|---:|---:|---:|---:|:---:|:---:|---:|")
    for r in top5.itertuples():
        q = "✓" if r.qualifies else " "
        lines.append(
            f"| {r.seed} | {r.n_trades} | {r.fade_frac:.1%} | "
            f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.3f} | "
            f"{r.oos_sign_count}/7 | {q} | ${r.total_pnl:,.0f} |"
        )
    lines.append("")

    lines.append("## Bottom 5 seeds by Sharpe-like")
    lines.append("")
    bot5 = stats_df.sort_values("oos_sharpe_like", ascending=True).head(5)
    lines.append("| Seed | trades | fade_frac | median OOS | sharpe_like | sign | qualifies | total |")
    lines.append("|---:|---:|---:|---:|---:|:---:|:---:|---:|")
    for r in bot5.itertuples():
        q = "✓" if r.qualifies else " "
        lines.append(
            f"| {r.seed} | {r.n_trades} | {r.fade_frac:.1%} | "
            f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.3f} | "
            f"{r.oos_sign_count}/7 | {q} | ${r.total_pnl:,.0f} |"
        )
    lines.append("")

    lines.append("## Per-window OOS P&L by seed (first 10 + last 5)")
    lines.append("")
    lines.append("| Seed | " + " | ".join(w.name for w in windows) + " |")
    lines.append("|---:|" + "|".join(["---:"] * len(windows)) + "|")
    show_seeds = list(range(1, 11)) + list(range(N_SEEDS - 4, N_SEEDS + 1))
    for seed in show_seeds:
        row = pnl_df[pnl_df["seed"] == seed].iloc[0]
        cells = [f"${row[w.name]:,.0f}" for w in windows]
        lines.append(f"| {seed} | " + " | ".join(cells) + " |")
    lines.append("")

    report = NULL_DIR / "report.md"
    report.write_text("\n".join(lines))
    print(f"Wrote {report}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
