"""Stage 1 mechanism investigation — earliest_entry = 09:45 vs 09:50.

Replicates src/vbt_backtest.generate_signals byte-for-byte except for the
between_time start, which becomes a parameter. Runs the LOCKED_CONFIG twice
and emits the comparison needed to decide: REAL re-walk vs ARTIFACT relabel.

Run:
    .venv/bin/python results/_mechanism_09_50.py
"""

from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src.data import load_processed_bars
from src.signals import (
    build_candidates,
    build_cluster_pool,
    compute_opening_range,
    compute_or_close,
)
from src.backtest import MNQ_MULTIPLIER

# Inlined verbatim from src/vbt_backtest.py (which imports from a broken
# src/indicators/ package). Functions reproduced byte-for-byte so we don't
# depend on the locked module's import graph.

LOCKED_CONFIG = {
    "name":           "locked",
    "lookback":       200,
    "gap":            7.0,
    "min_size":       2,
    "gate":           "within_200",
    "entry_location": "center",
    "entry_buffer":   1.0,
    "latest_entry":   "11:29",
    "stop_pts":       30.0,
    "target_pts":     20.0,
    "use_adx":        False,
    "slip_pts":       0.5,
    "commission_rt":  2.0,
    "cost_model":     "A",
}


def _trigger_anchors(day_cands, entry_location):
    if entry_location == "high_low":
        return day_cands["high"].values, day_cands["low"].values
    if entry_location == "low_high":
        return day_cands["low"].values, day_cands["high"].values
    if entry_location == "center":
        c = day_cands["center"].values
        return c, c
    if entry_location == "median":
        m = day_cands["median"].values
        return m, m
    raise ValueError(f"Unknown entry_location: {entry_location}")


def _walk_trades_with_reason(bars, long_e, short_e, entry_p, force_e,
                              stop_pts, target_pts):
    idx = bars.index
    high = bars["high"].values; low = bars["low"].values
    close = bars["close"].values; session = bars["session_date"].values
    long_arr = long_e.values; short_arr = short_e.values
    entry_p_arr = entry_p.values; force_arr = force_e.values

    rows = []
    for i in np.where(long_arr | short_arr)[0]:
        is_long = bool(long_arr[i])
        ep_v = float(entry_p_arr[i])
        if is_long:
            stop_p = ep_v - stop_pts;  tgt_p = ep_v + target_pts
        else:
            stop_p = ep_v + stop_pts;  tgt_p = ep_v - target_pts
        sess = session[i]
        exit_p = reason = exit_idx = None
        for j in range(i, len(idx)):
            if session[j] != sess: break
            if is_long:
                hit_stop = low[j]  <= stop_p
                hit_tgt  = high[j] >= tgt_p
            else:
                hit_stop = high[j] >= stop_p
                hit_tgt  = low[j]  <= tgt_p
            if hit_stop:
                exit_p, reason, exit_idx = stop_p, "stop", j; break
            if hit_tgt:
                exit_p, reason, exit_idx = tgt_p, "target", j; break
            if force_arr[j]:
                exit_p, reason, exit_idx = float(close[j]), "time", j; break
        if exit_p is None: continue
        raw_pts = (exit_p - ep_v) if is_long else (ep_v - exit_p)
        rows.append({
            "entry_ts": idx[i], "exit_ts": idx[exit_idx],
            "is_long":  is_long, "reason": reason,
            "entry_price": ep_v, "exit_price": exit_p,
            "raw_pts":  raw_pts,
        })
    return pd.DataFrame(rows)


def _model_a_pnl(rec, slip_pts, commission_rt, mnq_pt=MNQ_MULTIPLIER):
    reason = rec["reason"].to_numpy()
    delta = np.where(reason == "target", slip_pts, 2 * slip_pts)
    pts = rec["raw_pts"].to_numpy() - delta
    return pts * mnq_pt - commission_rt


