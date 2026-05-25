"""Tick-by-tick simulator for the overlap window 2026-03-17 .. 2026-04-15.

Strategy logic mirrors the original simulator (cluster detection, first-touch
mean-reversion entry, one-position-at-a-time, 9:46-11:30 NY trading window),
but execution is fully tick-driven. No bar high/low aggregation: limits fill
on the first tick whose last-price reaches them, and stop/target ordering is
resolved chronologically by walking ticks one by one.
"""

from collections import deque

import numpy as np
import pandas as pd

from clusters import find_clusters
from paths import ORB_TABLE_PARQUET, TICKS_OVERLAP_PARQUET, TRADES_PARQUET

LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
POINT_VALUE_USD = 2.0

OVERLAP_START = pd.Timestamp("2026-03-17")
OVERLAP_END = pd.Timestamp("2026-04-15")


def classify_setups(clusters_today, reference_price):
    setups = []
    for c in clusters_today:
        if c.low > reference_price:
            setups.append({"side": "sell", "limit_price": c.low, "cluster": c, "triggered": False})
        elif c.high < reference_price:
            setups.append({"side": "buy", "limit_price": c.high, "cluster": c, "triggered": False})
    return setups


def simulate_session(
    ts_ns, last_arr, setups, session_date, window_start_ns, fc_utc_ns, stop_pts, target_pts
):
    """Vectorized tick walk for a single session.

    ts_ns: int64 nanoseconds since epoch (UTC). last_arr: float prices.
    """
    if not setups or len(ts_ns) == 0:
        return []

    n = len(ts_ns)
    start_idx = int(np.searchsorted(ts_ns, window_start_ns, side="left"))
    fc_idx = int(np.searchsorted(ts_ns, fc_utc_ns, side="left"))
    if start_idx >= n:
        return []

    open_ref = float(last_arr[start_idx])
    trades = []
    i = start_idx

    while i < fc_idx:
        # Find earliest fill across all unfilled setups, with closest-to-open tiebreak
        best_setup = None
        best_idx = None
        best_dist = None
        for s in setups:
            if s["triggered"]:
                continue
            limit = s["limit_price"]
            seg = last_arr[i:fc_idx]
            if s["side"] == "sell":
                hits = np.flatnonzero(seg >= limit)
            else:
                hits = np.flatnonzero(seg <= limit)
            if len(hits) == 0:
                continue
            hit_i = i + int(hits[0])
            d = abs(limit - open_ref)
            if (best_idx is None) or (hit_i < best_idx) or (hit_i == best_idx and d < best_dist):
                best_setup = s
                best_idx = hit_i
                best_dist = d

        if best_setup is None:
            break

        best_setup["triggered"] = True
        entry_idx = best_idx
        entry = best_setup["limit_price"]
        side = best_setup["side"]

        if side == "buy":
            stop_p = entry - stop_pts
            target_p = entry + target_pts
            seg = last_arr[entry_idx + 1 : fc_idx]
            stop_hits = np.flatnonzero(seg <= stop_p)
            target_hits = np.flatnonzero(seg >= target_p)
        else:
            stop_p = entry + stop_pts
            target_p = entry - target_pts
            seg = last_arr[entry_idx + 1 : fc_idx]
            stop_hits = np.flatnonzero(seg >= stop_p)
            target_hits = np.flatnonzero(seg <= target_p)

        first_stop = int(stop_hits[0]) if len(stop_hits) else None
        first_target = int(target_hits[0]) if len(target_hits) else None

        if first_stop is None and first_target is None:
            # Force close at first tick at/after fc_utc
            if fc_idx < n:
                exit_idx = fc_idx
                exit_price = float(last_arr[fc_idx])
            else:
                exit_idx = n - 1
                exit_price = float(last_arr[exit_idx])
            reason = "force_close"
            pts = (exit_price - entry) if side == "buy" else (entry - exit_price)
        elif first_stop is None or (first_target is not None and first_target < first_stop):
            exit_idx = entry_idx + 1 + first_target
            reason = "target"
            exit_price = target_p
            pts = target_pts
        else:
            exit_idx = entry_idx + 1 + first_stop
            reason = "stop"
            exit_price = stop_p
            pts = -stop_pts

        trades.append(
            {
                "session_date": session_date,
                "side": side,
                "entry_time": pd.Timestamp(int(ts_ns[entry_idx]), tz="UTC"),
                "entry_price": entry,
                "exit_time": pd.Timestamp(int(ts_ns[exit_idx]), tz="UTC"),
                "exit_price": exit_price,
                "exit_reason": reason,
                "pnl_points": pts,
                "pnl_dollars": pts * POINT_VALUE_USD,
                "cluster_low": best_setup["cluster"].low,
                "cluster_high": best_setup["cluster"].high,
                "cluster_size": best_setup["cluster"].size,
            }
        )

        if reason == "force_close":
            break
        i = exit_idx + 1

    return trades


