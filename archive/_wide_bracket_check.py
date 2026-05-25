"""Confirmatory wide-bracket TP/SL surface on the LOCKED entries.

Signals computed once (within_200 / g7 / m2 / no-ADX / center / buffer=1.0,
earliest_entry=09:45, latest_entry=11:29). Exits + Model A P&L re-walked per
(stop_pts, target_pts).

Run:
    .venv/bin/python results/_wide_bracket_check.py
"""

from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import math
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

# Locked config (entry-side only — stop/target overridden in the loop below)
CFG = {
    "lookback":       200,
    "gap":            7.0,
    "min_size":       2,
    "gate":           "within_200",
    "entry_location": "center",
    "entry_buffer":   1.0,
    "earliest_entry": "09:45",
    "latest_entry":   "11:29",
    "slip_pts":       0.5,           # Model A — per side
    "commission_rt":  2.0,           # $/RT, NinjaTrader all-in
}

CELLS = [
    ("30 / 20  (anchor)", 30.0, 20.0),
    ("60 / 60",           60.0, 60.0),
    ("100 / 100",        100.0, 100.0),
    ("150 / 150",        150.0, 150.0),
    ("200 / 100",        200.0, 100.0),
]


# ── Inlined helpers (byte-equivalent to src/vbt_backtest.py) ──────────────
def _trigger_anchors(day_cands, entry_location):
    if entry_location == "center":
        c = day_cands["center"].values
        return c, c
    raise ValueError(f"Unsupported entry_location for this script: {entry_location}")


def generate_signals_locked(bars, candidates):
    idx = bars.index
    long_entries = pd.Series(False, index=idx)
    short_entries = pd.Series(False, index=idx)
    entry_prices = pd.Series(np.nan, index=idx)

    for session in candidates["session_date"].unique():
        day_cands = candidates[candidates["session_date"] == session]
        day_bars = bars[bars["session_date"] == session]
        if day_bars.empty:
            continue
        entry_bars = day_bars.between_time(CFG["earliest_entry"],
                                           CFG["latest_entry"],
                                           inclusive="both")
        if entry_bars.empty:
            continue
        long_anchors, short_anchors = _trigger_anchors(day_cands,
                                                       CFG["entry_location"])
        long_triggers = long_anchors + CFG["entry_buffer"]
        short_triggers = short_anchors - CFG["entry_buffer"]

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


def walk_trades(bars, long_e, short_e, entry_p, force_e, stop_pts, target_pts):
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


def model_a_pnl(rec, slip_pts, commission_rt, mnq_pt=MNQ_MULTIPLIER):
    reason = rec["reason"].to_numpy()
    delta = np.where(reason == "target", slip_pts, 2 * slip_pts)
    pts = rec["raw_pts"].to_numpy() - delta
    return pts * mnq_pt - commission_rt


def metrics_for_cell(rec, slip_pts, commission_rt):
    pnl = model_a_pnl(rec, slip_pts, commission_rt)
    n = len(pnl)
    if n == 0:
        return None
    wins   = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    pf = (gw / gl) if gl > 0 else float("inf")
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum)
    mdd = float((cum - peak).min())
    worst = float(pnl.min())
    reasons = rec["reason"]
    n_tgt  = int((reasons == "target").sum())
    n_stop = int((reasons == "stop").sum())
    n_time = int((reasons == "time").sum())
    hold = (rec["exit_ts"] - rec["entry_ts"]).dt.total_seconds() / 60.0
    avg_hold = float(hold.mean())
    return dict(
        n_trades=n,
        win_rate=float((pnl > 0).mean()),
        net_dollars=float(pnl.sum()),
        profit_factor=pf,
        max_drawdown=mdd,
        worst_loss=worst,
        pct_target=100 * n_tgt / n,
        pct_stop=100 * n_stop / n,
        pct_time=100 * n_time / n,
        avg_hold_min=avg_hold,
    )


def main():
    print("Loading bars + building locked pipeline (signals computed once)...",
          flush=True)
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    or_close = compute_or_close(bars)
    pool = build_cluster_pool(or_levels, lookback=CFG["lookback"],
                              gap=CFG["gap"], min_size=CFG["min_size"])
    cands = build_candidates(or_levels, pool, gate=CFG["gate"],
                              or_close=or_close)
    long_e, short_e, entry_p, force_e = generate_signals_locked(bars, cands)
    n_ent = int((long_e | short_e).sum())
    print(f"  {len(bars):,} bars / {len(cands):,} candidates / {n_ent} entries",
          flush=True)

    print(f"\nWalking exits per cell (Model A, {CFG['slip_pts']}pt/side, "
          f"${CFG['commission_rt']}/RT) ...", flush=True)
    results = []
    for label, stop, target in CELLS:
        rec = walk_trades(bars, long_e, short_e, entry_p, force_e,
                          stop_pts=stop, target_pts=target)
        m = metrics_for_cell(rec, CFG["slip_pts"], CFG["commission_rt"])
        m["label"] = label
        m["stop"] = stop; m["target"] = target
        results.append(m)
        print(f"  {label:<22} done — n={m['n_trades']}, "
              f"net=${m['net_dollars']:+,.0f}, PF={m['profit_factor']:.3f}",
              flush=True)

    # ── Table ───────────────────────────────────────────────────────────
    print("\n" + "=" * 113)
    print(f"WIDE BRACKET SURFACE  ·  within_200 / g7 / m2 / no-ADX / center / "
          f"buffer=1.0  ·  Model A  ·  $2/RT  ·  0.5pt slip")
    print("=" * 113)
    hdr = (f"{'cell':<20} {'n':>5} {'WR':>7} {'net $':>10} {'PF':>7} "
           f"{'max_dd':>10} {'worst':>9} "
           f"{'%tgt':>6} {'%stop':>6} {'%time':>6} {'hold(m)':>8}")
    print(hdr)
    print("-" * len(hdr))
    for m in results:
        print(
            f"{m['label']:<20} "
            f"{m['n_trades']:>5d} "
            f"{m['win_rate']*100:>6.2f}% "
            f"${m['net_dollars']:>+9,.0f} "
            f"{m['profit_factor']:>7.3f} "
            f"${m['max_drawdown']:>+9,.0f} "
            f"${m['worst_loss']:>+8,.0f} "
            f"{m['pct_target']:>5.1f}% "
            f"{m['pct_stop']:>5.1f}% "
            f"{m['pct_time']:>5.1f}% "
            f"{m['avg_hold_min']:>7.1f}"
        )

    # Save for the dashboard / future reference
    out = ROOT / "results" / "wide_bracket_surface.csv"
    pd.DataFrame(results).to_csv(out, index=False)
    print(f"\nSaved: {out.relative_to(ROOT)}")

    print("\nWIDE BRACKET CHECK DONE")


if __name__ == "__main__":
    main()
