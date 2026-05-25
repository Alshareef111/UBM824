"""Phase 7 — Three quantitative analyses for final assessment.

1. Window-trend regression slope ($/window) for the 6 deploy-qualifying configs.
   Linear fit of OOS P&L vs window index 1..7. Healthy = near zero or positive.
   Significantly negative slopes = deployment concern (signal decay).

2. Discrimination check on DI(15,8): compare DI's actual sharpe/median/total
   against the distribution from 30 BiasedRandom(seed, trend_prob=0.73) seeds.
   Tests whether DI is genuinely SELECTING clusters or just IMPOSING a 73% TREND
   directional bias that happened to fit history.

3. AllFade vs ADX∧DI on 2026 partial (Jan-Apr 2026). Tells us whether the
   composite preserves the strategy's recent edge in the most recent
   unverified data.

Output: results/archive/phase7_20260512/
"""
from __future__ import annotations

import sys
import time
from datetime import date

import numpy as np
import pandas as pd

from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.base import BiasedRandom
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs
from simulator_v2 import run_backtest, trades_to_dataframe
import walk_forward as wf

N_BIASED_SEEDS = 30
DI_TREND_PROB = 0.73  # observed DI(15,8) TREND ratio = 1237/1693

TODAY = date.today().strftime("%Y%m%d")
OUT_DIR = ARCHIVE_DIR / f"phase7_{TODAY}"
COMPOSITE_DIR = ARCHIVE_DIR / "composite_20260512"
LOCKED_BASELINE = ARCHIVE_DIR / "trades_baseline_extended_20260511.parquet"


# ============================================================
# ANALYSIS 1 — window-trend regression
# ============================================================

def analysis_1_window_trend():
    """Linear regression slope of OOS P&L vs window index for 6 deploy-qualifying configs."""
    summary = pd.read_parquet(COMPOSITE_DIR / "phase6_summary.parquet")
    deploy = summary[summary["qualifies_deploy"]].copy()
    deploy = deploy.sort_values("oos_sharpe_like", ascending=False).reset_index(drop=True)

    rows = []
    window_cols = [f"oos_W{i}" for i in range(1, 8)]
    x = np.arange(1, 8, dtype=float)
    n = len(x)

    for r in deploy.itertuples():
        y = np.array([getattr(r, c) for c in window_cols], dtype=float)
        # OLS via numpy
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        # Std-error of slope: sqrt(ss_res / (n-2) / sum((x - x̄)²))
        x_var = float(np.sum((x - x.mean()) ** 2))
        stderr = float(np.sqrt((ss_res / (n - 2)) / x_var)) if x_var > 0 and n > 2 else float("nan")
        # t-statistic for slope=0 hypothesis; df=n-2=5
        t_stat = float(slope / stderr) if stderr > 0 else float("nan")
        rows.append({
            "label": r.label,
            "sharpe": r.oos_sharpe_like,
            "median_oos": r.oos_median,
            "slope_per_window": float(slope),
            "intercept": float(intercept),
            "r_squared": r_squared,
            "stderr": stderr,
            "t_stat": t_stat,
            "W1": float(y[0]), "W7": float(y[-1]),
            "drift_W1_to_W7": float(y[-1] - y[0]),
            **{f"W{i+1}": float(y[i]) for i in range(7)},
        })
    return pd.DataFrame(rows)


# ============================================================
# ANALYSIS 2 — discrimination check on DI(15,8)
# ============================================================

