"""Trade simulator for the MNQ ORB-cluster mean-reversion strategy.

One position at a time (C2). At 9:45 NY each session: build the level pool
(last 200 days' ORB highs/lows + today's), find clusters, classify each as a
sell-above / buy-below / skip-spanning setup vs the 9:45 close, place resting
limits. During 9:46-11:29: walk bars; while no position is open, the closest-
to-open eligible limit fills first. Once a position is open, other limits are
ignored until exit. Stop-first conservative on same-bar stop+target. Any
position still open at end of bar 11:29 is force-closed at the 11:30 bar open.
"""

from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from clusters import Cluster, find_clusters

from paths import BARS_PARQUET, ORB_TABLE_PARQUET, ARCHIVE_DIR, ensure_dirs

TRADES_PARQUET = ARCHIVE_DIR / "trades_priors_only_20260511.parquet"

LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
STOP_POINTS = 30.0
TARGET_POINTS = 30.0
POINT_VALUE_USD = 2.0  # MNQ = $2 per point

TRADE_OPEN_HM = (9, 46)    # inclusive
TRADE_CLOSE_HM = (11, 30)  # exclusive — force-close at this bar's open
FORCE_CLOSE_HM = (11, 30)


@dataclass
class Setup:
    side: str  # "buy" or "sell"
    cluster: Cluster
    limit_price: float
    triggered: bool = False  # rule 11: one trade per cluster per day


@dataclass
class Trade:
    session_date: pd.Timestamp
    contract: str
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str  # "stop" | "target" | "force_close"
    pnl_points: float
    pnl_dollars: float
    cluster_low: float
    cluster_high: float
    cluster_size: int


def in_trade_window(ts_ny: pd.Series) -> pd.Series:
    h = ts_ny.dt.hour
    m = ts_ny.dt.minute
    after_start = (h > TRADE_OPEN_HM[0]) | ((h == TRADE_OPEN_HM[0]) & (m >= TRADE_OPEN_HM[1]))
    before_end = (h < TRADE_CLOSE_HM[0]) | ((h == TRADE_CLOSE_HM[0]) & (m < TRADE_CLOSE_HM[1]))
    return after_start & before_end


def classify_setups(clusters_today: list[Cluster], reference_price: float) -> list[Setup]:
    # First-touch entry: enter at the near side of the cluster zone,
    # anticipating reversion off the first level encountered.
    setups = []
    for c in clusters_today:
        if c.low > reference_price:
            setups.append(Setup(side="sell", cluster=c, limit_price=c.low))
        elif c.high < reference_price:
            setups.append(Setup(side="buy", cluster=c, limit_price=c.high))
        # cluster spans reference -> skip
    return setups


def find_first_fill(setups: list[Setup], bar: dict) -> Setup | None:
    """Among limits that would fill in this bar, pick the one whose price is
    closest to the bar open (closer-to-open tiebreaker for one-position-at-a-time).
    """
    candidates = []
    for s in setups:
        if s.triggered:
            continue
        if s.side == "sell" and bar["high"] >= s.limit_price:
            candidates.append(s)
        elif s.side == "buy" and bar["low"] <= s.limit_price:
            candidates.append(s)
    if not candidates:
        return None
    return min(candidates, key=lambda s: abs(s.limit_price - bar["open"]))


def check_exit(side: str, entry_price: float, bar: dict) -> tuple[str, float] | None:
    """Stop-first conservative if both stop and target lie inside the bar."""
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
    )


def find_force_close_bar(bars_today: pd.DataFrame) -> dict | None:
    match = bars_today[
        (bars_today["ts_ny"].dt.hour == FORCE_CLOSE_HM[0])
        & (bars_today["ts_ny"].dt.minute == FORCE_CLOSE_HM[1])
    ]
    if not match.empty:
        return match.iloc[0].to_dict()
    return None


def simulate_session(
    bars_today: pd.DataFrame,
    setups: list[Setup],
    session_date: pd.Timestamp,
) -> list[Trade]:
    trades: list[Trade] = []
    if not setups:
        return trades

    contract = bars_today["contract"].iloc[0]

    in_window = bars_today[in_trade_window(bars_today["ts_ny"])]
    bar_records = in_window.to_dict("records")

    open_pos = None  # active position dict when engine is locked

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
                }
                # Same-bar stop/target check on the entry bar
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
            # Fallback: no 11:30 bar available — use close of last bar in window.
            last = bar_records[-1]
            exit_price = float(last["close"])
            exit_time = last["ts_utc"]
        trades.append(make_trade(session_date, contract, open_pos,
                                 exit_time, exit_price, "force_close"))

    return trades


def run_backtest(bars: pd.DataFrame, orb_table: pd.DataFrame) -> list[Trade]:
    bars_by_session = {sd: g for sd, g in bars.groupby("session_date", sort=True)}
    orb_table = orb_table.sort_values("session_date").reset_index(drop=True)

    level_pool: deque = deque(maxlen=LOOKBACK)
    all_trades: list[Trade] = []

    for _, orb_row in orb_table.iterrows():
        session_date = orb_row["session_date"]
        if session_date not in bars_by_session:
            continue

        # Today's level pool: 200 historical (high, low) pairs flattened, plus today's two
        levels = []
        for hist_high, hist_low in level_pool:
            levels.append(hist_high)
            levels.append(hist_low)

        clusters_today = find_clusters(levels, max_gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE)
        setups = classify_setups(clusters_today, float(orb_row["orb_close"]))

        bars_today = bars_by_session[session_date]
        trades = simulate_session(bars_today, setups, session_date)
        all_trades.extend(trades)

        # Append today's ORB AFTER simulating, so it becomes part of tomorrow's history.
        level_pool.append((float(orb_row["orb_high"]), float(orb_row["orb_low"])))

    return all_trades


def main() -> None:
    ensure_dirs()
    print(f"Loading {BARS_PARQUET.name} and {ORB_TABLE_PARQUET.name}...")
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions")

    print("Running simulation...")
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
    flat = (df["pnl_points"] == 0).sum()
    total_pts = df["pnl_points"].sum()
    print(f"  Wins / Losses / Flat: {wins} / {losses} / {flat}")
    print(f"  Win rate: {wins / len(df) * 100:.1f}%")
    print(f"  Total P&L: {total_pts:.2f} pts (${total_pts * POINT_VALUE_USD:,.2f})")
    print("  Exit reasons:")
    for reason, n in df["exit_reason"].value_counts().items():
        print(f"    {reason}: {n}")


if __name__ == "__main__":
    main()
