"""V2 + 40/40 with cluster-size filter: F1 (MIN_CLUSTER_SIZE=4) and F2 (=5).

Module-level override on simulator_v2: set sim.MIN_CLUSTER_SIZE = 4 (or 5),
sim.STOP_POINTS = sim.TARGET_POINTS = 40.0 before sim.run_backtest. No fork.

Baseline reference (no re-run): results/archive/strategy_report_20260512/
trades_v2_4040.parquet and strategy_4040_test.md.

Outputs to results/archive/v2_4040_cluster_size_filter_20260514/:
  - report.md
  - trades_v2_4040_size4.parquet (F1)
  - trades_v2_4040_size5.parquet (F2)
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import simulator_v2 as sim
from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.base import UnanimousClassifier
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET
import walk_forward as wf

ADX_N, ADX_THR = 15, 30
DI_N, DI_THR = 15, 8
NEW_STOP_TARGET = 40.0

OUT_DIR = ARCHIVE_DIR / "v2_4040_cluster_size_filter_20260514"
BASELINE_PARQUET = ARCHIVE_DIR / "strategy_report_20260512" / "trades_v2_4040.parquet"

POINT_VALUE_USD = 2.0
ANNUALIZATION = 252

# Published baseline numbers from
# results/archive/strategy_report_20260512/strategy_4040_test.md (v2 40/40 column).
# Per spec: copy these directly; do not re-run baseline.
BASELINE_HEADLINE = {
    "n_trades": 908,
    "win_rate": 0.562,
    "total_pnl": 8808.0,
    "mean_pnl": 9.70,
    "avg_winner": 73.0,
    "avg_loser": -72.0,
    "profit_factor": 1.309,
    "max_dd": -1228.0,
    "max_dd_duration_days": 380,
    "max_dd_recovered": True,
    "sharpe_ann": 2.15,
    "sortino_ann": 3.61,
    "n_target": 442,
    "n_stop": 336,
    "n_force_close": 130,
}
BASELINE_WF = {
    "wf_sharpe_like": 6.86,
    "wf_median_oos": 1688.0,
    "wf_sign_count": 7,
    "wf_oos_sum": 11956.0,
    "wf_qualifies_deploy": True,
}


def stats(df: pd.DataFrame, all_sessions: pd.DatetimeIndex) -> dict:
    if len(df) == 0:
        return {
            "n_trades": 0, "n_wins": 0, "n_losses": 0, "win_rate": float("nan"),
            "total_pnl": 0.0, "mean_pnl": float("nan"), "avg_winner": 0.0,
            "avg_loser": 0.0, "profit_factor": float("nan"), "max_dd": 0.0,
            "max_dd_duration_days": 0, "max_dd_recovered": False,
            "sharpe_ann": float("nan"), "sortino_ann": float("nan"),
            "n_target": 0, "n_stop": 0, "n_force_close": 0,
        }
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
        "n_target": int((df["exit_reason"] == "target").sum()),
        "n_stop": int((df["exit_reason"] == "stop").sum()),
        "n_force_close": int((df["exit_reason"] == "force_close").sum()),
    }


def walk_forward_score(df: pd.DataFrame) -> dict:
    windows = wf.make_windows()
    pw = wf.per_window_pnl(df, windows, slice_="oos")
    total = float(df["pnl_dollars"].sum()) if len(df) else 0.0
    return {
        "wf_sharpe_like": wf.sharpe_like_score(pw),
        "wf_median_oos": wf.median_pnl(pw),
        "wf_sign_count": wf.sign_stability_count(pw),
        "wf_oos_sum": float(sum(pw.values())),
        "wf_qualifies_deploy": wf.qualifies(pw, total_pnl=total, sharpe_threshold=wf.NULL_P95_SHARPE_LIKE),
        **{f"wf_{w.name}": pw[w.name] for w in windows},
    }


def yearly(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame(columns=["n_trades", "pnl", "win_rate"]).rename_axis("year")
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


def exit_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Counts + mean P&L per exit type."""
    if len(df) == 0:
        return pd.DataFrame(columns=["count", "mean_pnl", "total_pnl"]).rename_axis("exit_reason")
    g = df.groupby("exit_reason")["pnl_dollars"].agg(["count", "mean", "sum"])
    g.columns = ["count", "mean_pnl", "total_pnl"]
    return g