def analysis_2_discrimination(bars, orb_table, windows):
    """Compare DI(15,8) scores to N_BIASED_SEEDS BiasedRandom(trend=0.73) seeds."""
    # Re-run DI(15,8) to get its actual scores
    print("  Re-running DI(15,8) for baseline scores...", flush=True)
    di_lk = di_lookup(bars, n=15)
    di_clf = DiClassifier(di_lk, n=15, threshold=8)
    di_trades = run_backtest(bars, orb_table, di_clf)
    di_df = trades_to_dataframe(di_trades)
    di_pw = wf.per_window_pnl(di_df, windows, slice_="oos")
    di_actual = {
        "label": "DI(15,8) actual",
        "n_trades": len(di_df),
        "n_fade": int((di_df["cluster_label"] == "FADE").sum()),
        "n_trend": int((di_df["cluster_label"] == "TREND").sum()),
        "total_pnl": float(di_df["pnl_dollars"].sum()),
        "oos_median": wf.median_pnl(di_pw),
        "oos_sharpe_like": wf.sharpe_like_score(di_pw),
        "oos_sign_count": wf.sign_stability_count(di_pw),
    }
    actual_trend_frac = di_actual["n_trend"] / di_actual["n_trades"]
    print(f"  DI(15,8) actual: trend_frac={actual_trend_frac:.3f}  sharpe={di_actual['oos_sharpe_like']:.2f}", flush=True)

    print(f"\n  Running {N_BIASED_SEEDS} BiasedRandom(trend_prob={DI_TREND_PROB}) seeds...", flush=True)
    rand_rows = []
    for seed in range(1, N_BIASED_SEEDS + 1):
        t0 = time.time()
        clf = BiasedRandom(seed=seed, trend_prob=DI_TREND_PROB)
        trades = run_backtest(bars, orb_table, clf)
        df = trades_to_dataframe(trades)
        pw = wf.per_window_pnl(df, windows, slice_="oos")
        rand_rows.append({
            "seed": seed,
            "n_trades": len(df),
            "n_fade": int((df["cluster_label"] == "FADE").sum()),
            "n_trend": int((df["cluster_label"] == "TREND").sum()),
            "trend_frac": int((df["cluster_label"] == "TREND").sum()) / max(1, len(df)),
            "total_pnl": float(df["pnl_dollars"].sum()),
            "oos_median": wf.median_pnl(pw),
            "oos_sharpe_like": wf.sharpe_like_score(pw),
            "oos_sign_count": wf.sign_stability_count(pw),
        })
        print(f"    seed={seed:>2}  trend_frac={rand_rows[-1]['trend_frac']:.3f}  "
              f"sharpe={rand_rows[-1]['oos_sharpe_like']:.2f}  "
              f"median=${rand_rows[-1]['oos_median']:>5.0f}  "
              f"total=${rand_rows[-1]['total_pnl']:>6.0f}  [{time.time()-t0:.1f}s]", flush=True)

    rand_df = pd.DataFrame(rand_rows)

    # Compute percentile of DI's actual score within the random distribution
    sharpe_pct = float((rand_df["oos_sharpe_like"] < di_actual["oos_sharpe_like"]).mean())
    median_pct = float((rand_df["oos_median"] < di_actual["oos_median"]).mean())
    total_pct = float((rand_df["total_pnl"] < di_actual["total_pnl"]).mean())

    discrimination = {
        "di_actual": di_actual,
        "biased_random_distribution": {
            "n_seeds": N_BIASED_SEEDS,
            "trend_prob": DI_TREND_PROB,
            "sharpe_mean": float(rand_df["oos_sharpe_like"].mean()),
            "sharpe_median": float(rand_df["oos_sharpe_like"].median()),
            "sharpe_p95": float(rand_df["oos_sharpe_like"].quantile(0.95)),
            "sharpe_max": float(rand_df["oos_sharpe_like"].max()),
            "median_mean": float(rand_df["oos_median"].mean()),
            "median_p95": float(rand_df["oos_median"].quantile(0.95)),
            "median_max": float(rand_df["oos_median"].max()),
            "total_mean": float(rand_df["total_pnl"].mean()),
            "total_p95": float(rand_df["total_pnl"].quantile(0.95)),
            "total_max": float(rand_df["total_pnl"].max()),
        },
        "di_percentile_within_random": {
            "sharpe": sharpe_pct,
            "median": median_pct,
            "total": total_pct,
        },
    }
    return discrimination, rand_df


# ============================================================
# ANALYSIS 3 — AllFade vs ADX∧DI on 2026 Jan-April
# ============================================================

