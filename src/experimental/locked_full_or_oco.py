"""
Full 7-year OR_close +/- 1 OCO stop-entry backtest with per-session
eligibility classification.

Spec:
- Period 2019-05-06 -> 2026-05-11 (warm-up ~200 sessions; first traded ~2020).
- Cluster pool: prior 200 sessions' OR levels, chain-gap = 7.0, min size = 2.
  (build_cluster_pool from src.signals; today's OR not in its own pool.)
- OR_close = close of the 09:44 NY bar (compute_or_close from src.signals).
- Eligibility per session:
    LONG  eligible if any cluster center is BELOW OR_close and within 200 pt.
    SHORT eligible if any cluster center is ABOVE OR_close and within 200 pt.
- At 09:45:00, arm only the eligible side(s):
    buy-stop  = OR_close + 1.0
    sell-stop = OR_close - 1.0
- OCO; first-touch wins (close >= open as within-bar tiebreak proxy).
- Bracket: target = fill +/- 20, stop = fill -/+ 30 (asymmetric R:R).
- Entry bar IS checked for stop/target; stop-first conservative when both
  in range. Force flat at the 11:30 NY bar's OPEN price if still open after
  the 11:29 bar.
- Costs: $2 commission round-trip + 0.5 pt total slip per trade.
- Production code untouched. Outputs to results/archive/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Make project importable when run as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data import load_processed_bars
from src.signals import build_cluster_pool, compute_opening_range, compute_or_close

ARCHIVE_DIR = PROJECT_ROOT / "results" / "archive"

# --- Config ----------------------------------------------------------------
LOOKBACK = 200
CLUSTER_GAP = 7.0
MIN_CLUSTER_SIZE = 2
PROXIMITY_PTS = 200.0
ENTRY_OFFSET = 1.0
TARGET_PTS = 20.0
STOP_PTS = 30.0

COMMISSION_PER_RT = 2.0  # $ per round-trip
SLIP_PTS_RT = 0.5        # total round-trip slippage in points
PT_VALUE = 2.0           # $ per point per MNQ contract

ENTRY_START = "09:45"
ENTRY_END = "11:29"
FORCE_FLAT = "11:30"

PERIOD_START = pd.Timestamp("2019-05-06", tz="America/New_York")
PERIOD_END = pd.Timestamp("2026-05-12", tz="America/New_York")  # exclusive

# --- Expected numbers (prior run of the identical analysis) ----------------
EXPECTED = {
    "trades": 1429,
    "wr_pct": 74.11,
    "net": 15844.0,
    "pf": 1.685,
    "max_dd": -637.50,
    "sharpe": 4.02,
    "long": 875,
    "short": 554,
    "both_armed": 1116,
    "long_only": 253,
    "short_only": 62,
}


# --- Eligibility -----------------------------------------------------------

def classify(clusters_centers: np.ndarray, or_close: float) -> tuple[bool, bool]:
    """(long_eligible, short_eligible) at this OR_close given the day's clusters."""
    if clusters_centers.size == 0:
        return False, False
    diff = clusters_centers - or_close
    within = np.abs(diff) <= PROXIMITY_PTS
    long_elig = bool(np.any((diff < 0) & within))
    short_elig = bool(np.any((diff > 0) & within))
    return long_elig, short_elig


# --- Single-session OCO walk ----------------------------------------------

