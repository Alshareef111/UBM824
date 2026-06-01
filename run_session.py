#!/usr/bin/env python3
"""
Session scheduler for MNQ ORB (account Sim101) -- the missing timer.

Arms itself, sleeps on the wall clock, and runs the live loop with NO human in
the entry path:
  - waits until 09:45:00 ET (just after the 09:44 NY 1-min bar closes)
  - gets that bar's CLOSE (auto-fetch from CrossTrade, or --or-close override)
  - hands it to step4_run_live.py to gate + place
  - waits until 11:30:00 ET and runs force_flat.py

It does not reimplement anything -- it composes the pieces you already have:
    run_session.py  ->  step4_run_live.py (gate + place)  ->  force_flat.py (flat)

OR close source:
  default       -> POST /v1/api/market/bars {instrument, periodType:"minute",
                   period:1, daysBack, limit}
                   -> {"bars":[{time,open,high,low,close,volume}, ...]}
                   Pulls from the NT8 feed (NOT Databento), account-agnostic.
                   Read the bar whose ET label == OR_BAR_LABEL, take its close.
  --or-close X  -> use X verbatim, skip the fetch (offline step4 tests, parquet
                   replay, manual forcing).

All timing is America/New_York (DST-correct via zoneinfo).

Modes:
  --dry-run     no real orders; on a fetch, prints the recent bars so you can
                calibrate OR_BAR_LABEL (your feed's timestamp convention)
  --test-in N   fire ENTRY N seconds from now, then force-flat
                TEST_FLAT_AFTER_SECS later (add --skip-flat for entry-only).
                Smoke-tests the full sequence without waiting for 09:45/11:30.
  --flat-now    run force_flat immediately, then exit
  --skip-flat   no force-flat leg

WINDOWS: `pip install tzdata` first (Windows ships no IANA tz database).
Keep the laptop awake + NT8 and the CrossTrade add-on connected across the whole
09:45->11:30 ET window (~16:45->18:30 Jeddah during US summer time).
"""
import os
import re
import sys
import time
import argparse
import subprocess
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import requests

try:
    ET = ZoneInfo("America/New_York")
except Exception:
    sys.exit("Missing tz database. On Windows run:  pip install tzdata")

BASE = "https://app.crosstrade.io/v1/api"
ACCOUNT = "Sim101"
INSTRUMENT = "MNQ 06-26"        # confirm vs your NT8 instrument string + the mid-June roll

# ET HH:MM label (AFTER UTC->ET conversion) of the bar whose CLOSE is the OR close.
# _bar_et_label converts the feed's UTC stamp to ET, so this value is in ET and stays
# correct across the DST changeover -- calibrate it ONCE, no re-tuning twice a year.
# CALIBRATE from a --dry-run ET= column: NinjaTrader often stamps a minute bar at its
# CLOSE, so the 09:44 *period* may show ET "09:45". Use whatever the ET column shows
# for that period (a COMPLETE bar, never the forming current minute).
OR_BAR_LABEL = "09:45"  # calibrated 2026-06-01: NT8 feed is close-stamped (the 09:30 cash-open volume spike lands on the 09:31 ET label), so the 09:44 period reads ET 09:45

ENTRY_TIME = dtime(9, 45)       # place the bracket at this ET wall time
FLAT_TIME = dtime(11, 30)       # force-flat at this ET wall time
BAR_SETTLE_SECS = 2             # fire a couple seconds past the minute so the bar is final
TEST_FLAT_AFTER_SECS = 15       # in --test-in, flat this long after entry (room for a fill)

PYTHON = sys.executable         # same interpreter -> same venv for the subprocesses
HERE = os.path.dirname(os.path.abspath(__file__))


def _headers():
    tok = os.environ.get("CROSSTRADE_TOKEN")
    if not tok:
        sys.exit("CROSSTRADE_TOKEN env var not set")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def now_et():
    return datetime.now(ET)


def next_et(t):
    """Next future ET datetime at wall-clock time t (today if still ahead, else tomorrow)."""
    n = now_et()
    c = n.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    return c if c > n else c + timedelta(days=1)


def sleep_until(target, label):
    while True:
        d = (target - now_et()).total_seconds()
        if d <= 0:
            return
        print(f"[{now_et():%H:%M:%S} ET] {d:,.0f}s -> {label} ({target:%H:%M:%S} ET)", flush=True)
        time.sleep(min(d, 30))   # wake every 30s so clock drift / laptop resume is caught quickly