def analysis_3_2026_period():
    """Compare locked baseline (AllFade) to ADX∧DI on Jan-Apr 2026."""
    baseline_trades = pd.read_parquet(LOCKED_BASELINE)
    adxdi_trades = pd.read_parquet(COMPOSITE_DIR / "trades" / "trades_B_ADXANDDI_unanimous.parquet")

    start_2026 = pd.Timestamp("2026-01-01")
    end_period = pd.Timestamp("2026-05-01")

    base_sd = pd.to_datetime(baseline_trades["session_date"])
    adx_sd = pd.to_datetime(adxdi_trades["session_date"])

    base_2026 = baseline_trades[(base_sd >= start_2026) & (base_sd < end_period)].copy()
    adx_2026 = adxdi_trades[(adx_sd >= start_2026) & (adx_sd < end_period)].copy()

    base_2026["month"] = pd.to_datetime(base_2026["session_date"]).dt.to_period("M")
    adx_2026["month"] = pd.to_datetime(adx_2026["session_date"]).dt.to_period("M")

    def summarize(df, label):
        return {
            "label": label,
            "n_trades": len(df),
            "total_pnl": float(df["pnl_dollars"].sum()) if len(df) else 0.0,
            "win_rate": float((df["pnl_dollars"] > 0).mean()) if len(df) else float("nan"),
            "monthly": df.groupby("month").agg(
                n=("pnl_dollars", "count"),
                pnl=("pnl_dollars", "sum"),
                wr=("pnl_dollars", lambda s: (s > 0).mean()),
            ),
        }

    base = summarize(base_2026, "AllFade (locked baseline)")
    adxdi = summarize(adx_2026, "ADX∧DI unanimous (deployment winner)")
    return base, adxdi


# ============================================================
# Driver
# ============================================================

