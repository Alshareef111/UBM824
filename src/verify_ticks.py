"""Per-trade tick-level verification of trades.parquet against ticks_overlap.parquet.

For each overlap trade (session_date 2026-03-17..2026-05-01):
  - confirm an entry-fill tick exists during the entry minute
  - stream subsequent ticks and determine which level (stop / target) hit first
  - compare to simulator's exit_reason
  - flag mismatches and compute the P&L impact
"""

import numpy as np
import pandas as pd

from paths import TICKS_OVERLAP_PARQUET, TRADES_PARQUET, VERIFICATION_PARQUET, ensure_dirs

OVERLAP_START_DATE = pd.Timestamp("2026-03-17")
OVERLAP_END_DATE = pd.Timestamp("2026-05-01")

STOP_POINTS = 30.0
TARGET_POINTS = 30.0
POINT_VALUE_USD = 2.0
ENTRY_MINUTE_SEC = 60

# 11:30 NY = 15:30 UTC (EDT, March-November)
FORCE_CLOSE_UTC_HM = (15, 30)


def fmt_money(x: float) -> str:
    return f"${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}"


def verify_trade(t, ticks_df: pd.DataFrame) -> dict:
    side = t.side
    entry_price = float(t.entry_price)
    entry_time = t.entry_time

    if side == "buy":
        stop_price = entry_price - STOP_POINTS
        target_price = entry_price + TARGET_POINTS
    else:
        stop_price = entry_price + STOP_POINTS
        target_price = entry_price - TARGET_POINTS

    entry_window_end = entry_time + pd.Timedelta(seconds=ENTRY_MINUTE_SEC)
    em = ticks_df[(ticks_df["ts_utc"] >= entry_time) & (ticks_df["ts_utc"] < entry_window_end)]
    last_arr = em["last"].to_numpy()
    ts_arr = em["ts_utc"].to_numpy()

    if side == "buy":
        fill_pos = np.where(last_arr <= entry_price)[0]
    else:
        fill_pos = np.where(last_arr >= entry_price)[0]

    if len(fill_pos) == 0:
        return {
            "entry_filled": False,
            "fill_ts": None,
            "fill_price": None,
            "tick_outcome": "NO_FILL",
            "tick_exit_ts": None,
            "tick_exit_price": None,
            "stop_price": stop_price,
            "target_price": target_price,
        }

    fill_idx = fill_pos[0]
    fill_ts = ts_arr[fill_idx]
    fill_price = float(last_arr[fill_idx])

    session_date = pd.Timestamp(t.session_date).date()
    fc_utc = pd.Timestamp(
        f"{session_date} {FORCE_CLOSE_UTC_HM[0]:02d}:{FORCE_CLOSE_UTC_HM[1]:02d}:00",
        tz="UTC",
    )

    after = ticks_df[(ticks_df["ts_utc"] > fill_ts) & (ticks_df["ts_utc"] < fc_utc)]
    a_last = after["last"].to_numpy()
    a_ts = after["ts_utc"].to_numpy()

    if side == "buy":
        stop_hits = np.where(a_last <= stop_price)[0]
        target_hits = np.where(a_last >= target_price)[0]
    else:
        stop_hits = np.where(a_last >= stop_price)[0]
        target_hits = np.where(a_last <= target_price)[0]

    first_stop = stop_hits[0] if len(stop_hits) else None
    first_target = target_hits[0] if len(target_hits) else None

    if first_stop is None and first_target is None:
        # neither hit before force-close
        fc_after = ticks_df[ticks_df["ts_utc"] >= fc_utc]
        if len(fc_after):
            fc_tick = fc_after.iloc[0]
            return {
                "entry_filled": True,
                "fill_ts": fill_ts,
                "fill_price": fill_price,
                "tick_outcome": "force_close",
                "tick_exit_ts": fc_tick["ts_utc"],
                "tick_exit_price": float(fc_tick["last"]),
                "stop_price": stop_price,
                "target_price": target_price,
            }
        return {
            "entry_filled": True,
            "fill_ts": fill_ts,
            "fill_price": fill_price,
            "tick_outcome": "force_close",
            "tick_exit_ts": None,
            "tick_exit_price": None,
            "stop_price": stop_price,
            "target_price": target_price,
        }

    if first_stop is None:
        outcome, exit_pos, exit_p = "target", first_target, target_price
    elif first_target is None:
        outcome, exit_pos, exit_p = "stop", first_stop, stop_price
    else:
        if a_ts[first_stop] <= a_ts[first_target]:
            outcome, exit_pos, exit_p = "stop", first_stop, stop_price
        else:
            outcome, exit_pos, exit_p = "target", first_target, target_price

    return {
        "entry_filled": True,
        "fill_ts": fill_ts,
        "fill_price": fill_price,
        "tick_outcome": outcome,
        "tick_exit_ts": a_ts[exit_pos],
        "tick_exit_price": float(exit_p),
        "stop_price": stop_price,
        "target_price": target_price,
    }


