"""SKIP analysis on the deployment winner — ADX(15,30) ∧ DI(15,8) unanimous.

SKIPs are cluster touches where the unanimous classifier returned Label.SKIP
(ADX and DI disagreed). The simulator consumes the cluster without firing a
trade. The trade output captures only FADE/TREND trades; SKIPs require
instrumenting the classifier call.

Recorded events (per SKIP):
  session_date, ts_utc (touch bar), cluster.low, cluster.high, cluster.size

Daily metrics:
  - Mean, median, p75, max SKIPs per trading session
  - % of sessions with 0 SKIPs
  - % of sessions where every cluster got SKIPPED (skips>0 AND trades==0)

Monthly metrics:
  - 7y × 12mo grid of absolute SKIP counts
  - 7y × 12mo grid of SKIP rate (skips / total cluster touches)
  - Linear regression: month index vs monthly skip rate.
    Rising rate would indicate ADX/DI increasingly disagree → regime drift.

Output: results/archive/strategy_report_20260512/skip_analysis.{md, parquet}
"""
from __future__ import annotations

import sys
import time
from datetime import date

import numpy as np
import pandas as pd

from clusters import Cluster
from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.base import Label, UnanimousClassifier
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs
from simulator_v2 import run_backtest, trades_to_dataframe

ADX_N, ADX_THR = 15, 30
DI_N, DI_THR = 15, 8

TODAY = date.today().strftime("%Y%m%d")
OUT_DIR = ARCHIVE_DIR / f"strategy_report_{TODAY}"


class RecordingUnanimous:
    """Wraps a UnanimousClassifier and records every SKIP event."""

    def __init__(self, inner: UnanimousClassifier):
        self.inner = inner
        self.skips: list[dict] = []
        self.n_fade = 0
        self.n_trend = 0
        self.name = inner.name

    def __call__(self, cluster: Cluster, touch_bar: dict, bars_today: pd.DataFrame) -> Label:
        label = self.inner(cluster, touch_bar, bars_today)
        if label == Label.SKIP:
            self.skips.append({
                "session_date": touch_bar["session_date"],
                "ts_utc": touch_bar["ts_utc"],
                "cluster_low": cluster.low,
                "cluster_high": cluster.high,
                "cluster_size": cluster.size,
            })
        elif label == Label.FADE:
            self.n_fade += 1
        elif label == Label.TREND:
            self.n_trend += 1
        return label


