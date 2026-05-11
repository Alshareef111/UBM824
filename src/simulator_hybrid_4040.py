"""Hybrid simulator — fade in directional regimes, breakout in flat regime.

Per-cluster regime classification at session start (9:46 NY, after ORB closes):
- For each cluster, the limit price is cluster.low (cluster ABOVE ref) or
  cluster.high (cluster BELOW ref) — same as the original fade simulator.
- Compute expected_normalized_distance = (limit_price - 9:46_bar_open) / lagged_ATR_10.
- If |expected_normalized_distance| <= HYBRID_FLAT_THRESHOLD: regime = "flat",
  reverse the trade direction (breakout). Otherwise: regime = "directional",
  use original fade direction.
- Trigger condition is decoupled from trade side via `trigger_above` (set by
  cluster position vs ref) so reverse-direction orders fire at the same price.
- Stop / target / force-close mechanics identical to simulator.py.

Output: results/archive/trades_hybrid.parquet
The locked baseline (data/processed/trades.parquet) is NOT touched.
"""

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from clusters import Cluster, find_clusters
from paths import BARS_PARQUET, ORB_TABLE_PARQUET, ARCHIVE_DIR, ensure_dirs

TRADES_PARQUET = ARCHIVE_DIR / "trades_hybrid_4040_20260511.parquet"

LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
STOP_POINTS = 40.0
TARGET_POINTS = 40.0
POINT_VALUE_USD = 2.0

TRADE_OPEN_HM = (9, 46)
TRADE_CLOSE_HM = (11, 30)
FORCE_CLOSE_HM = (11, 30)

HYBRID_FLAT_THRESHOLD = 0.09  # |(limit - 9:46_open) / ATR_10| <= this → flat regime → reverse
ATR_LOOKBACK = 10


@dataclass
class Setup:
    side: str           # "buy" or "sell" (after regime routing)
    cluster: Cluster
    limit_price: float
    trigger_above: bool # True if order fires when bar.high >= limit (cluster ABOVE ref)
    regime: str         # "flat" | "directional" | "UNLABELED"
    triggered: bool = False


@dataclass
class Trade:
    session_date: pd.Timestamp
    contract: str
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str
    pnl_points: float
    pnl_dollars: float
    cluster_low: float
    cluster_high: float
    cluster_size: int
    regime: str         # "flat" → breakout-routed, "directional" → fade-routed


def in_trade_window(ts_ny: pd.Series) -> pd.Series:
    h = ts_ny.dt.hour
    m = ts_ny.dt.minute
    after_start = (h > TRADE_OPEN_HM[0]) | ((h == TRADE_OPEN_HM[0]) & (m >= TRADE_OPEN_HM[1]))
    before_end = (h < TRADE_CLOSE_HM[0]) | ((h == TRADE_CLOSE_HM[0]) & (m < TRADE_CLOSE_HM[1]))
    return after_start & before_end


def classify_setups(clusters_today: list[Cluster], reference_price: float,
                    open_946: float | None, atr_10: float | None) -> list[Setup]:
    """Per-cluster regime classification + side routing.

    For each cluster:
      - cluster ABOVE ref → limit at cluster.low, trigger when price RISES into it
      - cluster BELOW ref → limit at cluster.high, trigger when price FALLS into it
      - cluster spans ref → SKIP

    Then compute expected_normalized_distance = (limit - open_946) / atr_10:
      - flat (|d| <= threshold) → REVERSE direction (breakout)
      - directional (|d| > threshold) → fade direction (original)
      - UNLABELED (no open_946 or atr_10) → fade default
    """
    setups = []
    for c in clusters_today:
        if c.low > reference_price:
            limit_price = c.low
            trigger_above = True
            fade_side = "sell"
        elif c.high < reference_price:
            limit_price = c.high
            trigger_above = False
            fade_side = "buy"
        else:
            continue  # cluster spans reference -> skip

        if open_946 is None or atr_10 is None or pd.isna(open_946) or pd.isna(atr_10):
            side = fade_side
            regime = "UNLABELED"
        else:
            expected_norm_dist = (limit_price - open_946) / atr_10
            if abs(expected_norm_dist) <= HYBRID_FLAT_THRESHOLD:
                side = "buy" if fade_side == "sell" else "sell"
                regime = "flat"
            else:
                side = fade_side
                regime = "directional"

        setups.append(Setup(side=side, cluster=c, limit_price=limit_price,
                            trigger_above=trigger_above, regime=regime))
    return setups


