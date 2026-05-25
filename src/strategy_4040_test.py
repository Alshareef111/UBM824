"""40/40 R:R variant test on the deployment winner.

Re-runs ADX(15,30) ∧ DI(15,8) unanimous AND-gate with stop/target = 40/40 points
instead of the locked-baseline 30/30. Also re-runs AllFade with 40/40 brackets
to provide a like-for-like baseline comparison.

The override is done by setting simulator_v2.STOP_POINTS / TARGET_POINTS at
module level before run_backtest is called. check_exit reads these globals
at each invocation, so the override propagates correctly.

Locked baseline geometry otherwise untouched: 3-pt clusters, first-touch entry,
C2 one-position-at-a-time, 9:46-11:30 NY trading window, force-close at 11:30
open, same-bar stop-first conservative.

4-way comparison output:
  - v2 30/30 (deployment winner, loaded from prior run)
  - v2 40/40 (this test)
  - AllFade 30/30 (locked extended baseline, loaded from R-006)
  - AllFade 40/40 (this test)

Output: results/archive/strategy_report_20260512/strategy_4040_test.{md, parquets}
"""
from __future__ import annotations

import sys
import time
from datetime import date

import numpy as np
import pandas as pd

# Override stop/target BEFORE importing anything that uses them downstream.
import simulator_v2 as sim
ORIGINAL_STOP = sim.STOP_POINTS
ORIGINAL_TARGET = sim.TARGET_POINTS

from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.base import AllFade, UnanimousClassifier
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET
import walk_forward as wf

ADX_N, ADX_THR = 15, 30
DI_N, DI_THR = 15, 8
NEW_STOP_TARGET = 40.0

V2_3030 = ARCHIVE_DIR / "trades_regime_v2_20260512.parquet"
BASE_3030 = ARCHIVE_DIR / "trades_baseline_extended_20260511.parquet"
OUT_DIR = ARCHIVE_DIR / "strategy_report_20260512"

POINT_VALUE_USD = 2.0
ANNUALIZATION = 252


def stats(df, all_sessions):
    """Compute the standard headline stats for a trades dataframe."""
    if len(df) == 0:
        return None
    wins = df["pnl_dollars"] > 0
    losses = df["pnl_dollars"] < 0
    win_pnls = df.loc[wins, "pnl_dollars"]
    loss_pnls = df.loc[losses, "pnl_dollars"]

    daily = df.groupby("session_date")["pnl_dollars"].sum()
    daily.index = pd.to_datetime(daily.index)
    daily = daily.reindex(all_sessions, fill_value=0.0)

    eq = daily.cumsum()
    peak = eq.cummax()
    dd = eq - peak
    max_dd = float(dd.min())
    trough = dd.idxmin()
    pre_trough = eq.loc[:trough]
    peak_d = pre_trough.idxmax()
    peak_value = pre_trough.max()
    after = eq.loc[trough:]
    rec_mask = after >= peak_value
    if rec_mask.any():
        rec_d = rec_mask.idxmax()
        dur = (rec_d - peak_d).days
    else:
        rec_d = None
        dur = (eq.index[-1] - peak_d).days

    sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(ANNUALIZATION)) if daily.std(ddof=1) > 0 else float("nan")
    downside_dev = float(np.sqrt(((daily.clip(upper=0.0)) ** 2).mean()))
    sortino = float(daily.mean() / downside_dev * np.sqrt(ANNUALIZATION)) if downside_dev > 0 else float("nan")

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
        "n_force_close": int((df["exit_reason"] == "force_close").sum()),
        "n_target": int((df["exit_reason"] == "target").sum()),
        "n_stop": int((df["exit_reason"] == "stop").sum()),
    }


def walk_forward_score(df):
    """Sharpe-like + sign + 4-gate qualification using the project's walk-forward harness."""
    windows = wf.make_windows()
    pw = wf.per_window_pnl(df, windows, slice_="oos")
    total = float(df["pnl_dollars"].sum())
    return {
        "wf_sharpe_like": wf.sharpe_like_score(pw),
        "wf_median_oos": wf.median_pnl(pw),
        "wf_sign_count": wf.sign_stability_count(pw),
        "wf_oos_sum": float(sum(pw.values())),
        "wf_qualifies_deploy": wf.qualifies(pw, total_pnl=total, sharpe_threshold=wf.NULL_P95_SHARPE_LIKE),
        **{f"wf_{w.name}": pw[w.name] for w in windows},
    }