def main():
    ensure_dirs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)

    print("Pre-computing ADX and DI lookups...", flush=True)
    adx_lk = adx_lookup(bars, n=ADX_N)
    di_lk = di_lookup(bars, n=DI_N)

    adx_clf = AdxClassifier(adx_lk, n=ADX_N, threshold=ADX_THR)
    di_clf = DiClassifier(di_lk, n=DI_N, threshold=DI_THR)
    inner = UnanimousClassifier([adx_clf, di_clf], name=f"ADX({ADX_N},{ADX_THR})∧DI({DI_N},{DI_THR})")
    recorder = RecordingUnanimous(inner)

    print(f"Running simulator with recorder on {recorder.name}...", flush=True)
    trades = run_backtest(bars, orb_table, recorder)
    trades_df = trades_to_dataframe(trades)
    print(f"  trades fired: {len(trades_df)}  (FADE={recorder.n_fade}, TREND={recorder.n_trend})", flush=True)
    print(f"  SKIP events: {len(recorder.skips):,}", flush=True)
    total_touches = len(trades_df) + len(recorder.skips)
    print(f"  total cluster-touch events: {total_touches:,}", flush=True)

    # Save raw SKIPs
    skips_df = pd.DataFrame(recorder.skips)
    skips_df.to_parquet(OUT_DIR / "skip_analysis.parquet", index=False)
    print(f"  Wrote {OUT_DIR / 'skip_analysis.parquet'} ({len(skips_df):,} rows)", flush=True)

    # Build per-session table: trades + skips counted per session_date
    trades_per_session = trades_df.groupby("session_date").size().rename("n_trades")
    skips_per_session = skips_df.groupby("session_date").size().rename("n_skips") if len(skips_df) else pd.Series(dtype=int, name="n_skips")
    daily = pd.concat([trades_per_session, skips_per_session], axis=1).fillna(0).astype(int)
    daily.index = pd.to_datetime(daily.index)
    daily["n_clusters"] = daily["n_trades"] + daily["n_skips"]
    daily["skip_rate"] = daily["n_skips"] / daily["n_clusters"].replace(0, np.nan)

    # DAILY METRICS
    n_sessions = len(daily)
    mean_skips = daily["n_skips"].mean()
    median_skips = daily["n_skips"].median()
    p75_skips = daily["n_skips"].quantile(0.75)
    max_skips = daily["n_skips"].max()
    pct_zero_skip = (daily["n_skips"] == 0).mean() * 100
    # Whole-day skip: had cluster touches, all were SKIPs (n_skips > 0, n_trades == 0)
    whole_day_skip = ((daily["n_skips"] > 0) & (daily["n_trades"] == 0))
    pct_whole_day_skip = whole_day_skip.mean() * 100

    print(f"\nDaily metrics over {n_sessions:,} sessions:")
    print(f"  Mean SKIPs/session:   {mean_skips:.2f}")
    print(f"  Median SKIPs/session: {median_skips:.0f}")
    print(f"  p75 SKIPs/session:    {p75_skips:.0f}")
    print(f"  Max SKIPs/session:    {max_skips}")
    print(f"  % sessions with 0 SKIPs:        {pct_zero_skip:.1f}%")
    print(f"  % sessions with whole-day skip: {pct_whole_day_skip:.1f}%")

    # MONTHLY METRICS — 7y × 12mo grid
    daily["year"] = daily.index.year
    daily["month"] = daily.index.month
    monthly_skips = daily.groupby(["year", "month"])["n_skips"].sum().unstack(fill_value=0)
    monthly_total = daily.groupby(["year", "month"])["n_clusters"].sum().unstack(fill_value=0)
    monthly_rate = (monthly_skips / monthly_total.replace(0, np.nan)) * 100  # %

    # Linear regression: month-index vs monthly skip rate (flatten to a time-series)
    monthly_series = daily.groupby(daily.index.to_period("M")).agg(
        n_skips=("n_skips", "sum"),
        n_clusters=("n_clusters", "sum"),
    )
    monthly_series["skip_rate"] = monthly_series["n_skips"] / monthly_series["n_clusters"].replace(0, np.nan)
    monthly_series = monthly_series.dropna(subset=["skip_rate"])
    x = np.arange(len(monthly_series), dtype=float)
    y = monthly_series["skip_rate"].to_numpy() * 100  # percentage
    slope, intercept = np.polyfit(x, y, 1)
    y_pred = slope * x + intercept
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    n_months = len(monthly_series)
    x_var = float(np.sum((x - x.mean()) ** 2))
    stderr = float(np.sqrt((ss_res / (n_months - 2)) / x_var)) if x_var > 0 and n_months > 2 else float("nan")
    t_stat = float(slope / stderr) if stderr > 0 else float("nan")

    print(f"\nMonthly skip-rate trend (n={n_months} months):")
    print(f"  slope: {slope:+.3f} pp / month   intercept: {intercept:.2f}%")
    print(f"  r² = {r_squared:.3f}   t = {t_stat:+.2f}   (|t|>2 ≈ p<0.05 at df={n_months-2})")
    print(f"  fitted skip rate: month-1 → {intercept:.1f}%, month-{n_months} → {intercept + slope*(n_months-1):.1f}%")

    daily_to_save = daily.reset_index().rename(columns={"index": "session_date"})
    daily_to_save.to_parquet(OUT_DIR / "skip_analysis_daily.parquet", index=False)
    monthly_to_save = monthly_series.reset_index()
    monthly_to_save["year_month"] = monthly_to_save["session_date"].astype(str)
    monthly_to_save = monthly_to_save.drop(columns=["session_date"])
    monthly_to_save.to_parquet(OUT_DIR / "skip_analysis_monthly.parquet", index=False)

    write_report(
        n_sessions=n_sessions,
        trades_total=len(trades_df),
        n_fade=recorder.n_fade,
        n_trend=recorder.n_trend,
        n_skips=len(skips_df),
        total_touches=total_touches,
        mean_skips=mean_skips,
        median_skips=median_skips,
        p75_skips=p75_skips,
        max_skips=max_skips,
        pct_zero_skip=pct_zero_skip,
        pct_whole_day_skip=pct_whole_day_skip,
        monthly_skips=monthly_skips,
        monthly_rate=monthly_rate,
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        t_stat=t_stat,
        n_months=n_months,
        monthly_series=monthly_series,
    )

    print(f"\nTotal elapsed: {(time.time()-t0):.1f}s", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


def write_report(**kw):
    lines: list[str] = []
    lines.append("# SKIP analysis — ADX(15,30) ∧ DI(15,8) unanimous (deployment winner)")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Source:** R-012 deployment configuration. SKIPs captured via classifier instrumentation.")
    lines.append("")
    lines.append("SKIPs are cluster touches where ADX and DI emitted opposite labels (one FADE, one TREND).")
    lines.append("Under unanimous AND-gate, these clusters are consumed without firing a trade.")
    lines.append("")

    lines.append("## Headline counts (7 years, 1,805 ORB-eligible sessions)")
    lines.append("")
    lines.append(f"- **Trades fired:** {kw['trades_total']:,} (FADE={kw['n_fade']:,}, TREND={kw['n_trend']:,})")
    lines.append(f"- **SKIPs:** {kw['n_skips']:,}")
    lines.append(f"- **Total cluster-touch events:** {kw['total_touches']:,}")
    lines.append(f"- **Overall SKIP rate:** {100.0 * kw['n_skips'] / kw['total_touches']:.1f}%")
    lines.append("")

    lines.append("## Daily metrics")
    lines.append("")
    lines.append(f"Over {kw['n_sessions']:,} trading sessions:")
    lines.append("")
    lines.append("| Statistic | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Mean SKIPs per session | {kw['mean_skips']:.2f} |")
    lines.append(f"| Median SKIPs per session | {int(kw['median_skips'])} |")
    lines.append(f"| p75 SKIPs per session | {int(kw['p75_skips'])} |")
    lines.append(f"| Max SKIPs per session | {int(kw['max_skips'])} |")
    lines.append(f"| % sessions with 0 SKIPs | {kw['pct_zero_skip']:.1f}% |")
    lines.append(f"| % sessions with whole-day skip (touches > 0, trades = 0) | {kw['pct_whole_day_skip']:.1f}% |")
    lines.append("")

    lines.append("## Monthly SKIP counts (7y × 12mo grid)")
    lines.append("")
    ms = kw["monthly_skips"]
    months_header = " | ".join(str(m) for m in range(1, 13))
    lines.append(f"| Year | {months_header} | Total |")
    lines.append("|---:|" + "|".join(["---:"] * 12) + "|---:|")
    for yr in sorted(ms.index):
        row = ms.loc[yr]
        cells = []
        for m in range(1, 13):
            v = row.get(m, 0)
            cells.append(f"{int(v)}" if v > 0 else "—")
        total = int(row.sum())
        lines.append(f"| **{yr}** | " + " | ".join(cells) + f" | **{total}** |")
    lines.append("")

    lines.append("## Monthly SKIP rate % (skips / total touches)")
    lines.append("")
    mr = kw["monthly_rate"]
    lines.append(f"| Year | {months_header} | Avg |")
    lines.append("|---:|" + "|".join(["---:"] * 12) + "|---:|")
    for yr in sorted(mr.index):
        row = mr.loc[yr]
        cells = []
        valid = []
        for m in range(1, 13):
            v = row.get(m, np.nan)
            if pd.isna(v):
                cells.append("—")
            else:
                cells.append(f"{v:.0f}%")
                valid.append(v)
        avg_str = f"{np.mean(valid):.0f}%" if valid else "—"
        lines.append(f"| **{yr}** | " + " | ".join(cells) + f" | **{avg_str}** |")
    lines.append("")

    lines.append("## Trend analysis — is the monthly SKIP rate stable, rising, or falling?")
    lines.append("")
    lines.append(f"Linear regression of monthly SKIP rate (%) vs month index (1..{kw['n_months']}).")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Slope | **{kw['slope']:+.3f} pp / month** |")
    lines.append(f"| Intercept | {kw['intercept']:.2f}% |")
    lines.append(f"| r² | {kw['r_squared']:.3f} |")
    lines.append(f"| t-statistic | {kw['t_stat']:+.2f} (df={kw['n_months']-2}, \\|t\\|>2 ≈ p<0.05) |")
    lines.append(f"| Fitted month-1 | {kw['intercept']:.1f}% |")
    lines.append(f"| Fitted month-{kw['n_months']} | {kw['intercept'] + kw['slope']*(kw['n_months']-1):.1f}% |")
    lines.append("")
    abs_t = abs(kw["t_stat"])
    if abs_t < 2.0:
        verdict = "**STABLE.** Slope not significantly different from zero (|t| < 2). SKIP rate fluctuates month-to-month but no time trend."
    elif kw["slope"] > 0:
        verdict = (
            f"**RISING ({kw['slope']:+.3f} pp/month, t={kw['t_stat']:.2f}).** ADX and DI are increasingly "
            "disagreeing over time. This is consistent with the regime-drift concern flagged in Phase 7 "
            "(2026 partial underperformance). Forward test should monitor SKIP rate as an early-warning signal."
        )
    else:
        verdict = (
            f"**FALLING ({kw['slope']:+.3f} pp/month, t={kw['t_stat']:.2f}).** ADX and DI are increasingly "
            "AGREEING over time — the unanimous filter is becoming less restrictive. Inverse of the "
            "regime-drift concern; suggests current regime fits the indicator pair well."
        )
    lines.append(f"**Verdict:** {verdict}")
    lines.append("")
    lines.append("**Interpretation context:**")
    lines.append("- Phase 7 flagged 2026 Jan-Apr underperformance vs AllFade (−$1,422 over 4 months).")
    lines.append("- A *rising* skip rate would mean: ADX and DI disagree more often in recent months → less filtering value → more trades getting through with conflicting signals.")
    lines.append("- A *stable* or *falling* skip rate means: the filter's restrictiveness is consistent or tightening → 2026 underperformance is more likely sample noise than systemic.")
    lines.append("")

    lines.append("## Recent months (last 12)")
    lines.append("")
    last_12 = kw["monthly_series"].tail(12).copy()
    last_12["skip_rate_pct"] = last_12["skip_rate"] * 100
    lines.append("| Month | n_skips | n_clusters | skip rate % |")
    lines.append("|---|---:|---:|---:|")
    for ym, row in last_12.iterrows():
        lines.append(f"| {ym} | {int(row['n_skips'])} | {int(row['n_clusters'])} | {row['skip_rate_pct']:.1f}% |")
    lines.append("")

    lines.append("## Artifacts")
    lines.append("")
    lines.append("- `skip_analysis.parquet` — raw SKIP events (one row per SKIP, with session_date, ts_utc, cluster_low/high/size)")
    lines.append("- `skip_analysis_daily.parquet` — per-session aggregates (n_trades, n_skips, n_clusters, skip_rate)")
    lines.append("- `skip_analysis_monthly.parquet` — per-month time series (n_skips, n_clusters, skip_rate)")

    (OUT_DIR / "skip_analysis.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'skip_analysis.md'}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