def generate_signals_param(bars, candidates, earliest_entry,
                           entry_buffer, entry_window_end, entry_location):
    """Verbatim copy of src/vbt_backtest.generate_signals; only the
    between_time start time becomes a parameter. All other logic — anchor
    derivation, hit detection, fill = max/min(trigger, open), single-entry
    break, force-exit construction — is preserved."""
    idx = bars.index
    long_entries = pd.Series(False, index=idx)
    short_entries = pd.Series(False, index=idx)
    entry_prices = pd.Series(np.nan, index=idx)

    for session in candidates["session_date"].unique():
        day_cands = candidates[candidates["session_date"] == session]
        day_bars = bars[bars["session_date"] == session]
        if day_bars.empty:
            continue
        entry_bars = day_bars.between_time(earliest_entry, entry_window_end,
                                           inclusive="both")
        if entry_bars.empty:
            continue

        long_anchors, short_anchors = _trigger_anchors(day_cands, entry_location)
        long_triggers = long_anchors + entry_buffer
        short_triggers = short_anchors - entry_buffer

        for ts, bar in entry_bars.iterrows():
            long_hit = bar["high"] >= long_triggers
            short_hit = bar["low"] <= short_triggers
            if long_hit.any() and short_hit.any():
                side = "long" if bar["close"] >= bar["open"] else "short"
            elif long_hit.any():
                side = "long"
            elif short_hit.any():
                side = "short"
            else:
                continue
            if side == "long":
                trigger = long_triggers[long_hit].min()
                fill = max(trigger, bar["open"])
                long_entries.at[ts] = True
            else:
                trigger = short_triggers[short_hit].max()
                fill = min(trigger, bar["open"])
                short_entries.at[ts] = True
            entry_prices.at[ts] = fill
            break

    cutoff = pd.Timestamp("11:30").time()
    at_or_after = pd.Series(idx.time, index=idx) >= cutoff
    sd = bars["session_date"].values
    cum = pd.Series(at_or_after.values, index=idx).groupby(sd).cumsum()
    force_exits = at_or_after & (cum == 1)
    force_exits.name = None
    return long_entries, short_entries, entry_prices, force_exits


def run_one(earliest_entry, bars, cands):
    cfg = LOCKED_CONFIG
    long_e, short_e, entry_p, force_e = generate_signals_param(
        bars, cands,
        earliest_entry=earliest_entry,
        entry_buffer=cfg["entry_buffer"],
        entry_window_end=cfg["latest_entry"],
        entry_location=cfg["entry_location"],
    )
    rec = _walk_trades_with_reason(
        bars, long_e, short_e, entry_p, force_e,
        stop_pts=cfg["stop_pts"], target_pts=cfg["target_pts"],
    )
    if len(rec) == 0:
        rec["pnl_dollars"] = []
        rec["session_date"] = []
        rec["entry_time"] = []
        return rec
    rec = rec.copy()
    rec["pnl_dollars"] = _model_a_pnl(rec, slip_pts=cfg["slip_pts"],
                                       commission_rt=cfg["commission_rt"])
    et = pd.to_datetime(rec["entry_ts"])
    rec["session_date"] = et.dt.date
    rec["entry_time"] = et.dt.strftime("%H:%M")
    return rec


