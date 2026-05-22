"""
src/vbt_backtest.py — vectorbt rewrite of src/backtest.py for fast sweeps.

Run from project root:
    .venv/bin/python -m src.vbt_backtest run     # validate vs reference
    .venv/bin/python -m src.vbt_backtest sweep   # 5x5 stop/target sweep
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import vectorbt as vbt
from scipy import stats
from vectorbt.portfolio.enums import StopEntryPrice, StopExitPrice

from src.data import load_processed_bars
from src.indicators import compute_adx_series, compute_plus_minus_di
from src.signals import (
    build_candidates,
    build_cluster_pool,
    compute_opening_range,
    compute_or_close,
    LOOKBACK_SESSIONS,
    CLUSTER_GAP,
    MIN_CLUSTER_SIZE,
)
from src.backtest import (
    STOP_POINTS, TARGET_POINTS, ENTRY_BUFFER, ENTRY_WINDOW_END,
    MNQ_MULTIPLIER, COMMISSION_PER_SIDE, SLIPPAGE_POINTS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"


def _trigger_anchors(day_cands, entry_location):
    """Return (long_anchors, short_anchors) per the entry_location mode."""
    if entry_location == "high_low":
        return day_cands["high"].values, day_cands["low"].values
    if entry_location == "low_high":
        return day_cands["low"].values, day_cands["high"].values
    if entry_location == "center":
        c = day_cands["center"].values
        return c, c
    if entry_location == "median":
        m = day_cands["median"].values
        return m, m
    raise ValueError(f"Unknown entry_location: {entry_location}")


def generate_signals(bars, candidates,
                     entry_buffer=ENTRY_BUFFER,
                     entry_window_end=ENTRY_WINDOW_END,
                     entry_location="high_low"):
    """Mirror src/backtest.generate_trades entry logic, encoded as Series."""
    idx = bars.index
    long_entries = pd.Series(False, index=idx)
    short_entries = pd.Series(False, index=idx)
    entry_prices = pd.Series(np.nan, index=idx)

    for session in candidates["session_date"].unique():
        day_cands = candidates[candidates["session_date"] == session]
        day_bars = bars[bars["session_date"] == session]
        if day_bars.empty:
            continue
        entry_bars = day_bars.between_time("09:45", entry_window_end,
                                           inclusive="both")
        if entry_bars.empty:
            continue

        long_anchors, short_anchors = _trigger_anchors(day_cands, entry_location)
        long_triggers = long_anchors + entry_buffer
        short_triggers = short_anchors - entry_buffer

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


def _build_stop_series(entry_prices, points):
    """Per-bar fraction = points / ffilled entry price (vbt reads at entry bar)."""
    ffill = entry_prices.ffill().bfill()
    return (points / ffill).replace([np.inf, -np.inf], np.nan)


def _manual_exits(bars, long_entries, short_entries, entry_prices,
                  stop_points, target_points, force_exits):
    """Walk each trade matching src/backtest.generate_trades exit logic:
    intrabar stop/target on the entry bar inclusive (stop-first tiebreak),
    then forward bars in-session, then force-close at the 11:30 bar's close.

    Returns long_exits, short_exits, exit_prices Series. For exits that the
    reference takes on the entry bar itself, we emit the signal on the NEXT
    in-session bar at the same stop/target price — vbt's signal model can't
    open and close at different prices on the same bar, but the trade P&L
    matches because we control the exit fill price.
    """
    idx = bars.index
    high = bars["high"].values
    low = bars["low"].values
    close = bars["close"].values
    session = bars["session_date"].values

    long_arr = long_entries.values
    short_arr = short_entries.values
    entry_p_arr = entry_prices.values
    force_arr = force_exits.values

    long_exits_arr = np.zeros(len(idx), dtype=bool)
    short_exits_arr = np.zeros(len(idx), dtype=bool)
    exit_price_arr = np.full(len(idx), np.nan)

    entry_idxs = np.where(long_arr | short_arr)[0]
    for i in entry_idxs:
        is_long = bool(long_arr[i])
        ep = float(entry_p_arr[i])
        if is_long:
            stop_p = ep - stop_points
            tgt_p = ep + target_points
        else:
            stop_p = ep + stop_points
            tgt_p = ep - target_points
        sess = session[i]

        exit_idx = None
        exit_price = None
        for j in range(i, len(idx)):
            if session[j] != sess:
                break
            if is_long:
                hit_stop = low[j] <= stop_p
                hit_tgt = high[j] >= tgt_p
            else:
                hit_stop = high[j] >= stop_p
                hit_tgt = low[j] <= tgt_p
            if hit_stop:
                exit_idx, exit_price = j, stop_p
                break
            if hit_tgt:
                exit_idx, exit_price = j, tgt_p
                break
            if force_arr[j]:
                exit_idx, exit_price = j, float(close[j])
                break

        if exit_idx is None:
            continue
        if exit_idx == i and exit_idx + 1 < len(idx) and session[exit_idx + 1] == sess:
            exit_idx = exit_idx + 1
        if is_long:
            long_exits_arr[exit_idx] = True
        else:
            short_exits_arr[exit_idx] = True
        exit_price_arr[exit_idx] = exit_price

    return (
        pd.Series(long_exits_arr, index=idx),
        pd.Series(short_exits_arr, index=idx),
        pd.Series(exit_price_arr, index=idx),
    )


def run_portfolio(bars, long_entries, short_entries, entry_prices, force_exits,
                  stop_points=STOP_POINTS, target_points=TARGET_POINTS,
                  init_cash=50000):
    long_exits, short_exits, exit_prices = _manual_exits(
        bars, long_entries, short_entries, entry_prices,
        stop_points, target_points, force_exits,
    )
    price_series = entry_prices.combine_first(exit_prices).combine_first(bars["close"])

    pf = vbt.Portfolio.from_signals(
        close=bars["close"],
        entries=long_entries,
        short_entries=short_entries,
        exits=long_exits,
        short_exits=short_exits,
        price=price_series,
        init_cash=init_cash,
        size=1,
        freq="1min",
        fees=0.0,
        slippage=0.0,
        accumulate=False,
    )
    return pf


def _trade_dollars(trades_df, mnq_multiplier, commission_per_side, slippage_points):
    """Convert vbt trade records to reference-accounting dollar P&L."""
    if len(trades_df) == 0:
        return np.array([])
    entry = trades_df["Avg Entry Price"].to_numpy()
    exit_ = trades_df["Avg Exit Price"].to_numpy()
    direction = trades_df["Direction"].astype(str).str.lower().to_numpy()
    is_long = direction == "long"
    pts = np.where(is_long, exit_ - entry, entry - exit_)
    pts -= 2 * slippage_points
    return pts * mnq_multiplier - 2 * commission_per_side


def summarize(pf, mnq_multiplier=MNQ_MULTIPLIER,
              commission_per_side=COMMISSION_PER_SIDE,
              slippage_points=SLIPPAGE_POINTS):
    trades = pf.trades.records_readable
    dollars = _trade_dollars(trades, mnq_multiplier, commission_per_side, slippage_points)
    n = len(dollars)
    if n == 0:
        return {"n_trades": 0, "n_wins": 0, "n_losses": 0, "win_rate": 0.0,
                "net_dollars": 0.0, "avg_trade_dollars": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0,
                "win_loss_ratio": float("nan"), "profit_factor": float("nan"),
                "max_drawdown_dollars": 0.0}
    wins = dollars > 0
    losses = dollars < 0
    n_win = int(wins.sum())
    n_loss = int(losses.sum())
    net = float(dollars.sum())
    avg_win = float(dollars[wins].mean()) if n_win else 0.0
    avg_loss = float(dollars[losses].mean()) if n_loss else 0.0
    gross_win = float(dollars[wins].sum())
    gross_loss = float(-dollars[losses].sum())
    pf_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    wl = abs(avg_win / avg_loss) if avg_loss < 0 else float("inf")
    cum = np.cumsum(dollars)
    peak = np.maximum.accumulate(cum)
    max_dd = float((cum - peak).min())
    return {
        "n_trades": n,
        "n_wins": n_win,
        "n_losses": n_loss,
        "win_rate": n_win / n,
        "net_dollars": net,
        "avg_trade_dollars": net / n,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "win_loss_ratio": wl,
        "profit_factor": pf_factor,
        "max_drawdown_dollars": max_dd,
    }


def _sweep_with_signals(bars, long_e, short_e, entry_p, force_e,
                        stop_range, target_range,
                        init_cash=50000, mnq_multiplier=MNQ_MULTIPLIER,
                        commission_per_side=COMMISSION_PER_SIDE,
                        slippage_points=SLIPPAGE_POINTS):
    rows = []
    for s in stop_range:
        for t in target_range:
            long_x, short_x, exit_p = _manual_exits(
                bars, long_e, short_e, entry_p, float(s), float(t), force_e,
            )
            price_series = entry_p.combine_first(exit_p).combine_first(bars["close"])
            pf = vbt.Portfolio.from_signals(
                close=bars["close"],
                entries=long_e, short_entries=short_e,
                exits=long_x, short_exits=short_x,
                price=price_series,
                init_cash=init_cash, size=1, freq="1min",
                fees=0.0, slippage=0.0, accumulate=False,
            )
            m = summarize(pf, mnq_multiplier=mnq_multiplier,
                          commission_per_side=commission_per_side,
                          slippage_points=slippage_points)
            rows.append({
                "stop": int(s), "target": int(t),
                "n_trades": m["n_trades"],
                "win_rate": m["win_rate"],
                "net_dollars": m["net_dollars"],
                "profit_factor": m["profit_factor"],
                "max_drawdown_dollars": m["max_drawdown_dollars"],
            })
    return pd.DataFrame(rows)


def sweep_stop_target(bars, candidates, stop_range, target_range,
                      entry_buffer=ENTRY_BUFFER, entry_window_end=ENTRY_WINDOW_END,
                      init_cash=50000, mnq_multiplier=MNQ_MULTIPLIER,
                      commission_per_side=COMMISSION_PER_SIDE,
                      slippage_points=SLIPPAGE_POINTS):
    """Per-combo loop over (stop, target). NOTE: vbt's sl_stop/tp_stop
    broadcasting was tried first but diverges from src/backtest.py by ~18% on
    avg win/loss (vbt's StopLimit can't fill at the exact stop/target price
    when the next bar gaps past it, and vbt skips entry-bar intrabar checks).
    Looping _manual_exits per combo costs ~1s/combo and matches the reference
    exactly. For a 5x5 sweep that's ~25s — still cheap, and the numbers are
    trustworthy."""
    long_e, short_e, entry_p, force_e = generate_signals(
        bars, candidates,
        entry_buffer=entry_buffer, entry_window_end=entry_window_end,
    )
    return _sweep_with_signals(
        bars, long_e, short_e, entry_p, force_e, stop_range, target_range,
        init_cash=init_cash, mnq_multiplier=mnq_multiplier,
        commission_per_side=commission_per_side, slippage_points=slippage_points,
    )


def _pipeline():
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    pool = build_cluster_pool(or_levels)
    cands = build_candidates(or_levels, pool)
    return bars, cands


REFERENCE = {
    "n_trades": 398, "win_rate": 0.570, "net_dollars": 3665.00,
    "avg_trade_dollars": 9.21, "avg_win": 76.57, "avg_loss": -80.21,
    "win_loss_ratio": 0.95, "profit_factor": 1.27,
}


def run():
    print("Loading bars + computing pipeline...")
    bars, cands = _pipeline()
    print("Generating signals...")
    long_e, short_e, entry_p, force_e = generate_signals(bars, cands)
    n_long = int(long_e.sum()); n_short = int(short_e.sum())
    print(f"  signals: {n_long+n_short} entries ({n_long} long / {n_short} short), "
          f"{int(force_e.sum())} force exits")

    print("Running vbt portfolio (40/40, default costs)...")
    pf = run_portfolio(bars, long_e, short_e, entry_p, force_e)
    m = summarize(pf)

    print(f"\n========== VALIDATION: vbt vs src/backtest.py ==========")
    header = f"{'metric':24s}  {'reference':>14s}  {'vbt':>14s}  {'delta':>10s}  verdict"
    print(header); print("-" * len(header))

    def fmt_num(v):
        if isinstance(v, float):
            return f"{v:.4f}"
        return f"{v}"

    overall_ok = True
    for k, ref_v in REFERENCE.items():
        vbt_v = m.get(k, float("nan"))
        if abs(ref_v) > 0:
            rel = (vbt_v - ref_v) / abs(ref_v)
            ok = abs(rel) <= 0.05
            delta_str = f"{rel*100:+.2f}%"
        else:
            ok = abs(vbt_v - ref_v) <= 1e-6
            delta_str = f"{vbt_v - ref_v:+.4f}"
        if not ok:
            overall_ok = False
        verdict = "MATCH" if ok else "MISMATCH"
        print(f"{k:24s}  {fmt_num(ref_v):>14s}  {fmt_num(vbt_v):>14s}  {delta_str:>10s}  {verdict}")

    print(f"\nMax drawdown (vbt): ${m['max_drawdown_dollars']:,.2f}")
    print(f"Verdict: {'ALL MATCH (within 5%)' if overall_ok else 'AT LEAST ONE MISMATCH'}")
    return pf, m


def sweep():
    print("Loading bars + computing pipeline...")
    bars, cands = _pipeline()
    stop_range = [20, 30, 40, 50, 60]
    target_range = [20, 30, 40, 50, 60]
    print(f"Running 5x5 sweep: stops={stop_range} x targets={target_range}...")
    df = sweep_stop_target(bars, cands, stop_range, target_range)

    print("\n========== PROFIT FACTOR HEATMAP ==========")
    pf_pivot = df.pivot(index="stop", columns="target", values="profit_factor")
    print(pf_pivot.round(3).to_string())

    print("\n========== NET $ HEATMAP ==========")
    net_pivot = df.pivot(index="stop", columns="target", values="net_dollars")
    print(net_pivot.round(0).to_string())

    print("\n========== N TRADES HEATMAP ==========")
    n_pivot = df.pivot(index="stop", columns="target", values="n_trades")
    print(n_pivot.to_string())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_sweep_stop_target.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return df


def sweep_fine():
    print("Loading bars + computing pipeline...")
    bars, cands = _pipeline()
    stop_range = [20, 25, 30, 35, 40, 45, 50, 55, 60]
    target_range = [20, 25, 30, 35, 40, 45, 50, 55, 60]
    print(f"Running 9x9 sweep (81 combos)...")
    df = sweep_stop_target(bars, cands, stop_range, target_range)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_sweep_stop_target_fine.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}")
    return df


def heatmap(file_arg=None):
    candidates = [
        RESULTS_DIR / "vbt_sweep_stop_target_fine.csv",
        RESULTS_DIR / "vbt_sweep_stop_target.csv",
    ]
    if file_arg:
        path = Path(file_arg)
        if not path.is_absolute():
            path = RESULTS_DIR / path
    else:
        existing = [p for p in candidates if p.exists()]
        if not existing:
            print(f"No sweep CSV found in {RESULTS_DIR}. Run `sweep` or `sweep_fine` first.")
            return
        path = max(existing, key=lambda p: p.stat().st_mtime)

    if not path.exists():
        print(f"File not found: {path}")
        return
    print(f"Reading: {path}")
    df = pd.read_csv(path)
    print(f"Grid: {df['stop'].nunique()} stops x {df['target'].nunique()} targets "
          f"({len(df)} cells)")

    specs = [
        ("profit_factor", "{:7.3f}"),
        ("net_dollars",   "{:7.0f}"),
        ("win_rate",      "{:7.3f}"),
    ]

    for metric, fmt in specs:
        pivot = df.pivot(index="stop", columns="target", values=metric).sort_index().sort_index(axis=1)
        print(f"\n========== {metric.upper()} ==========")
        print(pivot.to_string(float_format=lambda x: fmt.format(x)))

        flat = pivot.stack()
        best_idx = flat.idxmax()
        s_best, t_best = int(best_idx[0]), int(best_idx[1])
        best_val = float(flat.max())

        row_i = list(pivot.index).index(s_best)
        col_i = list(pivot.columns).index(t_best)
        neighbors = []
        if row_i > 0:
            neighbors.append(float(pivot.iat[row_i - 1, col_i]))
        if row_i < len(pivot.index) - 1:
            neighbors.append(float(pivot.iat[row_i + 1, col_i]))
        if col_i > 0:
            neighbors.append(float(pivot.iat[row_i, col_i - 1]))
        if col_i < len(pivot.columns) - 1:
            neighbors.append(float(pivot.iat[row_i, col_i + 1]))
        neighbors = [n for n in neighbors if not np.isnan(n)]
        med = float(np.median(neighbors)) if neighbors else float("nan")
        ratio = best_val / med if med not in (0.0,) and not np.isnan(med) else float("nan")
        label = ("PEAK" if ratio > 1.05 else
                 "PLATEAU" if ratio > 0.95 else
                 "VALLEY")
        print(f"  best: stop={s_best}, target={t_best}, "
              f"value={fmt.format(best_val).strip()}")
        print(f"  neighbor median ({len(neighbors)} cells): {fmt.format(med).strip()}")
        print(f"  robustness ratio: {ratio:.3f}  ({label})")


def walkforward_sweep():
    print("Loading bars + computing pipeline...")
    bars, cands = _pipeline()
    print("Generating signals on full series...")
    long_e, short_e, entry_p, force_e = generate_signals(bars, cands)

    sd = pd.to_datetime(bars["session_date"])
    train_mask = pd.Series(((sd >= "2019-01-01") & (sd <= "2022-12-31")).values,
                           index=bars.index)
    test_mask = pd.Series(((sd >= "2023-01-01") & (sd <= "2026-12-31")).values,
                          index=bars.index)

    long_e_tr = long_e & train_mask
    short_e_tr = short_e & train_mask
    entry_p_tr = entry_p.where(train_mask)
    long_e_te = long_e & test_mask
    short_e_te = short_e & test_mask
    entry_p_te = entry_p.where(test_mask)

    n_tr = int(long_e_tr.sum() + short_e_tr.sum())
    n_te = int(long_e_te.sum() + short_e_te.sum())
    print(f"  train entries: {n_tr}   test entries: {n_te}")

    stop_range = [20, 25, 30, 35, 40, 45, 50, 55, 60]
    target_range = [20, 25, 30, 35, 40, 45, 50, 55, 60]

    print(f"Sweep on TRAIN (9x9 = 81 combos)...")
    train_df = _sweep_with_signals(bars, long_e_tr, short_e_tr, entry_p_tr, force_e,
                                    stop_range, target_range)
    print(f"Sweep on TEST  (9x9 = 81 combos)...")
    test_df = _sweep_with_signals(bars, long_e_te, short_e_te, entry_p_te, force_e,
                                   stop_range, target_range)

    merged = train_df.merge(test_df, on=["stop", "target"],
                            suffixes=("_train", "_test"))
    merged = merged.rename(columns={
        "profit_factor_train": "train_pf",
        "profit_factor_test": "test_pf",
        "net_dollars_train": "train_net",
        "net_dollars_test": "test_net",
        "n_trades_train": "train_n",
        "n_trades_test": "test_n",
        "win_rate_train": "train_wr",
        "win_rate_test": "test_wr",
        "max_drawdown_dollars_train": "train_mdd",
        "max_drawdown_dollars_test": "test_mdd",
    })

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_walkforward_sweep.csv"
    merged.to_csv(out, index=False)

    best = merged.loc[merged["train_pf"].idxmax()]
    s_b, t_b = int(best["stop"]), int(best["target"])

    print(f"\n========== WALK-FORWARD AT TRAIN-BEST ({s_b}, {t_b}) ==========")
    cols = [
        ("best (stop, target)", f"({s_b}, {t_b})", f"({s_b}, {t_b}) — same"),
        ("n_trades", f"{int(best['train_n'])}", f"{int(best['test_n'])}"),
        ("win_rate", f"{best['train_wr']*100:.1f}%", f"{best['test_wr']*100:.1f}%"),
        ("net_dollars", f"${best['train_net']:,.0f}", f"${best['test_net']:,.0f}"),
        ("profit_factor", f"{best['train_pf']:.3f}", f"{best['test_pf']:.3f}"),
        ("max_drawdown", f"${best['train_mdd']:,.0f}", f"${best['test_mdd']:,.0f}"),
    ]
    label_w = max(len(r[0]) for r in cols)
    col_w = max(max(len(r[1]), len(r[2])) for r in cols) + 2
    header = f"{'metric'.ljust(label_w)}  {'train (2019-22)'.rjust(col_w)}  {'test (2023-26)'.rjust(col_w)}"
    print(header)
    print("-" * len(header))
    for label, a, b in cols:
        print(f"{label.ljust(label_w)}  {a.rjust(col_w)}  {b.rjust(col_w)}")

    drop = (best["train_pf"] - best["test_pf"]) / best["train_pf"] if best["train_pf"] else 0
    print(f"\nPF drop train → test: {drop*100:+.1f}%   "
          f"({'HOLDS' if best['test_pf'] >= 1.0 and abs(drop) < 0.3 else 'COLLAPSES' if best['test_pf'] < 1.0 else 'DEGRADED'})")

    print(f"\n========== TOP 5 TRAIN CELLS — out-of-sample check ==========")
    top5 = merged.sort_values("train_pf", ascending=False).head(5).reset_index(drop=True)
    print(f"{'rank':>4}  {'stop':>4}  {'target':>6}  "
          f"{'train_pf':>9}  {'train_net':>10}  {'test_pf':>9}  {'test_net':>10}")
    print("-" * 64)
    for i, row in top5.iterrows():
        print(f"{i+1:>4}  {int(row['stop']):>4}  {int(row['target']):>6}  "
              f"{row['train_pf']:>9.3f}  ${row['train_net']:>9,.0f}  "
              f"{row['test_pf']:>9.3f}  ${row['test_net']:>9,.0f}")

    print(f"\nSaved: {out}")
    return merged


SENSITIVITY_DEFAULTS = {
    "ENTRY_BUFFER":      1.0,
    "LOOKBACK_SESSIONS": 200,
    "CLUSTER_GAP":       3.0,
    "MIN_CLUSTER_SIZE":  3,
    "ENTRY_LOCATION":    "high_low",
}

SENSITIVITY_RANGES = [
    ("ENTRY_BUFFER",      [0.0, 0.25, 0.5, 1.0, 2.0, 4.0]),
    ("LOOKBACK_SESSIONS", [50, 100, 150, 200, 300]),
    ("CLUSTER_GAP",       [1.0, 2.0, 3.0, 4.0, 5.0, 7.0]),
    ("MIN_CLUSTER_SIZE",  [2, 3, 4, 5, 6]),
    ("ENTRY_LOCATION",    ["high_low", "low_high", "center", "median"]),
]


def _run_one(bars, cands, buffer, entry_location,
             stop_points=40.0, target_points=40.0):
    long_e, short_e, entry_p, force_e = generate_signals(
        bars, cands, entry_buffer=buffer, entry_location=entry_location,
    )
    pf = run_portfolio(bars, long_e, short_e, entry_p, force_e,
                       stop_points=stop_points, target_points=target_points)
    return summarize(pf)


def sensitivity():
    print("Loading bars + OR levels...")
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    print(f"  {len(bars):,} bars, {len(or_levels):,} sessions with OR")

    print("Building default cluster pool + candidates (cached for buffer/location sweeps)...")
    default_pool = build_cluster_pool(
        or_levels,
        lookback=SENSITIVITY_DEFAULTS["LOOKBACK_SESSIONS"],
        gap=SENSITIVITY_DEFAULTS["CLUSTER_GAP"],
        min_size=SENSITIVITY_DEFAULTS["MIN_CLUSTER_SIZE"],
    )
    default_cands = build_candidates(or_levels, default_pool)
    print(f"  default candidates: {len(default_cands):,} across "
          f"{default_cands['session_date'].nunique():,} sessions")

    rows = []
    for param_name, values in SENSITIVITY_RANGES:
        print(f"\nSweeping {param_name} across {values}...")
        needs_pool_rebuild = param_name in ("LOOKBACK_SESSIONS", "CLUSTER_GAP", "MIN_CLUSTER_SIZE")
        for val in values:
            lookback = SENSITIVITY_DEFAULTS["LOOKBACK_SESSIONS"]
            gap = SENSITIVITY_DEFAULTS["CLUSTER_GAP"]
            min_size = SENSITIVITY_DEFAULTS["MIN_CLUSTER_SIZE"]
            buffer = SENSITIVITY_DEFAULTS["ENTRY_BUFFER"]
            loc = SENSITIVITY_DEFAULTS["ENTRY_LOCATION"]
            if param_name == "ENTRY_BUFFER":
                buffer = val
            elif param_name == "LOOKBACK_SESSIONS":
                lookback = val
            elif param_name == "CLUSTER_GAP":
                gap = val
            elif param_name == "MIN_CLUSTER_SIZE":
                min_size = val
            elif param_name == "ENTRY_LOCATION":
                loc = val

            if needs_pool_rebuild:
                pool = build_cluster_pool(or_levels, lookback=lookback, gap=gap, min_size=min_size)
                cands = build_candidates(or_levels, pool)
            else:
                cands = default_cands

            m = _run_one(bars, cands, buffer, loc, stop_points=40.0, target_points=40.0)
            rows.append({
                "param_name": param_name,
                "param_value": val,
                "n_trades": m["n_trades"],
                "win_rate": m["win_rate"],
                "net_dollars": m["net_dollars"],
                "profit_factor": m["profit_factor"],
                "max_drawdown_dollars": m["max_drawdown_dollars"],
            })
            print(f"  {param_name}={val}: n={m['n_trades']}, "
                  f"net=${m['net_dollars']:,.0f}, PF={m['profit_factor']:.3f}")

    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_sensitivity.csv"
    df.to_csv(out, index=False)

    for param_name, _ in SENSITIVITY_RANGES:
        sub = df[df["param_name"] == param_name]
        default_val = SENSITIVITY_DEFAULTS[param_name]
        print(f"\n========== {param_name} (default = {default_val}) ==========")
        header = f"{'value':>12}  {'n_trades':>9}  {'win_rate':>9}  {'net_$':>12}  {'PF':>7}  {'max_dd':>10}"
        print(header)
        print("-" * len(header))
        for _, r in sub.iterrows():
            star = " *" if r["param_value"] == default_val else "  "
            val_s = f"{r['param_value']}{star}"
            print(f"{val_s:>12}  {int(r['n_trades']):>9}  "
                  f"{r['win_rate']*100:>8.1f}%  ${r['net_dollars']:>10,.0f}  "
                  f"{r['profit_factor']:>7.3f}  ${r['max_drawdown_dollars']:>8,.0f}")

    pf_ranges = []
    net_ranges = []
    for param_name, _ in SENSITIVITY_RANGES:
        sub = df[df["param_name"] == param_name]
        pf_ranges.append((param_name, float(sub["profit_factor"].max() - sub["profit_factor"].min())))
        net_ranges.append((param_name, float(sub["net_dollars"].max() - sub["net_dollars"].min())))
    pf_ranges.sort(key=lambda x: x[1], reverse=True)
    net_ranges.sort(key=lambda x: x[1], reverse=True)

    print("\n========== SENSITIVITY RANKING ==========")
    print("\nMost-sensitive params by PF range (max - min):")
    for name, rng in pf_ranges:
        print(f"  {name:<20} {rng:.3f}")
    print("\nMost-sensitive params by net $ range:")
    for name, rng in net_ranges:
        print(f"  {name:<20} ${rng:,.0f}")

    top3_by_pf = [n for n, _ in pf_ranges[:3]]
    print("\nCandidates for joint pairwise sweeps (top 3 by PF range, all pairs):")
    pairs = [(top3_by_pf[0], top3_by_pf[1]),
             (top3_by_pf[0], top3_by_pf[2]),
             (top3_by_pf[1], top3_by_pf[2])]
    for i, (a, b) in enumerate(pairs, 1):
        print(f"  {i}. {a} x {b}")

    print(f"\nSaved: {out}")
    return df


def _format_rows(df, cols=None):
    if cols is None:
        cols = ["lookback", "gap", "min_size", "n_trades", "win_rate",
                "net_dollars", "profit_factor", "max_drawdown", "sharpe_approx"]
    return df[cols].to_string(index=False, formatters={
        "gap":            lambda x: f"{x:.1f}",
        "win_rate":       lambda x: f"{x*100:5.1f}%",
        "net_dollars":    lambda x: f"${x:>7,.0f}",
        "profit_factor":  lambda x: f"{x:6.3f}",
        "max_drawdown":   lambda x: f"${x:>7,.0f}",
        "sharpe_approx":  lambda x: f"{x:5.2f}" if not np.isnan(x) else "  nan",
    })


def pairwise_sweep():
    print("Loading bars + OR levels...", flush=True)
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    print(f"  {len(bars):,} bars, {len(or_levels):,} sessions with OR", flush=True)

    lookbacks = [50, 100, 150, 200, 250, 300]
    gaps = [2.0, 3.0, 4.0, 5.0, 7.0]
    min_sizes = [2, 3, 4, 5]
    total = len(lookbacks) * len(gaps) * len(min_sizes)
    print(f"Sweeping {total} combos (lookback x gap x min_size); "
          f"fixed: entry_location=center, buffer=1.0, stop/target=40/40",
          flush=True)
    sys.stdout.flush()

    rows = []
    combo_idx = 0
    for lookback in lookbacks:
        for gap in gaps:
            for min_size in min_sizes:
                combo_idx += 1
                pool = build_cluster_pool(or_levels, lookback=lookback,
                                          gap=gap, min_size=min_size)
                cands = build_candidates(or_levels, pool)
                if len(cands) == 0:
                    print(f"  [{combo_idx:3d}/{total}] lb={lookback} gap={gap} ms={min_size}: "
                          f"0 candidates — skipped", flush=True)
                    rows.append({
                        "lookback": lookback, "gap": gap, "min_size": min_size,
                        "n_trades": 0, "win_rate": float("nan"),
                        "net_dollars": 0.0, "profit_factor": float("nan"),
                        "max_drawdown": 0.0, "sharpe_approx": float("nan"),
                    })
                    continue

                long_e, short_e, entry_p, force_e = generate_signals(
                    bars, cands, entry_buffer=1.0, entry_location="center",
                )
                pf = run_portfolio(bars, long_e, short_e, entry_p, force_e,
                                   stop_points=40.0, target_points=40.0)
                m = summarize(pf)

                trades = pf.trades.records_readable
                if len(trades) > 1:
                    dollars = _trade_dollars(trades, MNQ_MULTIPLIER,
                                              COMMISSION_PER_SIDE, SLIPPAGE_POINTS)
                    mu = float(np.mean(dollars))
                    sd = float(np.std(dollars, ddof=1))
                    sharpe = mu / sd * math.sqrt(252) if sd > 0 else float("nan")
                else:
                    sharpe = float("nan")

                rows.append({
                    "lookback": lookback, "gap": gap, "min_size": min_size,
                    "n_trades": m["n_trades"], "win_rate": m["win_rate"],
                    "net_dollars": m["net_dollars"],
                    "profit_factor": m["profit_factor"],
                    "max_drawdown": m["max_drawdown_dollars"],
                    "sharpe_approx": sharpe,
                })
                print(f"  [{combo_idx:3d}/{total}] lb={lookback} gap={gap} ms={min_size}: "
                      f"n={m['n_trades']:>4}, net=${m['net_dollars']:>7,.0f}, "
                      f"PF={m['profit_factor']:.3f}, S={sharpe:5.2f}",
                      flush=True)
                sys.stdout.flush()

    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_pairwise_sweep.csv"
    df.to_csv(out, index=False)

    valid = df[df["n_trades"] > 0].copy()

    print("\n========== TOP 10 BY PROFIT_FACTOR ==========", flush=True)
    top_pf = valid.sort_values("profit_factor", ascending=False).head(10).reset_index(drop=True)
    print(_format_rows(top_pf), flush=True)

    print("\n========== TOP 10 BY NET_DOLLARS ==========", flush=True)
    top_net = valid.sort_values("net_dollars", ascending=False).head(10).reset_index(drop=True)
    print(_format_rows(top_net), flush=True)

    print("\n========== TOP 10 BY SHARPE_APPROX ==========", flush=True)
    top_sh = valid.dropna(subset=["sharpe_approx"]).sort_values(
        "sharpe_approx", ascending=False).head(10).reset_index(drop=True)
    print(_format_rows(top_sh), flush=True)

    def to_key(row):
        return (int(row["lookback"]), float(row["gap"]), int(row["min_size"]))
    pf_set = {to_key(r) for _, r in top_pf.iterrows()}
    net_set = {to_key(r) for _, r in top_net.iterrows()}
    sh_set = {to_key(r) for _, r in top_sh.iterrows()}

    pareto_keys = [k for k in (pf_set | net_set | sh_set)
                   if sum([k in pf_set, k in net_set, k in sh_set]) >= 2]

    print("\n========== PARETO CANDIDATES (in 2+ top-10s) ==========", flush=True)
    if not pareto_keys:
        print("  (none — no combo dominates on multiple dimensions)", flush=True)
    else:
        prows = []
        for k in pareto_keys:
            lb, g, ms = k
            row = valid[(valid["lookback"] == lb) & (valid["gap"] == g)
                        & (valid["min_size"] == ms)].iloc[0].to_dict()
            row["in_lists"] = ",".join(
                n for n, s in zip(("PF", "net", "Sh"), (pf_set, net_set, sh_set)) if k in s
            )
            prows.append(row)
        p_df = pd.DataFrame(prows).sort_values("profit_factor", ascending=False).reset_index(drop=True)
        cols = ["lookback", "gap", "min_size", "n_trades", "win_rate",
                "net_dollars", "profit_factor", "max_drawdown", "sharpe_approx", "in_lists"]
        print(p_df[cols].to_string(index=False, formatters={
            "gap":            lambda x: f"{x:.1f}",
            "win_rate":       lambda x: f"{x*100:5.1f}%",
            "net_dollars":    lambda x: f"${x:>7,.0f}",
            "profit_factor":  lambda x: f"{x:6.3f}",
            "max_drawdown":   lambda x: f"${x:>7,.0f}",
            "sharpe_approx":  lambda x: f"{x:5.2f}" if not np.isnan(x) else "  nan",
        }), flush=True)

    print("\n========== WORST 5 (lowest PF among combos with trades) ==========", flush=True)
    worst = valid.sort_values("profit_factor", ascending=True).head(5).reset_index(drop=True)
    print(_format_rows(worst), flush=True)

    n_zero = int((df["n_trades"] == 0).sum())
    if n_zero:
        print(f"\nNote: {n_zero} combo(s) produced 0 trades and were excluded from rankings.", flush=True)

    print(
        "\nsharpe_approx = (per-trade $ mean / std) * sqrt(252)  "
        "— treats each trade as ~one daily observation (≤1 trade/session in this strategy).",
        flush=True,
    )
    print(f"Saved: {out}", flush=True)
    sys.stdout.flush()
    return df


def _per_trade_dollars(pf):
    return _trade_dollars(pf.trades.records_readable,
                          MNQ_MULTIPLIER, COMMISSION_PER_SIDE, SLIPPAGE_POINTS)


def _sharpe_from_pf(pf):
    arr = _per_trade_dollars(pf)
    if len(arr) < 2:
        return float("nan")
    sd = float(np.std(arr, ddof=1))
    if sd <= 0:
        return float("nan")
    return float(np.mean(arr) / sd * math.sqrt(252))


CANDIDATES_DEF = [
    ("A", {"lookback": 50,  "gap": 4.0, "min_size": 4}),
    ("B", {"lookback": 50,  "gap": 4.0, "min_size": 3}),
    ("C", {"lookback": 200, "gap": 7.0, "min_size": 2}),
    ("D", {"lookback": 200, "gap": 3.0, "min_size": 3}),
]


def walkforward_candidates():
    print("Loading bars + OR levels...", flush=True)
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    sd = pd.to_datetime(bars["session_date"])
    train_mask = pd.Series(((sd >= "2019-01-01") & (sd <= "2022-12-31")).values,
                           index=bars.index)
    test_mask = pd.Series(((sd >= "2023-01-01") & (sd <= "2026-12-31")).values,
                          index=bars.index)
    sys.stdout.flush()

    results = {}
    for name, params in CANDIDATES_DEF:
        print(f"\n--- Candidate {name}: lb={params['lookback']}, "
              f"gap={params['gap']}, ms={params['min_size']}", flush=True)
        pool = build_cluster_pool(or_levels, lookback=params["lookback"],
                                  gap=params["gap"], min_size=params["min_size"])
        cands = build_candidates(or_levels, pool)
        print(f"  candidates rows: {len(cands):,} across "
              f"{cands['session_date'].nunique():,} sessions", flush=True)
        long_e, short_e, entry_p, force_e = generate_signals(
            bars, cands, entry_buffer=1.0, entry_location="center",
        )

        long_e_tr = long_e & train_mask
        short_e_tr = short_e & train_mask
        entry_p_tr = entry_p.where(train_mask)
        pf_tr = run_portfolio(bars, long_e_tr, short_e_tr, entry_p_tr, force_e,
                              stop_points=40.0, target_points=40.0)
        m_tr = summarize(pf_tr)
        m_tr["sharpe_approx"] = _sharpe_from_pf(pf_tr)
        print(f"  TRAIN: n={m_tr['n_trades']}, "
              f"net=${m_tr['net_dollars']:,.0f}, PF={m_tr['profit_factor']:.3f}, "
              f"S={m_tr['sharpe_approx']:.2f}", flush=True)

        long_e_te = long_e & test_mask
        short_e_te = short_e & test_mask
        entry_p_te = entry_p.where(test_mask)
        pf_te = run_portfolio(bars, long_e_te, short_e_te, entry_p_te, force_e,
                              stop_points=40.0, target_points=40.0)
        m_te = summarize(pf_te)
        m_te["sharpe_approx"] = _sharpe_from_pf(pf_te)
        print(f"  TEST:  n={m_te['n_trades']}, "
              f"net=${m_te['net_dollars']:,.0f}, PF={m_te['profit_factor']:.3f}, "
              f"S={m_te['sharpe_approx']:.2f}", flush=True)

        tr_arr = _per_trade_dollars(pf_tr)
        te_arr = _per_trade_dollars(pf_te)
        if len(tr_arr) > 1 and len(te_arr) > 1:
            _, p_val = stats.ttest_ind(tr_arr, te_arr, equal_var=False)
            welch_p = float(p_val)
        else:
            welch_p = float("nan")
        print(f"  Welch p (train vs test per-trade $): {welch_p:.4f}", flush=True)
        sys.stdout.flush()

        train_pf = m_tr["profit_factor"]
        test_pf = m_te["profit_factor"]
        train_net = m_tr["net_dollars"]
        test_net = m_te["net_dollars"]

        if not np.isfinite(train_pf) or train_pf <= 0:
            verdict = "NEUTRAL"
        elif test_pf < 0.85 * train_pf:
            verdict = "DECAYED"
        elif test_pf > train_pf and test_net > train_net:
            verdict = "IMPROVED"
        elif (test_pf >= 0.95 * train_pf
              and (np.isnan(welch_p) or welch_p > 0.05)
              and test_pf > 1.0):
            verdict = "HOLDS"
        else:
            verdict = "NEUTRAL"

        results[name] = {
            "params": params, "train": m_tr, "test": m_te,
            "welch_p": welch_p, "verdict": verdict,
        }
        print(f"  Verdict: {verdict}", flush=True)
        sys.stdout.flush()

    print("\n========== SIDE-BY-SIDE: train vs test ==========", flush=True)
    metric_keys = [
        ("n_trades",           lambda v: f"{int(v):>8d}"),
        ("win_rate",           lambda v: f"{v*100:>7.1f}%"),
        ("net_dollars",        lambda v: f"${v:>+7,.0f}"),
        ("avg_trade_dollars",  lambda v: f"${v:>+7,.2f}"),
        ("profit_factor",      lambda v: f"{v:>8.3f}"),
        ("max_drawdown_dollars", lambda v: f"${v:>+7,.0f}"),
        ("sharpe_approx",      lambda v: f"{v:>8.2f}" if not np.isnan(v) else "     nan"),
    ]
    metric_labels = {
        "n_trades": "n_trades",
        "win_rate": "win_rate",
        "net_dollars": "net_$",
        "avg_trade_dollars": "avg_$",
        "profit_factor": "profit_factor",
        "max_drawdown_dollars": "max_dd",
        "sharpe_approx": "sharpe",
    }
    header = f"{'metric':<14s}"
    for name, _ in CANDIDATES_DEF:
        header += f"  {name+'_train':>9s}  {name+'_test':>9s}"
    print(header, flush=True)
    print("-" * len(header), flush=True)
    for key, fmt in metric_keys:
        line = f"{metric_labels[key]:<14s}"
        for name, _ in CANDIDATES_DEF:
            line += f"  {fmt(results[name]['train'][key]):>9s}"
            line += f"  {fmt(results[name]['test'][key]):>9s}"
        print(line, flush=True)

    print(f"\n========== Welch's p-value (per-trade $; train vs test) ==========", flush=True)
    for name, params in CANDIDATES_DEF:
        r = results[name]
        print(f"  {name} (lb={params['lookback']}, gap={params['gap']}, "
              f"ms={params['min_size']}): p = {r['welch_p']:.4f}", flush=True)

    print(f"\n========== VERDICTS ==========", flush=True)
    for name, params in CANDIDATES_DEF:
        r = results[name]
        train_pf = r["train"]["profit_factor"]
        test_pf = r["test"]["profit_factor"]
        ratio_pct = (test_pf / train_pf * 100) if train_pf else float("nan")
        print(f"  {name} (lb={params['lookback']}, gap={params['gap']}, "
              f"ms={params['min_size']}): {r['verdict']}", flush=True)
        print(f"     train_pf={train_pf:.3f} → test_pf={test_pf:.3f}  "
              f"({ratio_pct:.1f}% of train); welch_p={r['welch_p']:.4f}", flush=True)

    ranked = sorted(
        [n for n, _ in CANDIDATES_DEF if results[n]["verdict"] != "DECAYED"],
        key=lambda n: results[n]["test"]["profit_factor"],
        reverse=True,
    )
    print(f"\n========== FINAL RANKING (non-DECAYED, by test PF) ==========", flush=True)
    if not ranked:
        print("  (all candidates decayed)", flush=True)
    else:
        for i, name in enumerate(ranked, 1):
            r = results[name]; p = r["params"]
            print(f"  {i}. {name}  lb={p['lookback']}, gap={p['gap']}, ms={p['min_size']}: "
                  f"test_pf={r['test']['profit_factor']:.3f}, "
                  f"test_net=${r['test']['net_dollars']:,.0f}  ({r['verdict']})", flush=True)
    sys.stdout.flush()

    rows = []
    for name, params in CANDIDATES_DEF:
        r = results[name]
        for period in ("train", "test"):
            m = r[period]
            rows.append({
                "candidate": name,
                "lookback": params["lookback"],
                "gap": params["gap"],
                "min_size": params["min_size"],
                "period": period,
                "n_trades": m["n_trades"],
                "win_rate": m["win_rate"],
                "net_dollars": m["net_dollars"],
                "avg_trade_dollars": m["avg_trade_dollars"],
                "profit_factor": m["profit_factor"],
                "max_drawdown_dollars": m["max_drawdown_dollars"],
                "sharpe_approx": m["sharpe_approx"],
                "welch_p_train_vs_test": r["welch_p"] if period == "train" else float("nan"),
                "verdict": r["verdict"] if period == "train" else "",
            })
    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_walkforward_candidates.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved: {out}", flush=True)
    sys.stdout.flush()
    return df


ADX_THRESHOLD = 30.0
DI_THRESHOLD = 8.0
ADX_N = 15
DI_N = 15


def _gate_decision(adx_val, plus_di, minus_di, is_long,
                   adx_threshold=ADX_THRESHOLD, di_threshold=DI_THRESHOLD,
                   use_direction_check=True):
    if pd.isna(adx_val) or pd.isna(plus_di) or pd.isna(minus_di):
        return "SKIP_WARMUP"
    if adx_val < adx_threshold:
        return "SKIP_LOW_ADX"
    if abs(plus_di - minus_di) < di_threshold:
        return "SKIP_LOW_DI"
    if use_direction_check:
        if is_long and not (plus_di > minus_di):
            return "SKIP_DIR_LONG"
        if (not is_long) and not (minus_di > plus_di):
            return "SKIP_DIR_SHORT"
    return "TAKE"


def _apply_adx_di_filter(bars, long_e, short_e, entry_p,
                          adx_threshold=ADX_THRESHOLD,
                          di_threshold=DI_THRESHOLD,
                          use_direction_check=True,
                          adx_series=None, di_df=None):
    """Compute ADX(N)/+DI/-DI shifted by 1, apply gate to each entry signal.
    Returns (long_e_filtered, short_e_filtered, entry_p_filtered, filter_log_df)."""
    if adx_series is None:
        adx_series = compute_adx_series(bars, n=ADX_N)
    if di_df is None:
        di_df = compute_plus_minus_di(bars, n=DI_N)
    adx = adx_series.shift(1)
    di = di_df.shift(1)

    long_e_f = long_e.copy()
    short_e_f = short_e.copy()
    entry_p_f = entry_p.copy()

    entry_mask = (long_e | short_e).values
    entry_idxs = np.where(entry_mask)[0]

    rows = []
    for i in entry_idxs:
        ts = bars.index[i]
        is_long = bool(long_e.iat[i])
        adx_v = float(adx.iat[i]) if not pd.isna(adx.iat[i]) else float("nan")
        pdi = float(di["plus_di"].iat[i]) if not pd.isna(di["plus_di"].iat[i]) else float("nan")
        mdi = float(di["minus_di"].iat[i]) if not pd.isna(di["minus_di"].iat[i]) else float("nan")
        decision = _gate_decision(adx_v, pdi, mdi, is_long,
                                   adx_threshold, di_threshold,
                                   use_direction_check=use_direction_check)
        rows.append({
            "entry_ts": ts,
            "side": "long" if is_long else "short",
            "adx_value": adx_v,
            "plus_di": pdi,
            "minus_di": mdi,
            "di_spread": abs(pdi - mdi) if not (np.isnan(pdi) or np.isnan(mdi)) else float("nan"),
            "filter_decision": decision,
        })
        if decision != "TAKE":
            if is_long:
                long_e_f.iat[i] = False
            else:
                short_e_f.iat[i] = False
            entry_p_f.iat[i] = np.nan

    return long_e_f, short_e_f, entry_p_f, pd.DataFrame(rows)


def _build_trades_df(pf):
    tr = pf.trades.records_readable.copy()
    tr["pnl_dollars"] = _trade_dollars(
        tr, MNQ_MULTIPLIER, COMMISSION_PER_SIDE, SLIPPAGE_POINTS,
    )
    tr["entry_ts"] = pd.to_datetime(tr["Entry Timestamp"])
    tr["exit_ts"] = pd.to_datetime(tr["Exit Timestamp"])
    tr = tr.sort_values("exit_ts").reset_index(drop=True)
    tr["year"] = tr["exit_ts"].dt.year
    tr["cum_pnl"] = tr["pnl_dollars"].cumsum()
    tr["peak"] = tr["cum_pnl"].cummax()
    tr["drawdown"] = tr["cum_pnl"] - tr["peak"]
    return tr


def _yearly_metrics(tr):
    rows = []
    for year, g in tr.groupby("year"):
        n = len(g)
        wins = g[g["pnl_dollars"] > 0]["pnl_dollars"]
        losses = g[g["pnl_dollars"] < 0]["pnl_dollars"]
        cum = g["pnl_dollars"].cumsum().to_numpy()
        peak = np.maximum.accumulate(cum)
        rows.append({
            "year": int(year),
            "n_trades": n,
            "win_rate": len(wins) / n if n else 0.0,
            "net_dollars": float(g["pnl_dollars"].sum()),
            "avg_dollars": float(g["pnl_dollars"].mean()) if n else 0.0,
            "profit_factor": (float(wins.sum() / abs(losses.sum()))
                              if losses.sum() < 0 else float("inf")),
            "max_drawdown": float((cum - peak).min()) if n else 0.0,
        })
    return pd.DataFrame(rows)


def risk_audit_c():
    print("Loading bars + OR levels...", flush=True)
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    sys.stdout.flush()

    c_params = {"lookback": 200, "gap": 7.0, "min_size": 2}
    d_params = {"lookback": 200, "gap": 3.0, "min_size": 3}

    print(f"Building C: {c_params}", flush=True)
    pool_c = build_cluster_pool(or_levels, **c_params)
    cands_c = build_candidates(or_levels, pool_c)
    le_c, se_c, ep_c, fe_c = generate_signals(
        bars, cands_c, entry_buffer=1.0, entry_location="center",
    )
    pf_c = run_portfolio(bars, le_c, se_c, ep_c, fe_c,
                         stop_points=40.0, target_points=40.0)
    tr_c = _build_trades_df(pf_c)
    print(f"  C: {len(tr_c):,} trades", flush=True)

    print(f"Building D (baseline): {d_params}", flush=True)
    pool_d = build_cluster_pool(or_levels, **d_params)
    cands_d = build_candidates(or_levels, pool_d)
    le_d, se_d, ep_d, fe_d = generate_signals(
        bars, cands_d, entry_buffer=1.0, entry_location="center",
    )
    pf_d = run_portfolio(bars, le_d, se_d, ep_d, fe_d,
                         stop_points=40.0, target_points=40.0)
    tr_d = _build_trades_df(pf_d)
    print(f"  D: {len(tr_d):,} trades", flush=True)
    sys.stdout.flush()

    print("\n========== 1. YEARLY BREAKDOWN — Candidate C ==========", flush=True)
    yearly_c = _yearly_metrics(tr_c)
    print(f"{'year':>6}  {'n':>5}  {'wr':>6}  {'net_$':>10}  {'avg_$':>7}  "
          f"{'PF':>6}  {'max_dd':>9}", flush=True)
    for _, r in yearly_c.iterrows():
        pf_str = f"{r['profit_factor']:>6.3f}" if np.isfinite(r['profit_factor']) else "   inf"
        print(f"{int(r['year']):>6}  {int(r['n_trades']):>5}  "
              f"{r['win_rate']*100:>5.1f}%  ${r['net_dollars']:>+8,.0f}  "
              f"${r['avg_dollars']:>+5,.2f}  {pf_str}  "
              f"${r['max_drawdown']:>+7,.0f}", flush=True)
    sys.stdout.flush()

    print("\n========== 2. DRAWDOWN ANALYSIS ==========", flush=True)
    dd_periods = []
    in_dd = False
    start_idx = None
    cur_depth = 0.0
    for i, r in tr_c.iterrows():
        if r["drawdown"] < 0:
            if not in_dd:
                in_dd = True
                start_idx = i
                cur_depth = r["drawdown"]
            elif r["drawdown"] < cur_depth:
                cur_depth = r["drawdown"]
        else:
            if in_dd:
                dd_periods.append((start_idx, i, cur_depth))
                in_dd = False
    if in_dd:
        dd_periods.append((start_idx, len(tr_c) - 1, cur_depth))

    dd_info = []
    for s, e, depth in dd_periods:
        start_ts = tr_c.iloc[s]["entry_ts"]
        end_ts = tr_c.iloc[e]["exit_ts"]
        dd_info.append({
            "start": start_ts.date(),
            "end": end_ts.date(),
            "duration_days": (end_ts - start_ts).days,
            "depth": float(depth),
            "n_trades_in_dd": e - s + 1,
        })

    if dd_info:
        worst = min(dd_info, key=lambda d: d["depth"])
        print(f"Max drawdown:", flush=True)
        print(f"  depth:    ${worst['depth']:,.0f}", flush=True)
        print(f"  start:    {worst['start']}", flush=True)
        print(f"  end:      {worst['end']}", flush=True)
        print(f"  duration: {worst['duration_days']} days "
              f"({worst['n_trades_in_dd']} trades)", flush=True)

        longest = sorted(dd_info, key=lambda d: d["duration_days"], reverse=True)[:5]
        print(f"\nTop 5 longest drawdowns:", flush=True)
        print(f"{'rank':>4}  {'start':>12}  {'end':>12}  {'days':>5}  "
              f"{'depth':>9}  {'trades':>6}", flush=True)
        for i, d in enumerate(longest, 1):
            print(f"{i:>4}  {str(d['start']):>12}  {str(d['end']):>12}  "
                  f"{d['duration_days']:>5}  ${d['depth']:>+7,.0f}  "
                  f"{d['n_trades_in_dd']:>6}", flush=True)

    exit_dates = tr_c["exit_ts"].dt.tz_convert(None).dt.normalize() if tr_c["exit_ts"].dt.tz else tr_c["exit_ts"].dt.normalize()
    daily_pnl = tr_c["pnl_dollars"].groupby(exit_dates).sum()
    all_dates = pd.date_range(daily_pnl.index.min(), daily_pnl.index.max(), freq="D")
    daily_eq = daily_pnl.reindex(all_dates, fill_value=0.0).cumsum()
    daily_peak = daily_eq.cummax()
    underwater = daily_eq < daily_peak
    weekday_mask = pd.Series(daily_eq.index.weekday < 5, index=daily_eq.index)
    pct_cal = float(underwater.mean()) * 100
    pct_wd = float(underwater[weekday_mask].mean()) * 100
    print(f"\n% calendar days underwater: {pct_cal:.1f}% "
          f"({int(underwater.sum())} / {len(underwater)})", flush=True)
    print(f"% trading days   underwater: {pct_wd:.1f}% "
          f"({int(underwater[weekday_mask].sum())} / {int(weekday_mask.sum())})", flush=True)
    sys.stdout.flush()

    print("\n========== 3. RECENT HOLDOUT (2025-11-01 onward) ==========", flush=True)
    tz = tr_c["exit_ts"].dt.tz

    def in_range(ts_col, lo_str, hi_str):
        lo = pd.Timestamp(lo_str)
        hi = pd.Timestamp(hi_str)
        if tz:
            lo = lo.tz_localize(tz)
            hi = hi.tz_localize(tz)
        return (ts_col >= lo) & (ts_col <= hi)

    splits = [
        ("train (2019-22)",     "2019-01-01", "2022-12-31 23:59:59"),
        ("test (2023-25Oct)",   "2023-01-01", "2025-10-31 23:59:59"),
        ("holdout (25-Nov+)",   "2025-11-01", "2030-01-01 00:00:00"),
    ]
    split_rows = []
    for name, lo, hi in splits:
        g = tr_c[in_range(tr_c["exit_ts"], lo, hi)]
        n = len(g)
        wins = g[g["pnl_dollars"] > 0]["pnl_dollars"]
        losses = g[g["pnl_dollars"] < 0]["pnl_dollars"]
        net = float(g["pnl_dollars"].sum())
        wr = len(wins) / n if n else 0.0
        pf_val = (wins.sum() / abs(losses.sum())) if losses.sum() < 0 else (
            float("inf") if wins.sum() > 0 else float("nan"))
        split_rows.append((name, n, wr, net, pf_val))
    print(f"{'split':<22}  {'n':>5}  {'wr':>6}  {'net_$':>10}  {'PF':>6}", flush=True)
    for name, n, wr, net, pf_val in split_rows:
        pf_str = f"{pf_val:>6.3f}" if np.isfinite(pf_val) else "   nan"
        print(f"{name:<22}  {n:>5}  {wr*100:>5.1f}%  "
              f"${net:>+8,.0f}  {pf_str}", flush=True)
    sys.stdout.flush()

    print("\n========== 4. ROLLING-60-TRADE PF PERCENTILES ==========", flush=True)
    pnl_arr = tr_c["pnl_dollars"].to_numpy()
    rolling = []
    for i in range(60, len(pnl_arr) + 1):
        win = pnl_arr[i - 60:i]
        w = float(win[win > 0].sum())
        l = float(-win[win < 0].sum())
        if l > 0:
            rolling.append(w / l)
        elif w > 0:
            rolling.append(float("inf"))
    rolling_arr = np.array([x for x in rolling if np.isfinite(x)])
    if len(rolling_arr) > 0:
        for pct in (10, 25, 50, 75, 90):
            print(f"  {pct:>3d}th pct PF: {np.percentile(rolling_arr, pct):.3f}", flush=True)
        print(f"  windows: {len(rolling_arr)}   "
              f"min={rolling_arr.min():.3f}  max={rolling_arr.max():.3f}", flush=True)
        n_below_1 = int((rolling_arr < 1.0).sum())
        print(f"  windows with PF<1.0: {n_below_1} "
              f"({n_below_1/len(rolling_arr)*100:.1f}% of all windows)", flush=True)
    else:
        print("  (fewer than 60 trades; cannot compute)", flush=True)
    sys.stdout.flush()

    print("\n========== 5. C vs D — YEARLY P&L ==========", flush=True)
    yearly_d = _yearly_metrics(tr_d)
    c_by_year = yearly_c.set_index("year")
    d_by_year = yearly_d.set_index("year")
    all_years = sorted(set(c_by_year.index) | set(d_by_year.index))

    def get(df, y, col, default=0.0):
        return float(df.loc[y, col]) if y in df.index else default
    print(f"{'year':>6}  {'C_net':>10}  {'D_net':>10}  {'C_PF':>6}  {'D_PF':>6}  "
          f"{'C-D':>10}  {'C_n':>5}  {'D_n':>5}", flush=True)
    for y in all_years:
        cn = get(c_by_year, y, "net_dollars")
        dn = get(d_by_year, y, "net_dollars")
        cpf = get(c_by_year, y, "profit_factor", float("nan"))
        dpf = get(d_by_year, y, "profit_factor", float("nan"))
        cnn = int(get(c_by_year, y, "n_trades"))
        dnn = int(get(d_by_year, y, "n_trades"))
        print(f"{y:>6}  ${cn:>+8,.0f}  ${dn:>+8,.0f}  "
              f"{cpf:>6.3f}  {dpf:>6.3f}  ${cn - dn:>+8,.0f}  "
              f"{cnn:>5}  {dnn:>5}", flush=True)
    sys.stdout.flush()

    out_cols = ["session_date", "side", "entry_ts", "entry_price",
                "exit_ts", "exit_price", "pnl_dollars", "cum_pnl",
                "peak", "drawdown", "year"]
    save = tr_c.copy()
    save["session_date"] = save["exit_ts"].dt.date.astype(str)
    save["side"] = save["Direction"]
    save["entry_price"] = save["Avg Entry Price"]
    save["exit_price"] = save["Avg Exit Price"]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_risk_audit_c.csv"
    save[out_cols].to_csv(out, index=False)
    print(f"\nSaved trade-by-trade audit ({len(save)} rows): {out}", flush=True)
    sys.stdout.flush()
    return save


def _drawdown_periods(tr):
    """Identify drawdown periods on tr (sorted by exit_ts) with peak/drawdown cols."""
    periods = []
    in_dd = False
    s = None
    depth = 0.0
    for i, r in tr.iterrows():
        if r["drawdown"] < 0:
            if not in_dd:
                in_dd, s, depth = True, i, r["drawdown"]
            elif r["drawdown"] < depth:
                depth = r["drawdown"]
        else:
            if in_dd:
                periods.append((s, i, depth))
                in_dd = False
    if in_dd:
        periods.append((s, len(tr) - 1, depth))
    return [
        {
            "start": tr.iloc[s]["entry_ts"].date(),
            "end": tr.iloc[e]["exit_ts"].date(),
            "duration_days": (tr.iloc[e]["exit_ts"] - tr.iloc[s]["entry_ts"]).days,
            "depth": float(d),
            "n_trades": e - s + 1,
        }
        for s, e, d in periods
    ]


def _split_metrics(tr, tz):
    """Compute summary metrics for train/test/holdout slices of tr (which has
    entry_ts/exit_ts/pnl_dollars). Returns list of (label, n, wr, net, pf)."""
    def loc(ts):
        return ts.tz_localize(tz) if tz else ts
    splits = [
        ("train (2019-22)",   "2019-01-01", "2022-12-31 23:59:59"),
        ("test (2023-25Oct)", "2023-01-01", "2025-10-31 23:59:59"),
        ("holdout (25-Nov+)", "2025-11-01", "2030-01-01 00:00:00"),
    ]
    out = []
    for name, lo, hi in splits:
        lo_ts = loc(pd.Timestamp(lo))
        hi_ts = loc(pd.Timestamp(hi))
        g = tr[(tr["exit_ts"] >= lo_ts) & (tr["exit_ts"] <= hi_ts)]
        n = len(g)
        wins = g[g["pnl_dollars"] > 0]["pnl_dollars"]
        losses = g[g["pnl_dollars"] < 0]["pnl_dollars"]
        wr = len(wins) / n if n else 0.0
        net = float(g["pnl_dollars"].sum())
        pf = (wins.sum() / abs(losses.sum())) if losses.sum() < 0 else (
            float("inf") if wins.sum() > 0 else float("nan"))
        out.append((name, n, wr, net, pf))
    return out


def run_c_with_adx():
    print("Loading bars + OR levels...", flush=True)
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    sys.stdout.flush()

    c_params = {"lookback": 200, "gap": 7.0, "min_size": 2}
    print(f"Building candidate C: {c_params}", flush=True)
    pool = build_cluster_pool(or_levels, **c_params)
    cands = build_candidates(or_levels, pool)

    print(f"Generating unfiltered signals (entry_location=center, buffer=1.0)...", flush=True)
    long_e, short_e, entry_p, force_e = generate_signals(
        bars, cands, entry_buffer=1.0, entry_location="center",
    )
    n_long = int(long_e.sum()); n_short = int(short_e.sum())
    print(f"  unfiltered: {n_long+n_short} entries ({n_long} long, {n_short} short)",
          flush=True)
    sys.stdout.flush()

    print(f"Computing ADX({ADX_N}) and ±DI({DI_N}), applying gate "
          f"(ADX≥{ADX_THRESHOLD:.0f}, |DI|≥{DI_THRESHOLD:.0f}, "
          f"DI direction must agree)...", flush=True)
    long_e_f, short_e_f, entry_p_f, filter_log = _apply_adx_di_filter(
        bars, long_e, short_e, entry_p,
        adx_threshold=ADX_THRESHOLD, di_threshold=DI_THRESHOLD,
    )
    n_take = int((filter_log["filter_decision"] == "TAKE").sum())
    n_skip = len(filter_log) - n_take
    print(f"  filter: {n_take} TAKE, {n_skip} SKIP "
          f"({n_skip/len(filter_log)*100:.1f}% rejection rate)", flush=True)
    print(f"  skip breakdown:", flush=True)
    for reason, cnt in filter_log["filter_decision"].value_counts().items():
        if reason != "TAKE":
            print(f"    {reason}: {cnt}", flush=True)
    sys.stdout.flush()

    print(f"\nRunning unfiltered backtest (ground truth for would-have-been P&L)...",
          flush=True)
    pf_unf = run_portfolio(bars, long_e, short_e, entry_p, force_e,
                            stop_points=40.0, target_points=40.0)
    tr_unf = _build_trades_df(pf_unf)
    print(f"  unfiltered: {len(tr_unf)} trades, "
          f"net=${tr_unf['pnl_dollars'].sum():,.0f}", flush=True)

    print(f"Running filtered backtest...", flush=True)
    pf_f = run_portfolio(bars, long_e_f, short_e_f, entry_p_f, force_e,
                          stop_points=40.0, target_points=40.0)
    tr_f = _build_trades_df(pf_f)
    print(f"  filtered:   {len(tr_f)} trades, "
          f"net=${tr_f['pnl_dollars'].sum():,.0f}", flush=True)
    sys.stdout.flush()

    print("\n========== FULL-PERIOD METRICS: C+ADX/DI ==========", flush=True)
    m_f = summarize(pf_f)
    m_f["sharpe_approx"] = _sharpe_from_pf(pf_f)
    m_u = summarize(pf_unf)
    m_u["sharpe_approx"] = _sharpe_from_pf(pf_unf)
    fields = [
        ("n_trades",            lambda v: f"{int(v):>9d}"),
        ("win_rate",            lambda v: f"{v*100:>8.1f}%"),
        ("net_dollars",         lambda v: f"${v:>+8,.0f}"),
        ("avg_trade_dollars",   lambda v: f"${v:>+7,.2f}"),
        ("profit_factor",       lambda v: f"{v:>9.3f}"),
        ("max_drawdown_dollars",lambda v: f"${v:>+8,.0f}"),
        ("sharpe_approx",       lambda v: f"{v:>9.2f}" if not np.isnan(v) else "      nan"),
    ]
    labels = {
        "n_trades": "n_trades", "win_rate": "win_rate",
        "net_dollars": "net_$", "avg_trade_dollars": "avg_$",
        "profit_factor": "profit_factor",
        "max_drawdown_dollars": "max_dd", "sharpe_approx": "sharpe",
    }
    print(f"{'metric':<14}  {'C unfilt':>9}  {'C+ADX/DI':>9}  {'delta':>9}", flush=True)
    print("-" * 50, flush=True)
    for key, fmt in fields:
        u = m_u[key]; v = m_f[key]
        d = v - u
        if key == "n_trades":
            d_s = f"{int(d):>+9d}"
        elif key == "win_rate":
            d_s = f"{d*100:>+8.1f}%"
        elif key in ("net_dollars", "avg_trade_dollars", "max_drawdown_dollars"):
            d_s = f"${d:>+8,.0f}" if key != "avg_trade_dollars" else f"${d:>+7,.2f}"
        elif key == "profit_factor":
            d_s = f"{d:>+9.3f}"
        else:
            d_s = f"{d:>+9.2f}" if not (np.isnan(u) or np.isnan(v)) else "      nan"
        print(f"{labels[key]:<14}  {fmt(u):>9}  {fmt(v):>9}  {d_s}", flush=True)
    sys.stdout.flush()

    print("\n========== TRAIN / TEST / HOLDOUT (C+ADX/DI) ==========", flush=True)
    tz = tr_f["exit_ts"].dt.tz
    print(f"{'split':<22}  {'n':>5}  {'wr':>6}  {'net_$':>10}  {'PF':>6}", flush=True)
    for name, n, wr, net, pf_val in _split_metrics(tr_f, tz):
        pf_s = f"{pf_val:>6.3f}" if np.isfinite(pf_val) else "   nan"
        print(f"{name:<22}  {n:>5}  {wr*100:>5.1f}%  ${net:>+8,.0f}  {pf_s}", flush=True)
    sys.stdout.flush()

    print("\n========== YEARLY BREAKDOWN (C+ADX/DI) ==========", flush=True)
    yearly = _yearly_metrics(tr_f)
    print(f"{'year':>6}  {'n':>5}  {'wr':>6}  {'net_$':>10}  {'avg_$':>7}  "
          f"{'PF':>6}  {'max_dd':>9}", flush=True)
    for _, r in yearly.iterrows():
        pf_s = f"{r['profit_factor']:>6.3f}" if np.isfinite(r['profit_factor']) else "   nan"
        print(f"{int(r['year']):>6}  {int(r['n_trades']):>5}  "
              f"{r['win_rate']*100:>5.1f}%  ${r['net_dollars']:>+8,.0f}  "
              f"${r['avg_dollars']:>+5,.2f}  {pf_s}  "
              f"${r['max_drawdown']:>+7,.0f}", flush=True)
    sys.stdout.flush()

    print("\n========== FILTER ANALYSIS: would-have-been P&L of SKIPPED trades ==========",
          flush=True)
    merged = tr_unf.merge(
        filter_log[["entry_ts", "adx_value", "plus_di", "minus_di",
                    "di_spread", "filter_decision"]],
        on="entry_ts", how="left",
    )
    by_reason = merged.groupby("filter_decision").agg(
        n=("pnl_dollars", "count"),
        net=("pnl_dollars", "sum"),
        avg=("pnl_dollars", "mean"),
        wins=("pnl_dollars", lambda s: int((s > 0).sum())),
    ).reset_index()
    by_reason["win_rate"] = by_reason["wins"] / by_reason["n"]
    by_reason = by_reason.sort_values("net", ascending=False)
    print(f"{'decision':<18}  {'n':>5}  {'wr':>6}  {'net_$':>10}  {'avg_$':>9}", flush=True)
    for _, r in by_reason.iterrows():
        print(f"{r['filter_decision']:<18}  {int(r['n']):>5}  "
              f"{r['win_rate']*100:>5.1f}%  ${r['net']:>+8,.0f}  "
              f"${r['avg']:>+7,.2f}", flush=True)
    skipped = merged[merged["filter_decision"] != "TAKE"]
    taken = merged[merged["filter_decision"] == "TAKE"]
    print(f"\nSummary:", flush=True)
    print(f"  taken trades:   n={len(taken):>4}, net=${taken['pnl_dollars'].sum():>+8,.0f}, "
          f"avg=${taken['pnl_dollars'].mean():>+6,.2f}", flush=True)
    print(f"  skipped trades: n={len(skipped):>4}, "
          f"would-have-been net=${skipped['pnl_dollars'].sum():>+8,.0f}, "
          f"avg=${skipped['pnl_dollars'].mean():>+6,.2f}", flush=True)
    sys.stdout.flush()

    print("\n========== DRAWDOWN COMPARISON ==========", flush=True)
    print("Unfiltered C drawdowns (top 5 longest):", flush=True)
    dd_u = sorted(_drawdown_periods(tr_unf), key=lambda d: d["duration_days"], reverse=True)[:5]
    for i, d in enumerate(dd_u, 1):
        print(f"  {i}. {d['start']} → {d['end']}   "
              f"{d['duration_days']:>4}d  ${d['depth']:>+7,.0f}  "
              f"({d['n_trades']} trades)", flush=True)
    print("\nFiltered C+ADX/DI drawdowns (top 5 longest):", flush=True)
    dd_f = sorted(_drawdown_periods(tr_f), key=lambda d: d["duration_days"], reverse=True)[:5]
    for i, d in enumerate(dd_f, 1):
        print(f"  {i}. {d['start']} → {d['end']}   "
              f"{d['duration_days']:>4}d  ${d['depth']:>+7,.0f}  "
              f"({d['n_trades']} trades)", flush=True)

    overlap = [d for d in dd_f
               if pd.Timestamp(d["start"]) <= pd.Timestamp("2024-10-22")
               and pd.Timestamp(d["end"]) >= pd.Timestamp("2024-03-06")]
    print(f"\n2024 Mar-Oct drawdown check: unfiltered had max DD $-996 over 229 days. "
          f"Filtered drawdowns overlapping that window: {len(overlap)}", flush=True)
    if overlap:
        for d in overlap:
            print(f"  - {d['start']} → {d['end']}: "
                  f"${d['depth']:>+7,.0f} over {d['duration_days']} days "
                  f"({d['n_trades']} trades)", flush=True)
    sys.stdout.flush()

    out_cols = ["session_date", "side", "entry_ts", "entry_price",
                "exit_ts", "exit_price", "pnl_dollars",
                "cum_pnl", "peak", "drawdown",
                "adx_value", "plus_di", "minus_di", "di_spread",
                "filter_decision", "would_have_been_pnl", "year"]
    save = merged.copy()
    save["session_date"] = save["exit_ts"].dt.date.astype(str)
    save["side"] = save["Direction"]
    save["entry_price"] = save["Avg Entry Price"]
    save["exit_price"] = save["Avg Exit Price"]
    save["would_have_been_pnl"] = np.where(
        save["filter_decision"] != "TAKE", save["pnl_dollars"], np.nan,
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_c_with_adx.csv"
    save[out_cols].to_csv(out, index=False)
    print(f"\nSaved trade-by-trade ({len(save)} rows): {out}", flush=True)
    sys.stdout.flush()
    return save


def _setup_c_pipeline():
    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    pool = build_cluster_pool(or_levels, lookback=200, gap=7.0, min_size=2)
    cands = build_candidates(or_levels, pool)
    long_e, short_e, entry_p, force_e = generate_signals(
        bars, cands, entry_buffer=1.0, entry_location="center",
    )
    return bars, long_e, short_e, entry_p, force_e


def _summary_pack(pf):
    m = summarize(pf)
    m["sharpe_approx"] = _sharpe_from_pf(pf)
    return m


def run_c_adx_no_dir():
    print("Loading bars + building candidate C pipeline...", flush=True)
    bars, long_e, short_e, entry_p, force_e = _setup_c_pipeline()
    print(f"  unfiltered: {int((long_e | short_e).sum())} entries", flush=True)

    print("Computing ADX(15) and ±DI(15) once...", flush=True)
    adx_series = compute_adx_series(bars, n=ADX_N)
    di_df = compute_plus_minus_di(bars, n=DI_N)
    sys.stdout.flush()

    print("\nRunning UNFILTERED backtest...", flush=True)
    pf_unf = run_portfolio(bars, long_e, short_e, entry_p, force_e,
                            stop_points=40.0, target_points=40.0)
    m_unf = _summary_pack(pf_unf)
    tr_unf = _build_trades_df(pf_unf)
    print(f"  {m_unf['n_trades']} trades, net=${m_unf['net_dollars']:,.0f}, "
          f"PF={m_unf['profit_factor']:.3f}", flush=True)

    print("Running FULL FILTER (ADX≥30, |DI|≥8, direction check)...", flush=True)
    le_full, se_full, ep_full, log_full = _apply_adx_di_filter(
        bars, long_e, short_e, entry_p,
        adx_threshold=30.0, di_threshold=8.0, use_direction_check=True,
        adx_series=adx_series, di_df=di_df,
    )
    pf_full = run_portfolio(bars, le_full, se_full, ep_full, force_e,
                             stop_points=40.0, target_points=40.0)
    m_full = _summary_pack(pf_full)
    print(f"  {m_full['n_trades']} trades, net=${m_full['net_dollars']:,.0f}, "
          f"PF={m_full['profit_factor']:.3f}", flush=True)

    print("Running NO-DIR FILTER (ADX≥30, |DI|≥8, no direction check)...", flush=True)
    le_nd, se_nd, ep_nd, log_nd = _apply_adx_di_filter(
        bars, long_e, short_e, entry_p,
        adx_threshold=30.0, di_threshold=8.0, use_direction_check=False,
        adx_series=adx_series, di_df=di_df,
    )
    pf_nd = run_portfolio(bars, le_nd, se_nd, ep_nd, force_e,
                           stop_points=40.0, target_points=40.0)
    m_nd = _summary_pack(pf_nd)
    tr_nd = _build_trades_df(pf_nd)
    print(f"  {m_nd['n_trades']} trades, net=${m_nd['net_dollars']:,.0f}, "
          f"PF={m_nd['profit_factor']:.3f}", flush=True)
    sys.stdout.flush()

    print("\n========== 3-WAY SIDE-BY-SIDE ==========", flush=True)
    fields = [
        ("n_trades",             lambda v: f"{int(v):>9d}"),
        ("win_rate",             lambda v: f"{v*100:>8.1f}%"),
        ("net_dollars",          lambda v: f"${v:>+8,.0f}"),
        ("avg_trade_dollars",    lambda v: f"${v:>+7,.2f}"),
        ("profit_factor",        lambda v: f"{v:>9.3f}"),
        ("max_drawdown_dollars", lambda v: f"${v:>+8,.0f}"),
        ("sharpe_approx",        lambda v: f"{v:>9.2f}" if not np.isnan(v) else "      nan"),
    ]
    labels = {
        "n_trades": "n_trades", "win_rate": "win_rate",
        "net_dollars": "net_$", "avg_trade_dollars": "avg_$",
        "profit_factor": "profit_factor",
        "max_drawdown_dollars": "max_dd", "sharpe_approx": "sharpe",
    }
    print(f"{'metric':<14}  {'C unfilt':>9}  {'C+full':>9}  {'C+no-dir':>9}  "
          f"{'no-dir Δ':>9}", flush=True)
    print("-" * 64, flush=True)
    for key, fmt in fields:
        u = m_unf[key]; f = m_full[key]; n = m_nd[key]
        d = n - u
        if key == "n_trades":
            d_s = f"{int(d):>+9d}"
        elif key == "win_rate":
            d_s = f"{d*100:>+8.1f}%"
        elif key in ("net_dollars", "max_drawdown_dollars"):
            d_s = f"${d:>+8,.0f}"
        elif key == "avg_trade_dollars":
            d_s = f"${d:>+7,.2f}"
        elif key == "profit_factor":
            d_s = f"{d:>+9.3f}"
        else:
            d_s = f"{d:>+9.2f}" if not (np.isnan(u) or np.isnan(n)) else "      nan"
        print(f"{labels[key]:<14}  {fmt(u):>9}  {fmt(f):>9}  {fmt(n):>9}  {d_s}", flush=True)
    sys.stdout.flush()

    print("\n========== TRAIN / TEST / HOLDOUT (no-dir filter) ==========", flush=True)
    tz = tr_nd["exit_ts"].dt.tz
    print(f"{'split':<22}  {'n':>5}  {'wr':>6}  {'net_$':>10}  {'PF':>6}", flush=True)
    for name, n, wr, net, pf_val in _split_metrics(tr_nd, tz):
        pf_s = f"{pf_val:>6.3f}" if np.isfinite(pf_val) else "   nan"
        print(f"{name:<22}  {n:>5}  {wr*100:>5.1f}%  ${net:>+8,.0f}  {pf_s}", flush=True)

    print("\n========== YEARLY BREAKDOWN (no-dir filter) ==========", flush=True)
    yearly = _yearly_metrics(tr_nd)
    print(f"{'year':>6}  {'n':>5}  {'wr':>6}  {'net_$':>10}  {'avg_$':>7}  "
          f"{'PF':>6}  {'max_dd':>9}", flush=True)
    for _, r in yearly.iterrows():
        pf_s = f"{r['profit_factor']:>6.3f}" if np.isfinite(r['profit_factor']) else "   nan"
        print(f"{int(r['year']):>6}  {int(r['n_trades']):>5}  "
              f"{r['win_rate']*100:>5.1f}%  ${r['net_dollars']:>+8,.0f}  "
              f"${r['avg_dollars']:>+5,.2f}  {pf_s}  "
              f"${r['max_drawdown']:>+7,.0f}", flush=True)
    sys.stdout.flush()

    print("\n========== COST-BENEFIT (no-dir filter) ==========", flush=True)
    merged = tr_unf.merge(
        log_nd[["entry_ts", "adx_value", "plus_di", "minus_di",
                 "di_spread", "filter_decision"]],
        on="entry_ts", how="left",
    )
    by_reason = merged.groupby("filter_decision").agg(
        n=("pnl_dollars", "count"),
        net=("pnl_dollars", "sum"),
        avg=("pnl_dollars", "mean"),
        wins=("pnl_dollars", lambda s: int((s > 0).sum())),
    ).reset_index()
    by_reason["win_rate"] = by_reason["wins"] / by_reason["n"]
    by_reason = by_reason.sort_values("net", ascending=False)
    print(f"{'decision':<18}  {'n':>5}  {'wr':>6}  {'net_$':>10}  {'avg_$':>9}", flush=True)
    for _, r in by_reason.iterrows():
        print(f"{r['filter_decision']:<18}  {int(r['n']):>5}  "
              f"{r['win_rate']*100:>5.1f}%  ${r['net']:>+8,.0f}  "
              f"${r['avg']:>+7,.2f}", flush=True)
    sys.stdout.flush()

    return {"unfiltered": m_unf, "full": m_full, "no_dir": m_nd}


def adx_threshold_sweep():
    print("Loading bars + building candidate C pipeline...", flush=True)
    bars, long_e, short_e, entry_p, force_e = _setup_c_pipeline()
    print(f"  unfiltered: {int((long_e | short_e).sum())} entries", flush=True)

    print("Computing ADX(15) and ±DI(15) once...", flush=True)
    adx_series = compute_adx_series(bars, n=ADX_N)
    di_df = compute_plus_minus_di(bars, n=DI_N)
    sys.stdout.flush()

    adx_thresholds = [15, 20, 25, 30, 35]
    di_thresholds = [3, 5, 8, 12]
    total = len(adx_thresholds) * len(di_thresholds)
    print(f"Sweeping {total} combos (no directional rule, ADX_thr × DI_thr)...",
          flush=True)

    rows = []
    idx = 0
    for adx_thr in adx_thresholds:
        for di_thr in di_thresholds:
            idx += 1
            le, se, ep, log = _apply_adx_di_filter(
                bars, long_e, short_e, entry_p,
                adx_threshold=float(adx_thr), di_threshold=float(di_thr),
                use_direction_check=False,
                adx_series=adx_series, di_df=di_df,
            )
            pf = run_portfolio(bars, le, se, ep, force_e,
                                stop_points=40.0, target_points=40.0)
            m = _summary_pack(pf)
            rows.append({
                "adx_threshold": adx_thr,
                "di_threshold": di_thr,
                "n_trades": m["n_trades"],
                "win_rate": m["win_rate"],
                "net_dollars": m["net_dollars"],
                "avg_trade_dollars": m["avg_trade_dollars"],
                "profit_factor": m["profit_factor"],
                "max_drawdown": m["max_drawdown_dollars"],
                "sharpe_approx": m["sharpe_approx"],
            })
            print(f"  [{idx:>2}/{total}] ADX≥{adx_thr:>2} |DI|≥{di_thr:>2}: "
                  f"n={m['n_trades']:>4}, net=${m['net_dollars']:>+7,.0f}, "
                  f"PF={m['profit_factor']:.3f}, S={m['sharpe_approx']:.2f}",
                  flush=True)
            sys.stdout.flush()

    df = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "vbt_c_adx_threshold_sweep.csv"
    df.to_csv(out, index=False)

    valid = df[df["n_trades"] >= 100].copy()
    print(f"\nQualifying cells (n_trades ≥ 100): {len(valid)} of {len(df)}", flush=True)

    def _print_top(name, sort_col, fmt_col, n=5):
        print(f"\n========== TOP {n} BY {name.upper()} (n_trades ≥ 100) ==========",
              flush=True)
        if valid.empty:
            print("  (no qualifying cells)", flush=True)
            return
        top = valid.sort_values(sort_col, ascending=False).head(n).reset_index(drop=True)
        print(f"  {'rank':>4}  {'ADX':>4}  {'DI':>3}  {'n':>5}  {'wr':>6}  "
              f"{'net_$':>10}  {'avg_$':>8}  {'PF':>7}  {'max_dd':>9}  {'Sharpe':>7}",
              flush=True)
        for i, r in top.iterrows():
            print(f"  {i+1:>4}  {int(r['adx_threshold']):>4}  "
                  f"{int(r['di_threshold']):>3}  {int(r['n_trades']):>5}  "
                  f"{r['win_rate']*100:>5.1f}%  ${r['net_dollars']:>+8,.0f}  "
                  f"${r['avg_trade_dollars']:>+6,.2f}  "
                  f"{r['profit_factor']:>7.3f}  ${r['max_drawdown']:>+7,.0f}  "
                  f"{r['sharpe_approx']:>7.2f}", flush=True)
        sys.stdout.flush()

    _print_top("profit_factor", "profit_factor", None)
    _print_top("net_dollars", "net_dollars", None)
    _print_top("sharpe_approx", "sharpe_approx", None)
    print(f"\nSaved: {out}", flush=True)
    sys.stdout.flush()
    return df


# ─── LOCKED CONFIG (production / paper-trade) ─────────────────────────────
#
# The single source of truth for the production strategy. Every metric below
# was earned through the validation gates documented in docs/SESSION_HANDOFF.md
# (fill realism, slippage stress, walk-forward, BE-stop falsification).
#
# The signal path used here — compute_opening_range / compute_or_close /
# build_cluster_pool / build_candidates(gate=within_200) / generate_signals —
# IS the path a live system would call. The only thing not used live is
# vbt's portfolio object (we walk trades manually for Model A re-pricing).
# That walk is in _walk_trades_with_reason below and is deterministic.

LOCKED_CONFIG = {
    "name":           "locked",
    "lookback":       200,
    "gap":            7.0,
    "min_size":       2,
    "gate":           "within_200",
    "entry_location": "center",
    "entry_buffer":   1.0,
    "latest_entry":   "11:29",      # entry window end
    # earliest_entry "09:45" and force_exit "11:30" are hard-coded inside
    # generate_signals — confirmed in src/vbt_backtest.py:68 and :99-104.
    "stop_pts":       30.0,
    "target_pts":     20.0,
    "use_adx":        False,
    # Costs (override the global SLIPPAGE_POINTS / COMMISSION constants).
    "slip_pts":       0.5,           # per side; Model A
    "commission_rt":  2.0,           # NinjaTrader all-in, $/round-trip
    "cost_model":     "A",           # target = limit fill (no exit slip)
}

# Reproduction tolerances are tight on purpose — the walk is deterministic
# from the parquet data so any deviation indicates a code change.
LOCKED_EXPECTED = {
    "n_trades":      (1394, 0),        # exact match
    "win_rate":      (0.7733, 0.005),
    "net_dollars":   (19690.0, 50.0),
    "profit_factor": (1.990, 0.01),
    "max_drawdown":  (-455.0, 10.0),
    "sharpe":        (5.35, 0.05),
}


def _walk_trades_with_reason(bars, long_e, short_e, entry_p, force_e,
                              stop_pts, target_pts):
    """Single-pass per-trade extractor. Same exit logic as _manual_exits
    (stop-first tiebreak; force-exit at first bar with time >= 11:30)
    but emits per-trade records including exit reason — needed for the
    Model A re-pricing where target exits don't take exit slippage.
    """
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


def _model_a_pnl(rec, slip_pts, commission_rt, mnq_pt=MNQ_MULTIPLIER):
    """Apply Model A slippage + per-RT commission to a trade record DataFrame.

    Model A: entry always slips 1 side; target exits are limit fills (no
    exit slip); stop and time exits slip 1 side.
    """
    reason = rec["reason"].to_numpy()
    # delta = entry side (always) + exit side (only if not 'target')
    delta = np.where(reason == "target", slip_pts, 2 * slip_pts)
    pts = rec["raw_pts"].to_numpy() - delta
    return pts * mnq_pt - commission_rt


def _locked_metrics(pnl):
    """Compute the regression-checked metrics for the locked config."""
    n = len(pnl)
    if n == 0:
        return dict(n_trades=0, win_rate=0.0, net_dollars=0.0,
                    profit_factor=float("nan"), max_drawdown=0.0,
                    sharpe=float("nan"))
    wins = pnl[pnl > 0]; losses = pnl[pnl < 0]
    gw = float(wins.sum()); gl = float(-losses.sum())
    pf = (gw / gl) if gl > 0 else float("inf")
    sd = float(np.std(pnl, ddof=1)) if n > 1 else 0.0
    sharpe = (np.mean(pnl) / sd * math.sqrt(252)) if sd > 0 else float("nan")
    cum = np.cumsum(pnl); peak = np.maximum.accumulate(cum)
    mdd = float((cum - peak).min())
    return dict(n_trades=n, win_rate=len(wins)/n, net_dollars=float(pnl.sum()),
                profit_factor=pf, max_drawdown=mdd, sharpe=sharpe)


def build_locked_pipeline(bars=None, cfg=None):
    """Construct candidates + signals + force-exits for the locked config.

    This is the function a live signal generator should call: same
    compute_opening_range, same compute_or_close, same build_cluster_pool,
    same build_candidates(gate=within_200), same generate_signals.
    Returns (bars, candidates, long_e, short_e, entry_p, force_e).
    """
    if cfg is None:
        cfg = LOCKED_CONFIG
    if bars is None:
        bars = load_processed_bars()
    or_levels = compute_opening_range(bars)
    or_close = compute_or_close(bars)
    pool = build_cluster_pool(or_levels, lookback=cfg["lookback"],
                              gap=cfg["gap"], min_size=cfg["min_size"])
    cands = build_candidates(or_levels, pool, gate=cfg["gate"],
                              or_close=or_close)
    long_e, short_e, entry_p, force_e = generate_signals(
        bars, cands,
        entry_buffer=cfg["entry_buffer"],
        entry_window_end=cfg["latest_entry"],
        entry_location=cfg["entry_location"],
    )
    return bars, cands, long_e, short_e, entry_p, force_e


def run_locked(verbose=True):
    """Reproduce the locked-config metrics: 1394 trades, PF ~1.99, net ~$19,690.

    Returns a metrics dict. Used by the CLI ('run_locked') and the
    regression test (tests/test_locked.py).
    """
    cfg = LOCKED_CONFIG
    if verbose:
        print("Building locked pipeline (within_200 / g7 / m2 / 30 / 20)...",
              flush=True)
    bars, cands, long_e, short_e, entry_p, force_e = build_locked_pipeline()
    n_ent = int((long_e | short_e).sum())
    if verbose:
        print(f"  candidates: {len(cands):,}   entries: {n_ent}", flush=True)

    rec = _walk_trades_with_reason(bars, long_e, short_e, entry_p, force_e,
                                    stop_pts=cfg["stop_pts"],
                                    target_pts=cfg["target_pts"])
    pnl = _model_a_pnl(rec, slip_pts=cfg["slip_pts"],
                       commission_rt=cfg["commission_rt"])
    m = _locked_metrics(pnl)

    if verbose:
        print(f"\nLocked config metrics (Model A · slip {cfg['slip_pts']}pt/side · "
              f"${cfg['commission_rt']}/RT):", flush=True)
        print(f"  trades  = {m['n_trades']}")
        print(f"  WR      = {m['win_rate']*100:.2f}%")
        print(f"  net     = ${m['net_dollars']:+,.2f}")
        print(f"  PF      = {m['profit_factor']:.3f}")
        print(f"  max_dd  = ${m['max_drawdown']:+,.2f}")
        print(f"  Sharpe  = {m['sharpe']:.3f}")

        # Compare against frozen expected values
        print(f"\nReproduction check (tolerance shown in parens):")
        all_pass = True
        for key, (expected, tol) in LOCKED_EXPECTED.items():
            actual = m[key]
            ok = abs(actual - expected) <= tol
            if not ok: all_pass = False
            mark = "OK" if ok else "DRIFT"
            print(f"  {key:<14}: actual={actual:>12.4f}  expected={expected:>10.4f}  "
                  f"tol=±{tol}  [{mark}]")
        print(f"\nOverall: {'PASS' if all_pass else 'FAIL — config has drifted'}")
    return m


def run_with_config(cfg_name):
    """CLI entry — currently only knows 'locked', but extensible."""
    if cfg_name != "locked":
        raise SystemExit(f"Unknown config: {cfg_name!r}. Try 'locked'.")
    return run_locked()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    extra = sys.argv[2] if len(sys.argv) > 2 else None

    # `python -m src.vbt_backtest run --config locked` — paper-trade reproduction
    if cmd == "run" and extra == "--config":
        cfg_name = sys.argv[3] if len(sys.argv) > 3 else "locked"
        run_with_config(cfg_name)
        sys.exit(0)

    dispatch = {
        "run": run,
        "run_locked": run_locked,
        "sweep": sweep,
        "sweep_fine": sweep_fine,
        "heatmap": lambda: heatmap(extra),
        "walkforward_sweep": walkforward_sweep,
        "sensitivity": sensitivity,
        "pairwise_sweep": pairwise_sweep,
        "walkforward_candidates": walkforward_candidates,
        "risk_audit_c": risk_audit_c,
        "run_c_with_adx": run_c_with_adx,
        "run_c_adx_no_dir": run_c_adx_no_dir,
        "adx_threshold_sweep": adx_threshold_sweep,
    }
    dispatch.get(
        cmd,
        lambda: print(f"Unknown: {cmd}\nUsage: run | run_locked | "
                      f"run --config locked | sweep | sweep_fine | "
                      f"heatmap [file] | walkforward_sweep | sensitivity | "
                      f"pairwise_sweep | walkforward_candidates | risk_audit_c | "
                      f"run_c_with_adx | run_c_adx_no_dir | adx_threshold_sweep"),
    )()
