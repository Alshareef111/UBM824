"""
src/daily_setup.py — live daily-prep tool for the OR ±1 OCO model.

Each NY session this prints, in a 10-second-scannable block:
  - the day's OR_close (close of the 09:44 bar),
  - the eligibility category (BOTH / LONG-ONLY / SHORT-ONLY / NEITHER) with a
    live/paper action flag,
  - the resting OCO order spec (entry / target / stop) for the eligible side(s),
    in price AND MNQ ticks,
  - the trading window and force-flat time.

It REUSES the production signal path — no reimplementation of cluster logic:
  compute_opening_range / compute_or_close / build_cluster_pool from src.signals,
  parameters from src.vbt_backtest.LOCKED_CONFIG, data from src.paths.BARS_PARQUET.
``classify`` is two lines, inlined here so the live path never depends on
throwaway experimental code.

Eligibility (within_200 gate, prior-200-session pool, gap=7.0, min_size=2):
  LONG  eligible  ⇔ any cluster center < OR_close and |center − OR_close| ≤ 200
  SHORT eligible  ⇔ any cluster center > OR_close and |center − OR_close| ≤ 200

Orders (eligible side only; OCO, first-touch wins, fill cancels the other):
  LONG  buy-stop  = OR_close + 1.0 ; target = entry + 20 ; stop = entry − 30
  SHORT sell-stop = OR_close − 1.0 ; target = entry − 20 ; stop = entry + 30

Run from project root:
  python -m src.daily_setup --or-close 17850.25          # live (today)
  python -m src.daily_setup --check-date 2024-06-03       # self-check one session
  python -m src.daily_setup --selftest                    # 2 both/1 long/1 short/1 neither
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.data import load_processed_bars
from src.paths import BARS_PARQUET
from src.signals import build_cluster_pool, compute_opening_range, compute_or_close
from src.vbt_backtest import LOCKED_CONFIG

# ─── Parameters (single source of truth: production LOCKED_CONFIG) ──────────
LOOKBACK = LOCKED_CONFIG["lookback"]        # 200
GAP = LOCKED_CONFIG["gap"]                  # 7.0
MIN_SIZE = LOCKED_CONFIG["min_size"]        # 2
ENTRY_OFFSET = LOCKED_CONFIG["entry_buffer"]  # 1.0
TARGET_PTS = LOCKED_CONFIG["target_pts"]    # 20.0
STOP_PTS = LOCKED_CONFIG["stop_pts"]        # 30.0
PROXIMITY = 200.0                           # gate == "within_200"
assert LOCKED_CONFIG["gate"] == "within_200", "daily_setup assumes the within_200 gate"

TICK = 0.25                                 # MNQ tick size (points)
ENTRY_START = "09:45"                       # earliest entry (OR_close = 09:44 bar)
ENTRY_END = LOCKED_CONFIG["latest_entry"]   # "11:29"
FORCE_FLAT = "11:30"                        # force-flat at this bar's open
NY = ZoneInfo("America/New_York")

STALE_DAYS = 5                              # warn if data lags today by more than this

# Verbatim action flags per category (per spec).
FLAGS = {
    "BOTH": "TRADE LIVE  (both-armed: historically ~80% WR, PF 2.4)",
    "LONG-ONLY": "PAPER ONLY  (long-only: historically negative, PF 0.67 — sim only)",
    "SHORT-ONLY": "PAPER ONLY  (short-only: flat/small sample — sim only)",
    "NEITHER": "NO TRADE TODAY (no clusters within 200pt of OR close)",
}


# ─── Core logic ────────────────────────────────────────────────────────────


def classify(centers: np.ndarray, or_close: float) -> tuple[bool, bool]:
    """(long_eligible, short_eligible) for the day's cluster centers.

    A center arms LONG if it sits below OR_close, SHORT if above, in either
    case only when within the 200-pt proximity gate. A center exactly on
    OR_close arms neither side.
    """
    if centers.size == 0:
        return False, False
    diff = centers - or_close
    within = np.abs(diff) <= PROXIMITY
    return bool(np.any((diff < 0) & within)), bool(np.any((diff > 0) & within))


def category(long_elig: bool, short_elig: bool) -> str:
    if long_elig and short_elig:
        return "BOTH"
    if long_elig:
        return "LONG-ONLY"
    if short_elig:
        return "SHORT-ONLY"
    return "NEITHER"


def order_spec(or_close: float) -> dict:
    """Deterministic OCO bracket prices for both sides off OR_close."""
    long_entry = or_close + ENTRY_OFFSET
    short_entry = or_close - ENTRY_OFFSET
    return {
        "long": {
            "entry": long_entry,
            "target": long_entry + TARGET_PTS,
            "stop": long_entry - STOP_PTS,
        },
        "short": {
            "entry": short_entry,
            "target": short_entry - TARGET_PTS,
            "stop": short_entry + STOP_PTS,
        },
    }


# ─── Cluster-pool construction ─────────────────────────────────────────────


def _full_pool(or_levels: pd.DataFrame) -> pd.DataFrame:
    """Production cluster pool over the whole history (matches the backtest)."""
    return build_cluster_pool(or_levels, lookback=LOOKBACK, gap=GAP, min_size=MIN_SIZE)


def centers_for_session(pool: pd.DataFrame, session: date) -> np.ndarray:
    sub = pool[pool["session_date"] == session]
    return sub["center"].to_numpy(dtype=float)


def centers_for_today(or_levels: pd.DataFrame) -> tuple[np.ndarray, date]:
    """Clusters for a session *after* the last bar in the data.

    Appends a sentinel session that sorts last; build_cluster_pool's strictly
    trailing window (iloc[i-200:i]) then equals the last 200 real sessions —
    exactly the pool a live "today" would see (today's OR is never in its own
    pool). The sentinel's dummy OR values are never read.
    """
    last_session = or_levels.index[-1]
    sentinel = last_session + timedelta(days=1)
    sub = or_levels.tail(LOOKBACK).copy()
    sub.loc[sentinel, ["or_high", "or_low"]] = [np.nan, np.nan]
    pool = build_cluster_pool(sub, lookback=LOOKBACK, gap=GAP, min_size=MIN_SIZE)
    return centers_for_session(pool, sentinel), last_session


# ─── Rendering ─────────────────────────────────────────────────────────────

_W = 60
_RULE = "─" * _W
_DRULE = "═" * _W


def _ticks(points: float) -> int:
    return int(round(points / TICK))


def _order_block(label: str, trigger_name: str, side: dict, offset_sign: str,
                 tgt_sign: str, stop_sign: str) -> list[str]:
    o = side
    return [
        f"  {label:6s} {trigger_name:10s}@ {o['entry']:.2f}   "
        f"(OR {offset_sign}{ENTRY_OFFSET:.1f}  /  {offset_sign}{_ticks(ENTRY_OFFSET)} tk)",
        f"         target    @ {o['target']:.2f}   "
        f"({tgt_sign}{TARGET_PTS:.0f} pt   /  {tgt_sign}{_ticks(TARGET_PTS)} tk)",
        f"         stop      @ {o['stop']:.2f}   "
        f"({stop_sign}{STOP_PTS:.0f} pt   / {stop_sign}{_ticks(STOP_PTS)} tk)",
    ]


def render(or_close: float, cat: str, when: date, last_session: date,
           is_live: bool) -> str:
    spec = order_spec(or_close)
    lag = (when - last_session).days
    if lag > STALE_DAYS:
        stale = f"[!! STALE — {lag} days behind, regenerate the parquet]"
    else:
        stale = f"[OK — {lag} day{'s' if lag != 1 else ''} behind]"

    wd = when.strftime("%a %Y-%m-%d")
    lines = [
        _DRULE,
        f" DAILY SETUP — OR ±1 OCO          {wd} (NY)",
        _DRULE,
        f" OR close (09:44):  {or_close:.2f}",
        f" Data through:      {last_session}   {stale}",
        _RULE,
        f" Eligibility:  {cat}",
        f" ► {FLAGS[cat]}",
        _RULE,
    ]

    if cat == "NEITHER":
        lines += [" No orders. Stand down.", _DRULE]
        return "\n".join(lines)

    lines.append(" OCO — first touch wins, fill cancels the other side:" if cat == "BOTH"
                 else " Resting stop-entry bracket:")
    lines.append("")
    if cat in ("BOTH", "LONG-ONLY"):
        lines += _order_block("LONG", "buy-stop", spec["long"], "+", "+", "−")
        if cat == "LONG-ONLY":
            lines.append(" (no short — sell side not armed)")
        else:
            lines.append("")
    if cat in ("BOTH", "SHORT-ONLY"):
        lines += _order_block("SHORT", "sell-stop", spec["short"], "−", "−", "+")
        if cat == "SHORT-ONLY":
            lines.append(" (no long — buy side not armed)")
    lines += [
        _RULE,
        f" Window:  {ENTRY_START}–{ENTRY_END} NY     Force flat: {FORCE_FLAT} open",
        _DRULE,
    ]
    return "\n".join(lines)


# ─── Data plumbing ─────────────────────────────────────────────────────────


def _load():
    bars = load_processed_bars(BARS_PARQUET)
    or_levels = compute_opening_range(bars)
    or_close = compute_or_close(bars)
    # Session indices may come back as Timestamps depending on how the parquet
    # was generated; the rest of this tool treats sessions as datetime.date
    # (see _parse_date), so normalize here for uniform date arithmetic.
    or_levels.index = or_levels.index.map(lambda d: pd.Timestamp(d).date())
    or_close.index = or_close.index.map(lambda d: pd.Timestamp(d).date())
    return or_levels, or_close


def _parse_date(s: str) -> date:
    return pd.Timestamp(s).date()


# ─── Modes ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Setup:
    """Machine-readable twin of what ``render`` prints for one live session.

    The live order path (``step4_run_live.py``) consumes these fields directly,
    so what the operator SEES in daily_setup is exactly what gets TRADED.
    """
    or_close: float            # close of the 09:44 NY bar (operator-supplied live)
    category: str              # BOTH / LONG-ONLY / SHORT-ONLY / NEITHER
    long_eligible: bool
    short_eligible: bool
    or_plus_1: float           # LONG  buy-stop  trigger = OR_close + ENTRY_OFFSET
    or_minus_1: float          # SHORT sell-stop trigger = OR_close − ENTRY_OFFSET
    last_session: date         # newest session in the data (staleness check)
    spec: dict                 # order_spec(): entry/target/stop for both sides

    @property
    def tradeable(self) -> bool:
        """Live-tradeable ⇔ BOTH sides armed.

        daily_setup classifies LONG-ONLY / SHORT-ONLY as PAPER ONLY (negative /
        flat historical expectancy) and NEITHER as no-trade; only the both-armed
        straddle (~80% WR, PF 2.4 historically) is approved for a live account.
        A both-sided straddle is also the only setup the step4 placer expresses —
        it always rests a buy-stop AND a sell-stop — so this gate must be BOTH.
        """
        return self.category == "BOTH"


def compute_setup(or_close: float) -> Setup:
    """Live OR ±1 OCO setup for *today*, off the operator-supplied 09:44 OR close.

    Reuses the exact production live path (``centers_for_today`` → today's OR is
    never in its own 200-session pool), so this structured result matches what
    ``render`` prints. ``or_plus_1`` / ``or_minus_1`` are read back out of
    ``order_spec`` so the trigger prices stay single-sourced.
    """
    or_levels, _ = _load()
    centers, last_session = centers_for_today(or_levels)
    le, se = classify(centers, or_close)
    spec = order_spec(or_close)
    return Setup(
        or_close=float(or_close),
        category=category(le, se),
        long_eligible=le,
        short_eligible=se,
        or_plus_1=spec["long"]["entry"],
        or_minus_1=spec["short"]["entry"],
        last_session=last_session,
        spec=spec,
    )


def run_live(or_close: float) -> None:
    s = compute_setup(or_close)
    today = datetime.now(NY).date()
    print(render(s.or_close, s.category, today, s.last_session, is_live=True))


def _evaluate(or_levels, or_close_series, pool, when: date, or_close_override):
    """Return (or_close, category, long_elig, short_elig, spec) for one session."""
    if or_close_override is not None:
        oc = float(or_close_override)
    else:
        if when not in or_close_series.index or pd.isna(or_close_series.loc[when]):
            raise ValueError(f"No 09:44 OR_close in data for {when}; pass --or-close")
        oc = float(or_close_series.loc[when])
    centers = centers_for_session(pool, when)
    le, se = classify(centers, oc)
    return oc, category(le, se), le, se, order_spec(oc)


def check_date(when: date, or_close_override=None, verbose=True) -> bool:
    """Cross-reference one session against the locked OR-OCO reference.

    PASS ⇔ same eligibility category, same armed side(s), and OR-based order
    prices within 0.01 pt of the reference implementation.
    """
    # Reference oracle — imported ONLY in the self-check, never on the live path.
    from src.experimental.locked_full_or_oco import (
        ENTRY_OFFSET as R_OFF,
        STOP_PTS as R_STOP,
        TARGET_PTS as R_TGT,
        classify as ref_classify,
    )

    or_levels, or_close_series = _load()
    pool = _full_pool(or_levels)
    oc, cat, le, se, spec = _evaluate(or_levels, or_close_series, pool, when, or_close_override)

    centers = centers_for_session(pool, when)
    r_le, r_se = ref_classify(centers, oc)
    r_cat = category(r_le, r_se)
    # Reference's deterministic order prices, from its own constants.
    r_long = {"entry": oc + R_OFF, "target": oc + R_OFF + R_TGT, "stop": oc + R_OFF - R_STOP}
    r_short = {"entry": oc - R_OFF, "target": oc - R_OFF - R_TGT, "stop": oc - R_OFF + R_STOP}

    price_dev = max(
        abs(spec["long"]["entry"] - r_long["entry"]),
        abs(spec["long"]["target"] - r_long["target"]),
        abs(spec["long"]["stop"] - r_long["stop"]),
        abs(spec["short"]["entry"] - r_short["entry"]),
        abs(spec["short"]["target"] - r_short["target"]),
        abs(spec["short"]["stop"] - r_short["stop"]),
    )
    ok = (cat == r_cat) and (le == r_le) and (se == r_se) and (price_dev <= 0.01)

    if verbose:
        print(f"  {when}  OR_close={oc:>10.2f}  mine={cat:<10s} ref={r_cat:<10s} "
              f"sides=({int(le)},{int(se)})/({int(r_le)},{int(r_se)})  "
              f"max|Δprice|={price_dev:.4f}  -> {'PASS' if ok else 'FAIL'}")
    return ok


def selftest() -> None:
    or_levels, or_close_series = _load()
    pool = _full_pool(or_levels)
    sessions = or_levels.index.tolist()

    buckets: dict[str, list[date]] = {"BOTH": [], "LONG-ONLY": [], "SHORT-ONLY": [], "NEITHER": []}
    for i, sd in enumerate(sessions):
        if i < LOOKBACK:
            continue
        if sd not in or_close_series.index or pd.isna(or_close_series.loc[sd]):
            continue
        oc = float(or_close_series.loc[sd])
        le, se = classify(centers_for_session(pool, sd), oc)
        buckets[category(le, se)].append(sd)

    print("Eligibility census (post-warm-up sessions):")
    for k, v in buckets.items():
        print(f"  {k:11s}: {len(v)}")

    want = {"BOTH": 2, "LONG-ONLY": 1, "SHORT-ONLY": 1, "NEITHER": 1}
    rng = random.Random(42)
    picks: list[date] = []
    for cat, n in want.items():
        pool_dates = buckets[cat]
        if len(pool_dates) < n:
            raise SystemExit(f"Not enough {cat} sessions to sample ({len(pool_dates)} < {n})")
        picks += rng.sample(pool_dates, n)

    print(f"\nSelf-check on {len(picks)} sampled sessions "
          "(2 both / 1 long-only / 1 short-only / 1 neither):")
    results = [check_date(d, verbose=True) for d in sorted(picks)]
    n_pass = sum(results)
    print(f"\n{'='*60}\n  RESULT: {n_pass}/{len(results)} PASS — "
          f"{'ALL PASS ✓' if n_pass == len(results) else 'FAILURES PRESENT ✗'}\n{'='*60}")
    if n_pass != len(results):
        raise SystemExit(1)


# ─── CLI ───────────────────────────────────────────────────────────────────


def main() -> None:
    # Windows consoles default to cp1252, which can't encode the Δ/✓ glyphs
    # this tool prints. Force UTF-8 output where the stream supports it.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="OR ±1 OCO daily-prep tool")
    ap.add_argument("--or-close", type=float, default=None,
                    help="OR_close (close of the 09:44 NY bar). Required for live mode.")
    ap.add_argument("--check-date", type=str, default=None,
                    help="Self-check a single historical session (YYYY-MM-DD).")
    ap.add_argument("--selftest", action="store_true",
                    help="Run the 5-session self-check (2 both/1 long/1 short/1 neither).")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.check_date:
        when = _parse_date(args.check_date)
        if check_date(when, or_close_override=args.or_close, verbose=True):
            print("PASS")
        else:
            raise SystemExit("FAIL")
    else:
        if args.or_close is None:
            ap.error("live mode needs --or-close (close of the 09:44 NY bar)")
        run_live(args.or_close)


if __name__ == "__main__":
    main()
