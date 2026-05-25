"""V2 simulator — 40/40 R:R variant (fork of simulator_v2.py).

Identical to simulator_v2 except STOP_POINTS and TARGET_POINTS are 40.0
(instead of the locked 30/30). The per-cluster classifier hook, fill
mechanics, force-close behavior, and trade dataclass are all unchanged.

Use this together with the R-012 deployment-winner classifier
(ADX(15,30) AND DI(15,8) unanimous) to evaluate whether the V2 regime
edge survives a wider bracket. R-008 already showed wider stops/targets
hurt the OLD hybrid classifier (-$3,216 / 1,600 trades over 7y); this
simulator is the V2 equivalent so the question can be answered head-on.

DO NOT use this fork as a drop-in replacement for the locked baseline —
the trades parquet it emits is NOT byte-equivalent to the locked
baseline by design.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

from clusters import Cluster, find_clusters
from indicators.base import AllFade, Classifier, Label
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs

LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
STOP_POINTS = 40.0
TARGET_POINTS = 40.0
POINT_VALUE_USD = 2.0

TRADE_OPEN_HM = (9, 46)
TRADE_CLOSE_HM = (11, 30)
FORCE_CLOSE_HM = (11, 30)

BASELINE_COLS = [
    "session_date", "contract", "side",
    "entry_time", "entry_price",
    "exit_time", "exit_price", "exit_reason",
    "pnl_points", "pnl_dollars",
    "cluster_low", "cluster_high", "cluster_size",
]


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
    exit_reason: str
    pnl_points: float
    pnl_dollars: float
    cluster_low: float
    cluster_high: float
    cluster_size: int
    cluster_label: str


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
            setups.append(Setup(
                fade_side="sell", cluster=c, limit_price=c.low, trigger_above=True,
            ))
        elif c.high < reference_price:
            setups.append(Setup(
                fade_side="buy", cluster=c, limit_price=c.high, trigger_above=False,
            ))
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


def check_exit(side: str, entry_price: float, bar: dict) -> Optional[tuple[str, float]]:
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
        cluster_label=open_pos["cluster_label"],
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
                else:
                    side = "buy" if candidate.fade_side == "sell" else "sell"
                candidate.triggered = True
                open_pos = {
                    "side": side,
                    "entry_price": candidate.limit_price,
                    "entry_time": bar["ts_utc"],
                    "cluster": candidate.cluster,
                    "cluster_label": label.value,
                }
                exit_result = check_exit(side, candidate.limit_price, bar)
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
        trades = simulate_session(bars_today, setups, session_date, classifier)
        all_trades.extend(trades)

        level_pool.append((float(orb_row["orb_high"]), float(orb_row["orb_low"])))

    return all_trades


def trades_to_dataframe(trades: list[Trade], baseline_only: bool = False) -> pd.DataFrame:
    if not trades:
        cols = BASELINE_COLS if baseline_only else BASELINE_COLS + ["cluster_label"]
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame([asdict(t) for t in trades])
    if baseline_only:
        df = df[BASELINE_COLS]
    return df


def main() -> None:
    ensure_dirs()
    print(f"Loading {BARS_PARQUET.name} and {ORB_TABLE_PARQUET.name}...")
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions")

    classifier = AllFade()
    print(f"Classifier: {classifier.name}  (STOP={STOP_POINTS}, TARGET={TARGET_POINTS})")
    print("Running v2 4040 simulation...")
    trades = run_backtest(bars, orb_table, classifier)
    print(f"  {len(trades)} trades")
    if not trades:
        return
    df = trades_to_dataframe(trades)
    out_path = ARCHIVE_DIR / "trades_v2_4040_allfade.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {out_path.name}")
    total_pts = df["pnl_points"].sum()
    print(f"  Total P&L: {total_pts:.2f} pts (${total_pts * POINT_VALUE_USD:,.2f})")
    print(f"  Label split: {df['cluster_label'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
