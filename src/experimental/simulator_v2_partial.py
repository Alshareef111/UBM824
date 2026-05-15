"""V2 simulator + partial exit + runner-BE.

Fork of simulator_v2.py adding:
- 2-contract sizing (p1, p2) per entry
- p1: fixed target +TARGET_P1_POINTS
- p2: target = nearest cluster level in trade direction (entry cluster excluded)
- Initial stop STOP_POINTS for both contracts (configurable per variant)
- Runner-BE rule: when p1 exits at +TARGET_P1 on bar X, p2's stop moves from
  STOP_POINTS to entry price, effective from bar X+1 onward.
- If p1 force-closes at 11:30 (no +TARGET_P1 hit), both legs force-close together.
- If both contracts hit initial stop before p1 reaches +TARGET_P1, full position stops out.
- If no cluster exists in trade direction at session open, p2 has no price target.

Locked geometry preserved: 3-pt cluster gap, MIN_SIZE 3, lookback 200,
first-touch entry, C2 one-position-at-a-time, 9:46-11:30 NY trading window,
force-close at 11:30 bar OPEN, stop-first conservative per leg.

Same-bar precedence per existing D-005 stop-first conservative, applied
INDEPENDENTLY per leg. Both legs can exit on the same bar at different
reasons. If a bar covers stop AND target for a given leg, that leg stops.

Entry cluster always excluded from runner-target candidates (both FADE and
TREND inversions). Runner target = nearest OTHER cluster in trade direction.

Does NOT modify simulator_v2.py or any other existing file. Uses the same
clusters / classifiers / paths / walk_forward modules read-only.
"""
from __future__ import annotations

import sys
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

# Path setup so this file can be invoked from project root: `python3 src/experimental/...`
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from clusters import Cluster, find_clusters  # noqa: E402
from indicators.base import Classifier, Label  # noqa: E402

LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
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
class PartialTrade:
    session_date: pd.Timestamp
    contract: str
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    cluster_low: float
    cluster_high: float
    cluster_size: int
    cluster_label: str

    p2_target_price: Optional[float]
    p2_target_cluster_low: Optional[float]
    p2_target_cluster_high: Optional[float]

    p1_exit_time: pd.Timestamp
    p1_exit_price: float
    p1_exit_reason: str
    p1_pnl_points: float
    p1_pnl_dollars: float

    p2_exit_time: pd.Timestamp
    p2_exit_price: float
    p2_exit_reason: str
    p2_pnl_points: float
    p2_pnl_dollars: float

    runner_be_fired: bool
    p2_initial_stop_points: float
    p2_final_stop_price: float
    p2_stop_history: str

    pnl_points: float          # p1 + p2 (per-contract sum)
    pnl_dollars: float         # p1_pnl_dollars + p2_pnl_dollars (2-contract aggregate)
    initial_stop_points: float


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


def find_runner_target(
    clusters_today: list[Cluster],
    entry_cluster: Cluster,
    entry_price: float,
    side: str,
) -> tuple[Optional[float], Optional[Cluster]]:
    """Nearest cluster in trade direction, excluding entry cluster.

    BUY: cluster with cluster.low > entry_price (sits above entry). Target = cluster.low.
    SELL: cluster with cluster.high < entry_price (sits below entry). Target = cluster.high.

    Entry cluster is excluded by identity (Python object identity — same dataclass
    instance from the find_clusters output). Returns (target_price, cluster) or
    (None, None) if no cluster qualifies.
    """
    best_dist = None
    best_target = None
    best_cluster = None
    if side == "buy":
        for c in clusters_today:
            if c is entry_cluster:
                continue
            if c.low > entry_price:
                d = c.low - entry_price
                if best_dist is None or d < best_dist:
                    best_dist = d
                    best_target = c.low
                    best_cluster = c
    else:
        for c in clusters_today:
            if c is entry_cluster:
                continue
            if c.high < entry_price:
                d = entry_price - c.high
                if best_dist is None or d < best_dist:
                    best_dist = d
                    best_target = c.high
                    best_cluster = c
    return best_target, best_cluster