def run_session(
    bars_session: pd.DataFrame,
    or_close: float,
    long_armed: bool,
    short_armed: bool,
) -> dict | None:
    """Walk one session's bars; return a trade dict or None if no fill."""
    if not (long_armed or short_armed):
        return None

    entry_window = bars_session.between_time(ENTRY_START, ENTRY_END, inclusive="both")
    if entry_window.empty:
        return None

    buy_trigger = or_close + ENTRY_OFFSET
    sell_trigger = or_close - ENTRY_OFFSET

    entry_ts = side = entry_price = None
    for ts, bar in entry_window.iterrows():
        long_hit = long_armed and bar["high"] >= buy_trigger
        short_hit = short_armed and bar["low"] <= sell_trigger
        if long_hit and short_hit:
            side = "long" if bar["close"] >= bar["open"] else "short"
        elif long_hit:
            side = "long"
        elif short_hit:
            side = "short"
        else:
            continue
        entry_price = buy_trigger if side == "long" else sell_trigger
        entry_ts = ts
        break

    if entry_ts is None:
        return None

    if side == "long":
        stop_price = entry_price - STOP_PTS
        target_price = entry_price + TARGET_PTS
    else:
        stop_price = entry_price + STOP_PTS
        target_price = entry_price - TARGET_PTS

    # Bracket walk (entry bar included; stop-first when both in range).
    post = bars_session[bars_session.index >= entry_ts]
    exit_window = post.between_time(ENTRY_START, ENTRY_END, inclusive="both")

    exit_ts = exit_price = exit_reason = None
    for ts, bar in exit_window.iterrows():
        if side == "long":
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
        force = post.between_time(FORCE_FLAT, FORCE_FLAT, inclusive="both")
        if not force.empty:
            exit_ts = force.index[0]
            exit_price = force.iloc[0]["open"]
            exit_reason = "force_close"
        else:
            # No 11:30 bar present (data edge); use last available close.
            last_ts = exit_window.index[-1]
            exit_ts = last_ts
            exit_price = float(exit_window.loc[last_ts, "close"])
            exit_reason = "force_close"

    pnl_pts = (exit_price - entry_price) if side == "long" else (entry_price - exit_price)
    pnl_pts -= SLIP_PTS_RT
    pnl_dollars = pnl_pts * PT_VALUE - COMMISSION_PER_RT

    return {
        "side": side,
        "entry_ts": entry_ts,
        "entry_price": round(float(entry_price), 4),
        "stop_price": round(float(stop_price), 4),
        "target_price": round(float(target_price), 4),
        "exit_ts": exit_ts,
        "exit_price": round(float(exit_price), 4),
        "exit_reason": exit_reason,
        "pnl_points": round(float(pnl_pts), 4),
        "pnl_dollars": round(float(pnl_dollars), 2),
    }


# --- Headline + breakdown reporting ---------------------------------------

def headline(trades_df: pd.DataFrame) -> dict:
    n = len(trades_df)
    wins = int((trades_df["pnl_dollars"] > 0).sum())
    losses_pnl = trades_df.loc[trades_df["pnl_dollars"] < 0, "pnl_dollars"]
    wins_pnl = trades_df.loc[trades_df["pnl_dollars"] > 0, "pnl_dollars"]
    net = float(trades_df["pnl_dollars"].sum())
    gross_p = float(wins_pnl.sum())
    gross_l = float(losses_pnl.sum())
    pf = gross_p / abs(gross_l) if gross_l < 0 else float("inf")
    cum = trades_df.sort_values("entry_ts")["pnl_dollars"].cumsum().to_numpy()
    peak = np.maximum.accumulate(cum)
    max_dd = float((cum - peak).min())
    mean_t = float(trades_df["pnl_dollars"].mean())
    std_t = float(trades_df["pnl_dollars"].std(ddof=1))
    sharpe = mean_t / std_t * np.sqrt(252) if std_t > 0 else float("nan")
    return {
        "n": n,
        "wr_pct": wins / n * 100 if n else 0.0,
        "net": net,
        "pf": pf,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "long": int((trades_df["side"] == "long").sum()),
        "short": int((trades_df["side"] == "short").sum()),
    }


