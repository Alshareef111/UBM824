"""Phase 4 — ATR ratio solo sweep.

16 configs (4 N_short × 4 ratio thresholds) evaluated via walk-forward harness.
Magnitude: ATR(N_short) / ATR(N_long=4×N_short) at touch bar T-1.

  N_short  ∈ {15, 30, 60, 120}   (1-min bars)
  N_long   = 4 × N_short
  ratio thr ∈ {0.7, 1.0, 1.3, 1.6}

Uses the 4-gate qualification (locked 2026-05-12 after Phase 3 review):
  1. median(OOS) > 0
  2. >= 6/7 OOS windows positive
  3. OOS sharpe_like used for deployment rank (not a gate)
  4. total_pnl > 0 over full 7-year dataset

Output: results/archive/sweep_atr_YYYYMMDD/
"""
from __future__ import annotations

import sys
import time
from datetime import date

import pandas as pd

from regime_indicators.atr import AtrRatioClassifier, precompute_ratio_lookup
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs
from simulator_v2 import run_backtest, trades_to_dataframe
import walk_forward as wf

N_SHORTS = [15, 30, 60, 120]
N_LONG_RATIO = 4
THRESHOLDS = [0.7, 1.0, 1.3, 1.6]

TODAY = date.today().strftime("%Y%m%d")
SWEEP_DIR = ARCHIVE_DIR / f"sweep_atr_{TODAY}"
TRADES_SUBDIR = SWEEP_DIR / "trades"