def fetch_bars(limit=30):
    body = {"instrument": INSTRUMENT, "periodType": "minute", "period": 1, "daysBack": 1, "limit": limit}
    r = requests.post(f"{BASE}/market/bars", headers=_headers(), json=body, timeout=10)
    r.raise_for_status()
    return r.json().get("bars", [])


def _bar_et_label(t):
    """ET HH:MM for a feed bar stamp (UTC '...Z', .NET 100-ns fraction) -- DST-correct.
    3.11's fromisoformat rejects >6 fractional digits, so strip the fraction first."""
    s = re.sub(r"\.\d+", "", str(t).strip()).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ET).strftime("%H:%M")


def find_or_close(bars):
    for b in bars:
        if _bar_et_label(b.get("time")) == OR_BAR_LABEL:
            return float(b["close"]), b
    return None, None


def resolve_or_close(dry, override):
    """OR close, or None to abort. Uses --or-close verbatim if given, else fetches
    the OR_BAR_LABEL bar from /market/bars."""
    if override is not None:
        print(f"[{now_et():%H:%M:%S} ET] OR close = {override}  (override via --or-close)", flush=True)
        return float(override)
    bars = fetch_bars()
    if dry:
        print("recent 1-min bars (UTC stamp -> ET; confirm which CLOSE is your OR_BAR_LABEL):", flush=True)
        for b in bars[-8:]:
            print(f"   {b.get('time')}  ET={_bar_et_label(b.get('time'))}  close={b.get('close')}", flush=True)
    orc, bar = find_or_close(bars)
    if orc is None:
        print(f"!! no bar labeled {OR_BAR_LABEL} ET in the response -> NOT placing (fail-safe). "
              f"Recalibrate OR_BAR_LABEL from the bars above.", flush=True)
        return None
    print(f"[{now_et():%H:%M:%S} ET] OR close = {orc}  (bar time={bar.get('time')})", flush=True)
    return orc


def do_entry(dry, override):
    orc = resolve_or_close(dry, override)
    if orc is None:
        return
    cmd = [PYTHON, "step4_run_live.py", "--or-close", str(orc)] + (["--dry-run"] if dry else [])
    print("   ->", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=HERE, check=False)


def do_flat(dry):
    cmd = [PYTHON, "force_flat.py"] + (["--dry-run"] if dry else [])
    print("   ->", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=HERE, check=False)


def main():
    ap = argparse.ArgumentParser(description="MNQ ORB session scheduler (ET-timed)")
    ap.add_argument("--or-close", type=float, default=None,
                    help="override: use this OR close verbatim, skip the fetch")
    ap.add_argument("--dry-run", action="store_true", help="no real orders; prints bars to calibrate")
    ap.add_argument("--test-in", type=int, metavar="N", help="fire ENTRY N sec from now (then flat)")
    ap.add_argument("--flat-now", action="store_true", help="run force-flat immediately, then exit")
    ap.add_argument("--skip-flat", action="store_true", help="skip the force-flat leg")
    a = ap.parse_args()

    print(f"[{now_et():%Y-%m-%d %H:%M:%S %Z}] armed  acct={ACCOUNT}  instr={INSTRUMENT}  "
          f"dry={a.dry_run}  override={a.or_close}", flush=True)

    if a.flat_now:
        do_flat(a.dry_run)
        return

    if a.test_in is not None:
        sleep_until(now_et() + timedelta(seconds=a.test_in), "TEST entry")
        do_entry(a.dry_run, a.or_close)
        if not a.skip_flat:
            sleep_until(now_et() + timedelta(seconds=TEST_FLAT_AFTER_SECS), "TEST force-flat")
            do_flat(a.dry_run)
        return

    if now_et().weekday() >= 5:
        sys.exit("weekend in ET -- no session today")
    # NOTE: weekday guard only. Add a holiday calendar (e.g. pandas_market_calendars XNYS)
    # before running this fully unattended, or it will arm on market holidays.

    sleep_until(next_et(ENTRY_TIME) + timedelta(seconds=BAR_SETTLE_SECS), "entry")
    do_entry(a.dry_run, a.or_close)

    if not a.skip_flat:
        sleep_until(next_et(FLAT_TIME), "force-flat")
        do_flat(a.dry_run)

    print(f"[{now_et():%H:%M:%S} ET] session done", flush=True)


if __name__ == "__main__":
    main()