def cluster_size_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Trades by cluster size, with mean P&L per bucket. Buckets 3/4/5/6/7+."""
    if len(df) == 0:
        return pd.DataFrame(columns=["count", "mean_pnl", "total_pnl"]).rename_axis("cluster_size")
    df = df.copy()
    df["bucket"] = df["cluster_size"].clip(upper=7).astype(int)
    # Bucket label 7 will mean "7+"; preserve raw sizes too for sanity.
    g = df.groupby("bucket")["pnl_dollars"].agg(["count", "mean", "sum"])
    g.columns = ["count", "mean_pnl", "total_pnl"]
    g.index.name = "cluster_size"
    return g


def label_split(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {"FADE": 0, "TREND": 0}
    vc = df["cluster_label"].value_counts().to_dict()
    return {"FADE": int(vc.get("FADE", 0)), "TREND": int(vc.get("TREND", 0))}


def filter_effect_diagnostic(baseline_df: pd.DataFrame, variant_df: pd.DataFrame, min_size_threshold: int) -> dict:
    """Compare baseline trades to variant trades by (session_date, cluster_low, cluster_high).

    Returns stats on baseline trades that DO NOT appear in the variant — these are
    the trades that the higher MIN_CLUSTER_SIZE filtered out.
    """
    bkeys = set(zip(
        pd.to_datetime(baseline_df["session_date"]).astype("int64"),
        baseline_df["cluster_low"].astype(float),
        baseline_df["cluster_high"].astype(float),
    ))
    vkeys = set(zip(
        pd.to_datetime(variant_df["session_date"]).astype("int64"),
        variant_df["cluster_low"].astype(float),
        variant_df["cluster_high"].astype(float),
    )) if len(variant_df) else set()

    filtered_keys = bkeys - vkeys

    bdf = baseline_df.copy()
    bdf["_key"] = list(zip(
        pd.to_datetime(bdf["session_date"]).astype("int64"),
        bdf["cluster_low"].astype(float),
        bdf["cluster_high"].astype(float),
    ))
    filtered = bdf[bdf["_key"].isin(filtered_keys)].drop(columns=["_key"])

    out = {
        "n_filtered_out": int(len(filtered)),
        "total_pnl_filtered": float(filtered["pnl_dollars"].sum()) if len(filtered) else 0.0,
        "win_rate_filtered": float((filtered["pnl_dollars"] > 0).mean()) if len(filtered) else float("nan"),
        "exit_breakdown": exit_breakdown(filtered),
        "by_size": filtered["cluster_size"].value_counts().sort_index().to_dict() if len(filtered) else {},
        "below_threshold": int((filtered["cluster_size"] < min_size_threshold).sum()) if len(filtered) else 0,
        "at_or_above_threshold": int((filtered["cluster_size"] >= min_size_threshold).sum()) if len(filtered) else 0,
    }
    return out


def run_variant(min_cluster_size: int, bars: pd.DataFrame, orb_table: pd.DataFrame,
                adx_lk, di_lk) -> pd.DataFrame:
    """Set module-level constants, run backtest, return trades DataFrame."""
    sim.MIN_CLUSTER_SIZE = min_cluster_size
    sim.STOP_POINTS = NEW_STOP_TARGET
    sim.TARGET_POINTS = NEW_STOP_TARGET
    assert sim.MIN_CLUSTER_SIZE == min_cluster_size
    assert sim.STOP_POINTS == NEW_STOP_TARGET == sim.TARGET_POINTS

    adx_clf = AdxClassifier(adx_lk, n=ADX_N, threshold=ADX_THR)
    di_clf = DiClassifier(di_lk, n=DI_N, threshold=DI_THR)
    unan = UnanimousClassifier(
        [adx_clf, di_clf],
        name=f"ADX({ADX_N},{ADX_THR})∧DI({DI_N},{DI_THR}) 40/40 size>={min_cluster_size}",
    )

    t = time.time()
    trades = sim.run_backtest(bars, orb_table, unan)
    df = sim.trades_to_dataframe(trades)
    print(f"  {len(df)} trades  total ${df['pnl_dollars'].sum():,.2f}  [{time.time()-t:.1f}s]", flush=True)
    return df


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions", flush=True)

    print("Pre-computing ADX(15) and DI(15) lookups...", flush=True)
    adx_lk = adx_lookup(bars, n=ADX_N)
    di_lk = di_lookup(bars, n=DI_N)

    print(f"\n=== F1: MIN_CLUSTER_SIZE = 4, stop/target = {NEW_STOP_TARGET} ===", flush=True)
    f1_df = run_variant(4, bars, orb_table, adx_lk, di_lk)
    f1_df.to_parquet(OUT_DIR / "trades_v2_4040_size4.parquet", index=False)

    print(f"\n=== F2: MIN_CLUSTER_SIZE = 5, stop/target = {NEW_STOP_TARGET} ===", flush=True)
    f2_df = run_variant(5, bars, orb_table, adx_lk, di_lk)
    f2_df.to_parquet(OUT_DIR / "trades_v2_4040_size5.parquet", index=False)

    # Load baseline (V2 + 40/40, size ≥ 3) for diagnostic + comparison.
    baseline_df = pd.read_parquet(BASELINE_PARQUET)

    # Union session dates for daily reindex.
    all_dates = set()
    for d in [baseline_df, f1_df, f2_df]:
        all_dates |= set(pd.to_datetime(d["session_date"]))
    all_sessions = pd.DatetimeIndex(sorted(all_dates))

    # Baseline headline numbers come from the published strategy_4040_test.md (do not re-run).
    b_stats = BASELINE_HEADLINE
    f1_stats = stats(f1_df, all_sessions)
    f2_stats = stats(f2_df, all_sessions)

    b_wf = BASELINE_WF
    f1_wf = walk_forward_score(f1_df)
    f2_wf = walk_forward_score(f2_df)

    b_year = yearly(baseline_df)
    f1_year = yearly(f1_df)
    f2_year = yearly(f2_df)

    f1_diag = filter_effect_diagnostic(baseline_df, f1_df, min_size_threshold=4)
    f2_diag = filter_effect_diagnostic(baseline_df, f2_df, min_size_threshold=5)

    write_report(
        b_stats, f1_stats, f2_stats,
        b_wf, f1_wf, f2_wf,
        b_year, f1_year, f2_year,
        f1_df, f2_df,
        f1_diag, f2_diag,
        baseline_df,
    )
    print(f"\nTotal elapsed: {(time.time()-t0):.1f}s", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


def write_report(
    b_stats, f1_stats, f2_stats,
    b_wf, f1_wf, f2_wf,
    b_year, f1_year, f2_year,
    f1_df, f2_df,
    f1_diag, f2_diag,
    baseline_df,
):
    fmt_money = lambda v: f"${v:,.0f}" if not (isinstance(v, float) and (np.isnan(v) or np.isinf(v))) else "—"
    fmt_money2 = lambda v: f"${v:,.2f}" if not (isinstance(v, float) and (np.isnan(v) or np.isinf(v))) else "—"
    fmt_pct = lambda v: f"{v:.1%}" if not (isinstance(v, float) and np.isnan(v)) else "—"

    lines: list[str] = []
    lines.append("# Cluster-size filter test — V2 + 40/40 with MIN_CLUSTER_SIZE = {4, 5}")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("**Change tested:** raise `MIN_CLUSTER_SIZE` from baseline 3 to 4 (F1) and 5 (F2).")
    lines.append("**All other rules unchanged from V2 + 40/40 baseline:**")
    lines.append("- ADX(15,30) ∧ DI(15,8) unanimous classifier, FADE/TREND side-flip")
    lines.append("- 1 contract, 40-pt stop / 40-pt target, 1:1 R:R")
    lines.append("- Near-border entry (cluster.low for short, cluster.high for long)")
    lines.append("- 9:46–11:30 NY window, force-close at 11:30 bar open")
    lines.append("- 3-pt cluster gap, 200-session lookback, C2 one-position-at-a-time, stop-first conservative")
    lines.append("")
    lines.append("Baseline column copied from `results/archive/strategy_report_20260512/strategy_4040_test.md` "
                 "(v2 40/40). F1 and F2 freshly run; baseline NOT re-run.")
    lines.append("")

    # Headline 3-way table
    lines.append("## Headline stats — baseline vs F1 vs F2")
    lines.append("")
    lines.append("| Metric | Baseline (size ≥ 3) | F1: size ≥ 4 | F2: size ≥ 5 |")
    lines.append("|---|---:|---:|---:|")
    metrics = [
        ("Trades", lambda h: f"{h['n_trades']:,}"),
        ("WR%", lambda h: fmt_pct(h["win_rate"])),
        ("Total P&L", lambda h: f"**{fmt_money(h['total_pnl'])}**"),
        ("Mean per entry", lambda h: fmt_money2(h["mean_pnl"])),
        ("Avg winner", lambda h: fmt_money(h["avg_winner"])),
        ("Avg loser", lambda h: fmt_money(h["avg_loser"])),
        ("PF", lambda h: f"{h['profit_factor']:.3f}" if h["profit_factor"] != float("inf") else "∞"),
        ("Max DD", lambda h: fmt_money(h["max_dd"])),
        ("DD duration (days)", lambda h: f"{h['max_dd_duration_days']}"),
        ("DD recovered", lambda h: "yes" if h["max_dd_recovered"] else "no"),
        ("Ann. Sharpe", lambda h: f"{h['sharpe_ann']:.2f}"),
        ("Ann. Sortino", lambda h: f"{h['sortino_ann']:.2f}"),
    ]
    for label, fn in metrics:
        cells = [fn(b_stats), fn(f1_stats), fn(f2_stats)]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    # WF rows
    wf_metrics = [
        ("WF Sharpe-like", lambda w: f"**{w['wf_sharpe_like']:.2f}**"),
        ("Median per-window OOS", lambda w: fmt_money(w["wf_median_oos"])),
        ("Sign stability k/7", lambda w: f"{w['wf_sign_count']}/7"),
        ("Sum per-window OOS", lambda w: fmt_money(w["wf_oos_sum"])),
        ("4-gate qualified", lambda w: "✓" if w["wf_qualifies_deploy"] else " "),
    ]
    for label, fn in wf_metrics:
        cells = [fn(b_wf), fn(f1_wf), fn(f2_wf)]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")

    def write_variant_subsection(name: str, df: pd.DataFrame, st: dict, wfs: dict,
                                 yr: pd.DataFrame, diag: dict, min_size: int):
        lines.append(f"## {name}")
        lines.append("")

        # 1. Walk-forward per-window OOS
        windows = wf.make_windows()
        lines.append(f"### Walk-forward per-window OOS")
        lines.append("")
        lines.append("| " + " | ".join(w.name for w in windows) + " | Sharpe-like | Sign |")
        lines.append("|" + "|".join(["---:"] * (len(windows) + 2)) + "|")
        cells = [fmt_money(wfs[f"wf_{w.name}"]) for w in windows]
        lines.append("| " + " | ".join(cells) + f" | {wfs['wf_sharpe_like']:.2f} | {wfs['wf_sign_count']}/7 |")
        lines.append("")

        # 2. Calendar-year P&L
        lines.append("### Calendar-year P&L")
        lines.append("")
        lines.append("| Year | Trades | P&L | WR% |")
        lines.append("|---:|---:|---:|---:|")
        for y in sorted(yr.index):
            lines.append(f"| {y} | {int(yr.loc[y,'n_trades'])} | {fmt_money(yr.loc[y,'pnl'])} | {fmt_pct(yr.loc[y,'win_rate'])} |")
        lines.append("")

        # 3. Exit-type breakdown
        lines.append("### Exit-type breakdown")
        lines.append("")
        eb = exit_breakdown(df)
        lines.append("| Exit | Count | Mean P&L | Total P&L |")
        lines.append("|---|---:|---:|---:|")
        for reason in ["target", "stop", "force_close"]:
            if reason in eb.index:
                row = eb.loc[reason]
                lines.append(f"| {reason} | {int(row['count'])} | {fmt_money2(row['mean_pnl'])} | {fmt_money(row['total_pnl'])} |")
            else:
                lines.append(f"| {reason} | 0 | — | — |")
        lines.append("")

        # 4. FADE/TREND label split
        lines.append("### FADE/TREND label split")
        lines.append("")
        ls = label_split(df)
        baseline_ls = label_split(baseline_df)
        lines.append(f"- Baseline: {baseline_ls['FADE']} FADE / {baseline_ls['TREND']} TREND")
        lines.append(f"- {name}: {ls['FADE']} FADE / {ls['TREND']} TREND")
        lines.append("")

        # 5. Cluster-size distribution (post-filter)
        lines.append("### Cluster-size distribution (3 / 4 / 5 / 6 / 7+)")
        lines.append("")
        csd = cluster_size_distribution(df)
        lines.append("| Size | Count | Mean P&L | Total P&L |")
        lines.append("|---:|---:|---:|---:|")
        for size in [3, 4, 5, 6, 7]:
            label = "7+" if size == 7 else str(size)
            if size in csd.index:
                row = csd.loc[size]
                lines.append(f"| {label} | {int(row['count'])} | {fmt_money2(row['mean_pnl'])} | {fmt_money(row['total_pnl'])} |")
            else:
                lines.append(f"| {label} | 0 | — | — |")
        lines.append("")

        # 6. Filter-effect diagnostic
        lines.append(f"### Filter-effect diagnostic vs baseline (matched by session_date + cluster_low + cluster_high)")
        lines.append("")
        lines.append(f"- Baseline trades that do NOT appear in this variant: **{diag['n_filtered_out']}**")
        lines.append(f"- Total P&L of those filtered-out trades (in baseline): **{fmt_money(diag['total_pnl_filtered'])}**")
        lines.append(f"- WR% of filtered-out trades: **{fmt_pct(diag['win_rate_filtered'])}**")
        lines.append(f"- Of those, cluster_size < {min_size} (filter-explained): {diag['below_threshold']}")
        lines.append(f"- Of those, cluster_size >= {min_size} (C2-reorder displaced): {diag['at_or_above_threshold']}")
        lines.append("")
        lines.append("Exit-type breakdown of filtered-out trades:")
        lines.append("")
        lines.append("| Exit | Count | Mean P&L | Total P&L |")
        lines.append("|---|---:|---:|---:|")
        feb = diag["exit_breakdown"]
        for reason in ["target", "stop", "force_close"]:
            if reason in feb.index:
                row = feb.loc[reason]
                lines.append(f"| {reason} | {int(row['count'])} | {fmt_money2(row['mean_pnl'])} | {fmt_money(row['total_pnl'])} |")
            else:
                lines.append(f"| {reason} | 0 | — | — |")
        lines.append("")
        if diag["by_size"]:
            lines.append("Filtered-out trades by cluster_size (raw):")
            lines.append("")
            lines.append("| Size | Count |")
            lines.append("|---:|---:|")
            for s in sorted(diag["by_size"]):
                lines.append(f"| {int(s)} | {int(diag['by_size'][s])} |")
            lines.append("")

    write_variant_subsection("F1 — MIN_CLUSTER_SIZE = 4", f1_df, f1_stats, f1_wf, f1_year, f1_diag, 4)
    write_variant_subsection("F2 — MIN_CLUSTER_SIZE = 5", f2_df, f2_stats, f2_wf, f2_year, f2_diag, 5)

    lines.append("## Files")
    lines.append("")
    lines.append("- `report.md` — this report")
    lines.append("- `trades_v2_4040_size4.parquet` — F1 trades")
    lines.append("- `trades_v2_4040_size5.parquet` — F2 trades")
    lines.append("")

    (OUT_DIR / "report.md").write_text("\n".join(lines))
    print(f"\nWrote {OUT_DIR / 'report.md'}", flush=True)

    # Terminal echo per spec: three-column table + filter diagnostics.
    print("\n" + "=" * 78)
    print("THREE-COLUMN COMPARISON")
    print("=" * 78)
    print(f"{'Metric':<28} {'Baseline':>14} {'F1 (>=4)':>14} {'F2 (>=5)':>14}")
    print("-" * 78)
    for label, fn in metrics + wf_metrics:
        b = fn(b_stats) if label in {"Trades","WR%","Total P&L","Mean per entry","Avg winner","Avg loser","PF","Max DD","DD duration (days)","DD recovered","Ann. Sharpe","Ann. Sortino"} else fn(b_wf)
        f1c = fn(f1_stats) if label in {"Trades","WR%","Total P&L","Mean per entry","Avg winner","Avg loser","PF","Max DD","DD duration (days)","DD recovered","Ann. Sharpe","Ann. Sortino"} else fn(f1_wf)
        f2c = fn(f2_stats) if label in {"Trades","WR%","Total P&L","Mean per entry","Avg winner","Avg loser","PF","Max DD","DD duration (days)","DD recovered","Ann. Sharpe","Ann. Sortino"} else fn(f2_wf)
        b = b.replace("**", "")
        f1c = f1c.replace("**", "")
        f2c = f2c.replace("**", "")
        print(f"{label:<28} {b:>14} {f1c:>14} {f2c:>14}")
    print("=" * 78)
    print()
    print("FILTER-EFFECT DIAGNOSTIC — F1 (size>=4)")
    print(f"  filtered-out trades: {f1_diag['n_filtered_out']}")
    print(f"  total P&L of filtered: ${f1_diag['total_pnl_filtered']:,.0f}")
    print(f"  WR% of filtered: {f1_diag['win_rate_filtered']:.1%}" if not np.isnan(f1_diag['win_rate_filtered']) else "  WR% of filtered: —")
    print(f"  by size: {f1_diag['by_size']}")
    print()
    print("FILTER-EFFECT DIAGNOSTIC — F2 (size>=5)")
    print(f"  filtered-out trades: {f2_diag['n_filtered_out']}")
    print(f"  total P&L of filtered: ${f2_diag['total_pnl_filtered']:,.0f}")
    print(f"  WR% of filtered: {f2_diag['win_rate_filtered']:.1%}" if not np.isnan(f2_diag['win_rate_filtered']) else "  WR% of filtered: —")
    print(f"  by size: {f2_diag['by_size']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
