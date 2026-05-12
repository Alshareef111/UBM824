"""Phase 6 — LOO + composite runs (Variants A and B).

Variant A (framework-faithful, all 5 corners at locked solo-best params):
  ADX(N=15, thr=30) + DI(N=15, thr=8) + ROC(N=60, thr=80) +
  ATR(Ns=30, thr=1.3) + VWAP(9:30_ny, thr=50)
  - 5 solos
  - 5 LOOs (each = 4-way unanimous, excluding one corner)
  - 1 full unanimous (5-way)

Variant B (deployment-relevant, 2 confirmed corners):
  ADX(15, 30) + DI(15, 8)
  - 2 solos (= A's ADX and DI solos)
  - 1 unanimous (ADX ∧ DI)
  - LOOs degenerate to solos

12 unique configs total. Each evaluated via walk-forward harness.

Three required comparisons in the report:
  1. ADX solo vs DI solo vs ADX∧DI unanimous (Variant B central question).
  2. Variant A LOOs ranked by improvement from removing each indicator.
  3. Variant B vs best Variant A LOO.

Deployment 4-gate qualification (sharpened 2026-05-12):
  median > 0, sign >= 6/7, sharpe > null p95 (1.06), total_pnl > 0.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import date

import pandas as pd

from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.roc import RocClassifier, precompute_lookup as roc_lookup
from indicators.atr import AtrRatioClassifier, precompute_ratio_lookup
from indicators.vwap import VwapClassifier, precompute_lookup as vwap_lookup
from indicators.base import UnanimousClassifier
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs
from simulator_v2 import run_backtest, trades_to_dataframe
import walk_forward as wf

TODAY = date.today().strftime("%Y%m%d")
OUT_DIR = ARCHIVE_DIR / f"composite_{TODAY}"
TRADES_SUBDIR = OUT_DIR / "trades"

# Locked solo representatives from Phases 1-5
LOCKED_ADX = ("ADX(15,30)", 15, 30)
LOCKED_DI = ("DI(15,8)", 15, 8)
LOCKED_ROC = ("ROC(60,80)", 60, 80)
LOCKED_ATR = ("ATR(30,1.3)", 30, 120, 1.3)
LOCKED_VWAP = ("VWAP(9:30_ny,50)", "9:30_ny", 50)


@dataclass
class ConfigResult:
    variant: str           # "A_solo", "A_loo", "A_full", "B_unanimous"
    label: str             # human-readable identifier ("A solo ADX", "A LOO-ROC", etc.)
    name: str
    classifier_repr: str   # short identifier
    n_trades: int
    n_fade: int
    n_trend: int
    n_skipped_clusters: int  # cluster touches consumed by SKIP (no trade)
    total_pnl: float
    is_pnl_sum: float
    oos_pnl_sum: float
    oos_median: float
    oos_sharpe_like: float
    oos_sign_count: int
    qualifies_3g: bool       # median>0 + sign>=6
    qualifies_4g: bool       # + total>0
    qualifies_deploy: bool   # + sharpe>null_p95
    per_window: dict


def run_classifier(bars, orb_table, classifier, windows) -> tuple[ConfigResult, pd.DataFrame]:
    trades = run_backtest(bars, orb_table, classifier)
    df = trades_to_dataframe(trades)
    pw = wf.per_window_pnl(df, windows, slice_="oos")
    pw_is = wf.per_window_pnl(df, windows, slice_="is")
    total = float(df["pnl_dollars"].sum()) if len(df) else 0.0
    label_split = df["cluster_label"].value_counts().to_dict() if len(df) else {}
    return ConfigResult(
        variant="",  # set by caller
        label="",    # set by caller
        name=classifier.name,
        classifier_repr=classifier.name,
        n_trades=len(df),
        n_fade=int(label_split.get("FADE", 0)),
        n_trend=int(label_split.get("TREND", 0)),
        n_skipped_clusters=0,  # filled in below; trades_to_df doesn't capture SKIPs
        total_pnl=total,
        is_pnl_sum=float(sum(pw_is.values())),
        oos_pnl_sum=float(sum(pw.values())),
        oos_median=wf.median_pnl(pw),
        oos_sharpe_like=wf.sharpe_like_score(pw),
        oos_sign_count=wf.sign_stability_count(pw),
        qualifies_3g=wf.qualifies(pw),
        qualifies_4g=wf.qualifies(pw, total_pnl=total),
        qualifies_deploy=wf.qualifies(pw, total_pnl=total, sharpe_threshold=wf.NULL_P95_SHARPE_LIKE),
        per_window=pw,
    ), df


def main():
    ensure_dirs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TRADES_SUBDIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions", flush=True)

    print("\nPre-computing indicator lookups for locked representatives...", flush=True)
    t = time.time()
    adx_lk = adx_lookup(bars, n=LOCKED_ADX[1])
    print(f"  ADX(N={LOCKED_ADX[1]}) ready [{time.time()-t:.1f}s]", flush=True)
    t = time.time()
    di_lk = di_lookup(bars, n=LOCKED_DI[1])
    print(f"  DI(N={LOCKED_DI[1]}) ready [{time.time()-t:.1f}s]", flush=True)
    t = time.time()
    roc_lk = roc_lookup(bars, n=LOCKED_ROC[1])
    print(f"  ROC(N={LOCKED_ROC[1]}) ready [{time.time()-t:.1f}s]", flush=True)
    t = time.time()
    atr_lk = precompute_ratio_lookup(bars, n_short=LOCKED_ATR[1], n_long=LOCKED_ATR[2])
    print(f"  ATR(Ns={LOCKED_ATR[1]},Nl={LOCKED_ATR[2]}) ready [{time.time()-t:.1f}s]", flush=True)
    t = time.time()
    vwap_lk = vwap_lookup(bars, anchor=LOCKED_VWAP[1])
    print(f"  VWAP({LOCKED_VWAP[1]}) ready [{time.time()-t:.1f}s]", flush=True)

    # Build solo classifiers
    clf_adx = AdxClassifier(adx_lk, n=LOCKED_ADX[1], threshold=LOCKED_ADX[2])
    clf_di = DiClassifier(di_lk, n=LOCKED_DI[1], threshold=LOCKED_DI[2])
    clf_roc = RocClassifier(roc_lk, n=LOCKED_ROC[1], threshold=LOCKED_ROC[2])
    clf_atr = AtrRatioClassifier(atr_lk, n_short=LOCKED_ATR[1], n_long=LOCKED_ATR[2], threshold=LOCKED_ATR[3])
    clf_vwap = VwapClassifier(vwap_lk, anchor=LOCKED_VWAP[1], threshold=LOCKED_VWAP[2])

    solos = {
        "ADX": clf_adx,
        "DI": clf_di,
        "ROC": clf_roc,
        "ATR": clf_atr,
        "VWAP": clf_vwap,
    }

    # LOO classifiers (Variant A): each LOO_X = unanimous over the 4 NOT-X
    loos_a = {}
    for excluded in solos:
        others = [c for k, c in solos.items() if k != excluded]
        loos_a[f"LOO-{excluded}"] = UnanimousClassifier(others, name=f"LOO-{excluded} (4-way)")

    # Full unanimous (Variant A)
    full_a = UnanimousClassifier(list(solos.values()), name="Full5 (ADX∧DI∧ROC∧ATR∧VWAP)")

    # Variant B unanimous
    unanimous_b = UnanimousClassifier([clf_adx, clf_di], name="B Unanimous (ADX∧DI)")

    windows = wf.make_windows()

    # Build the full config list
    config_specs = []
    for name, clf in solos.items():
        config_specs.append(("A_solo", f"A solo {name}", clf))
    for name, clf in loos_a.items():
        config_specs.append(("A_loo", f"A {name}", clf))
    config_specs.append(("A_full", "A Full5 unanimous", full_a))
    config_specs.append(("B_unanimous", "B ADX∧DI unanimous", unanimous_b))

    print(f"\nRunning {len(config_specs)} configs through walk-forward:", flush=True)
    results = []
    trade_dfs = {}
    for variant, label, clf in config_specs:
        t_one = time.time()
        res, df = run_classifier(bars, orb_table, clf, windows)
        res.variant = variant
        res.label = label
        elapsed = time.time() - t_one
        deploy_q = "DEPLOY-QUAL" if res.qualifies_deploy else "           "
        q4 = "4G" if res.qualifies_4g and not res.qualifies_deploy else "  "
        q3 = "3G" if res.qualifies_3g and not res.qualifies_4g else "  "
        print(
            f"  {deploy_q} {q4} {q3}  {label:36s}  trades={res.n_trades:>4}  "
            f"OOS median=${res.oos_median:>7.0f}  sharpe={res.oos_sharpe_like:>6.2f}  "
            f"sign={res.oos_sign_count}/7  total=${res.total_pnl:>7.0f}  [{elapsed:.1f}s]",
            flush=True,
        )
        results.append(res)
        trade_dfs[label] = df

    # Save trade outputs
    for label, df in trade_dfs.items():
        safe = label.replace(" ", "_").replace("∧", "AND").replace("(", "").replace(")", "")
        df.to_parquet(TRADES_SUBDIR / f"trades_{safe}.parquet", index=False)

    # Save summary parquet
    summary_rows = []
    for r in results:
        row = {
            "variant": r.variant,
            "label": r.label,
            "name": r.name,
            "n_trades": r.n_trades,
            "n_fade": r.n_fade,
            "n_trend": r.n_trend,
            "total_pnl": r.total_pnl,
            "is_pnl_sum": r.is_pnl_sum,
            "oos_pnl_sum": r.oos_pnl_sum,
            "oos_median": r.oos_median,
            "oos_sharpe_like": r.oos_sharpe_like,
            "oos_sign_count": r.oos_sign_count,
            "qualifies_3g": r.qualifies_3g,
            "qualifies_4g": r.qualifies_4g,
            "qualifies_deploy": r.qualifies_deploy,
        }
        for w in windows:
            row[f"oos_{w.name}"] = r.per_window[w.name]
        summary_rows.append(row)
    pd.DataFrame(summary_rows).to_parquet(OUT_DIR / "phase6_summary.parquet", index=False)

    write_report(results, windows)
    print(f"\nTotal elapsed: {(time.time()-t0)/60:.1f} min", flush=True)
    print(f"Artifacts: {OUT_DIR}", flush=True)


def write_report(results: list[ConfigResult], windows):
    # Index by label (set in main)
    by_label = {r.label: r for r in results}
    a_solo_adx = by_label["A solo ADX"]
    a_solo_di = by_label["A solo DI"]
    b_unan = by_label["B ADX∧DI unanimous"]
    a_full = by_label["A Full5 unanimous"]
    loo_map = {k: by_label[f"A LOO-{k}"] for k in ["ADX", "DI", "ROC", "ATR", "VWAP"]}

    lines: list[str] = []
    lines.append("# Phase 6 — LOO + Composite Runs")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Null p95 Sharpe-like threshold:** {wf.NULL_P95_SHARPE_LIKE}")
    lines.append("")
    lines.append("## Deployment qualification gates (4-gate, locked 2026-05-12)")
    lines.append("")
    lines.append("1. median(per-window OOS P&L) > 0")
    lines.append("2. ≥ 6 of 7 OOS windows positive")
    lines.append(f"3. sharpe_like > {wf.NULL_P95_SHARPE_LIKE} (null p95)")
    lines.append("4. total_pnl > 0 (sum of all trade P&L over full 7-year dataset)")
    lines.append("")
    lines.append("## All configs (12 unique)")
    lines.append("")
    lines.append("| Config | trades | F / T | median OOS | sharpe | sign | total | DEPLOY |")
    lines.append("|---|---:|---|---:|---:|:---:|---:|:---:|")
    for r in results:
        q = "✓" if r.qualifies_deploy else (" 4g" if r.qualifies_4g else (" 3g" if r.qualifies_3g else " "))
        lines.append(
            f"| {r.label} | {r.n_trades} | {r.n_fade} / {r.n_trend} | "
            f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.2f} | "
            f"{r.oos_sign_count}/7 | ${r.total_pnl:,.0f} | {q} |"
        )
    lines.append("")

    # Comparison 1
    lines.append("## Comparison 1 — ADX solo vs DI solo vs ADX∧DI unanimous")
    lines.append("")
    lines.append("Variant B's central question: does requiring agreement improve over either alone?")
    lines.append("")
    lines.append("| Config | trades | F / T | median OOS | sharpe | sign | total | DEPLOY |")
    lines.append("|---|---:|---|---:|---:|:---:|---:|:---:|")
    for r in [a_solo_adx, a_solo_di, b_unan]:
        q = "✓" if r.qualifies_deploy else "  "
        lines.append(
            f"| {r.label} | {r.n_trades} | {r.n_fade} / {r.n_trend} | "
            f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.2f} | "
            f"{r.oos_sign_count}/7 | ${r.total_pnl:,.0f} | {q} |"
        )
    lines.append("")
    # Verdict
    best_solo = max([a_solo_adx, a_solo_di], key=lambda r: r.oos_sharpe_like)
    if b_unan.oos_sharpe_like > best_solo.oos_sharpe_like:
        verdict = (f"**Verdict:** unanimous beats the better solo ({best_solo.label}, "
                   f"sharpe {best_solo.oos_sharpe_like:.2f}) — outcome 3 (unanimous wins).")
    else:
        verdict = (f"**Verdict:** the better solo ({best_solo.label}, sharpe "
                   f"{best_solo.oos_sharpe_like:.2f}) beats unanimous ({b_unan.oos_sharpe_like:.2f}) — "
                   f"outcome {1 if best_solo == a_solo_adx else 2}.")
    lines.append(verdict)
    lines.append("")
    lines.append(f"- ADX solo:        sharpe={a_solo_adx.oos_sharpe_like:.2f}, median=${a_solo_adx.oos_median:,.0f}, sign={a_solo_adx.oos_sign_count}/7, trades={a_solo_adx.n_trades}")
    lines.append(f"- DI solo:         sharpe={a_solo_di.oos_sharpe_like:.2f}, median=${a_solo_di.oos_median:,.0f}, sign={a_solo_di.oos_sign_count}/7, trades={a_solo_di.n_trades}")
    lines.append(f"- ADX∧DI unanimous: sharpe={b_unan.oos_sharpe_like:.2f}, median=${b_unan.oos_median:,.0f}, sign={b_unan.oos_sign_count}/7, trades={b_unan.n_trades}")
    lines.append("")

    # Comparison 2
    lines.append("## Comparison 2 — Variant A LOOs ranked by improvement from removing each indicator")
    lines.append("")
    lines.append("Δsharpe = LOO sharpe − Full5 sharpe. Positive = removing this indicator HELPS (it was a drag).")
    lines.append(f"Full5 baseline: sharpe={a_full.oos_sharpe_like:.2f}, median=${a_full.oos_median:,.0f}, sign={a_full.oos_sign_count}/7, trades={a_full.n_trades}")
    lines.append("")
    loo_rows = []
    for ind in ["ADX", "DI", "ROC", "ATR", "VWAP"]:
        r = loo_map[ind]
        loo_rows.append((ind, r, r.oos_sharpe_like - a_full.oos_sharpe_like,
                         r.oos_median - a_full.oos_median,
                         r.total_pnl - a_full.total_pnl))
    loo_rows.sort(key=lambda x: x[2], reverse=True)
    lines.append("| Removed | LOO trades | LOO sharpe | Δsharpe vs Full5 | LOO median | Δmedian | LOO total | Δtotal | DEPLOY |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for ind, r, dsharpe, dmed, dtot in loo_rows:
        q = "✓" if r.qualifies_deploy else "  "
        lines.append(
            f"| **{ind}** | {r.n_trades} | {r.oos_sharpe_like:.2f} | "
            f"{dsharpe:+.2f} | ${r.oos_median:,.0f} | ${dmed:+,.0f} | "
            f"${r.total_pnl:,.0f} | ${dtot:+,.0f} | {q} |"
        )
    lines.append("")
    biggest_drag = loo_rows[0]
    lines.append(f"**Biggest drag on Full5:** removing **{biggest_drag[0]}** improved sharpe by {biggest_drag[2]:+.2f}.")
    lines.append("")

    # Comparison 3
    lines.append("## Comparison 3 — Variant B (ADX∧DI) vs best Variant A LOO")
    lines.append("")
    best_a_loo = max(loo_rows, key=lambda x: x[1].oos_sharpe_like)[1]
    lines.append(f"Best A LOO by sharpe: **{best_a_loo.label}**")
    lines.append("")
    lines.append("| Config | trades | F / T | median OOS | sharpe | sign | total | DEPLOY |")
    lines.append("|---|---:|---|---:|---:|:---:|---:|:---:|")
    for r in [b_unan, best_a_loo]:
        q = "✓" if r.qualifies_deploy else "  "
        lines.append(
            f"| {r.label} | {r.n_trades} | {r.n_fade} / {r.n_trend} | "
            f"${r.oos_median:,.0f} | {r.oos_sharpe_like:.2f} | "
            f"{r.oos_sign_count}/7 | ${r.total_pnl:,.0f} | {q} |"
        )
    lines.append("")
    if b_unan.oos_sharpe_like > best_a_loo.oos_sharpe_like:
        lines.append(f"**Verdict:** Variant B (tight 2-corner stack) beats the best Variant A LOO by sharpe.")
    else:
        lines.append(f"**Verdict:** Best Variant A LOO ({best_a_loo.label}) beats Variant B unanimous by sharpe.")
    lines.append("")

    # Per-window detail
    lines.append("## Per-window OOS P&L for all 12 configs")
    lines.append("")
    lines.append("| Config | " + " | ".join(w.name for w in windows) + " | sharpe |")
    lines.append("|---|" + "|".join(["---:"] * (len(windows) + 1)) + "|")
    for r in results:
        cells = [f"${r.per_window[w.name]:,.0f}" for w in windows]
        lines.append(f"| {r.label} | " + " | ".join(cells) + f" | {r.oos_sharpe_like:.2f} |")
    lines.append("")

    lines.append("## Deployment-qualifying configs (4-gate)")
    lines.append("")
    deploy_qual = [r for r in results if r.qualifies_deploy]
    if not deploy_qual:
        lines.append("**No configs pass the deployment 4-gate qualification.**")
    else:
        deploy_qual.sort(key=lambda r: r.oos_sharpe_like, reverse=True)
        lines.append("| Rank | Config | sharpe | median | sign | total |")
        lines.append("|---:|---|---:|---:|:---:|---:|")
        for i, r in enumerate(deploy_qual, 1):
            lines.append(
                f"| {i} | {r.label} | {r.oos_sharpe_like:.2f} | "
                f"${r.oos_median:,.0f} | {r.oos_sign_count}/7 | ${r.total_pnl:,.0f} |"
            )
        lines.append("")
        lines.append(f"**Deployment winner candidate:** {deploy_qual[0].label}")
    lines.append("")

    report_path = OUT_DIR / "report.md"
    report_path.write_text("\n".join(lines))
    print(f"Wrote {report_path}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