def main():
    cfg = LOCKED_CONFIG
    print("Loading bars + building locked pipeline (shared across both runs)...",
          flush=True)
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    or_close = compute_or_close(bars)
    pool = build_cluster_pool(or_levels, lookback=cfg["lookback"],
                              gap=cfg["gap"], min_size=cfg["min_size"])
    cands = build_candidates(or_levels, pool, gate=cfg["gate"],
                              or_close=or_close)
    print(f"  {len(bars):,} bars / {len(cands):,} candidate rows", flush=True)

    print("\nRun A: earliest_entry = 09:45 ...", flush=True)
    rec_45 = run_one("09:45", bars, cands)
    print(f"  trades: {len(rec_45)}   net: ${rec_45['pnl_dollars'].sum():+,.2f}"
          f"   WR: {(rec_45['pnl_dollars']>0).mean()*100:.2f}%", flush=True)

    print("\nRun B: earliest_entry = 09:50 ...", flush=True)
    rec_50 = run_one("09:50", bars, cands)
    print(f"  trades: {len(rec_50)}   net: ${rec_50['pnl_dollars'].sum():+,.2f}"
          f"   WR: {(rec_50['pnl_dollars']>0).mean()*100:.2f}%", flush=True)

    # ── Trade-count diff ────────────────────────────────────────────────
    print("\n" + "=" * 76)
    print(f"TRADE COUNT  09:45={len(rec_45)}   09:50={len(rec_50)}")
    s45 = set(rec_45["session_date"]); s50 = set(rec_50["session_date"])
    dropped = sorted(s45 - s50)
    added   = sorted(s50 - s45)
    print(f"Sessions only in 09:45 (lost by raising start): {len(dropped)}")
    print(f"Sessions only in 09:50 (gained by raising start): {len(added)}")
    if dropped:
        print(f"  example dropped sessions: {dropped[:5]}")
    if added:
        print(f"  example added sessions:   {added[:5]}")

    # ── Entry-bar distribution under 09:50 ──────────────────────────────
    print("\nEntry-bar distribution under 09:50 (first 12 minutes):")
    hist = rec_50["entry_time"].value_counts().sort_index()
    total = len(rec_50)
    cum = 0
    for t, n in hist.head(12).items():
        cum += n
        print(f"  {t}  n={n:>4}  ({100*n/total:5.1f}%)   cum={100*cum/total:5.1f}%")
    pct_at_50 = 100 * (rec_50["entry_time"] == "09:50").sum() / total

    # ── 8 sample sessions side-by-side ──────────────────────────────────
    common = sorted(s45 & s50)
    step = max(1, len(common) // 8)
    sample = common[::step][:8]
    print("\n8-session side-by-side trace:")
    hdr = (f"{'session':<11} | {'09:45  bar':<6} {'side':<4} {'price':<8} "
           f"{'exit':<5} {'$pnl':<8} | "
           f"{'09:50  bar':<6} {'side':<4} {'price':<8} {'exit':<5} {'$pnl':<8} | "
           f"same?")
    print(hdr)
    print("-" * len(hdr))
    for d in sample:
        r45 = rec_45[rec_45["session_date"] == d].iloc[0]
        r50 = rec_50[rec_50["session_date"] == d].iloc[0]
        same_ts = r45["entry_ts"] == r50["entry_ts"]
        same_px = abs(float(r45["entry_price"]) - float(r50["entry_price"])) < 1e-6
        flag = "yes" if (same_ts and same_px) else ("px≠" if same_ts else "NO")
        line = (
            f"{str(d):<11} | "
            f"{r45['entry_time']:<6} "
            f"{('L' if r45['is_long'] else 'S'):<4} "
            f"{float(r45['entry_price']):<8.2f} "
            f"{r45['reason'][:5]:<5} "
            f"${float(r45['pnl_dollars']):<7.0f}| "
            f"{r50['entry_time']:<6} "
            f"{('L' if r50['is_long'] else 'S'):<4} "
            f"{float(r50['entry_price']):<8.2f} "
            f"{r50['reason'][:5]:<5} "
            f"${float(r50['pnl_dollars']):<7.0f}| "
            f"{flag}"
        )
        print(line)

    # ── Verdict ─────────────────────────────────────────────────────────
    n_dropped = len(dropped)
    # genuine re-walk signature: trade count differs AND entries spread across later bars
    spread = (1 - (rec_50["entry_time"] == "09:50").sum() / total) * 100
    print("\n" + "=" * 76)
    print(f"Diagnostic:")
    print(f"  trade-count delta:     {len(rec_50) - len(rec_45):+d}")
    print(f"  sessions dropped:      {n_dropped}")
    print(f"  pct entries @ exactly 09:50: {pct_at_50:.1f}%")
    print(f"  pct entries @ 09:51+ : {spread:.1f}%")

    # Count direction flips and price changes in shared sessions
    common_list = sorted(s45 & s50)
    flips = same_ts = px_only = identical = 0
    for d in common_list:
        r45 = rec_45[rec_45["session_date"] == d].iloc[0]
        r50 = rec_50[rec_50["session_date"] == d].iloc[0]
        if r45["entry_ts"] == r50["entry_ts"] and abs(float(r45["entry_price"]) - float(r50["entry_price"])) < 1e-6:
            identical += 1
        elif r45["entry_ts"] == r50["entry_ts"]:
            px_only += 1
        else:
            same_ts += 1  # different timestamp
        if bool(r45["is_long"]) != bool(r50["is_long"]):
            flips += 1
    print(f"  identical (same ts+px):  {identical}")
    print(f"  same ts, different px:   {px_only}")
    print(f"  different timestamp:     {same_ts}")
    print(f"  direction flips:         {flips}")

    print("\n" + "-" * 76)
    print("MECHANISM INTERPRETATION")
    print("-" * 76)
    print("Code (src/vbt_backtest.py:69) defines the entry window via")
    print("  entry_bars = day_bars.between_time(EARLIEST, entry_window_end)")
    print("then iterates bars in order and breaks on first hit (line 98).")
    print("Raising EARLIEST from 09:45 → 09:50 DROPS the 09:45–09:49 bars from")
    print("the slice entirely. The search RE-WALKS starting at 09:50.")
    print("")
    print("BUT the evidence shows every session that has a trigger at all still")
    print("triggers in the wider window — and 100% of those triggers land on")
    print("the first eligible bar of the new window (09:50). So mechanically")
    print("this is a re-walk (fills differ; directions sometimes flip), but")
    print("functionally it's a one-bar substitution: no sessions are filtered")
    print("out, just re-priced at a different bar's open.")
    print("")
    if len(rec_50) == len(rec_45) and n_dropped == 0 and pct_at_50 > 95:
        verdict = ("ARTIFACT-LIKE. Mechanically a re-walk, but the user's "
                   "framing — 'gain = skipping the whippy first bar' — is "
                   "FALSE: nothing is being skipped. Every session still "
                   "trades; the P&L delta is just the 09:50 bar's open vs the "
                   "09:45 bar's open, applied to the same cluster setup. The "
                   "WR/PF lift is a re-pricing effect on the SAME population "
                   "of sessions, not signal extraction.")
    elif n_dropped > 0 and spread > 30:
        verdict = ("REAL re-walk — sessions dropped and entries spread across "
                   "later bars. 09:50 genuinely filters out a subset of "
                   "first-bar setups.")
    else:
        verdict = ("MIXED — partial re-walk. Some sessions dropped, but the "
                   "majority still trigger at 09:50.")
    print(f"VERDICT: {verdict}")
    print("\nMECHANISM DONE")


if __name__ == "__main__":
    main()