def main():
    ensure_dirs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading bars + ORB table for re-runs...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    windows = wf.make_windows()

    # ANALYSIS 1
    print("\n=== Analysis 1: Window-trend regression ===", flush=True)
    a1 = analysis_1_window_trend()
    a1.to_parquet(OUT_DIR / "window_trend.parquet", index=False)
    print(a1[["label", "sharpe", "slope_per_window", "r_squared", "t_stat", "drift_W1_to_W7"]].to_string(index=False), flush=True)

    # ANALYSIS 2
    print("\n=== Analysis 2: DI discrimination check ===", flush=True)
    a2, rand_df = analysis_2_discrimination(bars, orb_table, windows)
    rand_df.to_parquet(OUT_DIR / "discrimination_biased_random.parquet", index=False)

    print(f"\n  DI(15,8) actual scores:")
    print(f"    sharpe={a2['di_actual']['oos_sharpe_like']:.2f}  "
          f"median=${a2['di_actual']['oos_median']:.0f}  "
          f"total=${a2['di_actual']['total_pnl']:.0f}  "
          f"trend_frac={a2['di_actual']['n_trend']/a2['di_actual']['n_trades']:.3f}")
    print(f"\n  BiasedRandom(73%) distribution over {N_BIASED_SEEDS} seeds:")
    d = a2['biased_random_distribution']
    print(f"    sharpe: mean={d['sharpe_mean']:.2f}  p95={d['sharpe_p95']:.2f}  max={d['sharpe_max']:.2f}")
    print(f"    median: mean=${d['median_mean']:.0f}  p95=${d['median_p95']:.0f}  max=${d['median_max']:.0f}")
    print(f"    total:  mean=${d['total_mean']:.0f}  p95=${d['total_p95']:.0f}  max=${d['total_max']:.0f}")
    p = a2['di_percentile_within_random']
    print(f"\n  DI percentile within random:  sharpe={p['sharpe']:.1%}  median={p['median']:.1%}  total={p['total']:.1%}")

    # ANALYSIS 3
    print("\n=== Analysis 3: AllFade vs ADX∧DI on 2026 Jan-Apr ===", flush=True)
    base, adxdi = analysis_3_2026_period()
    print(f"\n  AllFade (locked baseline):       trades={base['n_trades']:>4}  total=${base['total_pnl']:>7.0f}  WR={base['win_rate']:.1%}")
    print(f"  ADX∧DI unanimous (deployment):   trades={adxdi['n_trades']:>4}  total=${adxdi['total_pnl']:>7.0f}  WR={adxdi['win_rate']:.1%}")
    print(f"\n  AllFade monthly:")
    print(base["monthly"].to_string())
    print(f"\n  ADX∧DI monthly:")
    print(adxdi["monthly"].to_string())

    # Write report
    write_report(a1, a2, rand_df, base, adxdi)

    print(f"\nTotal elapsed: {(time.time()-t0)/60:.1f} min", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


def write_report(a1, a2, rand_df, base, adxdi):
    lines: list[str] = []
    lines.append("# Phase 7 — Quantitative Analyses")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("")

    # Analysis 1
    lines.append("## Analysis 1 — Window-trend regression on deploy-qualifying configs")
    lines.append("")
    lines.append("Linear regression of OOS P&L vs window index (W1..W7).")
    lines.append("Slope ≥ 0 = healthy / no decay. Significantly negative = signal weakening across time.")
    lines.append("")
    lines.append("Note: 7 windows give df=5 for OLS. |t| > 2.57 ≈ p<0.05 two-tailed; |t| > 4.03 ≈ p<0.01.")
    lines.append("")
    lines.append("| Config | sharpe | slope $/window | r² | t-stat | W1 P&L | W7 P&L | drift |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in a1.itertuples():
        lines.append(
            f"| {r.label} | {r.sharpe:.2f} | "
            f"{r.slope_per_window:+,.0f} | {r.r_squared:.2f} | {r.t_stat:+.2f} | "
            f"${r.W1:,.0f} | ${r.W7:,.0f} | ${r.drift_W1_to_W7:+,.0f} |"
        )
    lines.append("")
    lines.append("**Interpretation:**")
    deploy_winner = a1.iloc[0]
    lines.append(f"- **B ADX∧DI unanimous** (deployment winner): slope `${deploy_winner['slope_per_window']:+,.0f}/window`, "
                 f"r²={deploy_winner['r_squared']:.2f}, t={deploy_winner['t_stat']:+.2f}. Drift W1→W7: ${deploy_winner['drift_W1_to_W7']:+,.0f}.")
    healthy = a1[a1["slope_per_window"] > -50]
    severe = a1[a1["slope_per_window"] < -150]
    lines.append(f"- **{len(healthy)} of {len(a1)} configs** show healthy slope (>-$50/window).")
    if len(severe) > 0:
        lines.append(f"- **Severe-decay configs** (slope < -$150/window): " + ", ".join(severe["label"].tolist()))
    lines.append("")

    # Analysis 2
    lines.append("## Analysis 2 — DI(15,8) discrimination check")
    lines.append("")
    lines.append(f"Comparing DI(15,8) actual scores against {N_BIASED_SEEDS} BiasedRandom(trend_prob={DI_TREND_PROB}) seeds.")
    lines.append("Random labeling preserves DI's TREND bias (73%) but otherwise selects clusters randomly.")
    lines.append("If DI is genuinely *selecting* high-conviction clusters, its scores should exceed this null.")
    lines.append("If DI is merely *imposing* a 73% TREND bias that happens to fit, scores should be average.")
    lines.append("")
    d = a2["biased_random_distribution"]
    actual = a2["di_actual"]
    p = a2["di_percentile_within_random"]
    lines.append("| Metric | DI(15,8) actual | Random p50 | Random p95 | Random max | DI percentile |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(f"| Sharpe-like | **{actual['oos_sharpe_like']:.2f}** | {d['sharpe_median']:.2f} | {d['sharpe_p95']:.2f} | {d['sharpe_max']:.2f} | **{p['sharpe']:.1%}** |")
    lines.append(f"| Median OOS | **${actual['oos_median']:,.0f}** | ${d['median_mean']:,.0f} | ${d['median_p95']:,.0f} | ${d['median_max']:,.0f} | **{p['median']:.1%}** |")
    lines.append(f"| Total P&L | **${actual['total_pnl']:,.0f}** | ${d['total_mean']:,.0f} | ${d['total_p95']:,.0f} | ${d['total_max']:,.0f} | **{p['total']:.1%}** |")
    lines.append("")
    lines.append("**Interpretation:**")
    if p["sharpe"] >= 0.95 and p["median"] >= 0.95:
        lines.append("- DI's scores exceed the 95th percentile of the same-bias random distribution on both")
        lines.append("  Sharpe-like and median. **Strong evidence that DI is selecting good clusters,**")
        lines.append("  not just imposing a directional bias.")
    elif p["sharpe"] >= 0.80 and p["median"] >= 0.80:
        lines.append("- DI's scores exceed the 80th percentile of the random distribution. **Moderate evidence**")
        lines.append("  of genuine selection beyond the directional bias.")
    else:
        lines.append(f"- DI's percentiles within the random distribution are: sharpe={p['sharpe']:.0%}, median={p['median']:.0%}, total={p['total']:.0%}.")
        lines.append("  Substantial fraction of DI's edge appears attributable to the 73% TREND bias alone.")
        lines.append("  **Weak discrimination — the indicator's selection adds limited value beyond the bias.**")
    lines.append("")

    # Analysis 3
    lines.append("## Analysis 3 — AllFade vs ADX∧DI on 2026 partial (Jan-Apr 2026)")
    lines.append("")
    lines.append("Tests whether the unanimous composite preserves edge in the most recent unverified period.")
    lines.append("")
    lines.append("| | trades | total P&L | win rate |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| **AllFade (locked baseline)** | {base['n_trades']} | ${base['total_pnl']:,.0f} | {base['win_rate']:.1%} |")
    lines.append(f"| **ADX∧DI unanimous (deployment)** | {adxdi['n_trades']} | ${adxdi['total_pnl']:,.0f} | {adxdi['win_rate']:.1%} |")
    lines.append("")
    lines.append("### Monthly breakdown")
    lines.append("")
    lines.append("| Month | AllFade trades | AllFade P&L | AllFade WR | ADX∧DI trades | ADX∧DI P&L | ADX∧DI WR |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    months = sorted(set(base["monthly"].index) | set(adxdi["monthly"].index))
    for m in months:
        b_row = base["monthly"].loc[m] if m in base["monthly"].index else None
        a_row = adxdi["monthly"].loc[m] if m in adxdi["monthly"].index else None
        b_n = int(b_row["n"]) if b_row is not None else 0
        b_p = float(b_row["pnl"]) if b_row is not None else 0.0
        b_w = b_row["wr"] if b_row is not None else float("nan")
        a_n = int(a_row["n"]) if a_row is not None else 0
        a_p = float(a_row["pnl"]) if a_row is not None else 0.0
        a_w = a_row["wr"] if a_row is not None else float("nan")
        lines.append(
            f"| {m} | {b_n} | ${b_p:,.0f} | {b_w:.0%} | {a_n} | ${a_p:,.0f} | {a_w:.0%} |"
            if a_n > 0 and b_n > 0 else
            f"| {m} | {b_n} | ${b_p:,.0f} | {f'{b_w:.0%}' if b_n > 0 else '—'} | "
            f"{a_n} | ${a_p:,.0f} | {f'{a_w:.0%}' if a_n > 0 else '—'} |"
        )
    lines.append("")
    if adxdi["total_pnl"] > base["total_pnl"]:
        lines.append(f"**ADX∧DI outperforms AllFade in 2026-partial by ${adxdi['total_pnl'] - base['total_pnl']:,.0f}.** Recent edge preserved.")
    else:
        lines.append(f"**ADX∧DI underperforms AllFade in 2026-partial by ${base['total_pnl'] - adxdi['total_pnl']:,.0f}.** "
                     f"Recent regime may diverge — deployment concern.")
    lines.append("")

    (OUT_DIR / "report.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'report.md'}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
