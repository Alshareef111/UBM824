"""Standard strategy-performance report on ADX(15,30) ∧ DI(15,8) unanimous.

Treats the deployment winner as one strategy, not an indicator stack.
Compares directly against the AllFade locked baseline on the same 7-year dataset.

Sections:
  1. Headline stats — trades, P&L, win rate, profit factor, drawdown, Sharpe, Sortino
  2. Equity curve plot — v2 cumulative + AllFade overlay, drawdown shaded
  3. Calendar-year table — year-by-year side-by-side comparison
  4. FADE vs TREND breakdown
  5. Exit-type breakdown

All plotted data saved as parquet so the chart numbers can be re-derived.
Output: results/archive/strategy_report_20260512/
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paths import ARCHIVE_DIR

V2_TRADES = ARCHIVE_DIR / "trades_regime_v2_20260512.parquet"
BASELINE_TRADES = ARCHIVE_DIR / "trades_baseline_extended_20260511.parquet"
SKIP_DAILY = ARCHIVE_DIR / "strategy_report_20260512" / "skip_analysis_daily.parquet"

TODAY = date.today().strftime("%Y%m%d")
OUT_DIR = ARCHIVE_DIR / f"strategy_report_{TODAY}"

POINT_VALUE_USD = 2.0
ANNUALIZATION = 252  # trading days/year


# ============================================================
# Core stats
# ============================================================

@dataclass
class HeadlineStats:
    name: str
    n_trades: int
    n_wins: int
    n_losses: int
    n_flat: int
    total_pnl: float
    mean_pnl: float
    median_pnl: float
    win_rate: float
    avg_winner: float
    avg_loser: float
    profit_factor: float
    max_drawdown: float
    max_dd_peak_date: pd.Timestamp
    max_dd_trough_date: pd.Timestamp
    max_dd_recovery_date: pd.Timestamp | None
    max_dd_duration_days: int
    annualized_sharpe: float
    annualized_sortino: float


def daily_pnl_series(trades_df: pd.DataFrame, all_sessions: pd.DatetimeIndex) -> pd.Series:
    """Sum trade P&L by session_date, reindexed to include all sessions (0 on no-trade days)."""
    if len(trades_df) == 0:
        return pd.Series(0.0, index=all_sessions, name="daily_pnl")
    by_day = trades_df.groupby("session_date")["pnl_dollars"].sum()
    by_day.index = pd.to_datetime(by_day.index)
    daily = by_day.reindex(all_sessions, fill_value=0.0)
    daily.name = "daily_pnl"
    return daily


def equity_and_drawdown(daily: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (cumulative equity, running peak, drawdown=equity-peak)."""
    eq = daily.cumsum()
    peak = eq.cummax()
    dd = eq - peak  # <= 0
    return eq, peak, dd


def max_dd_episode(equity: pd.Series, dd: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp | None, int]:
    """(peak_date, trough_date, recovery_date or None, duration_days)."""
    trough_date = dd.idxmin()
    pre_trough = equity.loc[:trough_date]
    peak_date = pre_trough.idxmax()
    peak_value = pre_trough.max()
    after = equity.loc[trough_date:]
    recovered_mask = after >= peak_value
    if recovered_mask.any():
        recovery_date = recovered_mask.idxmax()
        duration_days = (recovery_date - peak_date).days
    else:
        recovery_date = None
        duration_days = (equity.index[-1] - peak_date).days
    return peak_date, trough_date, recovery_date, duration_days


def annualized_sharpe(daily: pd.Series) -> float:
    s = daily.std(ddof=1)
    if s == 0 or pd.isna(s):
        return float("nan")
    return float(daily.mean() / s * np.sqrt(ANNUALIZATION))


def annualized_sortino(daily: pd.Series, mar: float = 0.0) -> float:
    diff = daily - mar
    downside = diff.clip(upper=0.0)
    dd_dev = float(np.sqrt((downside ** 2).mean()))
    if dd_dev == 0 or pd.isna(dd_dev):
        return float("nan")
    return float(diff.mean() / dd_dev * np.sqrt(ANNUALIZATION))