def yearly(df):
    df = df.copy()
    df["session_date"] = pd.to_datetime(df["session_date"])
    df["year"] = df["session_date"].dt.year
    rows = []
    for yr in sorted(df["year"].unique()):
        sub = df[df["year"] == yr]
        wins = (sub["pnl_dollars"] > 0).sum()
        rows.append({
            "year": int(yr),
            "n_trades": int(len(sub)),
            "pnl": float(sub["pnl_dollars"].sum()),
            "win_rate": float(wins / len(sub)) if len(sub) else float("nan"),
        })
    return pd.DataFrame(rows).set_index("year")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print(f"Override: sim.STOP_POINTS = {NEW_STOP_TARGET}, sim.TARGET_POINTS = {NEW_STOP_TARGET}", flush=True)
    sim.STOP_POINTS = NEW_STOP_TARGET
    sim.TARGET_POINTS = NEW_STOP_TARGET
    assert sim.STOP_POINTS == 40.0 and sim.TARGET_POINTS == 40.0

    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)

    print("Pre-computing ADX(15) and DI(15) lookups...", flush=True)
    adx_lk = adx_lookup(bars, n=ADX_N)
    di_lk = di_lookup(bars, n=DI_N)

    print(f"\nRunning AllFade with stop={sim.STOP_POINTS}, target={sim.TARGET_POINTS}...", flush=True)
    t = time.time()
    allfade_4040 = sim.run_backtest(bars, orb_table, AllFade())
    allfade_4040_df = sim.trades_to_dataframe(allfade_4040)
    print(f"  {len(allfade_4040_df)} trades  total ${allfade_4040_df['pnl_dollars'].sum():,.2f}  [{time.time()-t:.1f}s]", flush=True)

    print(f"\nRunning ADX∧DI unanimous with stop={sim.STOP_POINTS}, target={sim.TARGET_POINTS}...", flush=True)
    adx_clf = AdxClassifier(adx_lk, n=ADX_N, threshold=ADX_THR)
    di_clf = DiClassifier(di_lk, n=DI_N, threshold=DI_THR)
    unan = UnanimousClassifier([adx_clf, di_clf], name=f"ADX({ADX_N},{ADX_THR})∧DI({DI_N},{DI_THR}) 40/40")
    t = time.time()
    v2_4040 = sim.run_backtest(bars, orb_table, unan)
    v2_4040_df = sim.trades_to_dataframe(v2_4040)
    print(f"  {len(v2_4040_df)} trades  total ${v2_4040_df['pnl_dollars'].sum():,.2f}  [{time.time()-t:.1f}s]", flush=True)

    # Save trade outputs
    v2_4040_df.to_parquet(OUT_DIR / "trades_v2_4040.parquet", index=False)
    allfade_4040_df.to_parquet(OUT_DIR / "trades_allfade_4040.parquet", index=False)

    # Load prior 30/30 results for comparison
    v2_3030_df = pd.read_parquet(V2_3030)
    base_3030_df = pd.read_parquet(BASE_3030)

    # All-sessions index (union)
    all_dates = set()
    for d in [v2_3030_df, v2_4040_df, base_3030_df, allfade_4040_df]:
        all_dates |= set(pd.to_datetime(d["session_date"]))
    all_sessions = pd.DatetimeIndex(sorted(all_dates))

    # Compute headlines for all four
    runs = {
        "v2 30/30": v2_3030_df,
        "v2 40/40": v2_4040_df,
        "AllFade 30/30": base_3030_df,
        "AllFade 40/40": allfade_4040_df,
    }
    headlines = {name: stats(df, all_sessions) for name, df in runs.items()}
    wf_scores = {name: walk_forward_score(df) for name, df in runs.items()}

    # Save combined headlines table
    combined = []
    for name, h in headlines.items():
        row = {"strategy": name, **h, **wf_scores[name]}
        combined.append(row)
    pd.DataFrame(combined).to_parquet(OUT_DIR / "headlines_4040.parquet", index=False)

    # Yearly comparison
    yr = {name: yearly(df) for name, df in runs.items()}

    write_report(headlines, wf_scores, yr)
    print(f"\nTotal elapsed: {(time.time()-t0):.1f}s", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


def write_report(headlines, wf_scores, yearly_tables):
    fmt_money = lambda v: f"${v:,.0f}"
    fmt_pct = lambda v: f"{v:.1%}" if not pd.isna(v) else "—"

    lines: list[str] = []
    lines.append("# 40/40 R:R variant test — ADX(15,30) ∧ DI(15,8) Unanimous")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("**Change tested:** stop/target widened from locked 30 points to 40 points (still 1:1 R:R).")
    lines.append("**All other geometry locked:** 3-pt clusters, first-touch, C2, 9:46-11:30 NY, force-close at 11:30 open.")
    lines.append("")
    lines.append("Comparison set: deployment winner ADX∧DI (30/30 from prior step, 40/40 from this test)")
    lines.append("plus AllFade baseline (locked 30/30, 40/40 freshly computed for like-for-like).")
    lines.append("")

    # Headline 4-way table
    lines.append("## Headline stats — 4-way comparison")
    lines.append("")
    lines.append("| Metric | v2 30/30 | v2 40/40 | AllFade 30/30 | AllFade 40/40 |")
    lines.append("|---|---:|---:|---:|---:|")
    names = ["v2 30/30", "v2 40/40", "AllFade 30/30", "AllFade 40/40"]
    metrics = [
        ("Trades", lambda h: f"{h['n_trades']:,}"),
        ("Win rate", lambda h: fmt_pct(h["win_rate"])),
        ("Total P&L", lambda h: f"**{fmt_money(h['total_pnl'])}**"),
        ("Mean / trade", lambda h: f"${h['mean_pnl']:.2f}"),
        ("Avg winner", lambda h: f"${h['avg_winner']:.0f}"),
        ("Avg loser", lambda h: f"${h['avg_loser']:.0f}"),
        ("Profit factor", lambda h: f"{h['profit_factor']:.3f}" if h["profit_factor"] != float("inf") else "∞"),
        ("Max drawdown", lambda h: fmt_money(h["max_dd"])),
        ("Max-DD duration (days)", lambda h: str(h["max_dd_duration_days"])),
        ("Max-DD recovered?", lambda h: "yes" if h["max_dd_recovered"] else "no"),
        ("Annualized Sharpe", lambda h: f"{h['sharpe_ann']:.2f}"),
        ("Annualized Sortino", lambda h: f"{h['sortino_ann']:.2f}"),
        ("Target exits", lambda h: f"{h['n_target']}"),
        ("Stop exits", lambda h: f"{h['n_stop']}"),
        ("Force-close exits", lambda h: f"{h['n_force_close']}"),
    ]
    for label, fn in metrics:
        cells = [fn(headlines[n]) for n in names]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")

    # Walk-forward
    lines.append("## Walk-forward — 7 OOS windows (3y IS + 1y OOS, advance 6mo)")
    lines.append("")
    lines.append("| Metric | v2 30/30 | v2 40/40 | AllFade 30/30 | AllFade 40/40 |")
    lines.append("|---|---:|---:|---:|---:|")
    wf_metrics = [
        ("Sharpe-like (median/stdev)", lambda w: f"**{w['wf_sharpe_like']:.2f}**"),
        ("Median per-window OOS P&L", lambda w: fmt_money(w["wf_median_oos"])),
        ("Sign-stability (k/7)", lambda w: f"{w['wf_sign_count']}/7"),
        ("Sum per-window OOS P&L", lambda w: fmt_money(w["wf_oos_sum"])),
        ("Qualifies 4-gate deploy", lambda w: "✓" if w["wf_qualifies_deploy"] else " "),
    ]
    for label, fn in wf_metrics:
        cells = [fn(wf_scores[n]) for n in names]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")

    # Per-window detail
    lines.append("## Per-window OOS P&L")
    lines.append("")
    windows = wf.make_windows()
    lines.append("| Strategy | " + " | ".join(w.name for w in windows) + " |")
    lines.append("|---|" + "|".join(["---:"] * 7) + "|")
    for n in names:
        cells = [fmt_money(wf_scores[n][f"wf_{w.name}"]) for w in windows]
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    lines.append("")

    # Calendar-year
    lines.append("## Calendar-year P&L (4-way)")
    lines.append("")
    years = sorted(set().union(*[set(yt.index) for yt in yearly_tables.values()]))
    lines.append("| Year | v2 30/30 | v2 40/40 | AllFade 30/30 | AllFade 40/40 |")
    lines.append("|---:|---:|---:|---:|---:|")
    for yr in years:
        cells = []
        for n in names:
            yt = yearly_tables[n]
            if yr in yt.index:
                cells.append(fmt_money(yt.loc[yr, "pnl"]))
            else:
                cells.append("—")
        lines.append(f"| {yr} | " + " | ".join(cells) + " |")
    lines.append("")

    # Δ analysis
    lines.append("## Δ analysis: does widening the bracket help v2?")
    lines.append("")
    h_3030 = headlines["v2 30/30"]
    h_4040 = headlines["v2 40/40"]
    w_3030 = wf_scores["v2 30/30"]
    w_4040 = wf_scores["v2 40/40"]
    lines.append("| Metric | 30/30 | 40/40 | Δ |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Trades | {h_3030['n_trades']:,} | {h_4040['n_trades']:,} | {h_4040['n_trades']-h_3030['n_trades']:+,} |")
    lines.append(f"| Win rate | {fmt_pct(h_3030['win_rate'])} | {fmt_pct(h_4040['win_rate'])} | {(h_4040['win_rate']-h_3030['win_rate'])*100:+.1f}pp |")
    lines.append(f"| Total P&L | {fmt_money(h_3030['total_pnl'])} | {fmt_money(h_4040['total_pnl'])} | **{fmt_money(h_4040['total_pnl']-h_3030['total_pnl'])}** |")
    lines.append(f"| Mean / trade | ${h_3030['mean_pnl']:.2f} | ${h_4040['mean_pnl']:.2f} | ${h_4040['mean_pnl']-h_3030['mean_pnl']:+.2f} |")
    lines.append(f"| Profit factor | {h_3030['profit_factor']:.3f} | {h_4040['profit_factor']:.3f} | {h_4040['profit_factor']-h_3030['profit_factor']:+.3f} |")
    lines.append(f"| Max drawdown | {fmt_money(h_3030['max_dd'])} | {fmt_money(h_4040['max_dd'])} | {fmt_money(h_4040['max_dd']-h_3030['max_dd'])} |")
    lines.append(f"| Annualized Sharpe | {h_3030['sharpe_ann']:.2f} | {h_4040['sharpe_ann']:.2f} | {h_4040['sharpe_ann']-h_3030['sharpe_ann']:+.2f} |")
    lines.append(f"| Walk-forward sharpe-like | {w_3030['wf_sharpe_like']:.2f} | {w_4040['wf_sharpe_like']:.2f} | {w_4040['wf_sharpe_like']-w_3030['wf_sharpe_like']:+.2f} |")
    lines.append(f"| Walk-forward sign | {w_3030['wf_sign_count']}/7 | {w_4040['wf_sign_count']}/7 | — |")
    lines.append(f"| Force-close exits | {h_3030['n_force_close']} | {h_4040['n_force_close']} | {h_4040['n_force_close']-h_3030['n_force_close']:+} |")
    lines.append("")

    delta = h_4040["total_pnl"] - h_3030["total_pnl"]
    delta_sharpe = w_4040["wf_sharpe_like"] - w_3030["wf_sharpe_like"]
    if delta > 0 and delta_sharpe > 0:
        verdict = ("**Verdict:** 40/40 IMPROVES the deployment winner on both absolute P&L and walk-forward Sharpe. "
                   "Worth considering as the actual deployment configuration.")
    elif delta < 0 and delta_sharpe < 0:
        verdict = ("**Verdict:** 40/40 HURTS the deployment winner on both absolute P&L and walk-forward Sharpe. "
                   "Stay with 30/30 — the locked baseline R:R is correct.")
    else:
        verdict = (f"**Verdict:** mixed. P&L Δ {fmt_money(delta)}, Sharpe Δ {delta_sharpe:+.2f}. "
                   "Trade-off — investigate which metric matters most for deployment.")
    lines.append(verdict)
    lines.append("")

    lines.append("## Files")
    lines.append("")
    lines.append("- `strategy_4040_test.md` — this report")
    lines.append("- `trades_v2_4040.parquet` — ADX∧DI unanimous with 40/40 brackets")
    lines.append("- `trades_allfade_4040.parquet` — AllFade locked behavior with 40/40 brackets")
    lines.append("- `headlines_4040.parquet` — 4-way headline + walk-forward stats")

    (OUT_DIR / "strategy_4040_test.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'strategy_4040_test.md'}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
