"""
src/backtest.py — Generate trades, compute P&L, and diagnose execution.

Run from project root:
    python -m src.backtest run            # Run backtest, save trade log
    python -m src.backtest diagnose       # Empirical diagnostic of entry-bar issues
    python -m src.backtest walkforward    # Train/test split + t-test for regime stability
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from src.data import load_processed_bars
from src.signals import (
    build_candidates,
    build_cluster_pool,
    compute_opening_range,
)

STOP_POINTS = 40.0
TARGET_POINTS = 40.0
ENTRY_BUFFER = 1.0
ENTRY_WINDOW_END = "11:29"
FORCED_EXIT_TIME = "11:30"

MNQ_TICK_SIZE = 0.25
MNQ_MULTIPLIER = 2.0
COMMISSION_PER_SIDE = 0.50
SLIPPAGE_TICKS = 1
SLIPPAGE_POINTS = SLIPPAGE_TICKS * MNQ_TICK_SIZE

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"


def generate_trades(
    bars: pd.DataFrame,
    candidates: pd.DataFrame,
    stop_points: float = STOP_POINTS,
    target_points: float = TARGET_POINTS,
    entry_buffer: float = ENTRY_BUFFER,
    entry_window_end: str = ENTRY_WINDOW_END,
    forced_exit_time: str = FORCED_EXIT_TIME,
) -> pd.DataFrame:
    """One trade max per session. First breakout wins.

    Fill model: stop-buy/sell at trigger, but if bar opens past trigger
    (gap-open), fill at the bar's open price (worse). This avoids the
    look-ahead bias of assuming we filled at a level the market gapped over.

    Exit model: stop/target/time. Entry bar IS checked for stop/target —
    conservative (stop wins if both in bar range).

    Args:
        bars:             NY-indexed bars with ``session_date``, OHLC.
        candidates:       Per-session breakout candidates (output of
                          ``build_candidates``).
        stop_points:      Stop distance in points.
        target_points:    Target distance in points.
        entry_buffer:     Points added/subtracted from cluster high/low to
                          form stop-trigger price.
        entry_window_end: Latest ET time to take an entry (HH:MM).
        forced_exit_time: Latest ET time to hold; close at this bar's
                          ``close`` if neither stop nor target hit.

    Returns:
        DataFrame of trades with columns ``session_date``, ``side``,
        ``entry_ts``, ``trigger_price``, ``entry_price``, ``gap_pts``,
        ``stop_price``, ``target_price``, ``exit_ts``, ``exit_price``,
        ``exit_reason``, ``pnl_points``, ``pnl_dollars``.
    """
    trades = []
    sessions = candidates["session_date"].unique()

    for session in sessions:
        day_cands = candidates[candidates["session_date"] == session]
        day_bars = bars[bars["session_date"] == session]
        if day_bars.empty:
            continue

        entry_bars = day_bars.between_time("09:45", entry_window_end,
                                           inclusive="both")
        if entry_bars.empty:
            continue

        long_triggers = (day_cands["high"] + entry_buffer).values
        short_triggers = (day_cands["low"] - entry_buffer).values

        entry_ts = entry_side = entry_price = trigger_price = None
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

            # ─ REALISTIC FILL ─
            # If bar opens past trigger, fill at bar.open (gap), not trigger.
            if side == "long":
                trigger_price = long_triggers[long_hit].min()
                entry_price = max(trigger_price, bar["open"])
            else:
                trigger_price = short_triggers[short_hit].max()
                entry_price = min(trigger_price, bar["open"])

            entry_ts = ts
            entry_side = side
            break

        if entry_ts is None:
            continue

        if entry_side == "long":
            stop_price = entry_price - stop_points
            target_price = entry_price + target_points
        else:
            stop_price = entry_price + stop_points
            target_price = entry_price - target_points

        # ─ EXIT WALK ─ now INCLUDES the entry bar (>= instead of >)
        # The entry bar's intrabar range may already contain stop or target;
        # conservative tiebreaker: stop wins if both.
        post = day_bars[day_bars.index >= entry_ts]
        exit_window = post.between_time("00:00", forced_exit_time,
                                        inclusive="both")

        exit_ts = exit_price = exit_reason = None
        for ts, bar in exit_window.iterrows():
            if entry_side == "long":
                if bar["low"] <= stop_price:
                    exit_ts, exit_price, exit_reason = ts, stop_price, "stop"
                    break
                if bar["high"] >= target_price:
                    exit_ts, exit_price, exit_reason = ts, target_price, "target"
                    break
            else:
                if bar["high"] >= stop_price:
                    exit_ts, exit_price, exit_reason = ts, stop_price, "stop"
                    break
                if bar["low"] <= target_price:
                    exit_ts, exit_price, exit_reason = ts, target_price, "target"
                    break

        if exit_ts is None:
            if exit_window.empty:
                continue
            last = exit_window.iloc[-1]
            exit_ts = exit_window.index[-1]
            exit_price = last["close"]
            exit_reason = "time"

        if entry_side == "long":
            pnl_pts = exit_price - entry_price
        else:
            pnl_pts = entry_price - exit_price
        pnl_pts -= 2 * SLIPPAGE_POINTS

        trades.append({
            "session_date": session,
            "side": entry_side,
            "entry_ts": entry_ts,
            "trigger_price": round(trigger_price, 4),
            "entry_price": round(entry_price, 4),
            "gap_pts": round(abs(entry_price - trigger_price), 4),
            "stop_price": round(stop_price, 4),
            "target_price": round(target_price, 4),
            "exit_ts": exit_ts,
            "exit_price": round(exit_price, 4),
            "exit_reason": exit_reason,
            "pnl_points": round(pnl_pts, 4),
            "pnl_dollars": round(pnl_pts * MNQ_MULTIPLIER - 2 * COMMISSION_PER_SIDE, 2),
        })

    return pd.DataFrame(trades)


def _pipeline():
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    pool = build_cluster_pool(or_levels)
    cands = build_candidates(or_levels, pool)
    trades = generate_trades(bars, cands)
    return bars, trades


def run():
    print("Loading bars + computing pipeline...")
    bars, trades = _pipeline()
    if trades.empty:
        print("No trades generated.")
        return

    n = len(trades)
    n_win = int((trades["pnl_dollars"] > 0).sum())
    n_loss = int((trades["pnl_dollars"] < 0).sum())
    net = trades["pnl_dollars"].sum()

    print(f"\n========== TRADE SUMMARY (realistic-fill model) ==========")
    print(f"Total trades:     {n}")
    print(f"Wins:             {n_win} ({n_win/n*100:.1f}%)")
    print(f"Losses:           {n_loss} ({n_loss/n*100:.1f}%)")
    print(f"Net P&L:          ${net:,.2f}")
    print(f"Avg per trade:    ${trades['pnl_dollars'].mean():,.2f}")
    if n_win > 0 and n_loss > 0:
        aw = trades[trades["pnl_dollars"] > 0]["pnl_dollars"].mean()
        al = trades[trades["pnl_dollars"] < 0]["pnl_dollars"].mean()
        print(f"Avg win/loss:     ${aw:.2f} / ${al:.2f}")
        print(f"Win/Loss ratio:   {abs(aw/al):.2f}")
        pf = (trades[trades["pnl_dollars"] > 0]["pnl_dollars"].sum()
              / abs(trades[trades["pnl_dollars"] < 0]["pnl_dollars"].sum()))
        print(f"Profit factor:    {pf:.2f}")

    print(f"\nExit reason:")
    print(trades["exit_reason"].value_counts().to_string())

    print(f"\nGap-open stats (entry_price - trigger_price):")
    print(trades["gap_pts"].describe().to_string())

    trades["year"] = pd.to_datetime(trades["session_date"]).dt.year
    yearly = trades.groupby("year").agg(
        trades=("pnl_dollars", "count"),
        wins=("pnl_dollars", lambda x: int((x > 0).sum())),
        net=("pnl_dollars", "sum"),
        avg=("pnl_dollars", "mean"),
    ).round(2)
    print(f"\n========== YEARLY ==========")
    print(yearly.to_string())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "trades_realistic_fill.csv"
    trades.drop(columns="year").to_csv(out, index=False)
    print(f"\nSaved: {out}")


def diagnose():
    """Empirical diagnostic of entry-bar issues — no assumptions."""
    print("Regenerating pipeline + trades...")
    bars, trades = _pipeline()
    print(f"  {len(trades)} trades\n")

    entry_bars = bars.loc[trades["entry_ts"]].reset_index(drop=True)

    is_long = (trades["side"] == "long").values
    won = (trades["pnl_dollars"] > 0).values
    lost = (trades["pnl_dollars"] < 0).values

    bar_open = entry_bars["open"].values
    bar_high = entry_bars["high"].values
    bar_low = entry_bars["low"].values

    entry_price = trades["entry_price"].values
    stop_price = trades["stop_price"].values
    target_price = trades["target_price"].values
    trigger_price = trades["trigger_price"].values

    intrabar_stop = np.where(is_long, bar_low <= stop_price,
                              bar_high >= stop_price)
    intrabar_target = np.where(is_long, bar_high >= target_price,
                                bar_low <= target_price)
    gap_open = np.where(is_long, bar_open > trigger_price,
                         bar_open < trigger_price)

    print(f"========== ENTRY-BAR DIAGNOSTICS ==========")
    print(f"Total trades:                       {len(trades)}")
    print(f"  Recorded winners:                 {won.sum()}")
    print(f"  Recorded losers:                  {lost.sum()}")

    print(f"\n--- Q1: stop crossed on ENTRY bar (intrabar) ---")
    print(f"Trades where entry bar's range crossed stop: {intrabar_stop.sum()} "
          f"({intrabar_stop.sum()/len(trades)*100:.1f}%)")
    print(f"  ...of those, recorded as WINNERS: {(intrabar_stop & won).sum()}")
    print(f"  ...of those, recorded as LOSERS:  {(intrabar_stop & lost).sum()}")

    print(f"\n--- Q2: target reached on ENTRY bar (intrabar) ---")
    print(f"Trades where entry bar's range reached target: {intrabar_target.sum()} "
          f"({intrabar_target.sum()/len(trades)*100:.1f}%)")

    print(f"\n--- Q3: entry bar opened past trigger (gap fill, now modeled) ---")
    print(f"Trades with gap-open: {gap_open.sum()} "
          f"({gap_open.sum()/len(trades)*100:.1f}%)")
    if gap_open.sum() > 0:
        gap_pts = np.where(is_long, bar_open - trigger_price,
                            trigger_price - bar_open)
        gap_pts = gap_pts[gap_open]
        print(f"  Mean gap:   {gap_pts.mean():.2f} pts")
        print(f"  Median gap: {np.median(gap_pts):.2f} pts")
        print(f"  Max gap:    {gap_pts.max():.2f} pts")


def _period_stats(trades):
    pnl = trades["pnl_dollars"]
    n = len(trades)
    if n == 0:
        return {"n_trades": 0}
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    n_win = len(wins)
    n_loss = len(losses)
    avg_win = float(wins.mean()) if n_win else 0.0
    avg_loss = float(losses.mean()) if n_loss else 0.0
    pf = (wins.sum() / abs(losses.sum())) if losses.sum() < 0 else float("inf")
    wl_ratio = abs(avg_win / avg_loss) if avg_loss < 0 else float("inf")
    cum = trades.sort_values("entry_ts")["pnl_dollars"].cumsum().to_numpy()
    peak = np.maximum.accumulate(cum)
    max_dd = float((cum - peak).min())
    return {
        "n_trades": n,
        "win_rate": n_win / n,
        "net": float(pnl.sum()),
        "avg": float(pnl.mean()),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "wl_ratio": wl_ratio,
        "profit_factor": pf,
        "max_dd": max_dd,
    }


def walkforward():
    print("Loading bars + computing pipeline...")
    bars, trades = _pipeline()
    if trades.empty:
        print("No trades generated.")
        return

    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"])
    train_start = pd.Timestamp("2019-01-01", tz=trades["entry_ts"].dt.tz)
    train_end = pd.Timestamp("2022-12-31 23:59:59", tz=trades["entry_ts"].dt.tz)
    test_start = pd.Timestamp("2023-01-01", tz=trades["entry_ts"].dt.tz)
    test_end = pd.Timestamp("2026-12-31 23:59:59", tz=trades["entry_ts"].dt.tz)

    train = trades[(trades["entry_ts"] >= train_start) & (trades["entry_ts"] <= train_end)]
    test = trades[(trades["entry_ts"] >= test_start) & (trades["entry_ts"] <= test_end)]
    dropped = len(trades) - len(train) - len(test)

    s_train = _period_stats(train)
    s_test = _period_stats(test)

    print(f"\n========== WALK-FORWARD (train 2019-2022 / test 2023-2026) ==========")
    print(f"Total trades: {len(trades)}   train: {len(train)}   test: {len(test)}"
          + (f"   (dropped: {dropped})" if dropped else ""))

    if s_train["n_trades"] == 0 or s_test["n_trades"] == 0:
        print("\nOne period has zero trades — cannot run comparison.")
        return

    def fmt_money(x): return f"${x:,.2f}"
    def fmt_pct(x): return f"{x*100:.1f}%"
    def fmt_ratio(x): return "inf" if not np.isfinite(x) else f"{x:.2f}"

    rows = [
        ("n_trades",       f"{s_train['n_trades']}",            f"{s_test['n_trades']}"),
        ("win_rate",       fmt_pct(s_train['win_rate']),        fmt_pct(s_test['win_rate'])),
        ("net P&L",        fmt_money(s_train['net']),           fmt_money(s_test['net'])),
        ("avg / trade",    fmt_money(s_train['avg']),           fmt_money(s_test['avg'])),
        ("avg win",        fmt_money(s_train['avg_win']),       fmt_money(s_test['avg_win'])),
        ("avg loss",       fmt_money(s_train['avg_loss']),      fmt_money(s_test['avg_loss'])),
        ("win/loss ratio", fmt_ratio(s_train['wl_ratio']),      fmt_ratio(s_test['wl_ratio'])),
        ("profit factor",  fmt_ratio(s_train['profit_factor']), fmt_ratio(s_test['profit_factor'])),
        ("max drawdown",   fmt_money(s_train['max_dd']),        fmt_money(s_test['max_dd'])),
    ]
    label_w = max(len(r[0]) for r in rows)
    col_w = max(max(len(r[1]), len(r[2])) for r in rows) + 2
    header = f"{'metric'.ljust(label_w)}  {'train (2019-22)'.rjust(col_w)}  {'test (2023-26)'.rjust(col_w)}"
    print("\n" + header)
    print("-" * len(header))
    for label, a, b in rows:
        print(f"{label.ljust(label_w)}  {a.rjust(col_w)}  {b.rjust(col_w)}")

    t_stat, p_val = stats.ttest_ind(
        train["pnl_dollars"].to_numpy(),
        test["pnl_dollars"].to_numpy(),
        equal_var=False,
    )
    print(f"\nWelch's t-test on per-trade $:  t = {t_stat:.3f}   p = {p_val:.4f}")

    same_sign = (s_train["avg"] > 0) == (s_test["avg"] > 0)
    if p_val < 0.05:
        verdict = ("REGIME DEPENDENCY — train and test per-trade returns differ significantly "
                   f"(p={p_val:.4f}). Out-of-sample behavior is not the same as in-sample.")
    elif not same_sign:
        verdict = ("INCONSISTENT — t-test not significant, but per-trade averages have "
                   "opposite signs. Underpowered or genuinely regime-dependent; treat with caution.")
    else:
        verdict = ("CONSISTENT — no statistically significant difference between train and test "
                   f"per-trade returns (p={p_val:.4f}). Same-signed averages.")
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    {"run": run, "diagnose": diagnose, "walkforward": walkforward}.get(
        cmd, lambda: print(f"Unknown: {cmd}\nUsage: run | diagnose | walkforward")
    )()