def find_first_fill(setups: list[Setup], bar: dict) -> Setup | None:
    """Trigger keyed on cluster position (trigger_above), not trade side."""
    candidates = []
    for s in setups:
        if s.triggered:
            continue
        if s.trigger_above and bar["high"] >= s.limit_price:
            candidates.append(s)
        elif (not s.trigger_above) and bar["low"] <= s.limit_price:
            candidates.append(s)
    if not candidates:
        return None
    return min(candidates, key=lambda s: abs(s.limit_price - bar["open"]))


def check_exit(side: str, entry_price: float, bar: dict) -> tuple[str, float] | None:
    if side == "buy":
        stop = entry_price - STOP_POINTS
        target = entry_price + TARGET_POINTS
        stop_hit = bar["low"] <= stop
        target_hit = bar["high"] >= target
    else:
        stop = entry_price + STOP_POINTS
        target = entry_price - TARGET_POINTS
        stop_hit = bar["high"] >= stop
        target_hit = bar["low"] <= target
    if stop_hit:
        return ("stop", stop)
    if target_hit:
        return ("target", target)
    return None


def pnl_points(side: str, entry: float, exit_: float) -> float:
    return (exit_ - entry) if side == "buy" else (entry - exit_)


def make_trade(session_date, contract, open_pos, exit_time, exit_price, exit_reason) -> Trade:
    pts = pnl_points(open_pos["side"], open_pos["entry_price"], exit_price)
    return Trade(
        session_date=session_date,
        contract=contract,
        side=open_pos["side"],
        entry_time=open_pos["entry_time"],
        entry_price=open_pos["entry_price"],
        exit_time=exit_time,
        exit_price=exit_price,
        exit_reason=exit_reason,
        pnl_points=pts,
        pnl_dollars=pts * POINT_VALUE_USD,
        cluster_low=open_pos["cluster"].low,
        cluster_high=open_pos["cluster"].high,
        cluster_size=open_pos["cluster"].size,
        regime=open_pos["regime"],
    )


def find_force_close_bar(bars_today: pd.DataFrame) -> dict | None:
    match = bars_today[
        (bars_today["ts_ny"].dt.hour == FORCE_CLOSE_HM[0])
        & (bars_today["ts_ny"].dt.minute == FORCE_CLOSE_HM[1])
    ]
    if not match.empty:
        return match.iloc[0].to_dict()
    return None


def simulate_session(bars_today, setups, session_date) -> list[Trade]:
    trades: list[Trade] = []
    if not setups:
        return trades

    contract = bars_today["contract"].iloc[0]
    in_window = bars_today[in_trade_window(bars_today["ts_ny"])]
    bar_records = in_window.to_dict("records")
    open_pos = None

    for bar in bar_records:
        if open_pos is None:
            fill = find_first_fill(setups, bar)
            if fill is not None:
                fill.triggered = True
                open_pos = {
                    "side": fill.side,
                    "entry_price": fill.limit_price,
                    "entry_time": bar["ts_utc"],
                    "cluster": fill.cluster,
                    "regime": fill.regime,
                }
                exit_result = check_exit(open_pos["side"], open_pos["entry_price"], bar)
                if exit_result is not None:
                    reason, exit_price = exit_result
                    trades.append(make_trade(session_date, contract, open_pos,
                                             bar["ts_utc"], exit_price, reason))
                    open_pos = None
        else:
            exit_result = check_exit(open_pos["side"], open_pos["entry_price"], bar)
            if exit_result is not None:
                reason, exit_price = exit_result
                trades.append(make_trade(session_date, contract, open_pos,
                                         bar["ts_utc"], exit_price, reason))
                open_pos = None

    if open_pos is not None:
        fc_bar = find_force_close_bar(bars_today)
        if fc_bar is not None:
            exit_price = float(fc_bar["open"])
            exit_time = fc_bar["ts_utc"]
        else:
            last = bar_records[-1]
            exit_price = float(last["close"])
            exit_time = last["ts_utc"]
        trades.append(make_trade(session_date, contract, open_pos,
                                 exit_time, exit_price, "force_close"))

    return trades


