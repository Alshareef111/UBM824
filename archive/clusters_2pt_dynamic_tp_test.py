"""STACKED variant — 2-pt clusters + dynamic-TP exit rule.

Combined geometry change:
  - CLUSTER_GAP 3.0 → 2.0 (max adjacent gap in chain rule; Option B unchanged)
  - Stop: 30 pts fixed
  - TP: nearest cluster boundary in trade direction at entry (touched/untouched
    both eligible); 30-pt fallback when no cluster in trade direction

All other geometry locked. ADX(15,30) ∧ DI(15,8) parameters LOCKED per directive.

Reference runs at same new geometry:
  - AllFade — every cluster traded fade-direction, same exit rule
  - AllTrend — every cluster traded inverted, same exit rule

Three comparisons:
  (a) ADX∧DI new geometry  vs  v2 30/30 fixed locked baseline   — combined change
  (b) ADX∧DI new geometry  vs  AllFade new geometry             — classifier value at new geom
  (c) ADX∧DI new geometry  vs  v2 dyntp-only (3-pt + dyntp)     — cluster-span effect alone

Comparison (c) is the cluster-isolated read: holds TP rule constant.

Output: results/archive/clusters_2pt_dynamic_tp_20260512/

Interpretation note: user wrote "max pairwise distance ≤ 2 pts" but also said
"cluster_gap unchanged". These describe different rules (diameter vs chain).
Following locked spec D-002 (Option B chain rule) and R-002 precedent
(gap=2.0 with chain rule), this test uses CLUSTER_GAP=2.0 with chain rule.
"""
from __future__ import annotations

import sys
import time
from collections import deque
from datetime import date

import numpy as np
import pandas as pd

# Critical: import simulator_v2_dyntp THEN override CLUSTER_GAP before run_backtest
import simulator_v2_dyntp as sim
ORIGINAL_GAP = sim.CLUSTER_GAP
NEW_GAP = 2.0

from clusters import find_clusters
from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.base import AllFade, AllTrend, UnanimousClassifier
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET
import walk_forward as wf

ADX_N, ADX_THR = 15, 30
DI_N, DI_THR = 15, 8

OUT_DIR = ARCHIVE_DIR / "clusters_2pt_dynamic_tp_20260512"
V2_3030_LOCKED = ARCHIVE_DIR / "trades_regime_v2_20260512.parquet"   # comp (a)
V2_DYNTP_3PT = ARCHIVE_DIR / "dynamic_tp_20260512" / "trades_v2_dyntp.parquet"  # comp (c)

POINT_VALUE_USD = 2.0
ANNUALIZATION = 252


