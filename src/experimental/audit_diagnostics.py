"""Read-only diagnostics for the framework-integrity audit (2026-05-15).

Outputs to results/archive/audit_framework_integrity_20260515/.
Touches no simulator code, no locked baselines, no protected files.

Computes:
  P1: bar-vs-tick gap on the existing 32-trade verification set
  P3: overlay-vs-engine comparison for the cluster-size filter test
  P4: same-bar stop+target frequency on baseline V2+40/40 trades
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from paths import (
    ARCHIVE_DIR,
    BARS_PARQUET,
    VERIFICATION_PARQUET,
)

AUDIT_DIR = ARCHIVE_DIR / "audit_framework_integrity_20260515"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

V2_4040_PARQUET = ARCHIVE_DIR / "strategy_report_20260512" / "trades_v2_4040.parquet"
F1_PARQUET = ARCHIVE_DIR / "v2_4040_cluster_size_filter_20260514" / "trades_v2_4040_size4.parquet"
F2_PARQUET = ARCHIVE_DIR / "v2_4040_cluster_size_filter_20260514" / "trades_v2_4040_size5.parquet"


def p1_tick_vs_bar():
    print("\n" + "=" * 78)
    print("PRIORITY 1 — Bar-vs-tick gap (existing 32-trade verification set)")
    print("=" * 78)

    v = pd.read_parquet(VERIFICATION_PARQUET)
    print(f"Verification set: {len(v)} trades, {v['session_date'].nunique()} sessions")
    print(f"Window: {v['session_date'].min()} -> {v['session_date'].max()}")

    # The verification parquet already has both sim_outcome (bar) and tick_outcome.
    # pnl_dollars = bar-sim P&L (locked 30/30)
    # real_pnl    = tick P&L (in points; multiply by 2 for $)
    bar_pnl_usd = float(v["pnl_dollars"].sum())
    tick_pnl_usd = float(v["real_pnl"].sum()) * 2.0
    bar_wr = float((v["pnl_dollars"] > 0).mean())
    tick_wr = float((v["real_pnl"] > 0).mean())
    matched = int(v["match"].sum())

    # Per-trade delta
    v["bar_usd"] = v["pnl_dollars"]
    v["tick_usd"] = v["real_pnl"] * 2.0
    v["delta_usd"] = v["bar_usd"] - v["tick_usd"]
    deltas = v["delta_usd"]

    print(f"\nBar total P&L:   ${bar_pnl_usd:,.2f}")
    print(f"Tick total P&L:  ${tick_pnl_usd:,.2f}")
    print(f"Bar - Tick:      ${bar_pnl_usd - tick_pnl_usd:,.2f}")
    if tick_pnl_usd != 0:
        rel = (bar_pnl_usd - tick_pnl_usd) / abs(tick_pnl_usd) * 100
        print(f"Relative over/under-statement: {rel:+.1f}%")
    elif bar_pnl_usd != 0:
        print(
            f"Tick P&L is $0 — bar simulator credits ${bar_pnl_usd:,.0f} that tick replay does not (relative = ∞)"
        )
    print(f"\nBar win rate:    {bar_wr:.1%}")
    print(f"Tick win rate:   {tick_wr:.1%}")
    print(f"Outcome match:   {matched}/{len(v)} ({matched / len(v):.1%})")

    print("\nPer-trade delta (bar - tick) distribution:")
    print(f"  median: ${deltas.median():,.2f}")
    print(f"  p10:    ${deltas.quantile(0.10):,.2f}")
    print(f"  p90:    ${deltas.quantile(0.90):,.2f}")
    print(f"  min/max ${deltas.min():,.2f} / ${deltas.max():,.2f}")

    mismatches = v[~v["match"]][
        [
            "session_date",
            "side",
            "exit_reason",
            "sim_outcome",
            "tick_outcome",
            "bar_usd",
            "tick_usd",
            "delta_usd",
        ]
    ]
    print(f"\nMismatched trades ({len(mismatches)}):")
    print(mismatches.to_string(index=False))

    out_path = AUDIT_DIR / "p1_tick_vs_bar_per_trade.parquet"
    v[
        [
            "session_date",
            "side",
            "entry_time",
            "exit_reason",
            "sim_outcome",
            "tick_outcome",
            "match",
            "bar_usd",
            "tick_usd",
            "delta_usd",
        ]
    ].to_parquet(out_path, index=False)
    print(f"\nWrote {out_path}")

    return {
        "n_trades": len(v),
        "bar_pnl_usd": bar_pnl_usd,
        "tick_pnl_usd": tick_pnl_usd,
        "delta_usd": bar_pnl_usd - tick_pnl_usd,
        "match_rate": matched / len(v),
        "n_mismatches": len(mismatches),
        "relative_overstatement_pct": ((bar_pnl_usd - tick_pnl_usd) / abs(tick_pnl_usd) * 100)
        if tick_pnl_usd != 0
        else float("inf"),
    }


def p3_overlay_vs_engine():
    print("\n" + "=" * 78)
    print("PRIORITY 3 — Overlay mode vs engine mode (cluster-size filter test)")
    print("=" * 78)

    baseline = pd.read_parquet(V2_4040_PARQUET)
    f1_engine = pd.read_parquet(F1_PARQUET)
    f2_engine = pd.read_parquet(F2_PARQUET)

    # Overlay: post-hoc filter baseline by cluster_size threshold
    f1_overlay = baseline[baseline["cluster_size"] >= 4]
    f2_overlay = baseline[baseline["cluster_size"] >= 5]

    def headline(df, label):
        if len(df) == 0:
            return {"label": label, "n": 0, "wr": float("nan"), "pnl": 0.0}
        return {
            "label": label,
            "n": len(df),
            "wr": float((df["pnl_dollars"] > 0).mean()),
            "pnl": float(df["pnl_dollars"].sum()),
        }

    rows = [
        headline(baseline, "Baseline V2+40/40 (size>=3, full)"),
        headline(f1_overlay, "F1 overlay (filter baseline by size>=4)"),
        headline(f1_engine, "F1 engine (sim with MIN_CLUSTER_SIZE=4)"),
        headline(f2_overlay, "F2 overlay (filter baseline by size>=5)"),
        headline(f2_engine, "F2 engine (sim with MIN_CLUSTER_SIZE=5)"),
    ]

    print(f"\n{'Variant':<48} {'Trades':>8} {'WR':>8} {'P&L':>12}")
    print("-" * 78)
    for r in rows:
        wr_s = f"{r['wr']:.1%}" if not np.isnan(r["wr"]) else "—"
        print(f"{r['label']:<48} {r['n']:>8} {wr_s:>8} ${r['pnl']:>10,.0f}")

    # Compute set-difference between overlay and engine
    def keyset(df):
        return set(
            zip(
                pd.to_datetime(df["session_date"]).astype("int64"),
                df["cluster_low"].astype(float),
                df["cluster_high"].astype(float),
            )
        )

    f1_o_k = keyset(f1_overlay)
    f1_e_k = keyset(f1_engine)
    f2_o_k = keyset(f2_overlay)
    f2_e_k = keyset(f2_engine)

    print("\nF1 set comparison (clusters keyed by session_date + cluster_low + cluster_high):")
    print(f"  overlay only (in baseline filtered, NOT triggered by engine): {len(f1_o_k - f1_e_k)}")
    print(f"  engine only  (triggered by engine, NOT in baseline filtered): {len(f1_e_k - f1_o_k)}")
    print(f"  shared:                                                       {len(f1_o_k & f1_e_k)}")

    print("\nF2 set comparison:")
    print(f"  overlay only: {len(f2_o_k - f2_e_k)}")
    print(f"  engine only:  {len(f2_e_k - f2_o_k)}")
    print(f"  shared:       {len(f2_o_k & f2_e_k)}")

    summary = pd.DataFrame(rows)
    summary.to_parquet(AUDIT_DIR / "p3_overlay_vs_engine.parquet", index=False)
    print(f"\nWrote {AUDIT_DIR / 'p3_overlay_vs_engine.parquet'}")

    return {
        "rows": rows,
        "f1_overlay_only": len(f1_o_k - f1_e_k),
        "f1_engine_only": len(f1_e_k - f1_o_k),
        "f1_shared": len(f1_o_k & f1_e_k),
        "f2_overlay_only": len(f2_o_k - f2_e_k),
        "f2_engine_only": len(f2_e_k - f2_o_k),
        "f2_shared": len(f2_o_k & f2_e_k),
    }


def p4_same_bar_stop_target():
    """For each trade in V2+40/40 baseline, look at the entry bar and the exit bar.

    Count bars where stop AND target were both inside the bar's range
    (ambiguous chronology). Entry-bar same-bar exits are D-014 territory;
    exit-bar same-bar reachable is D-005 territory.
    """
    print("\n" + "=" * 78)
    print("PRIORITY 4 — Same-bar stop+target reachable (V2+40/40 baseline)")
    print("=" * 78)

    trades = pd.read_parquet(V2_4040_PARQUET)
    bars = pd.read_parquet(BARS_PARQUET)

    # bars has ts_utc, high, low, etc. trades has entry_time, exit_time in UTC.
    bars["ts_utc"] = pd.to_datetime(bars["ts_utc"], utc=True)
    bars_idx = bars.set_index("ts_utc")[["high", "low"]]

    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)

    STOP = 40.0
    TARGET = 40.0

    entry_both_reach = 0
    exit_bar_both_reach = 0
    same_bar_entry_exit = 0
    samples_entry = []
    samples_exit = []

    for t in trades.itertuples():
        # Entry-bar check
        try:
            entry_bar = bars_idx.loc[t.entry_time]
        except KeyError:
            continue
        if t.side == "buy":
            stop_p = t.entry_price - STOP
            target_p = t.entry_price + TARGET
            stop_reach = entry_bar["low"] <= stop_p
            target_reach = entry_bar["high"] >= target_p
        else:
            stop_p = t.entry_price + STOP
            target_p = t.entry_price - TARGET
            stop_reach = entry_bar["high"] >= stop_p
            target_reach = entry_bar["low"] <= target_p

        if stop_reach and target_reach:
            entry_both_reach += 1
            if len(samples_entry) < 5:
                samples_entry.append(
                    {
                        "session_date": str(t.session_date),
                        "side": t.side,
                        "entry_time": str(t.entry_time),
                        "entry_price": float(t.entry_price),
                        "bar_high": float(entry_bar["high"]),
                        "bar_low": float(entry_bar["low"]),
                        "stop": float(stop_p),
                        "target": float(target_p),
                        "exit_reason": t.exit_reason,
                    }
                )

        # Exit-bar check (only if exit_time != entry_time)
        if t.exit_time == t.entry_time:
            same_bar_entry_exit += 1
            continue
        if t.exit_reason == "force_close":
            continue
        try:
            exit_bar = bars_idx.loc[t.exit_time]
        except KeyError:
            continue
        if t.side == "buy":
            stop_reach_x = exit_bar["low"] <= stop_p
            target_reach_x = exit_bar["high"] >= target_p
        else:
            stop_reach_x = exit_bar["high"] >= stop_p
            target_reach_x = exit_bar["low"] <= target_p
        if stop_reach_x and target_reach_x:
            exit_bar_both_reach += 1
            if len(samples_exit) < 5:
                samples_exit.append(
                    {
                        "session_date": str(t.session_date),
                        "side": t.side,
                        "exit_time": str(t.exit_time),
                        "entry_price": float(t.entry_price),
                        "exit_bar_high": float(exit_bar["high"]),
                        "exit_bar_low": float(exit_bar["low"]),
                        "stop": float(stop_p),
                        "target": float(target_p),
                        "exit_reason": t.exit_reason,
                    }
                )

    n = len(trades)
    print(f"\nTotal trades: {n}")
    print(
        f"Entry-bar same-bar entry+exit (exit_time == entry_time): {same_bar_entry_exit} ({same_bar_entry_exit / n:.1%})"
    )
    print(
        f"Entry-bar: stop AND target both reachable: {entry_both_reach} ({entry_both_reach / n:.1%})  [D-014 territory]"
    )
    print(
        f"Exit-bar (non-entry, non-force):  stop AND target both reachable: {exit_bar_both_reach} ({exit_bar_both_reach / n:.1%})  [D-005 territory]"
    )

    print("\nSample entry-bar same-bar-both-reach (max 5):")
    for s in samples_entry:
        print(f"  {s}")
    print("\nSample exit-bar both-reach (max 5):")
    for s in samples_exit:
        print(f"  {s}")

    out = pd.DataFrame(
        {
            "metric": [
                "n_trades",
                "same_bar_entry_exit",
                "entry_bar_both_reachable",
                "exit_bar_both_reachable",
            ],
            "value": [n, same_bar_entry_exit, entry_both_reach, exit_bar_both_reach],
            "fraction": [
                1.0,
                same_bar_entry_exit / n,
                entry_both_reach / n,
                exit_bar_both_reach / n,
            ],
        }
    )
    out.to_parquet(AUDIT_DIR / "p4_same_bar_stop_target.parquet", index=False)
    print(f"\nWrote {AUDIT_DIR / 'p4_same_bar_stop_target.parquet'}")

    return {
        "n": n,
        "same_bar_entry_exit": same_bar_entry_exit,
        "entry_both_reach": entry_both_reach,
        "exit_both_reach": exit_bar_both_reach,
    }


def p4b_d014_chronology_risk():
    """Tighter D-014 check: among same-bar entry+exit trades, how many have
    bar.open on the FAR side of the limit relative to the recorded exit reason?

    If a BUY filled at L (cluster.high, below prevailing price) and the same bar
    credited target=L+40, the bar.high must be >= L+40. If bar.open is also
    >= L+40 (i.e., open was ABOVE target), then bar.high may equal bar.open
    (start of bar) — well BEFORE the limit fill at bar.low time. The credited
    target win is then anachronistic. This is D-014's signature.
    """
    print("\n" + "=" * 78)
    print("PRIORITY 4b — D-014 entry-bar chronology risk (V2+40/40 baseline)")
    print("=" * 78)

    trades = pd.read_parquet(V2_4040_PARQUET)
    bars = pd.read_parquet(BARS_PARQUET)
    bars["ts_utc"] = pd.to_datetime(bars["ts_utc"], utc=True)
    bars_idx = bars.set_index("ts_utc")[["open", "high", "low"]]

    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)

    same_bar_mask = trades["entry_time"] == trades["exit_time"]
    sb = trades[same_bar_mask].copy()

    risky_target = 0
    risky_stop = 0
    risky_breakdown_by_reason = {"target": 0, "stop": 0, "force_close": 0}

    for t in sb.itertuples():
        try:
            b = bars_idx.loc[t.entry_time]
        except KeyError:
            continue
        if t.side == "buy":
            target = t.entry_price + 40.0
            stop = t.entry_price - 40.0
            if t.exit_reason == "target" and b["open"] >= target:
                risky_target += 1
                risky_breakdown_by_reason["target"] += 1
            elif t.exit_reason == "stop" and b["open"] <= stop:
                risky_stop += 1
                risky_breakdown_by_reason["stop"] += 1
        else:  # sell
            target = t.entry_price - 40.0
            stop = t.entry_price + 40.0
            if t.exit_reason == "target" and b["open"] <= target:
                risky_target += 1
                risky_breakdown_by_reason["target"] += 1
            elif t.exit_reason == "stop" and b["open"] >= stop:
                risky_stop += 1
                risky_breakdown_by_reason["stop"] += 1

    print(f"Same-bar entry+exit trades: {len(sb)}")
    print(f"  by exit reason: {sb['exit_reason'].value_counts().to_dict()}")
    print("\nRisky chronology (bar.open already past the credited exit level):")
    print(f"  risky target wins: {risky_target}")
    print(f"  risky stop losses: {risky_stop}")
    print(
        f"  total risky:       {risky_target + risky_stop} / {len(sb)} same-bar trades "
        f"= {(risky_target + risky_stop) / max(1, len(sb)):.1%} of same-bar; "
        f"{(risky_target + risky_stop) / len(trades):.1%} of all 908 trades"
    )

    return {
        "same_bar_count": int(len(sb)),
        "risky_target": int(risky_target),
        "risky_stop": int(risky_stop),
        "risky_total": int(risky_target + risky_stop),
    }


def p5_nan_indicator():
    """For each V2+40/40 baseline trade, look up ADX(15) and DI(15) at touch bar T-1.

    Count trades where either indicator was NaN (warm-up period). Those trades
    were classified as FADE by warm-up default — not by indicator decision.
    """
    print("\n" + "=" * 78)
    print("PRIORITY 5 — NaN indicator at fill (V2+40/40 baseline)")
    print("=" * 78)

    # Use the exact lookup dict that the simulator builds, so keys match.
    from indicators.adx import precompute_lookup as adx_precompute
    from indicators.di import precompute_lookup as di_precompute

    bars = pd.read_parquet(BARS_PARQUET)
    bars["ts_utc"] = pd.to_datetime(bars["ts_utc"], utc=True)

    lookup_adx = adx_precompute(bars, n=15)
    lookup_di = di_precompute(bars, n=15)

    trades = pd.read_parquet(V2_4040_PARQUET)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["adx_at_fill"] = trades["entry_time"].map(lambda t: lookup_adx.get(t, np.nan))
    trades["di_at_fill"] = trades["entry_time"].map(lambda t: lookup_di.get(t, np.nan))
    trades["adx_nan"] = trades["adx_at_fill"].isna()
    trades["di_nan"] = trades["di_at_fill"].isna()
    trades["any_nan"] = trades["adx_nan"] | trades["di_nan"]

    n = len(trades)
    n_adx_nan = int(trades["adx_nan"].sum())
    n_di_nan = int(trades["di_nan"].sum())
    n_any_nan = int(trades["any_nan"].sum())

    print(f"Total trades: {n}")
    print(f"ADX NaN at fill: {n_adx_nan} ({n_adx_nan / n:.1%})")
    print(f"DI  NaN at fill: {n_di_nan} ({n_di_nan / n:.1%})")
    print(f"Either NaN:      {n_any_nan} ({n_any_nan / n:.1%})")

    if n_any_nan > 0:
        nan_trades = trades[trades["any_nan"]]
        # These trades were labeled FADE by warm-up default. Confirm.
        labels = nan_trades["cluster_label"].value_counts().to_dict()
        print(f"Cluster labels of NaN-defaulted trades: {labels}")
        pnl = float(nan_trades["pnl_dollars"].sum())
        wr = float((nan_trades["pnl_dollars"] > 0).mean())
        print(f"NaN-defaulted trade P&L: ${pnl:,.2f}, WR {wr:.1%}")

    out = trades[
        [
            "session_date",
            "entry_time",
            "side",
            "pnl_dollars",
            "cluster_label",
            "adx_at_fill",
            "di_at_fill",
            "adx_nan",
            "di_nan",
            "any_nan",
        ]
    ]
    out.to_parquet(AUDIT_DIR / "p5_nan_indicator_per_trade.parquet", index=False)
    print(f"\nWrote {AUDIT_DIR / 'p5_nan_indicator_per_trade.parquet'}")

    return {"n_trades": n, "n_adx_nan": n_adx_nan, "n_di_nan": n_di_nan, "n_any_nan": n_any_nan}


def main():
    p1 = p1_tick_vs_bar()
    p3 = p3_overlay_vs_engine()
    p4 = p4_same_bar_stop_target()
    p4b = p4b_d014_chronology_risk()
    p5 = p5_nan_indicator()

    # Headline summary for SUMMARY.md to consume
    print("\n" + "=" * 78)
    print("AUDIT DIAGNOSTIC SUMMARY")
    print("=" * 78)
    print(
        f"P1 (32-trade verification): bar ${p1['bar_pnl_usd']:,.0f} vs tick ${p1['tick_pnl_usd']:,.0f}, "
        f"delta ${p1['delta_usd']:,.0f}, mismatches {p1['n_mismatches']}/{p1['n_trades']}"
    )
    print("P3 cluster-size overlay vs engine — see results above")
    print(
        f"P4: entry_both_reach {p4['entry_both_reach']}/{p4['n']} ({p4['entry_both_reach'] / p4['n']:.1%}), "
        f"exit_both_reach {p4['exit_both_reach']}/{p4['n']} ({p4['exit_both_reach'] / p4['n']:.1%})"
    )
    print(
        f"P4b: D-014 risky chronology {p4b['risky_total']}/{p4b['same_bar_count']} same-bar trades"
    )
    print(f"P5: any-NaN at fill {p5['n_any_nan']}/{p5['n_trades']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