def compute_headline(trades_df: pd.DataFrame, all_sessions: pd.DatetimeIndex, name: str) -> HeadlineStats:
    n_trades = len(trades_df)
    wins = trades_df["pnl_dollars"] > 0
    losses = trades_df["pnl_dollars"] < 0
    flat = trades_df["pnl_dollars"] == 0
    win_pnls = trades_df.loc[wins, "pnl_dollars"]
    loss_pnls = trades_df.loc[losses, "pnl_dollars"]

    daily = daily_pnl_series(trades_df, all_sessions)
    eq, peak, dd = equity_and_drawdown(daily)
    peak_d, trough_d, recovery_d, dur = max_dd_episode(eq, dd)

    return HeadlineStats(
        name=name,
        n_trades=n_trades,
        n_wins=int(wins.sum()),
        n_losses=int(losses.sum()),
        n_flat=int(flat.sum()),
        total_pnl=float(trades_df["pnl_dollars"].sum()) if n_trades else 0.0,
        mean_pnl=float(trades_df["pnl_dollars"].mean()) if n_trades else 0.0,
        median_pnl=float(trades_df["pnl_dollars"].median()) if n_trades else 0.0,
        win_rate=float(wins.mean()) if n_trades else 0.0,
        avg_winner=float(win_pnls.mean()) if len(win_pnls) else 0.0,
        avg_loser=float(loss_pnls.mean()) if len(loss_pnls) else 0.0,
        profit_factor=(float(win_pnls.sum() / -loss_pnls.sum()) if len(loss_pnls) and loss_pnls.sum() < 0 else float("inf")),
        max_drawdown=float(dd.min()),
        max_dd_peak_date=peak_d,
        max_dd_trough_date=trough_d,
        max_dd_recovery_date=recovery_d,
        max_dd_duration_days=int(dur),
        annualized_sharpe=annualized_sharpe(daily),
        annualized_sortino=annualized_sortino(daily),
    )


# ============================================================
# Tables
# ============================================================

def yearly_table(trades_df: pd.DataFrame, all_sessions: pd.DatetimeIndex, label: str) -> pd.DataFrame:
    daily = daily_pnl_series(trades_df, all_sessions)
    df = pd.DataFrame({"daily": daily})
    df["year"] = df.index.year
    trades_df = trades_df.copy()
    trades_df["session_date"] = pd.to_datetime(trades_df["session_date"])
    trades_df["year"] = trades_df["session_date"].dt.year

    rows = []
    for yr in sorted(df["year"].unique()):
        yr_daily = df[df["year"] == yr]["daily"]
        yr_trades = trades_df[trades_df["year"] == yr]
        eq = yr_daily.cumsum()
        peak = eq.cummax()
        dd = eq - peak
        max_dd = float(dd.min()) if len(dd) else 0.0
        wins = (yr_trades["pnl_dollars"] > 0).sum() if len(yr_trades) else 0
        rows.append({
            "year": int(yr),
            f"{label}_trades": int(len(yr_trades)),
            f"{label}_pnl": float(yr_trades["pnl_dollars"].sum()) if len(yr_trades) else 0.0,
            f"{label}_wr": float(wins / len(yr_trades)) if len(yr_trades) else float("nan"),
            f"{label}_max_dd": max_dd,
        })
    return pd.DataFrame(rows).set_index("year")