def run_one(bars, orb_table, lookup, n_short, n_long, thr, windows):
    clf = AtrRatioClassifier(lookup, n_short=n_short, n_long=n_long, threshold=thr)
    trades = run_backtest(bars, orb_table, clf)
    df = trades_to_dataframe(trades)
    pw_oos = wf.per_window_pnl(df, windows, slice_="oos")
    pw_is = wf.per_window_pnl(df, windows, slice_="is")
    total_pnl = float(df["pnl_dollars"].sum()) if len(df) else 0.0
    label_split = df["cluster_label"].value_counts().to_dict() if len(df) else {}
    return {
        "n_short": n_short,
        "n_long": n_long,
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
        "qualifies_3gate": wf.qualifies(pw_oos),
        "qualifies": wf.qualifies(pw_oos, total_pnl=total_pnl),
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

    print("Pre-computing ATR ratio lookups for each (N_short, N_long=4*N_short) pair...", flush=True)
    lookups = {}
    for ns in N_SHORTS:
        nl = N_LONG_RATIO * ns
        t_pre = time.time()
        lookups[ns] = precompute_ratio_lookup(bars, ns, nl)
        print(f"  ATR(Ns={ns},Nl={nl}) ready in {time.time()-t_pre:.1f}s", flush=True)
    print(f"  Pre-compute total: {time.time()-t0:.1f}s", flush=True)

    windows = wf.make_windows()
    rows = []
    qualifying_dfs = {}

    print(f"\nSweeping {len(N_SHORTS)*len(THRESHOLDS)} configs (4-gate qualification):", flush=True)
    for ns in N_SHORTS:
        nl = N_LONG_RATIO * ns
        for thr in THRESHOLDS:
            t_one = time.time()
            row, df = run_one(bars, orb_table, lookups[ns], ns, nl, thr, windows)
            elapsed = time.time() - t_one
            q4 = "QUAL" if row["qualifies"] else "    "
            q3 = "3G+" if row["qualifies_3gate"] and not row["qualifies"] else "   "
            print(
                f"  {q4}{q3}  Ns={ns:>3} Nl={nl:>4} thr={thr:>4}  trades={row['n_trades']:>4} "
                f"(F={row['n_fade']:>4} T={row['n_trend']:>4})  "
                f"OOS median=${row['oos_median']:>7.0f}  sharpe={row['oos_sharpe_like']:>6.2f}  "
                f"sign={row['oos_sign_count']}/7  total=${row['total_pnl']:>7.0f}  [{elapsed:.1f}s]",
                flush=True,
            )
            rows.append(row)
            if row["qualifies"] or row["qualifies_3gate"]:
                qualifying_dfs[(ns, thr)] = df

    results_df = pd.DataFrame(rows)
    results_df.to_parquet(SWEEP_DIR / "sweep_results.parquet", index=False)
    print(f"\nWrote sweep_results.parquet ({len(results_df)} rows)", flush=True)

    top5 = results_df.sort_values("oos_sharpe_like", ascending=False).head(5)
    keep_keys = set(qualifying_dfs.keys()) | {(r.n_short, r.threshold) for r in top5.itertuples()}
    for (ns, thr) in keep_keys:
        if (ns, thr) in qualifying_dfs:
            df = qualifying_dfs[(ns, thr)]
        else:
            nl = N_LONG_RATIO * ns
            print(f"  Re-running ATR(Ns={ns},thr={thr}) for trade output...", flush=True)
            clf = AtrRatioClassifier(lookups[ns], n_short=ns, n_long=nl, threshold=thr)
            trades = run_backtest(bars, orb_table, clf)
            df = trades_to_dataframe(trades)
        out = TRADES_SUBDIR / f"trades_atr_ns{ns}_thr{thr}.parquet"
        df.to_parquet(out, index=False)

    write_report(results_df, windows)
    print(f"\nTotal elapsed: {(time.time()-t0)/60:.1f} min", flush=True)
    print(f"Artifacts: {SWEEP_DIR}", flush=True)


def write_report(results_df, windows):
    q4 = results_df[results_df["qualifies"]].sort_values("oos_sharpe_like", ascending=False)
    q3_only = results_df[results_df["qualifies_3gate"] & ~results_df["qualifies"]].sort_values("oos_sharpe_like", ascending=False)
    top5_sharpe = results_df.sort_values("oos_sharpe_like", ascending=False).head(5)

    lines: list[str] = []
    lines.append("# Phase 4 — ATR ratio solo sweep")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Sweep:** {len(N_SHORTS)} N_short × {len(THRESHOLDS)} thresholds = {len(N_SHORTS)*len(THRESHOLDS)} configs")
    lines.append(f"**N_short values:** {N_SHORTS}  (1-min bars)")
    lines.append(f"**N_long values:** {[ns*N_LONG_RATIO for ns in N_SHORTS]}  (= 4 × N_short)")
    lines.append(f"**Thresholds:** {THRESHOLDS}  (ATR(N_short)/ATR(N_long) ratio)")
    lines.append("")
    lines.append("## Decision rule")
    lines.append("")
    lines.append("Per cluster touch at bar T: look up ATR(N_short)/ATR(N_long) at T-1.")
    lines.append("- ratio ≥ threshold → TREND (vol expanding → invert direction)")
    lines.append("- ratio < threshold → FADE (vol contracting → locked-baseline direction)")
    lines.append("")
    lines.append("## Qualification gates (4-gate, locked 2026-05-12)")
    lines.append("")
    lines.append("1. median(per-window OOS P&L) > 0")
    lines.append("2. ≥ 6 of 7 OOS windows positive (sign stability)")
    lines.append("3. (OOS Sharpe-like used for deployment rank, not a gate)")
    lines.append("4. total_pnl > 0 (sum of all trade P&L over full 7-year dataset)")
    lines.append("")

    lines.append(f"## Qualifying under 4-gate: {len(q4)}")
    lines.append("")
    if len(q4) > 0:
        lines.append("| N_short | thr | trades | median OOS | sharpe_like | sign | total_pnl |")
        lines.append("|---:|---:|---:|---:|---:|:---:|---:|")
        for r in q4.itertuples():
            lines.append(
                f"| {r.n_short} | {r.threshold} | {r.n_trades} | "
                f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.3f} | "
                f"{r.oos_sign_count}/7 | ${r.total_pnl:,.0f} |"
            )
    else:
        lines.append("**No configs qualify under all 4 gates.**")
    lines.append("")

    if len(q3_only) > 0:
        lines.append(f"## Configs qualifying under OLD 3-gate but FAILING 4th gate (total<0): {len(q3_only)}")
        lines.append("")
        lines.append("These would have qualified pre-Phase 4 but fail the new total_pnl>0 gate.")
        lines.append("")
        lines.append("| N_short | thr | trades | median OOS | sharpe_like | sign | total_pnl |")
        lines.append("|---:|---:|---:|---:|---:|:---:|---:|")
        for r in q3_only.itertuples():
            lines.append(
                f"| {r.n_short} | {r.threshold} | {r.n_trades} | "
                f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.3f} | "
                f"{r.oos_sign_count}/7 | ${r.total_pnl:,.0f} |"
            )
        lines.append("")

    lines.append("## Top 5 by Sharpe-like score (regardless of qualification)")
    lines.append("")
    lines.append("| N_short | thr | trades | median OOS | sharpe_like | sign | qual_4g | total_pnl |")
    lines.append("|---:|---:|---:|---:|---:|:---:|:---:|---:|")
    for r in top5_sharpe.itertuples():
        q = "✓" if r.qualifies else (" 3G" if r.qualifies_3gate else " ")
        lines.append(
            f"| {r.n_short} | {r.threshold} | {r.n_trades} | "
            f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.3f} | "
            f"{r.oos_sign_count}/7 | {q} | ${r.total_pnl:,.0f} |"
        )
    lines.append("")

    lines.append("## Full surface (N_short × threshold)")
    lines.append("")
    for stat, fmt_, header in [
        ("oos_sharpe_like", lambda v: f"{v:.2f}" if not pd.isna(v) else "—", "Sharpe-like"),
        ("oos_median", lambda v: f"${v:.0f}" if not pd.isna(v) else "—", "Median OOS"),
        ("oos_sign_count", lambda v: f"{int(v)}" if not pd.isna(v) else "—", "Sign k/7"),
        ("total_pnl", lambda v: f"${v:.0f}" if not pd.isna(v) else "—", "Total P&L"),
    ]:
        lines.append(f"### {header}")
        lines.append("")
        pivot = results_df.pivot(index="n_short", columns="threshold", values=stat)
        lines.append("| Ns \\ thr | " + " | ".join(str(t) for t in pivot.columns) + " |")
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
        lines.append(f"| ATR(Ns={r.n_short},thr={r.threshold}) | " + " | ".join(cells) + " |")
    lines.append("")

    report = SWEEP_DIR / "report.md"
    report.write_text("\n".join(lines))
    print(f"Wrote {report}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
