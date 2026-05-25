"""ADX sanity checks for the Phase 1 representative ADX(N=15, thr=30).

Two lightweight diagnostics requested in Phase 1 review:
  1. Monthly distribution of TREND-classified trades and their P&L —
     looking for wins distributed across time, not concentrated in a few
     specific months/regimes.
  2. Mean ADX(15) value at TREND entries vs FADE entries — confirming the
     threshold mechanically separates the populations as labeled.

Result is logged to results/archive/sweep_adx_20260512/sanity.md. The
ADX representative (N=15, thr=30) is NOT modified by these checks per
user directive.
"""
from __future__ import annotations

import sys
from datetime import date

import numpy as np
import pandas as pd

from indicators.adx import compute_adx_series
from paths import ARCHIVE_DIR, BARS_PARQUET

ADX_N = 15
ADX_THR = 30
TRADES_FILE = ARCHIVE_DIR / "sweep_adx_20260512" / "trades" / "trades_adx_n15_thr30.parquet"
SANITY_OUT = ARCHIVE_DIR / "sweep_adx_20260512" / "sanity.md"


def main():
    print(f"Loading trades from {TRADES_FILE.name}...", flush=True)
    trades = pd.read_parquet(TRADES_FILE)
    print(f"  {len(trades):,} trades", flush=True)

    print(f"Loading bars and computing ADX({ADX_N}) at touch_bar - 1min...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    adx = compute_adx_series(bars, ADX_N)
    # ADX value at bar T-1 keyed by bar T's ts_utc (what the classifier looked up)
    adx_at_prior = pd.Series(adx.shift(1).to_numpy(), index=bars["ts_utc"].to_numpy())
    trades["adx_at_entry_minus_1"] = trades["entry_time"].map(lambda t: adx_at_prior.get(t, np.nan))

    # SANITY 2 — mean ADX at TREND vs FADE entries
    by_label = trades.groupby("cluster_label")["adx_at_entry_minus_1"].agg(
        ["count", "mean", "min", "max", "std"]
    )

    # SANITY 1 — monthly distribution of TREND trades + P&L
    trades["month"] = pd.to_datetime(trades["session_date"]).dt.to_period("M")
    trend_only = trades[trades["cluster_label"] == "TREND"].copy()
    fade_only = trades[trades["cluster_label"] == "FADE"].copy()

    monthly_trend = trend_only.groupby("month").agg(
        n_trend=("pnl_dollars", "count"),
        trend_pnl=("pnl_dollars", "sum"),
        trend_win_rate=("pnl_dollars", lambda s: (s > 0).mean()),
    )
    monthly_fade = fade_only.groupby("month").agg(
        n_fade=("pnl_dollars", "count"),
        fade_pnl=("pnl_dollars", "sum"),
    )
    monthly = monthly_trend.join(monthly_fade, how="outer").fillna(0)
    monthly["combined_pnl"] = monthly["trend_pnl"] + monthly["fade_pnl"]

    # Concentration check — what fraction of TREND P&L comes from top-5 months?
    trend_pnl_sorted = monthly["trend_pnl"].sort_values(ascending=False)
    top5_share = float(trend_pnl_sorted.head(5).sum() / trend_pnl_sorted.sum()) if trend_pnl_sorted.sum() != 0 else float("nan")
    n_positive_months = int((monthly["trend_pnl"] > 0).sum())
    n_negative_months = int((monthly["trend_pnl"] < 0).sum())
    n_zero_months = int((monthly["trend_pnl"] == 0).sum())
    total_months = len(monthly)

    write_report(by_label, monthly, top5_share, n_positive_months, n_negative_months,
                 n_zero_months, total_months, trend_only, fade_only)

    print("\nSummary:")
    print(f"  Mean ADX(15) at TREND entries: {by_label.loc['TREND','mean']:.2f}")
    print(f"  Mean ADX(15) at FADE entries:  {by_label.loc['FADE','mean']:.2f}")
    print(f"  TREND months: {total_months} ({n_positive_months}+ / {n_negative_months}- / {n_zero_months}=0)")
    print(f"  Top-5-month share of TREND P&L: {top5_share:.1%}")
    print(f"  Sanity report: {SANITY_OUT}")


def write_report(by_label, monthly, top5_share, n_pos, n_neg, n_zero, n_total,
                 trend_df, fade_df):
    lines: list[str] = []
    lines.append(f"# ADX sanity checks — ADX(N={ADX_N}, thr={ADX_THR})")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Trades file:** `{TRADES_FILE.name}`")
    lines.append(f"**Representative is LOCKED — no re-sweep regardless of findings.**")
    lines.append("")

    # SANITY 2 — threshold separation
    lines.append("## Sanity 2 — Mean ADX(15) at TREND vs FADE entries")
    lines.append("")
    lines.append("Confirms the threshold mechanically separates the populations as labeled.")
    lines.append(f"Threshold = {ADX_THR}. Expect mean(TREND) > 30 > mean(FADE).")
    lines.append("")
    lines.append("| Label | count | mean | min | max | stdev |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for label in by_label.index:
        row = by_label.loc[label]
        lines.append(
            f"| {label} | {int(row['count']):,} | {row['mean']:.2f} | "
            f"{row['min']:.2f} | {row['max']:.2f} | {row['std']:.2f} |"
        )
    lines.append("")

    tmean = by_label.loc["TREND", "mean"]
    fmean = by_label.loc["FADE", "mean"]
    tmin = by_label.loc["TREND", "min"]
    fmax = by_label.loc["FADE", "max"]
    verdict = []
    if tmin >= ADX_THR:
        verdict.append(f"All TREND entries have ADX(15) ≥ {ADX_THR} (clean separation above threshold)")
    else:
        verdict.append(f"WARN: some TREND entries below {ADX_THR} (likely NaN warm-up handling)")
    if fmax < ADX_THR:
        verdict.append(f"All FADE entries have ADX(15) < {ADX_THR} (clean separation below threshold)")
    else:
        verdict.append(f"WARN: some FADE entries at/above {ADX_THR} — investigate")
    if tmean > fmean:
        verdict.append(f"Mean ADX at TREND ({tmean:.2f}) > mean at FADE ({fmean:.2f}) — separation correct")
    else:
        verdict.append(f"WARN: mean TREND ({tmean:.2f}) <= mean FADE ({fmean:.2f})")
    lines.append("**Verdict:**")
    for v in verdict:
        lines.append(f"- {v}")
    lines.append("")

    # SANITY 1 — temporal distribution
    lines.append("## Sanity 1 — Monthly distribution of TREND trades + P&L")
    lines.append("")
    lines.append("Looking for wins distributed across time, not concentrated in a few months.")
    lines.append("")
    lines.append(f"**TREND trades total:** {len(trend_df):,}  P&L ${trend_df['pnl_dollars'].sum():,.0f}")
    lines.append(f"**FADE trades total:**  {len(fade_df):,}  P&L ${fade_df['pnl_dollars'].sum():,.0f}")
    lines.append(f"**Months with TREND activity:** {n_total}")
    lines.append(f"  - positive TREND P&L months: {n_pos}")
    lines.append(f"  - negative TREND P&L months: {n_neg}")
    lines.append(f"  - zero/break-even months: {n_zero}")
    lines.append(f"**Top-5-month share of TREND P&L:** {top5_share:.1%}")
    lines.append("")

    concentration_verdict = (
        "  HIGH concentration — TREND edge driven by few months (potentially regime-specific)"
        if top5_share > 0.60
        else (
            "  MODERATE concentration — edge meaningfully cross-temporal but with outlier months"
            if top5_share > 0.40
            else "  LOW concentration — TREND wins distributed across many months"
        )
    )
    lines.append("**Concentration verdict:**")
    lines.append(concentration_verdict)
    lines.append("")

    lines.append("### Monthly breakdown")
    lines.append("")
    lines.append("| Month | n_TREND | TREND P&L | TREND WR | n_FADE | FADE P&L | Combined |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for m, row in monthly.iterrows():
        nt = int(row.get("n_trend", 0))
        wr = row.get("trend_win_rate", 0)
        wr_str = f"{wr:.0%}" if nt > 0 else "—"
        lines.append(
            f"| {m} | {nt} | ${row['trend_pnl']:,.0f} | {wr_str} | "
            f"{int(row.get('n_fade', 0))} | ${row['fade_pnl']:,.0f} | ${row['combined_pnl']:,.0f} |"
        )

    SANITY_OUT.write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main() or 0)