def consistency_check(actual: dict, elig_counts: dict) -> bool:
    """Compare headline + eligibility counts to EXPECTED; return True if all OK."""
    print("\n========== CONSISTENCY CHECK ==========")
    print(f"{'metric':12s} {'actual':>12s} {'expected':>12s} {'delta':>10s}  status")
    ok = True

    def chk(name, a, e, tol):
        nonlocal ok
        delta = a - e
        bad = abs(delta) > tol
        if bad:
            ok = False
        print(
            f"{name:12s} {str(round(a, 3)):>12s} {str(round(e, 3)):>12s} "
            f"{f'{delta:+.3f}':>10s}  {'MISMATCH' if bad else 'OK'}"
        )

    chk("trades", actual["n"], EXPECTED["trades"], 0)
    chk("WR%", actual["wr_pct"], EXPECTED["wr_pct"], 0.05)
    chk("net$", actual["net"], EXPECTED["net"], 50)
    chk("PF", actual["pf"], EXPECTED["pf"], 0.005)
    chk("MaxDD$", actual["max_dd"], EXPECTED["max_dd"], 50)
    chk("sharpe", actual["sharpe"], EXPECTED["sharpe"], 0.05)
    chk("long", actual["long"], EXPECTED["long"], 0)
    chk("short", actual["short"], EXPECTED["short"], 0)
    chk("both_armed", elig_counts.get("both_armed", 0), EXPECTED["both_armed"], 0)
    chk("long_only", elig_counts.get("long_only", 0), EXPECTED["long_only"], 0)
    chk("short_only", elig_counts.get("short_only", 0), EXPECTED["short_only"], 0)
    return ok


def print_breakdown(trades_df: pd.DataFrame) -> None:
    print("\n========== BREAKDOWN BY ELIGIBILITY ==========")
    hdr = (
        f"{'category':14s} {'n':>5s} {'WR%':>7s} {'net$':>11s} {'PF':>7s} "
        f"{'%tgt':>6s} {'%stop':>6s} {'%force':>7s} {'avg$/trade':>11s}"
    )
    print(hdr)
    print("-" * len(hdr))
    for cat in ("both_armed", "long_only", "short_only"):
        sub = trades_df[trades_df["eligibility"] == cat]
        nn = len(sub)
        if nn == 0:
            print(f"{cat:14s}  (no trades)")
            continue
        wins = int((sub["pnl_dollars"] > 0).sum())
        wr = wins / nn * 100
        net = float(sub["pnl_dollars"].sum())
        gp = float(sub.loc[sub["pnl_dollars"] > 0, "pnl_dollars"].sum())
        gl = float(sub.loc[sub["pnl_dollars"] < 0, "pnl_dollars"].sum())
        pf = gp / abs(gl) if gl < 0 else float("inf")
        ex = sub["exit_reason"].value_counts()
        pt = ex.get("target", 0) / nn * 100
        ps = ex.get("stop", 0) / nn * 100
        pfc = ex.get("force_close", 0) / nn * 100
        avg = float(sub["pnl_dollars"].mean())
        print(
            f"{cat:14s} {nn:>5d} {wr:>6.2f}% ${net:>10,.2f} {pf:>7.3f} "
            f"{pt:>5.1f}% {ps:>5.1f}% {pfc:>6.1f}% ${avg:>10.2f}"
        )


def print_neither_by_year(elig_df: pd.DataFrame) -> None:
    print("\n========== NEITHER-ELIGIBLE SESSIONS BY YEAR ==========")
    neither = elig_df[elig_df["eligibility"] == "neither"]
    if neither.empty:
        print("  (none)")
        return
    by_year = (
        neither.assign(year=pd.to_datetime(neither["session_date"]).dt.year)
        .groupby("year")
        .size()
    )
    for y, c in by_year.items():
        print(f"  {y}: {c}")
    print(f"  total: {len(neither)}")


# --- Main ------------------------------------------------------------------

