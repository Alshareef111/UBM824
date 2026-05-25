"""Re-validate the V2 deployment winner under the dynamic-TP exit rule.

ADX(15,30) ∧ DI(15,8) unanimous (LOCKED — not re-swept) re-run with the
new exit logic:
  - Stop: 30 pts fixed (unchanged)
  - Target: nearest cluster boundary in trade direction at entry, regardless
    of touched/untouched status
  - Fallback: 30 pts fixed if no cluster exists in trade direction

Reports:
  1. Per-window OOS P&L (walk-forward 7 windows)
  2. Exit-type breakdown: cluster-target / stop / force-close / fallback-30pt
  3. Win rate, mean per-trade P&L, max drawdown
  4. Sharpe-like score + 4-gate qualification (null p95 = 1.06)
  5. TP-distance distribution
  6. Side-by-side with fixed 30/30

Output: results/archive/dynamic_tp_20260512/
"""
from __future__ import annotations

import sys
import time
from datetime import date

import numpy as np
import pandas as pd

from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.base import UnanimousClassifier
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET
import simulator_v2_dyntp as sim_dyn
import walk_forward as wf

ADX_N, ADX_THR = 15, 30
DI_N, DI_THR = 15, 8

OUT_DIR = ARCHIVE_DIR / "dynamic_tp_20260512"
V2_3030_FIXED = ARCHIVE_DIR / "trades_regime_v2_20260512.parquet"

POINT_VALUE_USD = 2.0
ANNUALIZATION = 252


def headline_stats(df: pd.DataFrame, all_sessions: pd.DatetimeIndex) -> dict:
    if len(df) == 0:
        return {}
    wins = df["pnl_dollars"] > 0
    losses = df["pnl_dollars"] < 0
    win_pnls = df.loc[wins, "pnl_dollars"]
    loss_pnls = df.loc[losses, "pnl_dollars"]
    daily = df.groupby("session_date")["pnl_dollars"].sum()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.reindex(all_sessions, fill_value=0.0)
    eq = daily.cumsum()
    dd = eq - eq.cummax()
    max_dd = float(dd.min())
    trough = dd.idxmin()
    peak_d = eq.loc[:trough].idxmax()
    peak_val = eq.loc[:trough].max()
    after = eq.loc[trough:]
    rec_mask = after >= peak_val
    if rec_mask.any():
        rec_d = rec_mask.idxmax()
        dur = (rec_d - peak_d).days
    else:
        rec_d = None
        dur = (eq.index[-1] - peak_d).days
    sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(ANNUALIZATION)) if daily.std(ddof=1) > 0 else float("nan")
    downside = float(np.sqrt(((daily.clip(upper=0.0)) ** 2).mean()))
    sortino = float(daily.mean() / downside * np.sqrt(ANNUALIZATION)) if downside > 0 else float("nan")
    return {
        "n_trades": int(len(df)),
        "n_wins": int(wins.sum()),
        "n_losses": int(losses.sum()),
        "win_rate": float(wins.mean()),
        "total_pnl": float(df["pnl_dollars"].sum()),
        "mean_pnl": float(df["pnl_dollars"].mean()),
        "avg_winner": float(win_pnls.mean()) if len(win_pnls) else 0.0,
        "avg_loser": float(loss_pnls.mean()) if len(loss_pnls) else 0.0,
        "profit_factor": float(win_pnls.sum() / -loss_pnls.sum()) if len(loss_pnls) and loss_pnls.sum() < 0 else float("inf"),
        "max_dd": max_dd,
        "max_dd_duration_days": int(dur),
        "max_dd_recovered": rec_d is not None,
        "sharpe_ann": sharpe,
        "sortino_ann": sortino,
    }


