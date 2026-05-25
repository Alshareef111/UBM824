"""Diagnostic: how many stop exits actually had stop AND target inside the
same 1-minute bar (the conservative stop-first rule resolved the ambiguity)?
"""

from pathlib import Path

import pandas as pd

from paths import TRADES_PARQUET, BARS_PARQUET

STOP_POINTS = 30.0
TARGET_POINTS = 30.0
POINT_VALUE_USD = 2.0


def fmt_money(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.2f}"


def main() -> None:
    trades = pd.read_parquet(TRADES_PARQUET)
    bars = pd.read_parquet(BARS_PARQUET)

    # stop / target prices per trade
    is_buy = trades["side"] == "buy"
    trades["stop_price"] = trades["entry_price"].where(~is_buy, trades["entry_price"] - STOP_POINTS)
    trades.loc[is_buy, "stop_price"] = trades.loc[is_buy, "entry_price"] - STOP_POINTS
    trades.loc[~is_buy, "stop_price"] = trades.loc[~is_buy, "entry_price"] + STOP_POINTS
    trades.loc[is_buy, "target_price"] = trades.loc[is_buy, "entry_price"] + TARGET_POINTS
    trades.loc[~is_buy, "target_price"] = trades.loc[~is_buy, "entry_price"] - TARGET_POINTS

    # join exit bar OHLC by ts_utc
    bar_lookup = bars[["ts_utc", "ts_ny", "open", "high", "low", "close"]].rename(
        columns={"ts_utc": "exit_time", "open": "bar_open", "high": "bar_high",
                 "low": "bar_low", "close": "bar_close", "ts_ny": "bar_ts_ny"}
    )
    merged = trades.merge(bar_lookup, on="exit_time", how="left")

    # ambiguous = exit bar contains BOTH stop and target levels
    buy_amb = (merged["side"] == "buy") & \
              (merged["bar_low"] <= merged["stop_price"]) & \
              (merged["bar_high"] >= merged["target_price"])
    sell_amb = (merged["side"] == "sell") & \
               (merged["bar_high"] >= merged["stop_price"]) & \
               (merged["bar_low"] <= merged["target_price"])
    merged["ambiguous"] = buy_amb | sell_amb

    stop_exits = merged[merged["exit_reason"] == "stop"]
    ambig_stops = stop_exits[stop_exits["ambiguous"]]

    n_total = len(merged)
    n_stop = len(stop_exits)
    n_ambig = len(ambig_stops)

    print("=" * 70)
    print("AMBIGUOUS BARS DIAGNOSTIC (stop AND target both inside exit bar)")
    print("=" * 70)
    print(f"Total trades:                   {n_total}")
    print(f"Total stop exits:               {n_stop}")
    print(f"Ambiguous stop exits:           {n_ambig}")
    print(f"  As % of stop exits ({n_stop}):    {n_ambig / n_stop * 100:.1f}%")
    print(f"  As % of all trades ({n_total}):   {n_ambig / n_total * 100:.1f}%")
    print()

    # Flip experiment
    # currently each ambiguous stop = -30 pts. If treated as target = +30 pts.
    # Per trade swing = +60 pts = +$120.
    swing_pts_per = STOP_POINTS + TARGET_POINTS
    swing_usd_per = swing_pts_per * POINT_VALUE_USD
    delta_pts = n_ambig * swing_pts_per
    delta_usd = n_ambig * swing_usd_per

    current_total_usd = merged["pnl_dollars"].sum()
    flipped_total_usd = current_total_usd + delta_usd

    print("FLIP EXPERIMENT (assume target-first on ambiguous bars):")
    print(f"  Per-trade swing:        +{swing_pts_per:.0f} pts ({fmt_money(swing_usd_per)})")
    print(f"  Total swing:            +{delta_pts:.0f} pts ({fmt_money(delta_usd)})")
    print(f"  Original total P&L:     {fmt_money(current_total_usd)}")
    print(f"  Flipped total P&L:      {fmt_money(flipped_total_usd)}")
    print()

    # Examples
    print("EXAMPLE AMBIGUOUS TRADES (first 5):")
    print("-" * 70)
    cols = ["session_date", "side", "entry_time", "entry_price", "stop_price",
            "target_price", "exit_time", "bar_ts_ny", "bar_open", "bar_high",
            "bar_low", "bar_close"]
    for _, r in ambig_stops.head(5).iterrows():
        bar_range = r["bar_high"] - r["bar_low"]
        print(f"  Date:     {r['session_date'].date()}  ({r['side'].upper()})")
        print(f"  Entry:    {r['entry_price']:.2f}  at {r['entry_time']}")
        print(f"  Stop:     {r['stop_price']:.2f}     Target: {r['target_price']:.2f}")
        print(f"  Exit bar: {r['bar_ts_ny']}  (NY)")
        print(f"            O={r['bar_open']:.2f}  H={r['bar_high']:.2f}  "
              f"L={r['bar_low']:.2f}  C={r['bar_close']:.2f}  range={bar_range:.2f} pts")
        print()


if __name__ == "__main__":
    main()