def main() -> None:
    print("Loading processed bars ...", flush=True)
    bars = load_processed_bars()
    bars = bars[(bars.index >= PERIOD_START) & (bars.index < PERIOD_END)]
    print(f"  {len(bars):,} bars across {bars['session_date'].nunique():,} sessions")
    print(f"  range: {bars.index.min()} -> {bars.index.max()}")

    print("Computing OR + OR_close ...", flush=True)
    or_levels = compute_opening_range(bars)
    or_close = compute_or_close(bars)
    print(f"  OR computed for {len(or_levels):,} sessions")

    print(
        f"Building cluster pool (lookback={LOOKBACK}, gap={CLUSTER_GAP}, "
        f"min_size={MIN_CLUSTER_SIZE}) ...",
        flush=True,
    )
    pool = build_cluster_pool(
        or_levels, lookback=LOOKBACK, gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE
    )
    print(
        f"  {len(pool):,} clusters across "
        f"{pool['session_date'].nunique():,} sessions"
    )

    # Fast per-session lookups.
    bars_by_session = {d: g for d, g in bars.groupby("session_date", sort=True)}
    pool_centers_by_session: dict = {
        d: g["center"].to_numpy() for d, g in pool.groupby("session_date", sort=True)
    }

    sessions = or_levels.index.tolist()

    trades: list[dict] = []
    elig_rows: list[dict] = []

    print(f"Walking {len(sessions) - LOOKBACK:,} post-warm-up sessions ...", flush=True)
    for i, sd in enumerate(sessions):
        if i < LOOKBACK:
            continue
        if sd not in bars_by_session or sd not in or_close.index:
            continue
        oc = or_close.loc[sd]
        if pd.isna(oc):
            continue
        oc = float(oc)

        centers = pool_centers_by_session.get(sd, np.array([], dtype=float))
        long_elig, short_elig = classify(centers, oc)

        if long_elig and short_elig:
            cat = "both_armed"
        elif long_elig:
            cat = "long_only"
        elif short_elig:
            cat = "short_only"
        else:
            cat = "neither"
        elig_rows.append({"session_date": sd, "eligibility": cat, "or_close": oc})

        if cat == "neither":
            continue

        trade = run_session(bars_by_session[sd], oc, long_elig, short_elig)
        if trade is None:
            continue
        trade["session_date"] = sd
        trade["eligibility"] = cat
        trades.append(trade)

    trades_df = pd.DataFrame(trades)
    elig_df = pd.DataFrame(elig_rows)

    if trades_df.empty:
        print("\n!! No trades produced. Aborting before reporting.")
        return

    h = headline(trades_df)
    elig_counts = elig_df["eligibility"].value_counts().to_dict()

    print("\n========== HEADLINE ==========")
    print(f"  trades:   {h['n']}")
    print(f"  WR:       {h['wr_pct']:.2f}%")
    print(f"  net:      ${h['net']:,.2f}")
    print(f"  PF:       {h['pf']:.3f}")
    print(f"  max DD:   ${h['max_dd']:,.2f}")
    print(f"  sharpe:   {h['sharpe']:.2f}")
    print(f"  long:     {h['long']}")
    print(f"  short:    {h['short']}")
    print("\n  eligibility (sessions):")
    for k in ("both_armed", "long_only", "short_only", "neither"):
        print(f"    {k:11s}: {elig_counts.get(k, 0)}")

    ok = consistency_check(h, elig_counts)

    # Always persist outputs for inspection.
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    trades_out = ARCHIVE_DIR / "trades_locked_full_or_oco.parquet"
    elig_out = ARCHIVE_DIR / "eligibility_locked_full_or_oco.parquet"
    trades_df.to_parquet(trades_out, index=False)
    elig_df.to_parquet(elig_out, index=False)
    print(f"\nSaved: {trades_out}")
    print(f"Saved: {elig_out}")

    if not ok:
        print(
            "\n!! Headline / eligibility numbers DIVERGE from the prior run. "
            "Stopping before the breakdown so the discrepancy can be diagnosed. "
            "Outputs above are written to results/archive/ for inspection."
        )
        return

    print_breakdown(trades_df)
    print_neither_by_year(elig_df)


if __name__ == "__main__":
    main()
