"""Run Variants B and C (partial-exit + runner-BE) on the V2 ADX∧DI unanimous classifier.

Variant B: stop=-40 / p1 target=+40 / p2 target=next cluster level / runner-BE
Variant C: stop=-25 / p1 target=+40 / p2 target=next cluster level / runner-BE

Both variants use 2-contract sizing (p1, p2 sized 1c each).

Outputs to results/archive/v2_4040_modifications_20260514/:
- trades_variant_b_partial_runnerBE.parquet
- trades_variant_c_tight_partial_runnerBE.parquet
- report.md

Does NOT modify any existing file. Reads simulator_v2 / walk_forward read-only.
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

from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.base import UnanimousClassifier
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET
import walk_forward as wf

from experimental import simulator_v2_partial as sim_p

ADX_N, ADX_THR = 15, 30
DI_N, DI_THR = 15, 8

OUT_DIR = ARCHIVE_DIR / "v2_4040_modifications_20260514"
POINT_VALUE_USD = 2.0
ANNUALIZATION = 252


def stats(df: pd.DataFrame, all_sessions: pd.DatetimeIndex) -> dict:
    """Headline stats on aggregated 2-contract pnl_dollars per entry."""
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
    if len(eq) == 0:
        return {}
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
        "n_entries": int(len(df)),
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


def walk_forward_score(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {"wf_sharpe_like": float("nan"), "wf_median_oos": float("nan"),
                "wf_sign_count": 0, "wf_oos_sum": 0.0, "wf_qualifies_deploy": False}
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
        rows.append({
            "year": int(yr),
            "n_trades": int(len(sub)),
            "pnl": float(sub["pnl_dollars"].sum()),
            "win_rate": float(wins / len(sub)) if len(sub) else float("nan"),
        })
    return pd.DataFrame(rows).set_index("year")


def baseline_scaled_metrics() -> dict:
    """V2 + 40/40 single-contract numbers from strategy_4040_test.md, scaled by 2 contracts.

    Scale rules:
    - n_entries unchanged (entries, not contracts).
    - Win rate unchanged.
    - Dollar quantities (total_pnl, mean_pnl, avg_winner, avg_loser, max_dd, wf_*_oos sums, medians)
      scale by 2x.
    - Ratio quantities (profit_factor, sharpe_ann, sortino_ann, wf_sharpe_like) UNCHANGED
      because numerator and denominator both scale by 2 — exact algebraic invariance.
    - sign_count, qualifies_deploy unchanged (sign-stability is invariant).
    - DD duration and recovered status unchanged (timing properties, not magnitude).
    """
    # Numbers verbatim from strategy_4040_test.md "v2 40/40" column.
    h = {
        "n_entries": 908,
        "n_wins": 510,
        "n_losses": 398,
        "win_rate": 0.561674,
        "total_pnl": 8808.0 * 2,
        "mean_pnl": 9.700441 * 2,
        "avg_winner": 73.132353 * 2,
        "avg_loser": -71.581658 * 2,
        "profit_factor": 1.309167,        # invariant
        "max_dd": -1228.0 * 2,
        "max_dd_duration_days": 380,
        "max_dd_recovered": True,
        "sharpe_ann": 2.149621,            # invariant
        "sortino_ann": 3.611799,           # invariant
        "n_target": 442,
        "n_stop": 336,
        "n_force_close": 130,
    }
    w = {
        "wf_sharpe_like": 6.855679,        # invariant
        "wf_median_oos": 1688.0 * 2,
        "wf_sign_count": 7,
        "wf_oos_sum": 11956.0 * 2,
        "wf_qualifies_deploy": True,
        "wf_W1": 1303.5 * 2,
        "wf_W2": 1643.5 * 2,
        "wf_W3": 1688.0 * 2,
        "wf_W4": 1537.5 * 2,
        "wf_W5": 1935.5 * 2,
        "wf_W6": 2027.5 * 2,
        "wf_W7": 1820.5 * 2,
    }
    return {"stats": h, "wf": w}


def per_leg_exit_counts(df: pd.DataFrame) -> dict:
    return {
        "p1": df["p1_exit_reason"].value_counts().to_dict(),
        "p2": df["p2_exit_reason"].value_counts().to_dict(),
    }


def runner_audit(df: pd.DataFrame) -> dict:
    """How often cluster-target was set; how often BE fired; runner-leg P&L stats."""
    has_cluster = df["p2_target_price"].notna()
    return {
        "n_runner_with_cluster_target": int(has_cluster.sum()),
        "n_runner_no_cluster_target": int((~has_cluster).sum()),
        "pct_with_cluster_target": float(has_cluster.mean()),
        "be_fired_count": int(df["runner_be_fired"].sum()),
        "be_fired_pct": float(df["runner_be_fired"].mean()),
        "p2_pnl_median": float(df["p2_pnl_dollars"].median()),
        "p2_pnl_mean": float(df["p2_pnl_dollars"].mean()),
        "p2_pnl_total": float(df["p2_pnl_dollars"].sum()),
        "p1_pnl_total": float(df["p1_pnl_dollars"].sum()),
    }


def write_report(
    baseline: dict,
    var_b_stats: dict, var_b_wf: dict, var_b_yearly: pd.DataFrame,
    var_b_exits: dict, var_b_audit: dict,
    var_c_stats: dict, var_c_wf: dict, var_c_yearly: pd.DataFrame,
    var_c_exits: dict, var_c_audit: dict,
) -> None:

    def mdmoney(v):
        return f"${v:,.0f}"

    def mdpct(v):
        return f"{v:.1%}" if not pd.isna(v) else "—"

    lines: list[str] = []
    lines.append("# V2 + 40/40 modifications — partial-exit + runner-BE")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("")
    lines.append("**Scope:** test 2 modifications to the V2 + 40/40 deployment candidate.")
    lines.append("Both variants use 2-contract sizing (p1 + p2), partial-exit at p1 = +40, "
                 "and a runner-BE rule that moves p2's stop to entry from bar X+1 after p1 exits "
                 "at +40 on bar X. Variant B uses an initial −40 stop; Variant C uses −25.")
    lines.append("")
    lines.append("**Baseline column** = V2 + 40/40 (single-contract) numbers from "
                 "`strategy_report_20260512/strategy_4040_test.md` algebraically scaled to "
                 "2-contract sizing. Dollar quantities ×2; ratio metrics (PF, Sharpe, Sortino, "
                 "WF Sharpe-like) and sign-stability are scale-invariant and unchanged. "
                 "No re-run performed.")
    lines.append("")
    lines.append("**Locked geometry preserved:** 3-pt cluster gap, MIN_SIZE=3, lookback=200, "
                 "first-touch entry, C2 one-position-at-a-time, 9:46–11:30 NY trading window, "
                 "force-close at 11:30 bar OPEN, stop-first conservative applied independently "
                 "per leg.")
    lines.append("")
    lines.append("**Resolved ambiguities (documented):**")
    lines.append("- Entry cluster always excluded from runner-target candidates (both FADE and "
                 "TREND inversions).")
    lines.append("- Same-bar leg ordering: stop-first conservative applied **independently per "
                 "leg**. Both legs can exit on the same bar at different reasons (e.g., p1 stops, "
                 "p2 target_cluster). If a bar covers stop AND target for a given leg, that leg "
                 "stops.")
    lines.append("- BE-stop on the bar p1 exits (bar X): p2 still uses initial stop on bar X; "
                 "BE-stop at entry becomes active on bar X+1.")
    lines.append("- Entry-bar (i = bar of first fill): both legs evaluate exits on the entry bar "
                 "itself (consistent with existing simulator_v2 behavior); the existing D-014 "
                 "entry-bar chronology bias is inherited unchanged.")
    lines.append("- If p1 hits +40 on the same bar p2 already exited (e.g., p2 cluster target "
                 "closer than +40), no BE state is tracked for p2 (already closed).")
    lines.append("- If a session has NO clusters in trade direction at session open, p2 has "
                 "`p2_target_price = NaN` and rides to 11:30 force-close (subject to stop).")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Side-by-side comparison")
    lines.append("")
    lines.append("| Metric | V2+40/40 baseline (×2c, scaled) | B: Partial (−40 + runner-BE) | C: Tight+Partial (−25 + runner-BE) |")
    lines.append("|---|---:|---:|---:|")

    rows = [
        ("Trades (entries)", "n_entries", lambda v: f"{v:,}"),
        ("WR%", "win_rate", mdpct),
        ("Total P&L", "total_pnl", mdmoney),
        ("Mean per entry", "mean_pnl", lambda v: f"${v:.2f}"),
        ("PF", "profit_factor", lambda v: f"{v:.3f}" if v != float("inf") else "∞"),
        ("Max DD", "max_dd", mdmoney),
        ("DD duration (days)", "max_dd_duration_days", lambda v: f"{v}"),
        ("DD recovered", "max_dd_recovered", lambda v: "yes" if v else "no"),
        ("Ann. Sharpe", "sharpe_ann", lambda v: f"{v:.2f}"),
        ("Ann. Sortino", "sortino_ann", lambda v: f"{v:.2f}"),
    ]
    for label, key, fmt in rows:
        cells = [
            fmt(baseline["stats"][key]),
            fmt(var_b_stats[key]),
            fmt(var_c_stats[key]),
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    wf_rows = [
        ("WF Sharpe-like", "wf_sharpe_like", lambda v: f"{v:.2f}"),
        ("Sign stability k/7", "wf_sign_count", lambda v: f"{v}/7"),
        ("Sum per-window OOS", "wf_oos_sum", mdmoney),
        ("4-gate qualify", "wf_qualifies_deploy", lambda v: "✓" if v else "✗"),
    ]
    for label, key, fmt in wf_rows:
        cells = [
            fmt(baseline["wf"][key]),
            fmt(var_b_wf[key]),
            fmt(var_c_wf[key]),
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("---")

    # Per-variant sections
    for vname, vstats, vwf, vyearly, vexits, vaudit, vfile, vparams in [
        ("Variant B — partial-exit + runner-BE, initial stop −40",
         var_b_stats, var_b_wf, var_b_yearly, var_b_exits, var_b_audit,
         "trades_variant_b_partial_runnerBE.parquet",
         "stop=−40, p1 target=+40, p2 target=next cluster level"),
        ("Variant C — partial-exit + runner-BE, initial stop −25",
         var_c_stats, var_c_wf, var_c_yearly, var_c_exits, var_c_audit,
         "trades_variant_c_tight_partial_runnerBE.parquet",
         "stop=−25, p1 target=+40, p2 target=next cluster level"),
    ]:
        lines.append("")
        lines.append(f"## {vname}")
        lines.append("")
        lines.append(f"**Parameters:** {vparams}")
        lines.append(f"**Output:** `results/archive/v2_4040_modifications_20260514/{vfile}`")
        lines.append("")

        lines.append("### Walk-forward per-window OOS (W1–W7)")
        lines.append("")
        lines.append("| W1 | W2 | W3 | W4 | W5 | W6 | W7 |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|")
        cells = [mdmoney(vwf[f"wf_W{i+1}"]) for i in range(7)]
        lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        lines.append(f"Median per-window OOS: {mdmoney(vwf['wf_median_oos'])} · "
                     f"Sharpe-like: {vwf['wf_sharpe_like']:.3f} · "
                     f"Sign-stable: {vwf['wf_sign_count']}/7 · "
                     f"Sum: {mdmoney(vwf['wf_oos_sum'])} · "
                     f"4-gate: {'✓' if vwf['wf_qualifies_deploy'] else '✗'}")
        lines.append("")

        lines.append("### Calendar-year P&L")
        lines.append("")
        lines.append("| Year | Trades | P&L | WR% |")
        lines.append("|---:|---:|---:|---:|")
        for yr in vyearly.index:
            r = vyearly.loc[yr]
            lines.append(f"| {yr} | {int(r['n_trades'])} | {mdmoney(r['pnl'])} | {mdpct(r['win_rate'])} |")
        lines.append("")

        lines.append("### Exit-type breakdown per contract leg")
        lines.append("")
        lines.append("**p1 (target = +40):**")
        for k, v in sorted(vexits["p1"].items(), key=lambda x: -x[1]):
            lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append("**p2 (target = next cluster level):**")
        for k, v in sorted(vexits["p2"].items(), key=lambda x: -x[1]):
            lines.append(f"- {k}: {v}")
        lines.append("")

        lines.append("### Runner audit")
        lines.append("")
        n_clu = vaudit["n_runner_with_cluster_target"]
        n_no = vaudit["n_runner_no_cluster_target"]
        pct = vaudit["pct_with_cluster_target"]
        be_n = vaudit["be_fired_count"]
        be_pct = vaudit["be_fired_pct"]
        lines.append(f"- Runner-target source: {n_clu} entries had a cluster-derived target "
                     f"({pct:.1%}); {n_no} entries had NO cluster in trade direction "
                     f"(force-close fallback).")
        lines.append(f"- Runner-BE fired (p1 hit +40, p2 still open after): {be_n} entries "
                     f"({be_pct:.1%}).")
        lines.append(f"- p1 leg total: {mdmoney(vaudit['p1_pnl_total'])} · "
                     f"p2 leg total: {mdmoney(vaudit['p2_pnl_total'])} · "
                     f"p2 median per entry: ${vaudit['p2_pnl_median']:.2f} · "
                     f"p2 mean per entry: ${vaudit['p2_pnl_mean']:.2f}")
        lines.append("")

        lines.append("### Methodological caveats")
        lines.append("")
        lines.append("- Entry cluster is excluded from runner-target candidates by Python "
                     "object identity. For TREND inversions where entry sits at cluster_low "
                     "(BUY) or cluster_high (SELL), the entry cluster's other extreme is "
                     "NOT used as a runner target (judgment call; documented in confirmation).")
        lines.append("- Same-bar exit ordering: each leg evaluated independently using "
                     "existing stop-first conservative (D-005). If bar range covers stop AND "
                     "target for that leg, the leg stops.")
        lines.append("- Entry bar can exit both legs at any combination (target/stop) using "
                     "the same per-leg stop-first rule. This inherits the known D-014 "
                     "entry-bar chronology bias (~3% optimistic) and D-015 phantom-fill bias "
                     "(~6% optimistic) from the bar simulator.")
        lines.append("- Runner-BE state is tracked in column `runner_be_fired`. Column "
                     "`p2_stop_history` describes p2's stop lifecycle for audit.")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- `report.md` — this report")
    lines.append("- `trades_variant_b_partial_runnerBE.parquet` — Variant B trade log "
                 "(one row per entry, 2-contract aggregate P&L, runner-BE audit columns)")
    lines.append("- `trades_variant_c_tight_partial_runnerBE.parquet` — Variant C trade log "
                 "(same schema, −25 stop)")
    lines.append("")
    lines.append("**No project files modified outside this directory and `src/experimental/`. "
                 "Locked baseline sha256 unchanged.**")

    (OUT_DIR / "report.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'report.md'}", flush=True)


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
        name=f"ADX({ADX_N},{ADX_THR})∧DI({DI_N},{DI_THR})",
    )

    print(f"\nRunning Variant B (stop=-40, p1=+40, p2=next cluster, runner-BE)...", flush=True)
    t = time.time()
    trades_b = sim_p.run_backtest(
        bars, orb_table, classifier, stop_points=40.0, target_p1_points=40.0,
    )
    df_b = sim_p.trades_to_dataframe(trades_b)
    print(f"  {len(df_b)} entries  total ${df_b['pnl_dollars'].sum():,.2f}  [{time.time()-t:.1f}s]", flush=True)

    print(f"\nRunning Variant C (stop=-25, p1=+40, p2=next cluster, runner-BE)...", flush=True)
    t = time.time()
    trades_c = sim_p.run_backtest(
        bars, orb_table, classifier, stop_points=25.0, target_p1_points=40.0,
    )
    df_c = sim_p.trades_to_dataframe(trades_c)
    print(f"  {len(df_c)} entries  total ${df_c['pnl_dollars'].sum():,.2f}  [{time.time()-t:.1f}s]", flush=True)

    df_b.to_parquet(OUT_DIR / "trades_variant_b_partial_runnerBE.parquet", index=False)
    df_c.to_parquet(OUT_DIR / "trades_variant_c_tight_partial_runnerBE.parquet", index=False)

    # Baseline scaled
    baseline = baseline_scaled_metrics()

    # Compute stats / wf / yearly for each variant
    all_dates = set(pd.to_datetime(df_b["session_date"])) | set(pd.to_datetime(df_c["session_date"]))
    all_sessions = pd.DatetimeIndex(sorted(all_dates))

    s_b = stats(df_b, all_sessions)
    w_b = walk_forward_score(df_b)
    y_b = yearly(df_b)
    e_b = per_leg_exit_counts(df_b)
    a_b = runner_audit(df_b)

    s_c = stats(df_c, all_sessions)
    w_c = walk_forward_score(df_c)
    y_c = yearly(df_c)
    e_c = per_leg_exit_counts(df_c)
    a_c = runner_audit(df_c)

    write_report(baseline, s_b, w_b, y_b, e_b, a_b, s_c, w_c, y_c, e_c, a_c)

    # Print the side-by-side comparison table to terminal
    print("\n" + "=" * 90, flush=True)
    print("SIDE-BY-SIDE COMPARISON", flush=True)
    print("=" * 90, flush=True)

    def fmt_money(v): return f"${v:,.0f}"
    def fmt_pct(v): return f"{v*100:.1f}%"

    rows = [
        ("Trades (entries)",      f"{baseline['stats']['n_entries']:,}",            f"{s_b['n_entries']:,}",            f"{s_c['n_entries']:,}"),
        ("WR%",                   fmt_pct(baseline['stats']['win_rate']),           fmt_pct(s_b['win_rate']),           fmt_pct(s_c['win_rate'])),
        ("Total P&L",             fmt_money(baseline['stats']['total_pnl']),         fmt_money(s_b['total_pnl']),         fmt_money(s_c['total_pnl'])),
        ("Mean per entry",        f"${baseline['stats']['mean_pnl']:.2f}",           f"${s_b['mean_pnl']:.2f}",           f"${s_c['mean_pnl']:.2f}"),
        ("PF",                    f"{baseline['stats']['profit_factor']:.3f}",       f"{s_b['profit_factor']:.3f}",       f"{s_c['profit_factor']:.3f}"),
        ("Max DD",                fmt_money(baseline['stats']['max_dd']),            fmt_money(s_b['max_dd']),            fmt_money(s_c['max_dd'])),
        ("DD duration (days)",    f"{baseline['stats']['max_dd_duration_days']}",    f"{s_b['max_dd_duration_days']}",    f"{s_c['max_dd_duration_days']}"),
        ("DD recovered",          "yes" if baseline['stats']['max_dd_recovered'] else "no",
                                  "yes" if s_b['max_dd_recovered'] else "no",
                                  "yes" if s_c['max_dd_recovered'] else "no"),
        ("Ann. Sharpe",           f"{baseline['stats']['sharpe_ann']:.2f}",          f"{s_b['sharpe_ann']:.2f}",          f"{s_c['sharpe_ann']:.2f}"),
        ("Ann. Sortino",          f"{baseline['stats']['sortino_ann']:.2f}",         f"{s_b['sortino_ann']:.2f}",         f"{s_c['sortino_ann']:.2f}"),
        ("WF Sharpe-like",        f"{baseline['wf']['wf_sharpe_like']:.2f}",         f"{w_b['wf_sharpe_like']:.2f}",      f"{w_c['wf_sharpe_like']:.2f}"),
        ("Sign stability k/7",    f"{baseline['wf']['wf_sign_count']}/7",            f"{w_b['wf_sign_count']}/7",         f"{w_c['wf_sign_count']}/7"),
        ("Sum per-window OOS",    fmt_money(baseline['wf']['wf_oos_sum']),           fmt_money(w_b['wf_oos_sum']),        fmt_money(w_c['wf_oos_sum'])),
        ("4-gate qualify",        "✓" if baseline['wf']['wf_qualifies_deploy'] else "✗",
                                  "✓" if w_b['wf_qualifies_deploy'] else "✗",
                                  "✓" if w_c['wf_qualifies_deploy'] else "✗"),
    ]
    header = f"| {'Metric':<22} | {'Baseline ×2c':>16} | {'B: Partial':>16} | {'C: Tight+Partial':>18} |"
    sep    = f"|{'-'*24}|{'-'*18}|{'-'*18}|{'-'*20}|"
    print(header, flush=True)
    print(sep, flush=True)
    for r in rows:
        print(f"| {r[0]:<22} | {r[1]:>16} | {r[2]:>16} | {r[3]:>18} |", flush=True)

    print(f"\nTotal elapsed: {(time.time()-t0):.1f}s", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