def label_breakdown(trades_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lbl in ["FADE", "TREND"]:
        sub = trades_df[trades_df["cluster_label"] == lbl]
        wins = (sub["pnl_dollars"] > 0).sum()
        losses = (sub["pnl_dollars"] < 0).sum()
        win_pnls = sub.loc[sub["pnl_dollars"] > 0, "pnl_dollars"]
        loss_pnls = sub.loc[sub["pnl_dollars"] < 0, "pnl_dollars"]
        pf = float(win_pnls.sum() / -loss_pnls.sum()) if len(loss_pnls) and loss_pnls.sum() < 0 else float("inf")
        rows.append({
            "label": lbl,
            "n_trades": int(len(sub)),
            "n_wins": int(wins),
            "n_losses": int(losses),
            "win_rate": float(wins / len(sub)) if len(sub) else 0.0,
            "total_pnl": float(sub["pnl_dollars"].sum()),
            "mean_pnl": float(sub["pnl_dollars"].mean()) if len(sub) else 0.0,
            "avg_winner": float(win_pnls.mean()) if len(win_pnls) else 0.0,
            "avg_loser": float(loss_pnls.mean()) if len(loss_pnls) else 0.0,
            "profit_factor": pf,
        })
    return pd.DataFrame(rows)


def exit_breakdown(trades_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for reason in ["target", "stop", "force_close"]:
        sub = trades_df[trades_df["exit_reason"] == reason]
        wins = (sub["pnl_dollars"] > 0).sum() if len(sub) else 0
        rows.append({
            "exit_reason": reason,
            "n_trades": int(len(sub)),
            "pct_of_total": float(len(sub) / len(trades_df)) if len(trades_df) else 0.0,
            "mean_pnl": float(sub["pnl_dollars"].mean()) if len(sub) else 0.0,
            "total_pnl": float(sub["pnl_dollars"].sum()),
            "win_rate": float(wins / len(sub)) if len(sub) else 0.0,
        })
    return pd.DataFrame(rows)


# ============================================================
# Plot
# ============================================================

def plot_equity_curve(v2_daily, base_daily, out_path):
    v2_eq = v2_daily.cumsum()
    base_eq = base_daily.cumsum()
    v2_peak = v2_eq.cummax()
    v2_dd = v2_eq - v2_peak

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    ax1.plot(v2_eq.index, v2_eq.values, color="#1f77b4", linewidth=1.6, label="ADX∧DI v2 unanimous")
    ax1.plot(base_eq.index, base_eq.values, color="#d62728", linewidth=1.2, alpha=0.75, label="AllFade locked baseline")
    ax1.fill_between(v2_eq.index, v2_eq.values, v2_peak.values, where=(v2_dd < 0), color="#1f77b4", alpha=0.15, label="v2 drawdown")
    ax1.axhline(0, color="grey", linestyle="--", linewidth=0.6)
    ax1.set_ylabel("Cumulative P&L ($)")
    ax1.set_title("Equity curve — ADX∧DI v2 vs AllFade (7-year, 2019-05 to 2026-04)")
    ax1.legend(loc="upper left", frameon=False)
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(v2_dd.index, v2_dd.values, 0, color="#1f77b4", alpha=0.4)
    ax2.set_ylabel("Drawdown ($)")
    ax2.set_xlabel("Date")
    ax2.axhline(0, color="grey", linestyle="--", linewidth=0.6)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    plt.close()


# ============================================================
# Main
# ============================================================

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading trades...", flush=True)
    v2 = pd.read_parquet(V2_TRADES)
    base = pd.read_parquet(BASELINE_TRADES)
    print(f"  v2:       {len(v2)} trades  total ${v2['pnl_dollars'].sum():,.2f}")
    print(f"  AllFade:  {len(base)} trades  total ${base['pnl_dollars'].sum():,.2f}")

    # Daily session index — union of both, covering the dataset span
    v2_dates = pd.to_datetime(v2["session_date"])
    base_dates = pd.to_datetime(base["session_date"])
    all_sessions = pd.DatetimeIndex(sorted(set(v2_dates) | set(base_dates)))
    print(f"  spans {all_sessions.min().date()} to {all_sessions.max().date()} ({len(all_sessions)} unique active sessions)")

    # Headlines
    h_v2 = compute_headline(v2, all_sessions, "ADX∧DI v2 unanimous")
    h_base = compute_headline(base, all_sessions, "AllFade locked baseline")

    # SKIP count from prior analysis
    skip_daily = pd.read_parquet(SKIP_DAILY) if SKIP_DAILY.exists() else None
    n_skips = int(skip_daily["n_skips"].sum()) if skip_daily is not None else None
    n_total_clusters = n_skips + h_v2.n_trades if n_skips is not None else None

    # Yearly tables
    y_v2 = yearly_table(v2, all_sessions, "v2")
    y_base = yearly_table(base, all_sessions, "base")
    yearly = y_v2.join(y_base, how="outer").fillna(0)
    yearly["delta_pnl"] = yearly["v2_pnl"] - yearly["base_pnl"]
    yearly.to_parquet(OUT_DIR / "yearly_compare.parquet")

    # Label and exit breakdowns
    lab = label_breakdown(v2)
    lab.to_parquet(OUT_DIR / "label_breakdown.parquet", index=False)
    ex = exit_breakdown(v2)
    ex.to_parquet(OUT_DIR / "exit_breakdown.parquet", index=False)

    # Equity data
    v2_daily = daily_pnl_series(v2, all_sessions)
    base_daily = daily_pnl_series(base, all_sessions)
    v2_eq = v2_daily.cumsum()
    base_eq = base_daily.cumsum()
    v2_peak = v2_eq.cummax()
    v2_dd = v2_eq - v2_peak
    equity = pd.DataFrame({
        "session_date": all_sessions,
        "v2_daily_pnl": v2_daily.values,
        "v2_cumulative": v2_eq.values,
        "v2_peak": v2_peak.values,
        "v2_drawdown": v2_dd.values,
        "base_daily_pnl": base_daily.values,
        "base_cumulative": base_eq.values,
    })
    equity.to_parquet(OUT_DIR / "equity_data.parquet", index=False)
    equity.to_csv(OUT_DIR / "equity_data.csv", index=False)

    # Plot
    plot_equity_curve(v2_daily, base_daily, OUT_DIR / "equity_curve.png")
    print(f"Wrote {OUT_DIR / 'equity_curve.png'}", flush=True)

    write_report(h_v2, h_base, yearly, lab, ex, n_skips, n_total_clusters)
    print(f"Wrote {OUT_DIR / 'strategy_report.md'}", flush=True)


def write_report(h_v2, h_base, yearly, lab, ex, n_skips, n_total_clusters):
    fmt_money = lambda v: f"${v:,.2f}"
    fmt_int = lambda v: f"{int(v):,}"
    fmt_pct = lambda v: f"{v:.1%}" if not pd.isna(v) else "—"

    lines: list[str] = []
    lines.append("# Strategy Performance Report — ADX(15,30) ∧ DI(15,8) Unanimous (Deployment Winner)")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("**Period:** 2019-05-15 → 2026-04-15 (~7 years)")
    lines.append("**Geometry:** locked baseline (3-pt clusters, 30-pt bracket, first-touch, C2, 9:46-11:30 NY, force-close at 11:30 open)")
    lines.append("**Regime gate:** ADX(15,30) ∧ DI(15,8) unanimous AND-gate at touch bar T-1")
    lines.append("**Comparison:** locked AllFade baseline on the same 7-year dataset (R-006).")
    lines.append("")

    # ============================================================
    # 1. Headline stats
    # ============================================================
    lines.append("## 1. Headline stats")
    lines.append("")
    lines.append("Cluster-touch event counts (v2 only — AllFade has no SKIP path):")
    lines.append("")
    if n_skips is not None:
        lines.append(f"- **Total cluster-touch events:** {fmt_int(n_total_clusters)}")
        lines.append(f"- **FADE:** {fmt_int(lab.loc[lab['label']=='FADE','n_trades'].iloc[0])} ({lab.loc[lab['label']=='FADE','n_trades'].iloc[0]/n_total_clusters:.1%})")
        lines.append(f"- **TREND:** {fmt_int(lab.loc[lab['label']=='TREND','n_trades'].iloc[0])} ({lab.loc[lab['label']=='TREND','n_trades'].iloc[0]/n_total_clusters:.1%})")
        lines.append(f"- **SKIP:** {fmt_int(n_skips)} ({n_skips/n_total_clusters:.1%})")
        lines.append(f"- **Trades fired:** {fmt_int(h_v2.n_trades)} ({h_v2.n_trades/n_total_clusters:.1%})")
    else:
        lines.append(f"- **Trades fired:** {fmt_int(h_v2.n_trades)} (FADE+TREND)")
    lines.append("")

    lines.append("Performance metrics — v2 vs AllFade side-by-side:")
    lines.append("")
    lines.append("| Metric | ADX∧DI v2 | AllFade baseline | Δ |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Trades | {fmt_int(h_v2.n_trades)} | {fmt_int(h_base.n_trades)} | {fmt_int(h_v2.n_trades - h_base.n_trades)} |")
    lines.append(f"| Wins / Losses / Flat | {h_v2.n_wins} / {h_v2.n_losses} / {h_v2.n_flat} | {h_base.n_wins} / {h_base.n_losses} / {h_base.n_flat} | — |")
    lines.append(f"| Win rate | {fmt_pct(h_v2.win_rate)} | {fmt_pct(h_base.win_rate)} | {(h_v2.win_rate - h_base.win_rate)*100:+.1f}pp |")
    lines.append(f"| Total P&L | **{fmt_money(h_v2.total_pnl)}** | {fmt_money(h_base.total_pnl)} | **{fmt_money(h_v2.total_pnl - h_base.total_pnl)}** |")
    lines.append(f"| Mean per trade | {fmt_money(h_v2.mean_pnl)} | {fmt_money(h_base.mean_pnl)} | {fmt_money(h_v2.mean_pnl - h_base.mean_pnl)} |")
    lines.append(f"| Median per trade | {fmt_money(h_v2.median_pnl)} | {fmt_money(h_base.median_pnl)} | — |")
    lines.append(f"| Avg winner | {fmt_money(h_v2.avg_winner)} | {fmt_money(h_base.avg_winner)} | — |")
    lines.append(f"| Avg loser | {fmt_money(h_v2.avg_loser)} | {fmt_money(h_base.avg_loser)} | — |")
    pf_str_v2 = f"{h_v2.profit_factor:.3f}" if h_v2.profit_factor != float('inf') else "∞"
    pf_str_base = f"{h_base.profit_factor:.3f}" if h_base.profit_factor != float('inf') else "∞"
    lines.append(f"| Profit factor | {pf_str_v2} | {pf_str_base} | — |")
    lines.append(f"| Max drawdown | **{fmt_money(h_v2.max_drawdown)}** | {fmt_money(h_base.max_drawdown)} | — |")
    lines.append(f"| Max-DD duration (days, peak → recovery) | {h_v2.max_dd_duration_days} | {h_base.max_dd_duration_days} | — |")
    recov_v2 = h_v2.max_dd_recovery_date.date() if h_v2.max_dd_recovery_date else "no recovery"
    recov_base = h_base.max_dd_recovery_date.date() if h_base.max_dd_recovery_date else "no recovery"
    lines.append(f"| Annualized Sharpe (daily P&L, sqrt(252)) | **{h_v2.annualized_sharpe:.2f}** | {h_base.annualized_sharpe:.2f} | — |")
    lines.append(f"| Annualized Sortino (MAR=0) | **{h_v2.annualized_sortino:.2f}** | {h_base.annualized_sortino:.2f} | — |")
    lines.append("")
    lines.append(f"v2 max-DD episode: peak {h_v2.max_dd_peak_date.date()} → trough {h_v2.max_dd_trough_date.date()} → recovery {recov_v2}.")
    lines.append(f"AllFade max-DD episode: peak {h_base.max_dd_peak_date.date()} → trough {h_base.max_dd_trough_date.date()} → recovery {recov_base}.")
    lines.append("")

    # ============================================================
    # 2. Equity curve plot
    # ============================================================
    lines.append("## 2. Equity curve")
    lines.append("")
    lines.append("![Equity curve](equity_curve.png)")
    lines.append("")
    lines.append("Cumulative P&L over the full 7-year window, summed per session_date and cumulated daily.")
    lines.append("Drawdown shaded in blue beneath the v2 line. AllFade overlay in red for direct comparison.")
    lines.append("")
    lines.append("Underlying data: `equity_data.parquet` / `equity_data.csv` (one row per active session,")
    lines.append("with v2 and AllFade daily P&L and cumulative columns).")
    lines.append("")

    # ============================================================
    # 3. Calendar-year table
    # ============================================================
    lines.append("## 3. Calendar-year comparison")
    lines.append("")
    lines.append("| Year | v2 trades | v2 P&L | v2 WR | v2 max DD | AllFade trades | AllFade P&L | AllFade WR | AllFade max DD | Δ P&L |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for yr in yearly.index:
        r = yearly.loc[yr]
        lines.append(
            f"| {yr} | {int(r['v2_trades'])} | {fmt_money(r['v2_pnl'])} | "
            f"{fmt_pct(r['v2_wr'])} | {fmt_money(r['v2_max_dd'])} | "
            f"{int(r['base_trades'])} | {fmt_money(r['base_pnl'])} | "
            f"{fmt_pct(r['base_wr'])} | {fmt_money(r['base_max_dd'])} | "
            f"**{fmt_money(r['delta_pnl'])}** |"
        )
    lines.append("")
    lines.append("Underlying data: `yearly_compare.parquet`.")
    lines.append("")

    # ============================================================
    # 4. FADE vs TREND breakdown
    # ============================================================
    lines.append("## 4. FADE vs TREND breakdown")
    lines.append("")
    lines.append("Which mode does the work? FADE = locked-baseline-direction trades; TREND = inverted-direction trades.")
    lines.append("")
    lines.append("| Label | trades | wins / losses | win rate | total P&L | mean | avg winner | avg loser | profit factor |")
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for r in lab.itertuples():
        pf_str = f"{r.profit_factor:.3f}" if r.profit_factor != float('inf') else "∞"
        lines.append(
            f"| **{r.label}** | {r.n_trades} | {r.n_wins} / {r.n_losses} | "
            f"{fmt_pct(r.win_rate)} | **{fmt_money(r.total_pnl)}** | "
            f"{fmt_money(r.mean_pnl)} | {fmt_money(r.avg_winner)} | "
            f"{fmt_money(r.avg_loser)} | {pf_str} |"
        )
    lines.append("")
    lines.append("Underlying data: `label_breakdown.parquet`.")
    lines.append("")

    # ============================================================
    # 5. Exit-type breakdown
    # ============================================================
    lines.append("## 5. Exit-type breakdown")
    lines.append("")
    lines.append("| Exit reason | trades | % of total | mean P&L | total P&L | win rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in ex.itertuples():
        lines.append(
            f"| **{r.exit_reason}** | {r.n_trades} | "
            f"{fmt_pct(r.pct_of_total)} | {fmt_money(r.mean_pnl)} | "
            f"{fmt_money(r.total_pnl)} | {fmt_pct(r.win_rate)} |"
        )
    lines.append("")
    lines.append("Underlying data: `exit_breakdown.parquet`.")
    lines.append("")

    lines.append("## Files in this directory")
    lines.append("")
    lines.append("- `strategy_report.md` — this report")
    lines.append("- `equity_curve.png` — plotted equity + drawdown")
    lines.append("- `equity_data.parquet` / `.csv` — full daily P&L and cumulative series (both v2 and AllFade)")
    lines.append("- `yearly_compare.parquet` — calendar-year side-by-side table")
    lines.append("- `label_breakdown.parquet` — FADE vs TREND stats")
    lines.append("- `exit_breakdown.parquet` — exit-type stats")
    lines.append("- `skip_analysis.{md,parquet}` — SKIP analysis from prior step")

    (OUT_DIR / "strategy_report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main() or 0)