def main() -> None:
    ensure_dirs()
    trades = pd.read_parquet(TRADES_PARQUET)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades["session_date"] = pd.to_datetime(trades["session_date"])

    ticks = pd.read_parquet(TICKS_OVERLAP_PARQUET)
    ticks["ts_utc"] = pd.to_datetime(ticks["ts_utc"], utc=True)
    ticks = ticks.sort_values("ts_utc").reset_index(drop=True)

    overlap = (
        trades[
            (trades["session_date"] >= OVERLAP_START_DATE)
            & (trades["session_date"] <= OVERLAP_END_DATE)
        ]
        .copy()
        .reset_index(drop=True)
    )

    print(f"Verifying {len(overlap)} overlap trades against {len(ticks):,} ticks\n")

    results = []
    for t in overlap.itertuples():
        results.append(verify_trade(t, ticks))

    overlap["sim_outcome"] = overlap["exit_reason"]
    overlap["tick_outcome"] = [r["tick_outcome"] for r in results]
    overlap["entry_filled"] = [r["entry_filled"] for r in results]
    overlap["fill_ts"] = [r["fill_ts"] for r in results]
    overlap["fill_price"] = [r["fill_price"] for r in results]
    overlap["tick_exit_ts"] = [r["tick_exit_ts"] for r in results]
    overlap["tick_exit_price"] = [r["tick_exit_price"] for r in results]
    overlap["stop_price"] = [r["stop_price"] for r in results]
    overlap["target_price"] = [r["target_price"] for r in results]
    overlap["match"] = overlap["sim_outcome"] == overlap["tick_outcome"]

    def real_pnl(row):
        side = row["side"]
        if row["tick_outcome"] == "NO_FILL":
            return 0.0
        if row["tick_outcome"] == "force_close":
            te = row["tick_exit_price"]
            if te is None:
                return float(row["pnl_dollars"])
            return (
                (te - row["entry_price"]) if side == "buy" else (row["entry_price"] - te)
            ) * POINT_VALUE_USD
        if row["tick_outcome"] == "stop":
            return -STOP_POINTS * POINT_VALUE_USD
        return TARGET_POINTS * POINT_VALUE_USD

    overlap["real_pnl"] = overlap.apply(real_pnl, axis=1)

    total = len(overlap)
    matches = int(overlap["match"].sum())
    mismatches = total - matches
    no_fill = int((overlap["tick_outcome"] == "NO_FILL").sum())
    sim_pnl = float(overlap["pnl_dollars"].sum())
    real_pnl_sum = float(overlap["real_pnl"].sum())

    print("=" * 76)
    print("VERIFICATION SUMMARY")
    print("=" * 76)
    print(f"Total overlap trades:    {total}")
    print(f"Matches:                 {matches} ({matches / total * 100:.1f}%)")
    print(f"Mismatches:              {mismatches}")
    print(f"NO_FILL flags:           {no_fill}")
    print()
    print(f"Sim P&L  (overlap):      {fmt_money(sim_pnl)}")
    print(f"Tick P&L (overlap):      {fmt_money(real_pnl_sum)}")
    print(f"Net impact:              {fmt_money(real_pnl_sum - sim_pnl)}")
    print()

    if mismatches:
        print("MISMATCH DETAIL")
        print("-" * 76)
        mm = overlap[~overlap["match"]]
        for _, r in mm.iterrows():
            print(
                f"  {r['session_date'].date()}  {r['side'].upper():4s}  "
                f"entry={r['entry_price']:.2f}  stop={r['stop_price']:.2f}  "
                f"target={r['target_price']:.2f}"
            )
            print(
                f"      sim={r['sim_outcome']} ({fmt_money(r['pnl_dollars'])})    "
                f"tick={r['tick_outcome']} ({fmt_money(r['real_pnl'])})"
            )
            print(
                f"      entry_time={r['entry_time']}  fill_ts={r['fill_ts']}  "
                f"sim_exit={r['exit_time']}  tick_exit={r['tick_exit_ts']}"
            )
            print()

    print("PER-TRADE TABLE")
    print("-" * 76)
    print(
        f"{'Date':<12}{'Side':<6}{'Entry':>10}{'Sim':>14}{'Tick':>14}{'Match':>7}"
        f"{'SimPnL':>10}{'RealPnL':>10}"
    )
    for _, r in overlap.iterrows():
        match_s = "Y" if r["match"] else "N"
        print(
            f"{str(r['session_date'].date()):<12}{r['side']:<6}"
            f"{r['entry_price']:>10.2f}{r['sim_outcome']:>14}{r['tick_outcome']:>14}"
            f"{match_s:>7}{r['pnl_dollars']:>10.2f}{r['real_pnl']:>10.2f}"
        )

    # Persist for follow-up
    overlap.to_parquet(VERIFICATION_PARQUET, index=False)


if __name__ == "__main__":
    main()
