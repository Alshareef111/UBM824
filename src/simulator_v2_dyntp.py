"""V2 simulator — dynamic take-profit variant.

Take-profit is set at entry as the nearest cluster boundary in the trade
direction, regardless of whether that cluster has been touched earlier in
the session. If no cluster exists in the trade direction, fall back to a
fixed 30-pt TP.

Stop loss stays at 30 pts fixed. All other locked-baseline geometry
preserved: 3-pt clusters, first-touch entry, C2 one-position-at-a-time,
9:46-11:30 NY trading window, force-close at 11:30 bar OPEN.

"Trade direction" = direction the position needs price to move to profit
(up for BUY, down for SELL). The trade direction is determined by the
final side (after the classifier's FADE/TREND decision), NOT by the
cluster's above/below-close classification.

"Nearest cluster" — for BUY trades, the smallest cluster.low > entry_price.
For SELL trades, the largest cluster.high < entry_price. Strict inequality
excludes the entry cluster itself.

Output dataframe adds: target_price, target_source ("cluster" or "fallback"),
tp_distance_pts (|target_price - entry_price|).
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

from clusters import Cluster, find_clusters
from indicators.base import Classifier, Label
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs

# Locked-baseline constants (preserved)
LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
STOP_POINTS = 30.0
FALLBACK_TARGET_POINTS = 30.0  # used when no cluster exists in trade direction
POINT_VALUE_USD = 2.0

TRADE_OPEN_HM = (9, 46)
TRADE_CLOSE_HM = (11, 30)
FORCE_CLOSE_HM = (11, 30)


@dataclass
class Setup:
    fade_side: str
    cluster: Cluster
    limit_price: float
    trigger_above: bool
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
    exit_reason: str            # "stop" | "target" | "force_close"
    pnl_points: float
    pnl_dollars: float
    cluster_low: float
    cluster_high: float
    cluster_size: int
    cluster_label: str          # "FADE" or "TREND"
    target_price: float         # actual TP price set at entry
    target_source: str          # "cluster" or "fallback"
    tp_distance_pts: float      # |target_price - entry_price|


def in_trade_window(ts_ny: pd.Series) -> pd.Series:
    h = ts_ny.dt.hour
    m = ts_ny.dt.minute
    after_start = (h > TRADE_OPEN_HM[0]) | ((h == TRADE_OPEN_HM[0]) & (m >= TRADE_OPEN_HM[1]))
    before_end = (h < TRADE_CLOSE_HM[0]) | ((h == TRADE_CLOSE_HM[0]) & (m < TRADE_CLOSE_HM[1]))
    return after_start & before_end


def classify_setups(clusters_today: list[Cluster], reference_price: float) -> list[Setup]:
    setups: list[Setup] = []
    for c in clusters_today:
        if c.low > reference_price:
            setups.append(Setup(fade_side="sell", cluster=c, limit_price=c.low, trigger_above=True))
        elif c.high < reference_price:
            setups.append(Setup(fade_side="buy", cluster=c, limit_price=c.high, trigger_above=False))
    return setups


def find_first_fill(setups: list[Setup], bar: dict) -> Optional[Setup]:
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


def find_nearest_cluster_target(
    side: str, entry_price: float, clusters_today: list[Cluster],
    fallback_pts: float = FALLBACK_TARGET_POINTS,
) -> tuple[float, str]:
    """TP price = nearest cluster boundary in trade direction; else fallback."""
    if side == "buy":
        # trade direction = UP. Want smallest cluster.low strictly above entry.
        candidates = [c.low for c in clusters_today if c.low > entry_price]
        if candidates:
            return float(min(candidates)), "cluster"
        return float(entry_price + fallback_pts), "fallback"
    else:  # sell
        # trade direction = DOWN. Want largest cluster.high strictly below entry.
        candidates = [c.high for c in clusters_today if c.high < entry_price]
        if candidates:
            return float(max(candidates)), "cluster"
        return float(entry_price - fallback_pts), "fallback"


def check_exit_dynamic(side: str, entry_price: float, target_price: float, bar: dict) -> Optional[tuple[str, float]]:
    """Stop is fixed at entry ± STOP_POINTS. Target is the position's individual target_price.
    Stop-first conservative on same-bar stop+target.
    """
    if side == "buy":
        stop = entry_price - STOP_POINTS
        stop_hit = bar["low"] <= stop
        target_hit = bar["high"] >= target_price
    else:  # sell
        stop = entry_price + STOP_POINTS
        stop_hit = bar["high"] >= stop
        target_hit = bar["low"] <= target_price
    if stop_hit:
        return ("stop", stop)
    if target_hit:
        return ("target", target_price)
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
        cluster_label=open_pos["cluster_label"],
        target_price=open_pos["target_price"],
        target_source=open_pos["target_source"],
        tp_distance_pts=abs(open_pos["target_price"] - open_pos["entry_price"]),
    )


def find_force_close_bar(bars_today: pd.DataFrame) -> Optional[dict]:
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
    clusters_today: list[Cluster],
    session_date: pd.Timestamp,
    classifier: Classifier,
) -> list[Trade]:
    trades: list[Trade] = []
    if not setups:
        return trades

    contract = bars_today["contract"].iloc[0]
    in_window = bars_today[in_trade_window(bars_today["ts_ny"])]
    bar_records = in_window.to_dict("records")

    open_pos = None
    for bar in bar_records:
        if open_pos is None:
            candidate = find_first_fill(setups, bar)
            if candidate is not None:
                label = classifier(candidate.cluster, bar, bars_today)
                if label == Label.SKIP:
                    candidate.triggered = True
                    continue
                if label == Label.FADE:
                    side = candidate.fade_side
                else:  # TREND
                    side = "buy" if candidate.fade_side == "sell" else "sell"
                candidate.triggered = True

                entry_price = candidate.limit_price
                # Dynamic TP from cluster pool (touched/untouched both eligible)
                target_price, target_source = find_nearest_cluster_target(side, entry_price, clusters_today)

                open_pos = {
                    "side": side,
                    "entry_price": entry_price,
                    "entry_time": bar["ts_utc"],
                    "cluster": candidate.cluster,
                    "cluster_label": label.value,
                    "target_price": target_price,
                    "target_source": target_source,
                }
                exit_result = check_exit_dynamic(side, entry_price, target_price, bar)
                if exit_result is not None:
                    reason, exit_price = exit_result
                    trades.append(make_trade(session_date, contract, open_pos,
                                             bar["ts_utc"], exit_price, reason))
                    open_pos = None
        else:
            exit_result = check_exit_dynamic(
                open_pos["side"], open_pos["entry_price"], open_pos["target_price"], bar,
            )
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


def run_backtest(bars: pd.DataFrame, orb_table: pd.DataFrame, classifier: Classifier) -> list[Trade]:
    bars_by_session = {sd: g for sd, g in bars.groupby("session_date", sort=True)}
    orb_table = orb_table.sort_values("session_date").reset_index(drop=True)
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
        setups = classify_setups(clusters_today, float(orb_row["orb_close"]))

        bars_today = bars_by_session[session_date]
        trades = simulate_session(bars_today, setups, clusters_today, session_date, classifier)
        all_trades.extend(trades)
        level_pool.append((float(orb_row["orb_high"]), float(orb_row["orb_low"])))

    return all_trades


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([asdict(t) for t in trades])