def run_config(stop_pts, target_pts, ticks_df, orb_table, overlap_dates):
    level_pool: deque = deque(maxlen=LOOKBACK)
    all_trades = []

    # Pre-group ticks by UTC date
    ticks_df = ticks_df.copy()
    ticks_df["date"] = ticks_df["ts_utc"].dt.date
    ticks_by_date = {
        d: g.sort_values("ts_utc").reset_index(drop=True) for d, g in ticks_df.groupby("date")
    }

    for orb_row in orb_table.itertuples():
        sd = pd.Timestamp(orb_row.session_date)
        levels = []
        for h, l in level_pool:
            levels.append(h)
            levels.append(l)
        levels.append(orb_row.orb_high)
        levels.append(orb_row.orb_low)

        clusters = find_clusters(levels, max_gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE)
        setups = classify_setups(clusters, float(orb_row.orb_close))

        sd_date = sd.date()
        if sd_date in overlap_dates:
            session_ticks = ticks_by_date.get(sd_date)
            if session_ticks is not None and len(session_ticks):
                ts_ns = (
                    session_ticks["ts_utc"].astype("datetime64[ns, UTC]").astype("int64").to_numpy()
                )
                last_arr = session_ticks["last"].to_numpy()
                window_start_ns = int(pd.Timestamp(f"{sd_date} 13:46:00", tz="UTC").value)
                fc_utc_ns = int(pd.Timestamp(f"{sd_date} 15:30:00", tz="UTC").value)
                trades = simulate_session(
                    ts_ns, last_arr, setups, sd, window_start_ns, fc_utc_ns, stop_pts, target_pts
                )
                all_trades.extend(trades)

        level_pool.append((float(orb_row.orb_high), float(orb_row.orb_low)))

    return all_trades


def report(trades, label):
    if not trades:
        print(f"\n{label}: NO TRADES")
        return None
    df = pd.DataFrame(trades)
    n = len(df)
    wins = int((df["pnl_points"] > 0).sum())
    losses = int((df["pnl_points"] < 0).sum())
    flat = int((df["pnl_points"] == 0).sum())
    wr = wins / n * 100
    pts = df["pnl_points"].sum()
    usd = df["pnl_dollars"].sum()
    exp_pts = df["pnl_points"].mean()

    df_s = df.sort_values("entry_time").reset_index(drop=True)
    eq = df_s["pnl_dollars"].cumsum().to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    max_dd = float(dd.min()) if len(dd) else 0.0

    er = df["exit_reason"].value_counts().to_dict()
    targets = er.get("target", 0)
    stops = er.get("stop", 0)
    fc = er.get("force_close", 0)

    best = float(df["pnl_dollars"].max())
    worst = float(df["pnl_dollars"].min())

    print(f"\n=== {label} ===")
    print(f"  Trades:                   {n}")
    print(f"  Win/Loss/Flat:            {wins} / {losses} / {flat}")
    print(f"  Win rate:                 {wr:.1f}%")
    print(f"  Total P&L:                {pts:+.2f} pts  (${usd:+,.2f})")
    print(f"  Expectancy/trade:         {exp_pts:+.3f} pts  (${exp_pts * POINT_VALUE_USD:+.2f})")
    print(f"  Max drawdown:             ${max_dd:+,.2f}")
    print(f"  Targets / Stops / FC:     {targets} / {stops} / {fc}")
    print(f"  Best / Worst trade:       ${best:+,.2f} / ${worst:+,.2f}")
    return {
        "label": label,
        "n": n,
        "wins": wins,
        "losses": losses,
        "wr": wr,
        "pts": pts,
        "usd": usd,
        "exp_pts": exp_pts,
        "max_dd": max_dd,
        "targets": targets,
        "stops": stops,
        "fc": fc,
        "best": best,
        "worst": worst,
    }