def headline(df, all_sessions):
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
    max_dd = float(dd.min()) if len(dd) else 0.0
    trough = dd.idxmin() if len(dd) else None
    if trough is not None:
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
    else:
        rec_d = None
        dur = 0
    sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(ANNUALIZATION)) if daily.std(ddof=1) > 0 else float("nan")
    downside = float(np.sqrt(((daily.clip(upper=0.0)) ** 2).mean()))
    sortino = float(daily.mean() / downside * np.sqrt(ANNUALIZATION)) if downside > 0 else float("nan")
    return {
        "n_trades": int(len(df)),
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


def wf_scores(df):
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


def count_clusters_per_session(bars, orb_table, gap, min_size=3, lookback=200):
    """Replicate the cluster-detection loop without running the simulator."""
    bars_by_session = {sd: g for sd, g in bars.groupby("session_date", sort=True)}
    orb_table = orb_table.sort_values("session_date").reset_index(drop=True)
    level_pool = deque(maxlen=lookback)
    rows = []
    for _, orb_row in orb_table.iterrows():
        sd = orb_row["session_date"]
        if sd not in bars_by_session:
            continue
        levels = []
        for hh, hl in level_pool:
            levels.append(hh)
            levels.append(hl)
        levels.append(orb_row["orb_high"])
        levels.append(orb_row["orb_low"])
        cs = find_clusters(levels, max_gap=gap, min_size=min_size)
        rows.append({"session_date": sd, "n_clusters": len(cs), "n_levels": len(levels)})
        level_pool.append((float(orb_row["orb_high"]), float(orb_row["orb_low"])))
    return pd.DataFrame(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print(f"Override: simulator_v2_dyntp.CLUSTER_GAP = {NEW_GAP} (was {ORIGINAL_GAP})", flush=True)
    sim.CLUSTER_GAP = NEW_GAP
    assert sim.CLUSTER_GAP == 2.0

    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)

    # 1. Cluster-count diagnostic (3pt vs 2pt)
    print("\nCounting clusters per session under 2-pt vs 3-pt rules...", flush=True)
    counts_2pt = count_clusters_per_session(bars, orb_table, gap=2.0)
    counts_3pt = count_clusters_per_session(bars, orb_table, gap=3.0)
    counts = counts_2pt.merge(
        counts_3pt.rename(columns={"n_clusters": "n_clusters_3pt", "n_levels": "n_levels_3pt"}),
        on="session_date",
        how="outer",
    ).rename(columns={"n_clusters": "n_clusters_2pt", "n_levels": "n_levels_2pt"})
    counts.to_parquet(OUT_DIR / "cluster_counts.parquet", index=False)
    print(f"  Mean clusters/session:  2pt={counts['n_clusters_2pt'].mean():.2f}  3pt={counts['n_clusters_3pt'].mean():.2f}")
    print(f"  Median:                 2pt={counts['n_clusters_2pt'].median():.0f}  3pt={counts['n_clusters_3pt'].median():.0f}")
    print(f"  Sessions with 0 clusters: 2pt={(counts['n_clusters_2pt']==0).sum():,}  3pt={(counts['n_clusters_3pt']==0).sum():,}")

    print("\nPre-computing ADX(15) and DI(15) lookups...", flush=True)
    adx_lk = adx_lookup(bars, n=ADX_N)
    di_lk = di_lookup(bars, n=DI_N)
    adx_clf = AdxClassifier(adx_lk, n=ADX_N, threshold=ADX_THR)
    di_clf = DiClassifier(di_lk, n=DI_N, threshold=DI_THR)
    unan = UnanimousClassifier([adx_clf, di_clf], name="ADX∧DI 2pt+dyntp")

    # Run all three classifiers under new geometry
    runs = {}
    for label, clf in [
        ("ADX∧DI 2pt+dyntp", unan),
        ("AllFade 2pt+dyntp", AllFade()),
        ("AllTrend 2pt+dyntp", AllTrend()),
    ]:
        print(f"\nRunning {label} under CLUSTER_GAP={sim.CLUSTER_GAP}...", flush=True)
        t = time.time()
        trades = sim.run_backtest(bars, orb_table, clf)
        df = sim.trades_to_dataframe(trades)
        print(f"  {len(df)} trades  total ${df['pnl_dollars'].sum():,.2f}  [{time.time()-t:.1f}s]", flush=True)
        runs[label] = df
        safe = label.replace("∧", "AND").replace(" ", "_").replace("+", "_")
        df.to_parquet(OUT_DIR / f"trades_{safe}.parquet", index=False)

    # Load reference results
    v2_locked = pd.read_parquet(V2_3030_LOCKED)             # comp (a)
    v2_dyntp_3pt = pd.read_parquet(V2_DYNTP_3PT)             # comp (c)

    # Build all-sessions index spanning all dfs
    all_dates = set()
    for d in list(runs.values()) + [v2_locked, v2_dyntp_3pt]:
        all_dates |= set(pd.to_datetime(d["session_date"]))
    all_sessions = pd.DatetimeIndex(sorted(all_dates))

    # Compute stats for all configs in comparison
    configs = {
        "ADX∧DI 2pt+dyntp": runs["ADX∧DI 2pt+dyntp"],
        "AllFade 2pt+dyntp": runs["AllFade 2pt+dyntp"],
        "AllTrend 2pt+dyntp": runs["AllTrend 2pt+dyntp"],
        "v2 3pt+30/30 fixed (locked)": v2_locked,
        "v2 3pt+dyntp": v2_dyntp_3pt,
    }
    heads = {k: headline(v, all_sessions) for k, v in configs.items()}
    wfs = {k: wf_scores(v) for k, v in configs.items()}

    # TP distance distribution for the new ADX∧DI run
    adxdi_new = runs["ADX∧DI 2pt+dyntp"]
    tp_summary = {
        "min": float(adxdi_new["tp_distance_pts"].min()),
        "p5": float(adxdi_new["tp_distance_pts"].quantile(0.05)),
        "p25": float(adxdi_new["tp_distance_pts"].quantile(0.25)),
        "median": float(adxdi_new["tp_distance_pts"].median()),
        "p75": float(adxdi_new["tp_distance_pts"].quantile(0.75)),
        "p95": float(adxdi_new["tp_distance_pts"].quantile(0.95)),
        "max": float(adxdi_new["tp_distance_pts"].max()),
        "mean": float(adxdi_new["tp_distance_pts"].mean()),
    }
    bins = [0, 5, 10, 15, 20, 25, 30, 35, 40, 50, 75, 100, 150, 200, float("inf")]
    bin_labels = [
        "0-5", "5-10", "10-15", "15-20", "20-25", "25-30", "30-35", "35-40",
        "40-50", "50-75", "75-100", "100-150", "150-200", "200+",
    ]
    hist_counts, _ = np.histogram(adxdi_new["tp_distance_pts"], bins=bins)
    hist = pd.DataFrame({"bucket_pts": bin_labels, "n_trades": hist_counts})
    hist["pct"] = hist["n_trades"] / hist["n_trades"].sum()
    hist.to_parquet(OUT_DIR / "tp_distance_histogram.parquet", index=False)

    # Exit breakdown for ADX∧DI new
    exit_rows = []
    for elabel, mask in [
        ("cluster-target", (adxdi_new["exit_reason"] == "target") & (adxdi_new["target_source"] == "cluster")),
        ("fallback-30pt target", (adxdi_new["exit_reason"] == "target") & (adxdi_new["target_source"] == "fallback")),
        ("stop", adxdi_new["exit_reason"] == "stop"),
        ("force-close", adxdi_new["exit_reason"] == "force_close"),
    ]:
        sub = adxdi_new[mask]
        wins = (sub["pnl_dollars"] > 0).sum() if len(sub) else 0
        exit_rows.append({
            "exit_type": elabel,
            "n_trades": int(len(sub)),
            "pct_of_total": float(len(sub) / len(adxdi_new)) if len(adxdi_new) else 0.0,
            "mean_pnl": float(sub["pnl_dollars"].mean()) if len(sub) else 0.0,
            "total_pnl": float(sub["pnl_dollars"].sum()),
            "win_rate": float(wins / len(sub)) if len(sub) else float("nan"),
            "mean_tp_distance_pts": float(sub["tp_distance_pts"].mean()) if len(sub) else float("nan"),
        })
    exit_df = pd.DataFrame(exit_rows)
    exit_df.to_parquet(OUT_DIR / "exit_breakdown.parquet", index=False)

    # Save combined headlines parquet
    combined = []
    for k in configs:
        row = {"config": k, **heads[k], **wfs[k]}
        combined.append(row)
    pd.DataFrame(combined).to_parquet(OUT_DIR / "headlines.parquet", index=False)

    write_report(counts, heads, wfs, exit_df, hist, tp_summary, configs)

    print(f"\nTotal elapsed: {(time.time()-t0):.1f}s", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


def write_report(counts, heads, wfs, exit_df, hist, tp_summary, configs):
    fmt_money = lambda v: f"${v:,.0f}"
    fmt_money2 = lambda v: f"${v:,.2f}"
    fmt_pct = lambda v: f"{v:.1%}" if not pd.isna(v) else "—"
    windows = wf.make_windows()

    lines: list[str] = []
    lines.append("# 2-pt clusters + dynamic-TP — STACKED variant test")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append("")
    lines.append("## Strategy modification (stacked)")
    lines.append("")
    lines.append("- **Cluster geometry:** CLUSTER_GAP = 2.0 (was 3.0). Chain rule (Option B) unchanged; MIN_CLUSTER_SIZE = 3.")
    lines.append("- **Stop:** 30 pts fixed")
    lines.append("- **TP:** nearest cluster boundary in trade direction at entry (touched or untouched); 30-pt fallback if no cluster in trade direction")
    lines.append("- All other geometry locked: first-touch entry, C2, 9:46-11:30 NY trading window, force-close at 11:30 open")
    lines.append("- ADX(15,30) ∧ DI(15,8) parameters LOCKED per directive — no re-sweep")
    lines.append("")
    lines.append("**Interpretation note:** user wrote 'max pairwise distance ≤ 2 pts' but also 'cluster_gap unchanged'.")
    lines.append("Those describe different cluster rules. Per locked spec D-002 (Option B chain rule) and R-002 precedent")
    lines.append("(tested gap=2.0 with chain rule), this run uses CLUSTER_GAP=2.0 with chain-rule semantics. If the")
    lines.append("intended rule was diameter (max pairwise distance) at 2 pts, the test needs to be rerun.")
    lines.append("")

    # 1. Cluster count diagnostic
    lines.append("## 1. Cluster count per session — 2-pt vs 3-pt")
    lines.append("")
    lines.append("| Statistic | 2-pt clusters | 3-pt clusters | Δ |")
    lines.append("|---|---:|---:|---:|")
    for stat, fn in [
        ("Mean / session", lambda c: c.mean()),
        ("Median / session", lambda c: c.median()),
        ("p75 / session", lambda c: c.quantile(0.75)),
        ("Max / session", lambda c: c.max()),
        ("% sessions with 0 clusters", lambda c: (c == 0).mean() * 100),
        ("Total clusters across all sessions", lambda c: c.sum()),
    ]:
        v2 = fn(counts["n_clusters_2pt"])
        v3 = fn(counts["n_clusters_3pt"])
        if "%" in stat:
            lines.append(f"| {stat} | {v2:.1f}% | {v3:.1f}% | {v2-v3:+.1f}pp |")
        else:
            lines.append(f"| {stat} | {v2:.1f} | {v3:.1f} | {v2-v3:+.1f} |")
    lines.append("")

    # 2. Trade counts (same-geometry triad)
    lines.append("## 2. Trade counts — new-geometry reference triad")
    lines.append("")
    lines.append("| Strategy | trades | total P&L | win rate |")
    lines.append("|---|---:|---:|---:|")
    for k in ["ADX∧DI 2pt+dyntp", "AllFade 2pt+dyntp", "AllTrend 2pt+dyntp"]:
        h = heads[k]
        lines.append(f"| {k} | {h['n_trades']:,} | {fmt_money(h['total_pnl'])} | {fmt_pct(h['win_rate'])} |")
    lines.append("")

    # 3. Per-window OOS — same-geometry triad
    lines.append("## 3. Per-window OOS P&L — same-geometry triad")
    lines.append("")
    lines.append("| Strategy | " + " | ".join(w.name for w in windows) + " | Sharpe-like |")
    lines.append("|---|" + "|".join(["---:"] * 7) + "|---:|")
    for k in ["ADX∧DI 2pt+dyntp", "AllFade 2pt+dyntp", "AllTrend 2pt+dyntp"]:
        cells = [fmt_money(wfs[k][f"oos_{w.name}"]) for w in windows]
        lines.append(f"| {k} | " + " | ".join(cells) + f" | {wfs[k]['wf_sharpe_like']:.2f} |")
    lines.append("")

    # 4. Exit breakdown for ADX∧DI
    lines.append("## 4. Exit-type breakdown — ADX∧DI 2pt+dyntp")
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

    # 5+6. ADX∧DI headline + sharpe
    lines.append("## 5+6. ADX∧DI 2pt+dyntp — headline + walk-forward")
    lines.append("")
    h = heads["ADX∧DI 2pt+dyntp"]
    w = wfs["ADX∧DI 2pt+dyntp"]
    pf = f"{h['profit_factor']:.3f}" if h['profit_factor'] != float('inf') else "∞"
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Trades | {h['n_trades']:,} |")
    lines.append(f"| Win rate | {fmt_pct(h['win_rate'])} |")
    lines.append(f"| Total P&L | {fmt_money(h['total_pnl'])} |")
    lines.append(f"| Mean / trade | {fmt_money2(h['mean_pnl'])} |")
    lines.append(f"| Avg winner | {fmt_money2(h['avg_winner'])} |")
    lines.append(f"| Avg loser | {fmt_money2(h['avg_loser'])} |")
    lines.append(f"| Profit factor | {pf} |")
    lines.append(f"| Max drawdown | {fmt_money(h['max_dd'])} (duration {h['max_dd_duration_days']} days, recovered: {h['max_dd_recovered']}) |")
    lines.append(f"| Annualized Sharpe | {h['sharpe_ann']:.2f} |")
    lines.append(f"| Annualized Sortino | {h['sortino_ann']:.2f} |")
    lines.append(f"| Walk-forward Sharpe-like | **{w['wf_sharpe_like']:.2f}** |")
    lines.append(f"| Walk-forward median OOS | {fmt_money(w['wf_median_oos'])} |")
    lines.append(f"| Walk-forward sign | {w['wf_sign_count']}/7 |")
    lines.append(f"| **4-gate deploy qualify** | {'**✓ YES**' if w['wf_qualifies_deploy'] else '**NO**'} |")
    lines.append("")

    # 7. Comparisons
    lines.append("## 7. Comparisons")
    lines.append("")

    def comp_table(left_name, right_name):
        h_l = heads[left_name]
        h_r = heads[right_name]
        w_l = wfs[left_name]
        w_r = wfs[right_name]
        rows = [
            ("Trades", f"{h_l['n_trades']:,}", f"{h_r['n_trades']:,}", f"{h_l['n_trades']-h_r['n_trades']:+,}"),
            ("Win rate", fmt_pct(h_l["win_rate"]), fmt_pct(h_r["win_rate"]), f"{(h_l['win_rate']-h_r['win_rate'])*100:+.1f}pp"),
            ("Total P&L", fmt_money(h_l["total_pnl"]), fmt_money(h_r["total_pnl"]), fmt_money(h_l["total_pnl"]-h_r["total_pnl"])),
            ("Profit factor", f"{h_l['profit_factor']:.3f}" if h_l["profit_factor"] != float("inf") else "∞",
             f"{h_r['profit_factor']:.3f}" if h_r["profit_factor"] != float("inf") else "∞", "—"),
            ("Max drawdown", fmt_money(h_l["max_dd"]), fmt_money(h_r["max_dd"]), fmt_money(h_l["max_dd"]-h_r["max_dd"])),
            ("Ann Sharpe", f"{h_l['sharpe_ann']:.2f}", f"{h_r['sharpe_ann']:.2f}", f"{h_l['sharpe_ann']-h_r['sharpe_ann']:+.2f}"),
            ("WF Sharpe-like", f"{w_l['wf_sharpe_like']:.2f}", f"{w_r['wf_sharpe_like']:.2f}", f"{w_l['wf_sharpe_like']-w_r['wf_sharpe_like']:+.2f}"),
            ("WF median OOS", fmt_money(w_l["wf_median_oos"]), fmt_money(w_r["wf_median_oos"]), fmt_money(w_l["wf_median_oos"]-w_r["wf_median_oos"])),
            ("WF sign", f"{w_l['wf_sign_count']}/7", f"{w_r['wf_sign_count']}/7", "—"),
            ("4-gate deploy", "✓" if w_l["wf_qualifies_deploy"] else "NO",
             "✓" if w_r["wf_qualifies_deploy"] else "NO", "—"),
        ]
        out = []
        out.append(f"| Metric | {left_name} | {right_name} | Δ |")
        out.append("|---|---:|---:|---:|")
        for m, a, b, d in rows:
            out.append(f"| {m} | {a} | {b} | {d} |")
        return out

    lines.append("### (a) ADX∧DI new geometry vs locked baseline (3-pt + 30/30 fixed) — combined effect")
    lines.append("")
    lines.extend(comp_table("ADX∧DI 2pt+dyntp", "v2 3pt+30/30 fixed (locked)"))
    lines.append("")

    lines.append("### (b) ADX∧DI new geometry vs AllFade new geometry — classifier value at new geom")
    lines.append("")
    lines.extend(comp_table("ADX∧DI 2pt+dyntp", "AllFade 2pt+dyntp"))
    lines.append("")

    lines.append("### (c) ADX∧DI new geometry vs ADX∧DI 3-pt + dynamic-TP — cluster-isolated effect")
    lines.append("")
    lines.append("Cleanest cluster-only read: holds TP rule constant; changes only cluster_gap 3→2.")
    lines.append("")
    lines.extend(comp_table("ADX∧DI 2pt+dyntp", "v2 3pt+dyntp"))
    lines.append("")

    # 8. TP distance distribution
    lines.append("## 8. TP-distance distribution under 2-pt clusters (ADX∧DI)")
    lines.append("")
    s = tp_summary
    lines.append("| min | p5 | p25 | median | mean | p75 | p95 | max |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    lines.append(f"| {s['min']:.1f} | {s['p5']:.1f} | {s['p25']:.1f} | {s['median']:.1f} | {s['mean']:.1f} | {s['p75']:.1f} | {s['p95']:.1f} | {s['max']:.1f} |")
    lines.append("")
    lines.append("Histogram:")
    lines.append("")
    lines.append("| bucket (pts) | trades | % |")
    lines.append("|---|---:|---:|")
    for r in hist.itertuples():
        if r.n_trades > 0:
            lines.append(f"| {r.bucket_pts} | {int(r.n_trades)} | {r.pct:.1%} |")
    lines.append("")

    lines.append("## Files")
    lines.append("")
    lines.append("- `clusters_2pt_dynamic_tp_test.md` — this report")
    lines.append("- `trades_ADXANDDI_2pt_dyntp.parquet` — ADX∧DI new geometry trades")
    lines.append("- `trades_AllFade_2pt_dyntp.parquet` — AllFade same-geometry reference")
    lines.append("- `trades_AllTrend_2pt_dyntp.parquet` — AllTrend same-geometry reference")
    lines.append("- `cluster_counts.parquet` — per-session cluster counts 2pt vs 3pt")
    lines.append("- `exit_breakdown.parquet` — exit-type stats for ADX∧DI new geometry")
    lines.append("- `tp_distance_histogram.parquet` — TP distance distribution")
    lines.append("- `headlines.parquet` — all 5 configs side-by-side")

    (OUT_DIR / "clusters_2pt_dynamic_tp_test.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'clusters_2pt_dynamic_tp_test.md'}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
