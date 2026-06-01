#!/usr/bin/env python3
"""
check_feed_alignment.py -- READ-ONLY pre-live alignment check (Part 1).

Confirms the LIVE NT8 OR close (/market/bars, the close-stamped 09:45 ET bar) is on
the same price SCALE and the same bar PERIOD as the backtest's compute_or_close
(Panama back-adjusted Databento parquet), for sessions present in BOTH sources.

Why: the earlier spot-check compared DIFFERENT sessions (live Monday vs Databento's
prior Friday), so the 47-pt gap was just price drift, not an offset. This isolates
the offset by comparing the SAME session date in both sources.

Reuses run_session's UTC->ET parse (_bar_et_label) + BASE/INSTRUMENT/_headers, and
daily_setup._load() (the production compute_or_close path). It only reads
/market/bars and the parquet -- NO order endpoints, NO writes.

Interpretation (this script reports; it does NOT change anything):
  diffs ~0 and consistent  -> ALIGNED: scale + period both good; safe to arm re: this.
  diffs ~ a constant C      -> Panama SCALE offset of C; within_200 is shifted by C.
                               Fix later = map live OR close onto the cluster scale (+C).
  diffs VARY by session      -> period/stamp mismatch (OR_BAR_LABEL off-by-one, or the
                               two sources stamp differently). Flag for investigation.

Run:  python check_feed_alignment.py [--days-back 7] [--limit 20000]
"""
import argparse
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# Reuse the live scheduler's tested pieces (these resolve to the centralized
# xt_config values once Part 2 lands -- run_session re-exports them).
from run_session import BASE, INSTRUMENT, OR_BAR_LABEL, ET, _bar_et_label, _headers
from src.daily_setup import _load  # calls the production compute_or_close

TIMEOUT = 20


def fetch_bars_window(days_back, limit):
    """READ-ONLY: the same /market/bars call run_session uses, widened to span
    several sessions (run_session.fetch_bars hardcodes daysBack=1)."""
    body = {"instrument": INSTRUMENT, "periodType": "minute", "period": 1,
            "daysBack": days_back, "limit": limit}
    r = requests.post(f"{BASE}/market/bars", headers=_headers(), json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("bars", [])


def _bar_et_date(t):
    """ET calendar date for a feed bar stamp -- mirrors run_session._bar_et_label's
    UTC->ET parse (which returns only HH:MM, so the date is derived here)."""
    s = re.sub(r"\.\d+", "", str(t).strip()).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ET).date()


def nt8_or_closes(bars):
    """{session_date: close} for the OR bar (ET time == OR_BAR_LABEL) per session."""
    out = {}
    for b in bars:
        if _bar_et_label(b.get("time")) == OR_BAR_LABEL:
            d = _bar_et_date(b.get("time"))
            if d is not None:
                out[d] = float(b["close"])  # one OR bar per session
    return out


def main():
    ap = argparse.ArgumentParser(description="READ-ONLY NT8<->Databento OR-close alignment check")
    ap.add_argument("--days-back", type=int, default=7)
    ap.add_argument("--limit", type=int, default=20000)
    args = ap.parse_args()

    bars = fetch_bars_window(args.days_back, args.limit)
    nt8 = nt8_or_closes(bars)
    _, or_close_series = _load()
    db_dates = set(or_close_series.dropna().index)

    if bars:
        print(f"NT8 window: {len(bars)} bars, "
              f"{_bar_et_date(bars[0].get('time'))} .. {_bar_et_date(bars[-1].get('time'))}")
    print(f"NT8 sessions with an OR ({OR_BAR_LABEL} ET) bar: {sorted(nt8)}")

    overlap = sorted(d for d in nt8 if d in db_dates)
    print(f"Overlap with parquet (latest DB session {max(db_dates)}): {overlap}")
    if not overlap:
        print("No overlapping sessions -- widen --days-back/--limit, or the parquet lags the feed.")
        return

    print(f"\n{'session':<12}{'NT8 close':>13}{'Databento':>13}{'diff(NT8-DB)':>15}")
    diffs = []
    for d in overlap:
        nt8_c = nt8[d]
        db_c = float(or_close_series.loc[d])
        diff = nt8_c - db_c
        diffs.append(diff)
        print(f"{str(d):<12}{nt8_c:>13.2f}{db_c:>13.2f}{diff:>15.2f}")

    lo, hi, mean = min(diffs), max(diffs), sum(diffs) / len(diffs)
    spread = hi - lo
    print(f"\ndiff stats: mean={mean:.2f}  min={lo:.2f}  max={hi:.2f}  spread={spread:.2f}  n={len(diffs)}")
    if spread <= 1.0 and abs(mean) <= 1.0:
        print("READ: diffs ~0 and consistent -> ALIGNED (scale + period both good).")
    elif spread <= 1.0:
        print(f"READ: steady offset ~{mean:.2f} pt -> Panama SCALE offset; within_200 is shifted by ~{mean:.2f}. "
              "Fix later = add this offset to the live OR close before gating. Change nothing now.")
    else:
        print(f"READ: diffs VARY (spread {spread:.2f}) -> period/stamp mismatch "
              "(OR_BAR_LABEL off-by-one?). Investigate before arming.")


if __name__ == "__main__":
    main()