def compute_session_features(bars: pd.DataFrame) -> tuple[dict, dict]:
    """Per-session 9:46 NY bar open + lagged ATR-N (no look-ahead)."""
    nine46 = bars[(bars["ts_ny"].dt.hour == TRADE_OPEN_HM[0])
                  & (bars["ts_ny"].dt.minute == TRADE_OPEN_HM[1])]
    open_946_per = nine46.groupby("session_date")["open"].first().to_dict()

    bs = bars.sort_values("ts_utc")
    daily = (bs.groupby("session_date", as_index=False)
                .agg(sess_high=("high","max"),
                     sess_low=("low","min"),
                     sess_close=("close","last"))
                .sort_values("session_date").reset_index(drop=True))
    prev = daily["sess_close"].shift(1)
    daily["TR"] = pd.concat([
        daily["sess_high"] - daily["sess_low"],
        (daily["sess_high"] - prev).abs(),
        (daily["sess_low"]  - prev).abs(),
    ], axis=1).max(axis=1)
    # Lagged ATR: prior N TRs only — known before the session opens
    daily[f"ATR_{ATR_LOOKBACK}"] = daily["TR"].shift(1).rolling(ATR_LOOKBACK).mean()
    atr_per = dict(zip(daily["session_date"], daily[f"ATR_{ATR_LOOKBACK}"]))
    return open_946_per, atr_per


def run_backtest(bars: pd.DataFrame, orb_table: pd.DataFrame) -> list[Trade]:
    bars_by_session = {sd: g for sd, g in bars.groupby("session_date", sort=True)}
    orb_table = orb_table.sort_values("session_date").reset_index(drop=True)
    open_946_per, atr_per = compute_session_features(bars)

    level_pool: deque = deque(maxlen=LOOKBACK)
    all_trades: list[Trade] = []

    for _, orb_row in orb_table.iterrows():
        session_date = orb_row["session_date"]
        if session_date not in bars_by_session:
            continue

        levels = []
        for hist_high, hist_low in level_pool:
            levels.append(hist_high)
            levels.append(hist_low)
        levels.append(orb_row["orb_high"])
        levels.append(orb_row["orb_low"])

        clusters_today = find_clusters(levels, max_gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE)
        setups = classify_setups(
            clusters_today, float(orb_row["orb_close"]),
            open_946_per.get(session_date),
            atr_per.get(session_date),
        )

        bars_today = bars_by_session[session_date]
        trades = simulate_session(bars_today, setups, session_date)
        all_trades.extend(trades)

        level_pool.append((float(orb_row["orb_high"]), float(orb_row["orb_low"])))

    return all_trades


def main() -> None:
    ensure_dirs()
    print(f"Loading {BARS_PARQUET.name} and {ORB_TABLE_PARQUET.name}...")
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions")
    print(f"  Hybrid flat threshold: |normalized_distance| <= {HYBRID_FLAT_THRESHOLD}")

    print("Running hybrid simulation...")
    trades = run_backtest(bars, orb_table)
    print(f"  {len(trades)} trades")
    if not trades:
        print("No trades produced.")
        return

    df = pd.DataFrame([asdict(t) for t in trades])
    df.to_parquet(TRADES_PARQUET, index=False)
    print(f"Wrote {TRADES_PARQUET.name}")

    wins = (df["pnl_points"] > 0).sum()
    losses = (df["pnl_points"] < 0).sum()
    flat_pnl = (df["pnl_points"] == 0).sum()
    total_pts = df["pnl_points"].sum()
    print(f"  Wins / Losses / Flat: {wins} / {losses} / {flat_pnl}")
    print(f"  Win rate: {wins / len(df) * 100:.1f}%")
    print(f"  Total P&L: {total_pts:.2f} pts (${total_pts * POINT_VALUE_USD:,.2f})")
    print("  Exit reasons:")
    for reason, n in df["exit_reason"].value_counts().items():
        print(f"    {reason}: {n}")
    print("  Routed by regime:")
    for r, sub in df.groupby("regime"):
        print(f"    {r}: {len(sub)} trades, P&L ${sub['pnl_dollars'].sum():,.2f}")


if __name__ == "__main__":
    main()
