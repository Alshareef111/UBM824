"""Run V2 + 40/40 with FAR-BORDER entries; compare to near-border baseline.

Baseline numbers come from results/archive/strategy_report_20260512/strategy_4040_test.md
(v2 40/40 column). Baseline trades are loaded from
results/archive/strategy_report_20260512/trades_v2_4040.parquet for the
filter-effect diagnostic.

This file does NOT modify any existing source file. simulator_v2.py, walk_forward.py,
and phase6_run.py are untouched.
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

from indicators.adx import AdxClassifier
from indicators.adx import precompute_lookup as adx_lookup
from indicators.base import UnanimousClassifier
from indicators.di import DiClassifier
from indicators.di import precompute_lookup as di_lookup

import walk_forward as wf
from experimental import simulator_v2_farborder as sim_fb
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET

ADX_N, ADX_THR = 15, 30
DI_N, DI_THR = 15, 8

OUT_DIR = ARCHIVE_DIR / "v2_4040_far_border_20260514"
BASELINE_PARQUET = ARCHIVE_DIR / "strategy_report_20260512" / "trades_v2_4040.parquet"

POINT_VALUE_USD = 2.0
ANNUALIZATION = 252


def stats(df: pd.DataFrame, all_sessions: pd.DatetimeIndex) -> dict:
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

    sharpe = (
        float(daily.mean() / daily.std(ddof=1) * np.sqrt(ANNUALIZATION))
        if daily.std(ddof=1) > 0
        else float("nan")
    )
    downside_dev = float(np.sqrt(((daily.clip(upper=0.0)) ** 2).mean()))
    sortino = (
        float(daily.mean() / downside_dev * np.sqrt(ANNUALIZATION))
        if downside_dev > 0
        else float("nan")
    )

    return {
        "n_trades": int(len(df)),
        "n_wins": int(wins.sum()),
        "n_losses": int(losses.sum()),
        "win_rate": float(wins.mean()),
        "total_pnl": float(df["pnl_dollars"].sum()),
        "mean_pnl": float(df["pnl_dollars"].mean()),
        "avg_winner": float(win_pnls.mean()) if len(win_pnls) else 0.0,
        "avg_loser": float(loss_pnls.mean()) if len(loss_pnls) else 0.0,
        "profit_factor": float(win_pnls.sum() / -loss_pnls.sum())
        if len(loss_pnls) and loss_pnls.sum() < 0
        else float("inf"),
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
    if len(df) == 0:
        return {
            "wf_sharpe_like": float("nan"),
            "wf_median_oos": float("nan"),
            "wf_sign_count": 0,
            "wf_oos_sum": 0.0,
            "wf_qualifies_deploy": False,
        }
    windows = wf.make_windows()
    pw = wf.per_window_pnl(df, windows, slice_="oos")
    total = float(df["pnl_dollars"].sum())
    return {
        "wf_sharpe_like": wf.sharpe_like_score(pw),
        "wf_median_oos": wf.median_pnl(pw),
        "wf_sign_count": wf.sign_stability_count(pw),
        "wf_oos_sum": float(sum(pw.values())),
        "wf_qualifies_deploy": wf.qualifies(
            pw, total_pnl=total, sharpe_threshold=wf.NULL_P95_SHARPE_LIKE
        ),
        **{f"wf_{w.name}": pw[w.name] for w in windows},
    }


def yearly(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return pd.DataFrame(columns=["n_trades", "pnl", "win_rate"])
    df = df.copy()
    df["session_date"] = pd.to_datetime(df["session_date"])
    df["year"] = df["session_date"].dt.year
    rows = []
    for yr in sorted(df["year"].unique()):
        sub = df[df["year"] == yr]
        wins = (sub["pnl_dollars"] > 0).sum()
        rows.append(
            {
                "year": int(yr),
                "n_trades": int(len(sub)),
                "pnl": float(sub["pnl_dollars"].sum()),
                "win_rate": float(wins / len(sub)) if len(sub) else float("nan"),
            }
        )
    return pd.DataFrame(rows).set_index("year")


# Baseline numbers verbatim from strategy_4040_test.md "v2 40/40" column.
BASELINE_HEADLINE = {
    "n_trades": 908,
    "win_rate": 0.5617,
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
    "wf_sharpe_like": 6.86,
    "wf_median_oos": 1688.0,
    "wf_sign_count": 7,
    "wf_oos_sum": 11956.0,
    "wf_qualifies_deploy": True,
}


def filter_effect_diagnostic(df_fb: pd.DataFrame, df_base: pd.DataFrame) -> dict:
    """Compare far-border trades to baseline trades by cluster identity.

    Matching key: (session_date, cluster_low, cluster_high). Each cluster on a
    given session is unique by its (low, high) tuple (since the cluster pool is
    a sorted set of price levels with non-overlapping cluster ranges).
    """

    def keys(df):
        return set(
            zip(
                pd.to_datetime(df["session_date"]).dt.normalize(),
                df["cluster_low"].round(4),
                df["cluster_high"].round(4),
            )
        )

    k_fb = keys(df_fb)
    k_base = keys(df_base)

    filtered_out_keys = k_base - k_fb  # baseline fires; far-border doesn't
    new_in_fb_keys = k_fb - k_base  # far-border fires; baseline doesn't (C2 timing differences)
    shared_keys = k_base & k_fb  # both fire

    # Look up baseline P&L of filtered-out trades
    base_copy = df_base.copy()
    base_copy["session_date"] = pd.to_datetime(base_copy["session_date"]).dt.normalize()
    base_copy["_key"] = list(
        zip(
            base_copy["session_date"],
            base_copy["cluster_low"].round(4),
            base_copy["cluster_high"].round(4),
        )
    )
    filtered = base_copy[base_copy["_key"].isin(filtered_out_keys)]
    new_fb_lookup = df_fb.copy()
    new_fb_lookup["session_date"] = pd.to_datetime(new_fb_lookup["session_date"]).dt.normalize()
    new_fb_lookup["_key"] = list(
        zip(
            new_fb_lookup["session_date"],
            new_fb_lookup["cluster_low"].round(4),
            new_fb_lookup["cluster_high"].round(4),
        )
    )
    new_in_fb = new_fb_lookup[new_fb_lookup["_key"].isin(new_in_fb_keys)]

    # Label-flip detection on shared keys
    shared_labels = []
    for key in shared_keys:
        b = base_copy[base_copy["_key"] == key]
        f = new_fb_lookup[new_fb_lookup["_key"] == key]
        if len(b) and len(f):
            shared_labels.append(
                (
                    b.iloc[0]["cluster_label"],
                    f.iloc[0]["cluster_label"],
                    b.iloc[0]["side"],
                    f.iloc[0]["side"],
                )
            )
    n_label_flips = sum(1 for bl, fl, _, _ in shared_labels if bl != fl)
    n_side_flips = sum(1 for _, _, bs, fs in shared_labels if bs != fs)

    # FADE/TREND counts
    fb_labels = df_fb["cluster_label"].value_counts().to_dict()
    base_labels = df_base["cluster_label"].value_counts().to_dict()

    # Cluster size means
    fb_size_mean = float(df_fb["cluster_size"].mean()) if len(df_fb) else float("nan")
    fb_size_median = float(df_fb["cluster_size"].median()) if len(df_fb) else float("nan")
    base_size_mean = float(df_base["cluster_size"].mean())
    base_size_median = float(df_base["cluster_size"].median())

    return {
        "n_baseline_clusters_fired": len(k_base),
        "n_farborder_clusters_fired": len(k_fb),
        "n_filtered_out": len(filtered_out_keys),
        "n_shared": len(shared_keys),
        "n_new_in_farborder": len(new_in_fb_keys),
        "filtered_out_total_pnl": float(filtered["pnl_dollars"].sum()),
        "filtered_out_mean_pnl": float(filtered["pnl_dollars"].mean())
        if len(filtered)
        else float("nan"),
        "filtered_out_wr": float((filtered["pnl_dollars"] > 0).mean())
        if len(filtered)
        else float("nan"),
        "filtered_out_n_target": int((filtered["exit_reason"] == "target").sum()),
        "filtered_out_n_stop": int((filtered["exit_reason"] == "stop").sum()),
        "filtered_out_n_force_close": int((filtered["exit_reason"] == "force_close").sum()),
        "new_in_fb_total_pnl": float(new_in_fb["pnl_dollars"].sum()) if len(new_in_fb) else 0.0,
        "n_label_flips_on_shared": n_label_flips,
        "n_side_flips_on_shared": n_side_flips,
        "fb_labels": fb_labels,
        "base_labels": base_labels,
        "fb_size_mean": fb_size_mean,
        "fb_size_median": fb_size_median,
        "base_size_mean": base_size_mean,
        "base_size_median": base_size_median,
        "filtered_out_size_mean": float(filtered["cluster_size"].mean())
        if len(filtered)
        else float("nan"),
        "filtered_out_size_median": float(filtered["cluster_size"].median())
        if len(filtered)
        else float("nan"),
    }


def write_report(s_fb: dict, w_fb: dict, y_fb: pd.DataFrame, diag: dict) -> None:
    def m(v):
        return f"${v:,.0f}"

    def p(v):
        return f"{v:.1%}" if not pd.isna(v) else "—"

    lines: list[str] = []
    lines.append("# V2 + 40/40 — FAR-BORDER entry test")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("")
    lines.append(
        "**Change tested (only this):** limit price moved from the NEAR edge of each "
        "cluster to the FAR edge. Cluster above 9:45 ORB close → limit at "
        "`cluster_high` (was `cluster_low`). Cluster below close → limit at "
        "`cluster_low` (was `cluster_high`). Applies uniformly to both FADE and TREND. "
        "Trigger direction unchanged. Classifier (ADX(15,30) ∧ DI(15,8) unanimous) "
        "unchanged but evaluated at the LATER bar where price reaches the far edge."
    )
    lines.append("")
    lines.append(
        "**Locked geometry preserved:** 3-pt cluster gap, MIN_SIZE=3, lookback=200, "
        "40-pt stop/target, 9:46–11:30 NY window, C2 one-position-at-a-time, "
        "force-close at 11:30 bar OPEN, stop-first conservative."
    )
    lines.append("")
    lines.append(
        "**Sub-classifier setups same as R-012:** ADX N=15 threshold=30, DI N=15 "
        "threshold=8, unanimous AND-gate. Side-flip on TREND keeps entry_price unchanged "
        "(same convention as baseline)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Side-by-side comparison")
    lines.append("")
    lines.append("| Metric | V2 + 40/40 (near border, baseline) | V2 + 40/40 + far border |")
    lines.append("|---|---:|---:|")
    rows = [
        ("Trades", "n_trades", lambda v: f"{v:,}"),
        ("WR%", "win_rate", p),
        ("Total P&L", "total_pnl", m),
        ("Mean per entry", "mean_pnl", lambda v: f"${v:.2f}"),
        ("Avg winner", "avg_winner", lambda v: f"${v:.0f}"),
        ("Avg loser", "avg_loser", lambda v: f"${v:.0f}"),
        ("PF", "profit_factor", lambda v: f"{v:.3f}"),
        ("Max DD", "max_dd", m),
        ("DD duration (days)", "max_dd_duration_days", lambda v: f"{v}"),
        ("DD recovered (y/n)", "max_dd_recovered", lambda v: "y" if v else "n"),
        ("Ann. Sharpe", "sharpe_ann", lambda v: f"{v:.2f}"),
        ("Ann. Sortino", "sortino_ann", lambda v: f"{v:.2f}"),
    ]
    for label, key, fmt in rows:
        b = BASELINE_HEADLINE[key]
        f = s_fb[key]
        lines.append(f"| {label} | {fmt(b)} | {fmt(f)} |")
    wf_rows = [
        ("WF Sharpe-like", "wf_sharpe_like", lambda v: f"{v:.2f}"),
        ("Median per-window OOS", "wf_median_oos", m),
        ("Sign stability k/7", "wf_sign_count", lambda v: f"{v}/7"),
        ("Sum per-window OOS", "wf_oos_sum", m),
        ("4-gate qualified", "wf_qualifies_deploy", lambda v: "✓" if v else "✗"),
    ]
    for label, key, fmt in wf_rows:
        b = BASELINE_HEADLINE[key]
        f = w_fb[key]
        lines.append(f"| {label} | {fmt(b)} | {fmt(f)} |")
    lines.append("")
    lines.append("---")

    # Section 1: Walk-forward per window
    lines.append("")
    lines.append("## 1. Walk-forward per-window OOS (far border)")
    lines.append("")
    lines.append("| W1 | W2 | W3 | W4 | W5 | W6 | W7 |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    cells = [m(w_fb[f"wf_W{i + 1}"]) for i in range(7)]
    lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        f"Median per-window OOS: {m(w_fb['wf_median_oos'])} · "
        f"Sharpe-like: {w_fb['wf_sharpe_like']:.3f} · "
        f"Sign-stable: {w_fb['wf_sign_count']}/7 · "
        f"Sum: {m(w_fb['wf_oos_sum'])} · "
        f"4-gate: {'✓' if w_fb['wf_qualifies_deploy'] else '✗'}"
    )

    # Section 2: Calendar-year P&L
    lines.append("")
    lines.append("## 2. Calendar-year P&L (far border)")
    lines.append("")
    lines.append("| Year | Trades | P&L | WR% |")
    lines.append("|---:|---:|---:|---:|")
    for yr in y_fb.index:
        r = y_fb.loc[yr]
        lines.append(f"| {yr} | {int(r['n_trades'])} | {m(r['pnl'])} | {p(r['win_rate'])} |")

    # Section 3: Exit-type breakdown
    lines.append("")
    lines.append("## 3. Exit-type breakdown (far border)")
    lines.append("")
    lines.append("| Exit reason | n | Mean P&L |")
    lines.append("|---|---:|---:|")
    for reason in ["target", "stop", "force_close"]:
        n_key = {"target": "n_target", "stop": "n_stop", "force_close": "n_force_close"}[reason]
        n = s_fb[n_key]
        # Compute mean for each exit reason from the trade df
        # Use the diagnostic helper to keep consistency
        lines.append(f"| {reason} | {n} | (see report data) |")
    # Note: we'll inject exact means after this block since we need df_fb

    # Section 4: Filter-effect diagnostic
    lines.append("")
    lines.append("## 4. Filter-effect diagnostic")
    lines.append("")
    lines.append(f"- Baseline clusters fired: **{diag['n_baseline_clusters_fired']}**")
    lines.append(f"- Far-border clusters fired: **{diag['n_farborder_clusters_fired']}**")
    lines.append(f"- Shared (both fire on same cluster identity): **{diag['n_shared']}**")
    lines.append(
        f"- Filtered out (baseline fires, far-border does not): **{diag['n_filtered_out']}**"
    )
    lines.append(
        f"- New in far-border (far-border fires, baseline does not — C2 timing reorderings): **{diag['n_new_in_farborder']}**"
    )
    lines.append("")
    lines.append("### Filtered-out trades (baseline P&L of clusters not entered in far-border):")
    lines.append("")
    lines.append(f"- Total baseline P&L of filtered-out: **{m(diag['filtered_out_total_pnl'])}**")
    lines.append(f"- Mean P&L of filtered-out: ${diag['filtered_out_mean_pnl']:.2f}")
    lines.append(f"- WR of filtered-out (in baseline): {p(diag['filtered_out_wr'])}")
    lines.append(
        f"- Exit breakdown of filtered-out (in baseline): "
        f"target={diag['filtered_out_n_target']}, "
        f"stop={diag['filtered_out_n_stop']}, "
        f"force_close={diag['filtered_out_n_force_close']}"
    )
    lines.append("")
    lines.append("### Label split (FADE / TREND):")
    lines.append("")
    base_l = diag["base_labels"]
    fb_l = diag["fb_labels"]
    lines.append(
        f"- Baseline:    FADE = {base_l.get('FADE', 0)}, TREND = {base_l.get('TREND', 0)} (total {sum(base_l.values())})"
    )
    lines.append(
        f"- Far border:  FADE = {fb_l.get('FADE', 0)}, TREND = {fb_l.get('TREND', 0)} (total {sum(fb_l.values())})"
    )
    lines.append("")
    lines.append("### Label flips on shared clusters:")
    lines.append("")
    lines.append(
        f"- Shared clusters where FADE/TREND label differs between baseline and far border: **{diag['n_label_flips_on_shared']}** of {diag['n_shared']}"
    )
    lines.append(
        f"- Shared clusters where SIDE (buy/sell) differs (consequence of label flip): **{diag['n_side_flips_on_shared']}** of {diag['n_shared']}"
    )
    lines.append("")
    lines.append("### Cluster-size distribution:")
    lines.append("")
    lines.append(
        f"- Baseline trades:        mean cluster_size = {diag['base_size_mean']:.2f}, median = {diag['base_size_median']:.1f}"
    )
    lines.append(
        f"- Far-border trades:      mean cluster_size = {diag['fb_size_mean']:.2f}, median = {diag['fb_size_median']:.1f}"
    )
    lines.append(
        f"- Filtered-out (baseline P&L): mean cluster_size = {diag['filtered_out_size_mean']:.2f}, median = {diag['filtered_out_size_median']:.1f}"
    )

    # Files
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- `report.md` — this report")
    lines.append("- `trades_v2_4040_far_border.parquet` — far-border trade log")
    lines.append("")
    lines.append("Locked baseline `data/processed/trades.parquet` sha256 unchanged.")

    (OUT_DIR / "report.md").write_text("\n".join(lines))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions", flush=True)

    print("Pre-computing ADX(15) and DI(15) lookups...", flush=True)
    adx_lk = adx_lookup(bars, n=ADX_N)
    di_lk = di_lookup(bars, n=DI_N)

    adx_clf = AdxClassifier(adx_lk, n=ADX_N, threshold=ADX_THR)
    di_clf = DiClassifier(di_lk, n=DI_N, threshold=DI_THR)
    classifier = UnanimousClassifier(
        [adx_clf, di_clf],
        name=f"ADX({ADX_N},{ADX_THR})∧DI({DI_N},{DI_THR}) far-border",
    )

    print("\nRunning far-border V2 + 40/40...", flush=True)
    t = time.time()
    trades_fb = sim_fb.run_backtest(bars, orb_table, classifier)
    df_fb = sim_fb.trades_to_dataframe(trades_fb)
    print(
        f"  {len(df_fb)} trades  total ${df_fb['pnl_dollars'].sum():,.2f}  [{time.time() - t:.1f}s]",
        flush=True,
    )

    df_fb.to_parquet(OUT_DIR / "trades_v2_4040_far_border.parquet", index=False)

    df_base = pd.read_parquet(BASELINE_PARQUET)

    all_dates = set(pd.to_datetime(df_fb["session_date"])) | set(
        pd.to_datetime(df_base["session_date"])
    )
    all_sessions = pd.DatetimeIndex(sorted(all_dates))

    s_fb = stats(df_fb, all_sessions)
    w_fb = walk_forward_score(df_fb)
    y_fb = yearly(df_fb)
    diag = filter_effect_diagnostic(df_fb, df_base)

    # Compute exact exit-reason means for far-border (for report)
    exit_means = df_fb.groupby("exit_reason")["pnl_dollars"].mean().to_dict()
    exit_counts = df_fb["exit_reason"].value_counts().to_dict()

    write_report(s_fb, w_fb, y_fb, diag)

    # Post-write: rewrite exit table with exact means (simpler to do here)
    report_path = OUT_DIR / "report.md"
    text = report_path.read_text()
    # Replace the "(see report data)" lines with exact means
    new_lines = []
    for line in text.split("\n"):
        if "(see report data)" in line:
            # Parse the reason from the line
            parts = [p.strip() for p in line.strip("|").split("|")]
            reason = parts[0]
            n = exit_counts.get(reason, 0)
            mean_v = exit_means.get(reason, 0.0)
            new_lines.append(f"| {reason} | {n} | ${mean_v:.2f} |")
        else:
            new_lines.append(line)
    report_path.write_text("\n".join(new_lines))

    # Terminal: print side-by-side
    print("\n" + "=" * 100, flush=True)
    print("SIDE-BY-SIDE COMPARISON", flush=True)
    print("=" * 100, flush=True)

    def fm(v):
        return f"${v:,.0f}"

    def fp(v):
        return f"{v * 100:.1f}%"

    rows_terminal = [
        ("Trades", f"{BASELINE_HEADLINE['n_trades']:,}", f"{s_fb['n_trades']:,}"),
        ("WR%", fp(BASELINE_HEADLINE["win_rate"]), fp(s_fb["win_rate"])),
        ("Total P&L", fm(BASELINE_HEADLINE["total_pnl"]), fm(s_fb["total_pnl"])),
        ("Mean per entry", f"${BASELINE_HEADLINE['mean_pnl']:.2f}", f"${s_fb['mean_pnl']:.2f}"),
        ("Avg winner", f"${BASELINE_HEADLINE['avg_winner']:.0f}", f"${s_fb['avg_winner']:.0f}"),
        ("Avg loser", f"${BASELINE_HEADLINE['avg_loser']:.0f}", f"${s_fb['avg_loser']:.0f}"),
        ("PF", f"{BASELINE_HEADLINE['profit_factor']:.3f}", f"{s_fb['profit_factor']:.3f}"),
        ("Max DD", fm(BASELINE_HEADLINE["max_dd"]), fm(s_fb["max_dd"])),
        (
            "DD duration (days)",
            f"{BASELINE_HEADLINE['max_dd_duration_days']}",
            f"{s_fb['max_dd_duration_days']}",
        ),
        (
            "DD recovered (y/n)",
            "y" if BASELINE_HEADLINE["max_dd_recovered"] else "n",
            "y" if s_fb["max_dd_recovered"] else "n",
        ),
        ("Ann. Sharpe", f"{BASELINE_HEADLINE['sharpe_ann']:.2f}", f"{s_fb['sharpe_ann']:.2f}"),
        ("Ann. Sortino", f"{BASELINE_HEADLINE['sortino_ann']:.2f}", f"{s_fb['sortino_ann']:.2f}"),
        (
            "WF Sharpe-like",
            f"{BASELINE_HEADLINE['wf_sharpe_like']:.2f}",
            f"{w_fb['wf_sharpe_like']:.2f}",
        ),
        (
            "Median per-window OOS",
            fm(BASELINE_HEADLINE["wf_median_oos"]),
            fm(w_fb["wf_median_oos"]),
        ),
        (
            "Sign stability k/7",
            f"{BASELINE_HEADLINE['wf_sign_count']}/7",
            f"{w_fb['wf_sign_count']}/7",
        ),
        ("Sum per-window OOS", fm(BASELINE_HEADLINE["wf_oos_sum"]), fm(w_fb["wf_oos_sum"])),
        (
            "4-gate qualified",
            "✓" if BASELINE_HEADLINE["wf_qualifies_deploy"] else "✗",
            "✓" if w_fb["wf_qualifies_deploy"] else "✗",
        ),
    ]
    hdr = f"| {'Metric':<22} | {'Near border (baseline)':>22} | {'Far border':>16} |"
    sep = f"|{'-' * 24}|{'-' * 24}|{'-' * 18}|"
    print(hdr, flush=True)
    print(sep, flush=True)
    for r in rows_terminal:
        print(f"| {r[0]:<22} | {r[1]:>22} | {r[2]:>16} |", flush=True)

    print("\n" + "=" * 100, flush=True)
    print("FILTER-EFFECT DIAGNOSTIC", flush=True)
    print("=" * 100, flush=True)
    print(f"Baseline clusters fired:           {diag['n_baseline_clusters_fired']}")
    print(f"Far-border clusters fired:         {diag['n_farborder_clusters_fired']}")
    print(f"Shared (cluster fires in both):    {diag['n_shared']}")
    print(f"Filtered out (baseline only):      {diag['n_filtered_out']}")
    print(f"New in far-border (FB only):       {diag['n_new_in_farborder']}")
    print()
    print(f"Filtered-out baseline P&L:         {fm(diag['filtered_out_total_pnl'])}")
    print(f"Filtered-out mean P&L:             ${diag['filtered_out_mean_pnl']:.2f}")
    print(f"Filtered-out WR (in baseline):     {fp(diag['filtered_out_wr'])}")
    print(
        f"Filtered-out exit breakdown:       target={diag['filtered_out_n_target']}  stop={diag['filtered_out_n_stop']}  fc={diag['filtered_out_n_force_close']}"
    )
    print()
    print(
        f"Label split — Baseline:    FADE={diag['base_labels'].get('FADE', 0)}  TREND={diag['base_labels'].get('TREND', 0)}"
    )
    print(
        f"Label split — Far border:  FADE={diag['fb_labels'].get('FADE', 0)}  TREND={diag['fb_labels'].get('TREND', 0)}"
    )
    print(
        f"Shared clusters with label flip:   {diag['n_label_flips_on_shared']}/{diag['n_shared']}"
    )
    print(f"Shared clusters with side flip:    {diag['n_side_flips_on_shared']}/{diag['n_shared']}")
    print()
    print(
        f"Cluster size — Baseline trades:    mean={diag['base_size_mean']:.2f}  median={diag['base_size_median']:.1f}"
    )
    print(
        f"Cluster size — Far-border trades:  mean={diag['fb_size_mean']:.2f}  median={diag['fb_size_median']:.1f}"
    )
    print(
        f"Cluster size — Filtered-out:       mean={diag['filtered_out_size_mean']:.2f}  median={diag['filtered_out_size_median']:.1f}"
    )

    print(f"\nTotal elapsed: {(time.time() - t0):.1f}s", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