def walk_forward_scores(df: pd.DataFrame) -> dict:
    windows = wf.make_windows()
    pw = wf.per_window_pnl(df, windows, slice_="oos")
    total = float(df["pnl_dollars"].sum())
    return {
        "wf_sharpe_like": wf.sharpe_like_score(pw),
        "wf_median_oos": wf.median_pnl(pw),
        "wf_sign_count": wf.sign_stability_count(pw),
        "wf_oos_sum": float(sum(pw.values())),
        "wf_qualifies_deploy": wf.qualifies(pw, total_pnl=total, sharpe_threshold=wf.NULL_P95_SHARPE_LIKE),
        **{f"oos_{w.name}": pw[w.name] for w in windows},
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)

    print("Pre-computing ADX(15) and DI(15) lookups...", flush=True)
    adx_lk = adx_lookup(bars, n=ADX_N)
    di_lk = di_lookup(bars, n=DI_N)

    adx_clf = AdxClassifier(adx_lk, n=ADX_N, threshold=ADX_THR)
    di_clf = DiClassifier(di_lk, n=DI_N, threshold=DI_THR)
    unan = UnanimousClassifier([adx_clf, di_clf], name=f"ADX({ADX_N},{ADX_THR})∧DI({DI_N},{DI_THR}) dyntp")

    print("\nRunning simulator_v2_dyntp...", flush=True)
    t = time.time()
    trades = sim_dyn.run_backtest(bars, orb_table, unan)
    dyn_df = sim_dyn.trades_to_dataframe(trades)
    print(f"  {len(dyn_df)} trades  total ${dyn_df['pnl_dollars'].sum():,.2f}  [{time.time()-t:.1f}s]", flush=True)
    dyn_df.to_parquet(OUT_DIR / "trades_v2_dyntp.parquet", index=False)

    # Load fixed-30/30 v2 for comparison
    fixed_df = pd.read_parquet(V2_3030_FIXED)

    # Build all-sessions index
    all_dates = set(pd.to_datetime(dyn_df["session_date"])) | set(pd.to_datetime(fixed_df["session_date"]))
    all_sessions = pd.DatetimeIndex(sorted(all_dates))

    # Headline + walk-forward
    h_dyn = headline_stats(dyn_df, all_sessions)
    h_fixed = headline_stats(fixed_df, all_sessions)
    wf_dyn = walk_forward_scores(dyn_df)
    wf_fixed = walk_forward_scores(fixed_df)

    # Exit breakdown for dyntp: split target by source
    exit_rows = []
    for label, mask in [
        ("cluster-target", (dyn_df["exit_reason"] == "target") & (dyn_df["target_source"] == "cluster")),
        ("fallback-30pt target", (dyn_df["exit_reason"] == "target") & (dyn_df["target_source"] == "fallback")),
        ("stop", dyn_df["exit_reason"] == "stop"),
        ("force-close", dyn_df["exit_reason"] == "force_close"),
    ]:
        sub = dyn_df[mask]
        wins = (sub["pnl_dollars"] > 0).sum() if len(sub) else 0
        exit_rows.append({
            "exit_type": label,
            "n_trades": int(len(sub)),
            "pct_of_total": float(len(sub) / len(dyn_df)) if len(dyn_df) else 0.0,
            "mean_pnl": float(sub["pnl_dollars"].mean()) if len(sub) else 0.0,
            "total_pnl": float(sub["pnl_dollars"].sum()),
            "win_rate": float(wins / len(sub)) if len(sub) else float("nan"),
            "mean_tp_distance_pts": float(sub["tp_distance_pts"].mean()) if len(sub) and "tp_distance_pts" in sub.columns else float("nan"),
        })
    exit_df = pd.DataFrame(exit_rows)
    exit_df.to_parquet(OUT_DIR / "exit_breakdown.parquet", index=False)

    # TP-distance distribution
    tp_dist = dyn_df["tp_distance_pts"].copy()
    tp_summary = {
        "min": float(tp_dist.min()),
        "p5": float(tp_dist.quantile(0.05)),
        "p25": float(tp_dist.quantile(0.25)),
        "median": float(tp_dist.median()),
        "p75": float(tp_dist.quantile(0.75)),
        "p95": float(tp_dist.quantile(0.95)),
        "max": float(tp_dist.max()),
        "mean": float(tp_dist.mean()),
    }
    # Histogram bins
    bins = [0, 5, 10, 15, 20, 25, 30, 35, 40, 50, 75, 100, 150, 200, float("inf")]
    bin_labels = [
        "0-5", "5-10", "10-15", "15-20", "20-25", "25-30", "30-35", "35-40",
        "40-50", "50-75", "75-100", "100-150", "150-200", "200+",
    ]
    counts, _ = np.histogram(tp_dist, bins=bins)
    hist_df = pd.DataFrame({"bucket_pts": bin_labels, "n_trades": counts})
    hist_df["pct"] = hist_df["n_trades"] / hist_df["n_trades"].sum()
    hist_df.to_parquet(OUT_DIR / "tp_distance_histogram.parquet", index=False)

    write_report(h_dyn, h_fixed, wf_dyn, wf_fixed, exit_df, hist_df, tp_summary, dyn_df, fixed_df)
    print(f"\nTotal elapsed: {(time.time()-t0):.1f}s", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


def write_report(h_dyn, h_fixed, wf_dyn, wf_fixed, exit_df, hist_df, tp_summary, dyn_df, fixed_df):
    fmt_money = lambda v: f"${v:,.0f}"
    fmt_pct = lambda v: f"{v:.1%}" if not pd.isna(v) else "—"
    fmt_money2 = lambda v: f"${v:,.2f}"

    lines: list[str] = []
    lines.append("# Dynamic-TP variant — ADX(15,30) ∧ DI(15,8) Unanimous")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("")
    lines.append("## Strategy modification")
    lines.append("")
    lines.append("- **Stop:** 30 pts fixed (unchanged)")
    lines.append("- **Take profit:** nearest cluster boundary in trade direction at entry, regardless of touched/untouched")
    lines.append("- **Fallback:** 30 pts fixed if no cluster in trade direction")
    lines.append("- All other geometry locked: 3-pt clusters, first-touch, C2, 9:46-11:30 NY, force-close at 11:30 open")
    lines.append("")
    lines.append("ADX∧DI parameters NOT re-swept per directive. Locked at N=15 / thr=30 (ADX) and thr=8 (DI).")
    lines.append("")

    # 6. Side-by-side header (placed first for context)
    lines.append("## 1+3+4+6. Headline + walk-forward — side-by-side vs fixed 30/30")
    lines.append("")
    lines.append("| Metric | dynamic-TP (this test) | fixed 30/30 (prior) | Δ |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Trades | {h_dyn['n_trades']:,} | {h_fixed['n_trades']:,} | {h_dyn['n_trades']-h_fixed['n_trades']:+,} |")
    lines.append(f"| Win rate | {fmt_pct(h_dyn['win_rate'])} | {fmt_pct(h_fixed['win_rate'])} | {(h_dyn['win_rate']-h_fixed['win_rate'])*100:+.1f}pp |")
    lines.append(f"| Total P&L | **{fmt_money(h_dyn['total_pnl'])}** | {fmt_money(h_fixed['total_pnl'])} | **{fmt_money(h_dyn['total_pnl']-h_fixed['total_pnl'])}** |")
    lines.append(f"| Mean / trade | {fmt_money2(h_dyn['mean_pnl'])} | {fmt_money2(h_fixed['mean_pnl'])} | {fmt_money2(h_dyn['mean_pnl']-h_fixed['mean_pnl'])} |")
    lines.append(f"| Avg winner | {fmt_money2(h_dyn['avg_winner'])} | {fmt_money2(h_fixed['avg_winner'])} | — |")
    lines.append(f"| Avg loser | {fmt_money2(h_dyn['avg_loser'])} | {fmt_money2(h_fixed['avg_loser'])} | — |")
    pf_dyn = f"{h_dyn['profit_factor']:.3f}" if h_dyn['profit_factor'] != float('inf') else "∞"
    pf_fixed = f"{h_fixed['profit_factor']:.3f}" if h_fixed['profit_factor'] != float('inf') else "∞"
    lines.append(f"| Profit factor | **{pf_dyn}** | {pf_fixed} | — |")
    lines.append(f"| Max drawdown | {fmt_money(h_dyn['max_dd'])} | {fmt_money(h_fixed['max_dd'])} | {fmt_money(h_dyn['max_dd']-h_fixed['max_dd'])} |")
    lines.append(f"| Max-DD duration (days) | {h_dyn['max_dd_duration_days']} | {h_fixed['max_dd_duration_days']} | — |")
    lines.append(f"| Annualized Sharpe | **{h_dyn['sharpe_ann']:.2f}** | {h_fixed['sharpe_ann']:.2f} | {h_dyn['sharpe_ann']-h_fixed['sharpe_ann']:+.2f} |")
    lines.append(f"| Annualized Sortino | **{h_dyn['sortino_ann']:.2f}** | {h_fixed['sortino_ann']:.2f} | {h_dyn['sortino_ann']-h_fixed['sortino_ann']:+.2f} |")
    lines.append(f"| Walk-forward Sharpe-like | **{wf_dyn['wf_sharpe_like']:.2f}** | {wf_fixed['wf_sharpe_like']:.2f} | {wf_dyn['wf_sharpe_like']-wf_fixed['wf_sharpe_like']:+.2f} |")
    lines.append(f"| Walk-forward median OOS | {fmt_money(wf_dyn['wf_median_oos'])} | {fmt_money(wf_fixed['wf_median_oos'])} | {fmt_money(wf_dyn['wf_median_oos']-wf_fixed['wf_median_oos'])} |")
    lines.append(f"| Walk-forward sign | {wf_dyn['wf_sign_count']}/7 | {wf_fixed['wf_sign_count']}/7 | — |")
    lines.append(f"| 4-gate deploy qualify | {'✓' if wf_dyn['wf_qualifies_deploy'] else 'NO'} | {'✓' if wf_fixed['wf_qualifies_deploy'] else 'NO'} | — |")
    lines.append("")

    # 1. Per-window OOS
    lines.append("## 1. Per-window OOS P&L")
    lines.append("")
    windows = wf.make_windows()
    lines.append("| Strategy | " + " | ".join(w.name for w in windows) + " | Sharpe-like |")
    lines.append("|---|" + "|".join(["---:"] * 7) + "|---:|")
    cells_dyn = [fmt_money(wf_dyn[f"oos_{w.name}"]) for w in windows]
    cells_fixed = [fmt_money(wf_fixed[f"oos_{w.name}"]) for w in windows]
    lines.append("| **dynamic-TP** | " + " | ".join(cells_dyn) + f" | {wf_dyn['wf_sharpe_like']:.2f} |")
    lines.append("| fixed 30/30 | " + " | ".join(cells_fixed) + f" | {wf_fixed['wf_sharpe_like']:.2f} |")
    delta = [wf_dyn[f"oos_{w.name}"] - wf_fixed[f"oos_{w.name}"] for w in windows]
    lines.append("| Δ | " + " | ".join(f"{v:+,.0f}" for v in delta) + " | — |")
    lines.append("")

    # 2. Exit-type breakdown
    lines.append("## 2. Exit-type breakdown (dynamic-TP)")
    lines.append("")
    lines.append("| Exit type | trades | % of total | mean P&L | total P&L | win rate | mean TP dist (pts) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in exit_df.itertuples():
        tp_str = f"{r.mean_tp_distance_pts:.1f}" if not pd.isna(r.mean_tp_distance_pts) else "—"
        lines.append(
            f"| **{r.exit_type}** | {r.n_trades} | {fmt_pct(r.pct_of_total)} | "
            f"{fmt_money2(r.mean_pnl)} | {fmt_money(r.total_pnl)} | "
            f"{fmt_pct(r.win_rate)} | {tp_str} |"
        )
    lines.append("")

    # 5. TP-distance distribution
    lines.append("## 5. TP-distance distribution (set-at-entry)")
    lines.append("")
    lines.append("Summary stats:")
    lines.append("")
    lines.append("| min | p5 | p25 | median | mean | p75 | p95 | max |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    s = tp_summary
    lines.append(f"| {s['min']:.1f} | {s['p5']:.1f} | {s['p25']:.1f} | {s['median']:.1f} | {s['mean']:.1f} | {s['p75']:.1f} | {s['p95']:.1f} | {s['max']:.1f} |")
    lines.append("")
    lines.append("Compare to old fixed TP = 30.0 pts. Mean TP distance under dynamic rule = "
                 f"{s['mean']:.1f} pts; median = {s['median']:.1f} pts.")
    lines.append("")
    lines.append("Histogram of TP distance (pts) at entry:")
    lines.append("")
    lines.append("| bucket (pts) | trades | % |")
    lines.append("|---|---:|---:|")
    for r in hist_df.itertuples():
        if r.n_trades > 0:
            lines.append(f"| {r.bucket_pts} | {int(r.n_trades)} | {r.pct:.1%} |")
    lines.append("")

    # Calendar-year quick
    dyn_df_yr = dyn_df.copy()
    dyn_df_yr["session_date"] = pd.to_datetime(dyn_df_yr["session_date"])
    dyn_df_yr["year"] = dyn_df_yr["session_date"].dt.year
    fixed_df_yr = fixed_df.copy()
    fixed_df_yr["session_date"] = pd.to_datetime(fixed_df_yr["session_date"])
    fixed_df_yr["year"] = fixed_df_yr["session_date"].dt.year
    lines.append("## Calendar-year P&L")
    lines.append("")
    lines.append("| Year | dyntp trades | dyntp P&L | fixed trades | fixed P&L | Δ |")
    lines.append("|---:|---:|---:|---:|---:|---:|")
    years = sorted(set(dyn_df_yr["year"]) | set(fixed_df_yr["year"]))
    for yr in years:
        d_sub = dyn_df_yr[dyn_df_yr["year"] == yr]
        f_sub = fixed_df_yr[fixed_df_yr["year"] == yr]
        d_pnl = float(d_sub["pnl_dollars"].sum())
        f_pnl = float(f_sub["pnl_dollars"].sum())
        lines.append(f"| {yr} | {len(d_sub)} | {fmt_money(d_pnl)} | {len(f_sub)} | {fmt_money(f_pnl)} | **{fmt_money(d_pnl - f_pnl)}** |")
    lines.append("")

    # Re-sweep flag
    lines.append("## Re-sweep flag")
    lines.append("")
    lines.append("Under the dynamic-TP rule, the effective R:R varies per trade. The ADX/DI thresholds were")
    lines.append("locked under the original fixed 30/30 R:R. Some considerations for whether to re-sweep:")
    lines.append("")
    sharpe_delta = wf_dyn["wf_sharpe_like"] - wf_fixed["wf_sharpe_like"]
    pnl_delta = h_dyn["total_pnl"] - h_fixed["total_pnl"]
    if sharpe_delta > 0 and pnl_delta > 0:
        lines.append(f"- **Both Sharpe ({sharpe_delta:+.2f}) and total P&L ({fmt_money(pnl_delta)}) improved under dynamic-TP.**")
        lines.append("- This is consistent with the current ADX/DI thresholds still being near-optimal.")
        lines.append("- Re-sweep is NOT strictly required if the current parameters generalize well to dynamic-TP.")
        lines.append("- **However**, the cluster-TP rule changes the effective payoff distribution. A re-sweep")
        lines.append("  could find parameters that are even better-aligned with the dynamic-TP profile.")
        lines.append("- **Recommendation:** propose re-sweep as a follow-up. Do not run without explicit approval.")
    else:
        lines.append(f"- Sharpe Δ {sharpe_delta:+.2f}, P&L Δ {fmt_money(pnl_delta)}.")
        lines.append("- Mixed or negative result under current ADX/DI thresholds.")
        lines.append("- A re-sweep under dynamic-TP could potentially restore or exceed the fixed-TP edge.")
        lines.append("- **Recommendation:** propose re-sweep as a follow-up. Do not run without explicit approval.")
    lines.append("")

    lines.append("## Files")
    lines.append("")
    lines.append("- `dynamic_tp_test.md` — this report")
    lines.append("- `trades_v2_dyntp.parquet` — ADX∧DI unanimous trades under dynamic-TP rule")
    lines.append("- `exit_breakdown.parquet` — exit-type stats (cluster-target / fallback / stop / force-close)")
    lines.append("- `tp_distance_histogram.parquet` — TP distance bucket distribution")

    (OUT_DIR / "dynamic_tp_test.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'dynamic_tp_test.md'}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
