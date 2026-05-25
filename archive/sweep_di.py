"""Phase 2 — ±DI solo sweep.

49 configs (7 N values x 7 thresholds) evaluated via walk-forward harness.
Magnitude: |+DI(N) - -DI(N)| at touch bar T-1.

  N        ∈ {15, 30, 60, 120, 240, 390, 780}   (1-min bars)
  threshold ∈ {3, 5, 8, 12, 18, 25, 35}          (DI spread magnitude)

Same scoring, gates, and report structure as Phase 1.
Output: results/archive/sweep_di_YYYYMMDD/
"""
from __future__ import annotations

import sys
import time
from datetime import date

import pandas as pd

from regime_indicators.di import DiClassifier, precompute_lookup
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs
from simulator_v2 import run_backtest, trades_to_dataframe
import walk_forward as wf

N_VALUES = [15, 30, 60, 120, 240, 390, 780]
THRESHOLDS = [3, 5, 8, 12, 18, 25, 35]

TODAY = date.today().strftime("%Y%m%d")
SWEEP_DIR = ARCHIVE_DIR / f"sweep_di_{TODAY}"
TRADES_SUBDIR = SWEEP_DIR / "trades"


def run_one(bars, orb_table, lookup, n, thr, windows):
    clf = DiClassifier(lookup, n=n, threshold=thr)
    trades = run_backtest(bars, orb_table, clf)
    df = trades_to_dataframe(trades)
    pw_oos = wf.per_window_pnl(df, windows, slice_="oos")
    pw_is = wf.per_window_pnl(df, windows, slice_="is")
    label_split = df["cluster_label"].value_counts().to_dict() if len(df) else {}
    return {
        "n": n,
        "threshold": thr,
        "n_trades": len(df),
        "n_fade": int(label_split.get("FADE", 0)),
        "n_trend": int(label_split.get("TREND", 0)),
        "total_pnl": float(df["pnl_dollars"].sum()) if len(df) else 0.0,
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

    print("Pre-computing |+DI - -DI|(N) for each N...", flush=True)
    lookups = {}
    for n in N_VALUES:
        t_pre = time.time()
        lookups[n] = precompute_lookup(bars, n)
        print(f"  DI(N={n}) ready in {time.time()-t_pre:.1f}s", flush=True)
    print(f"  Pre-compute total: {time.time()-t0:.1f}s", flush=True)

    windows = wf.make_windows()
    rows = []
    qualifying_dfs = {}

    print(f"\nSweeping {len(N_VALUES)*len(THRESHOLDS)} configs:", flush=True)
    for n in N_VALUES:
        for thr in THRESHOLDS:
            t_one = time.time()
            row, df = run_one(bars, orb_table, lookups[n], n, thr, windows)
            elapsed = time.time() - t_one
            q = "QUAL" if row["qualifies"] else "    "
            print(
                f"  {q}  N={n:>4} thr={thr:>2}  trades={row['n_trades']:>4} "
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

    top5 = results_df.sort_values("oos_sharpe_like", ascending=False).head(5)
    keep_keys = set(qualifying_dfs.keys()) | {(r.n, r.threshold) for r in top5.itertuples()}
    for (n, thr) in keep_keys:
        if (n, thr) in qualifying_dfs:
            df = qualifying_dfs[(n, thr)]
        else:
            print(f"  Re-running DI(N={n},thr={thr}) for trade output...", flush=True)
            clf = DiClassifier(lookups[n], n=n, threshold=thr)
            trades = run_backtest(bars, orb_table, clf)
            df = trades_to_dataframe(trades)
        out = TRADES_SUBDIR / f"trades_di_n{n}_thr{thr}.parquet"
        df.to_parquet(out, index=False)

    write_report(results_df, windows)
    print(f"\nTotal elapsed: {(time.time()-t0)/60:.1f} min", flush=True)
    print(f"Artifacts: {SWEEP_DIR}", flush=True)


def write_report(results_df, windows):
    qualifying = results_df[results_df["qualifies"]].sort_values("oos_sharpe_like", ascending=False)
    top5_sharpe = results_df.sort_values("oos_sharpe_like", ascending=False).head(5)

    lines: list[str] = []
    lines.append("# Phase 2 — ±DI solo sweep")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Sweep:** {len(N_VALUES)} N × {len(THRESHOLDS)} thresholds = {len(N_VALUES)*len(THRESHOLDS)} configs")
    lines.append(f"**N values:** {N_VALUES}  (1-min bars)")
    lines.append(f"**Thresholds:** {THRESHOLDS}  (|+DI - -DI| spread magnitude)")
    lines.append("")
    lines.append("## Decision rule")
    lines.append("")
    lines.append("Per cluster touch at bar T: look up |+DI(N) - -DI(N)| at T-1.")
    lines.append("- spread ≥ threshold → TREND (invert direction)")
    lines.append("- spread < threshold → FADE (locked-baseline direction)")
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
        lines.append("**No configs qualify.**")
    lines.append("")

    lines.append("## Top 5 by Sharpe-like score")
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
    for stat, fmt_, header in [
        ("oos_sharpe_like", lambda v: f"{v:.2f}" if not pd.isna(v) else "—", "Sharpe-like"),
        ("oos_median", lambda v: f"${v:.0f}" if not pd.isna(v) else "—", "Median OOS"),
        ("oos_sign_count", lambda v: f"{int(v)}" if not pd.isna(v) else "—", "Sign k/7"),
    ]:
        lines.append(f"### {header}")
        lines.append("")
        pivot = results_df.pivot(index="n", columns="threshold", values=stat)
        lines.append("| N \\ thr | " + " | ".join(str(t) for t in pivot.columns) + " |")
        lines.append("|---:|" + "|".join(["---:"] * len(pivot.columns)) + "|")
        for n_val in pivot.index:
            row = pivot.loc[n_val]
            cells = [fmt_(v) for v in row.values]
            lines.append(f"| **{n_val}** | " + " | ".join(cells) + " |")
        lines.append("")

    lines.append("## Per-window OOS P&L for top-5 by Sharpe-like")
    lines.append("")
    lines.append("| Config | " + " | ".join(w.name for w in windows) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(windows)) + "|")
    for r in top5_sharpe.itertuples():
        cells = [f"${getattr(r, f'oos_{w.name}'):,.0f}" for w in windows]
        lines.append(f"| DI(N={r.n},thr={r.threshold}) | " + " | ".join(cells) + " |")
    lines.append("")

    report = SWEEP_DIR / "report.md"
    report.write_text("\n".join(lines))
    print(f"Wrote {report}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