def check_leg_exit(
    side: str,
    entry_price: float,
    bar: dict,
    stop_points: float,
    target_price: Optional[float],
) -> Optional[tuple[str, float]]:
    """Stop-first conservative for one leg.

    target_price is the explicit absolute price level (NOT a points offset),
    because p2's target may be cluster-derived. For p1, callers compute
    target_price = entry +/- TARGET_P1_POINTS.

    Returns (reason, exit_price) or None if no exit on this bar. Reason is
    one of: "stop", "target" (caller relabels as target_40 / target_cluster
    via the leg-specific exit annotation in simulate_session).
    """
    if side == "buy":
        stop = entry_price - stop_points
        stop_hit = bar["low"] <= stop
        target_hit = (target_price is not None) and bar["high"] >= target_price
    else:
        stop = entry_price + stop_points
        stop_hit = bar["high"] >= stop
        target_hit = (target_price is not None) and bar["low"] <= target_price
    if stop_hit:
        return ("stop", stop)
    if target_hit:
        return ("target", target_price)
    return None


def pnl_points_calc(side: str, entry: float, exit_: float) -> float:
    return (exit_ - entry) if side == "buy" else (entry - exit_)


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
    session_date: pd.Timestamp,
    classifier: Classifier,
    clusters_today: list[Cluster],
    stop_points: float,
    target_p1_points: float,
) -> list[PartialTrade]:
    trades: list[PartialTrade] = []
    if not setups:
        return trades

    contract = bars_today["contract"].iloc[0]
    in_window = bars_today[in_trade_window(bars_today["ts_ny"])]
    bar_records = in_window.to_dict("records")

    open_pos: Optional[dict] = None

    for i, bar in enumerate(bar_records):
        if open_pos is None:
            candidate = find_first_fill(setups, bar)
            if candidate is not None:
                label = classifier(candidate.cluster, bar, bars_today)
                if label == Label.SKIP:
                    candidate.triggered = True
                    continue
                side = candidate.fade_side if label == Label.FADE else (
                    "buy" if candidate.fade_side == "sell" else "sell"
                )
                candidate.triggered = True
                entry_price = candidate.limit_price
                p2_target_price, p2_target_cluster = find_runner_target(
                    clusters_today, candidate.cluster, entry_price, side
                )
                if side == "buy":
                    p1_target_price = entry_price + target_p1_points
                else:
                    p1_target_price = entry_price - target_p1_points
                open_pos = {
                    "side": side,
                    "entry_price": entry_price,
                    "entry_time": bar["ts_utc"],
                    "entry_bar_idx": i,
                    "cluster": candidate.cluster,
                    "cluster_label": label.value,
                    "p1_target_price": p1_target_price,
                    "p2_target_price": p2_target_price,
                    "p2_target_cluster": p2_target_cluster,
                    "p1_exit": None,        # set when p1 closes
                    "p2_exit": None,        # set when p2 closes
                    "p2_be_fired": False,
                    "p2_be_effective_from_idx": None,  # bar idx from which BE-stop applies
                }

                # Evaluate entry-bar exits independently per leg, stop-first conservative.
                exit_p1 = check_leg_exit(
                    side, entry_price, bar, stop_points, open_pos["p1_target_price"]
                )
                if exit_p1 is not None:
                    reason, px = exit_p1
                    open_pos["p1_exit"] = {
                        "time": bar["ts_utc"], "price": px,
                        "reason": "stop" if reason == "stop" else "target_40",
                        "bar_idx": i,
                    }
                exit_p2 = check_leg_exit(
                    side, entry_price, bar, stop_points, open_pos["p2_target_price"]
                )
                if exit_p2 is not None:
                    reason, px = exit_p2
                    open_pos["p2_exit"] = {
                        "time": bar["ts_utc"], "price": px,
                        "reason": "stop" if reason == "stop" else "target_cluster",
                        "bar_idx": i,
                        "stop_at_exit": entry_price - stop_points if side == "buy" else entry_price + stop_points,
                    }

                # If p1 hit +target on entry bar, BE engages from next bar.
                if (open_pos["p1_exit"] is not None
                        and open_pos["p1_exit"]["reason"] == "target_40"):
                    open_pos["p2_be_fired"] = True
                    open_pos["p2_be_effective_from_idx"] = i + 1

                # If both legs closed on entry bar, finalize.
                if open_pos["p1_exit"] is not None and open_pos["p2_exit"] is not None:
                    trades.append(_finalize(open_pos, session_date, contract, stop_points))
                    open_pos = None

        else:
            # Determine current p2 stop level for this bar
            if (open_pos["p2_be_fired"]
                    and open_pos["p2_be_effective_from_idx"] is not None
                    and i >= open_pos["p2_be_effective_from_idx"]):
                p2_stop_pts = 0.0  # BE: stop at entry price
            else:
                p2_stop_pts = stop_points

            side = open_pos["side"]
            entry_price = open_pos["entry_price"]

            # Evaluate p1 if still open
            if open_pos["p1_exit"] is None:
                exit_p1 = check_leg_exit(
                    side, entry_price, bar, stop_points, open_pos["p1_target_price"]
                )
                if exit_p1 is not None:
                    reason, px = exit_p1
                    open_pos["p1_exit"] = {
                        "time": bar["ts_utc"], "price": px,
                        "reason": "stop" if reason == "stop" else "target_40",
                        "bar_idx": i,
                    }
                    if reason == "target":
                        open_pos["p2_be_fired"] = True
                        open_pos["p2_be_effective_from_idx"] = i + 1

            # Evaluate p2 if still open
            if open_pos["p2_exit"] is None:
                exit_p2 = check_leg_exit(
                    side, entry_price, bar, p2_stop_pts, open_pos["p2_target_price"]
                )
                if exit_p2 is not None:
                    reason, px = exit_p2
                    if reason == "stop":
                        p2_reason = "stop_be" if p2_stop_pts == 0.0 else "stop"
                    else:
                        p2_reason = "target_cluster"
                    open_pos["p2_exit"] = {
                        "time": bar["ts_utc"], "price": px,
                        "reason": p2_reason,
                        "bar_idx": i,
                        "stop_at_exit": (
                            entry_price if p2_stop_pts == 0.0 else (
                                entry_price - stop_points if side == "buy" else entry_price + stop_points
                            )
                        ),
                    }

            if open_pos["p1_exit"] is not None and open_pos["p2_exit"] is not None:
                trades.append(_finalize(open_pos, session_date, contract, stop_points))
                open_pos = None

    # End of trading window: handle force-close
    if open_pos is not None:
        fc_bar = find_force_close_bar(bars_today)
        if fc_bar is not None:
            fc_price = float(fc_bar["open"])
            fc_time = fc_bar["ts_utc"]
        else:
            # Fallback: use last bar's close (shouldn't normally happen)
            last = bar_records[-1]
            fc_price = float(last["close"])
            fc_time = last["ts_utc"]

        side = open_pos["side"]
        entry_price = open_pos["entry_price"]

        if open_pos["p1_exit"] is None:
            # p1 never hit +40. Per spec: p1 force-closes; p2 also force-closes; no BE state.
            open_pos["p2_be_fired"] = False
            open_pos["p1_exit"] = {
                "time": fc_time, "price": fc_price,
                "reason": "force_close", "bar_idx": -1,
            }
            open_pos["p2_exit"] = {
                "time": fc_time, "price": fc_price,
                "reason": "force_close", "bar_idx": -1,
                "stop_at_exit": entry_price - stop_points if side == "buy" else entry_price + stop_points,
            }
        else:
            # p1 already exited at +40 earlier. p2 still open. Force-close p2.
            assert open_pos["p2_exit"] is None
            p2_stop_at_close = entry_price if open_pos["p2_be_fired"] else (
                entry_price - stop_points if side == "buy" else entry_price + stop_points
            )
            open_pos["p2_exit"] = {
                "time": fc_time, "price": fc_price,
                "reason": "force_close", "bar_idx": -1,
                "stop_at_exit": p2_stop_at_close,
            }

        trades.append(_finalize(open_pos, session_date, contract, stop_points))
        open_pos = None

    return trades