def main() -> None:
    ticks = pd.read_parquet(TICKS_OVERLAP_PARQUET)
    ticks["ts_utc"] = pd.to_datetime(ticks["ts_utc"], utc=True)
    ticks = ticks.sort_values("ts_utc").reset_index(drop=True)

    orb_table = (
        pd.read_parquet(ORB_TABLE_PARQUET).sort_values("session_date").reset_index(drop=True)
    )
    orb_table["session_date"] = pd.to_datetime(orb_table["session_date"])

    overlap_orb = orb_table[
        (orb_table["session_date"] >= OVERLAP_START) & (orb_table["session_date"] <= OVERLAP_END)
    ]
    overlap_dates = set(d.date() for d in overlap_orb["session_date"])

    print(f"Loaded {len(ticks):,} ticks and {len(orb_table)} ORB sessions")
    print(f"Overlap sessions to simulate: {len(overlap_dates)}")

    configs = [
        ("A: 30/30 (R:R 1:1)", 30.0, 30.0),
        ("B: 10/30 (R:R 1:3)", 10.0, 30.0),
        ("C: 15/30 (R:R 1:2)", 15.0, 30.0),
        ("D: 5/20  (R:R 1:4)", 5.0, 20.0),
    ]

    summaries = []
    for label, stop_pts, target_pts in configs:
        trades = run_config(stop_pts, target_pts, ticks, orb_table, overlap_dates)
        summaries.append(report(trades, label))

    # Bar-vs-tick for Config A
    bar_trades = pd.read_parquet(TRADES_PARQUET)
    bar_trades["session_date"] = pd.to_datetime(bar_trades["session_date"])
    bar_overlap = bar_trades[
        (bar_trades["session_date"] >= OVERLAP_START) & (bar_trades["session_date"] <= OVERLAP_END)
    ]
    n_b = len(bar_overlap)
    if n_b:
        wr_b = (bar_overlap["pnl_points"] > 0).sum() / n_b * 100
        er_b = bar_overlap["exit_reason"].value_counts().to_dict()
        eq = bar_overlap.sort_values("entry_time")["pnl_dollars"].cumsum().to_numpy()
        peak = np.maximum.accumulate(eq)
        dd_b = float((eq - peak).min())
        print("\n=== BAR-BASED 1-MIN SIM (same overlap period) for Config A ===")
        print(f"  Trades:                   {n_b}")
        print(f"  Win rate:                 {wr_b:.1f}%")
        print(
            f"  Total P&L:                {bar_overlap['pnl_points'].sum():+.2f} pts  "
            f"(${bar_overlap['pnl_dollars'].sum():+,.2f})"
        )
        print(f"  Expectancy/trade:         {bar_overlap['pnl_points'].mean():+.3f} pts")
        print(f"  Max drawdown:             ${dd_b:+,.2f}")
        print(
            f"  Targets / Stops / FC:     {er_b.get('target', 0)} / {er_b.get('stop', 0)} / {er_b.get('force_close', 0)}"
        )
        print(
            f"  Best / Worst trade:       ${bar_overlap['pnl_dollars'].max():+,.2f} / ${bar_overlap['pnl_dollars'].min():+,.2f}"
        )


if __name__ == "__main__":
    main()