def _finalize(
    open_pos: dict,
    session_date: pd.Timestamp,
    contract: str,
    stop_points: float,
) -> PartialTrade:
    side = open_pos["side"]
    entry_price = open_pos["entry_price"]
    p1 = open_pos["p1_exit"]
    p2 = open_pos["p2_exit"]

    p1_pts = pnl_points_calc(side, entry_price, p1["price"])
    p2_pts = pnl_points_calc(side, entry_price, p2["price"])

    if open_pos["p2_be_fired"]:
        eff_idx = open_pos["p2_be_effective_from_idx"]
        stop_history = (
            f"init -{stop_points:g} (1c risk) -> BE @ entry from bar idx {eff_idx} "
            f"(p1 target_40 @ idx {open_pos['p1_exit']['bar_idx']})"
        )
    else:
        stop_history = f"init -{stop_points:g} (never moved; p1 ended {p1['reason']})"

    p2_tgt_c = open_pos["p2_target_cluster"]
    return PartialTrade(
        session_date=session_date,
        contract=contract,
        side=side,
        entry_time=open_pos["entry_time"],
        entry_price=entry_price,
        cluster_low=open_pos["cluster"].low,
        cluster_high=open_pos["cluster"].high,
        cluster_size=open_pos["cluster"].size,
        cluster_label=open_pos["cluster_label"],
        p2_target_price=open_pos["p2_target_price"],
        p2_target_cluster_low=p2_tgt_c.low if p2_tgt_c is not None else None,
        p2_target_cluster_high=p2_tgt_c.high if p2_tgt_c is not None else None,
        p1_exit_time=p1["time"],
        p1_exit_price=p1["price"],
        p1_exit_reason=p1["reason"],
        p1_pnl_points=p1_pts,
        p1_pnl_dollars=p1_pts * POINT_VALUE_USD,
        p2_exit_time=p2["time"],
        p2_exit_price=p2["price"],
        p2_exit_reason=p2["reason"],
        p2_pnl_points=p2_pts,
        p2_pnl_dollars=p2_pts * POINT_VALUE_USD,
        runner_be_fired=open_pos["p2_be_fired"],
        p2_initial_stop_points=stop_points,
        p2_final_stop_price=p2["stop_at_exit"],
        p2_stop_history=stop_history,
        pnl_points=p1_pts + p2_pts,
        pnl_dollars=(p1_pts + p2_pts) * POINT_VALUE_USD,
        initial_stop_points=stop_points,
    )


def run_backtest(
    bars: pd.DataFrame,
    orb_table: pd.DataFrame,
    classifier: Classifier,
    stop_points: float,
    target_p1_points: float,
) -> list[PartialTrade]:
    bars_by_session = {sd: g for sd, g in bars.groupby("session_date", sort=True)}
    orb_table = orb_table.sort_values("session_date").reset_index(drop=True)

    level_pool: deque = deque(maxlen=LOOKBACK)
    all_trades: list[PartialTrade] = []

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
        trades = simulate_session(
            bars_today, setups, session_date, classifier,
            clusters_today, stop_points, target_p1_points,
        )
        all_trades.extend(trades)

        level_pool.append((float(orb_row["orb_high"]), float(orb_row["orb_low"])))

    return all_trades


def trades_to_dataframe(trades: list[PartialTrade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([asdict(t) for t in trades])
