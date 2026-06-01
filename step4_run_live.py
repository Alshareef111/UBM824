#!/usr/bin/env python3
"""
step4_run_live.py — place the morning OR ±1 OCO straddle on CrossTrade (Sim101).

Run once per NY session at ~09:45, right after the 09:44 bar closes:

    python step4_run_live.py --or-close 17850.25            # live
    python step4_run_live.py --or-close 17850.25 --dry-run  # preview, send nothing

It asks src.daily_setup for today's setup (the SAME code path daily_setup
prints), and ONLY when the day is both-armed (category == BOTH) does it rest the
straddle:

    BUY-STOP  @ OR_close + 1   (s.or_plus_1)   ┐ same ocoId, first touch wins,
    SELL-STOP @ OR_close − 1   (s.or_minus_1)  ┘ the fill cancels the other side.

Each entry carries the NinjaTrader ATM template "ORB 20-30", which attaches the
+20 target / −30 stop bracket automatically on fill — so we send only the entry.
This mirrors xt_bracket_test.py's proven request shape (we do NOT import it: it
fires test orders at import time).

LONG-ONLY / SHORT-ONLY are PAPER ONLY and NEITHER is no-trade per daily_setup,
so this script stands down on all three rather than place a one-sided live bet.
Force-flat at 11:30 ET is step 5 (force_flat.py), not this script.
"""
import argparse
import os
import sys
from datetime import datetime

import requests

from src.daily_setup import NY, STALE_DAYS, compute_setup   # (1) daily_setup entry point

# Windows consoles default to cp1252, which can't encode the ± / − glyphs; force
# UTF-8 where supported (same idiom as daily_setup.main).
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8")

ap = argparse.ArgumentParser(description="Place the morning OR ±1 OCO straddle")
ap.add_argument("--or-close", type=float, required=True,
                help="OR_close = close of the 09:44 NY bar (read off your platform at 09:45).")
ap.add_argument("--account", default="Sim101")
ap.add_argument("--instrument", default="MNQ 06-26",
                help="must match your NT8 instrument string + the mid-June roll.")
ap.add_argument("--strategy", default="ORB 20-30",
                help="NT8 ATM template; attaches +20 target / −30 stop on fill.")
ap.add_argument("--qty", type=int, default=1)
ap.add_argument("--dry-run", action="store_true", help="preview the calls, send nothing")
args = ap.parse_args()

ACCOUNT, INSTR, QTY, STRATEGY, DRY = (
    args.account, args.instrument, args.qty, args.strategy, args.dry_run)

BASE = "https://app.crosstrade.io/v1/api"
TIMEOUT = 10


def _headers():
    token = os.environ.get("CROSSTRADE_TOKEN")
    if not token:
        sys.exit("CROSSTRADE_TOKEN env var not set")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def place_bracket(action, stop, oco_id, strategy, qty):
    """Rest ONE stop-market entry (an OCO leg) carrying the ATM strategy.

    Mirrors xt_bracket_test.py's request exactly. Returns the requests.Response
    (or None on a dry run); the caller inspects .ok so a failed leg can't
    silently leave a one-sided straddle.
    """
    # guard: never place without an explicit account + instrument
    if not ACCOUNT or not INSTR:
        sys.exit("refusing to place: account and instrument are both required")
    order = {
        "instrument": INSTR, "action": action, "quantity": qty,
        "orderType": "STOPMARKET", "stopPrice": stop,
        "timeInForce": "DAY", "ocoId": oco_id, "strategy": strategy,
    }
    url = f"{BASE}/accounts/{ACCOUNT}/orders/place"
    if DRY:
        print(f"[dry] POST {url}  {order}")
        return None
    r = requests.post(url, headers=_headers(), json=order, timeout=TIMEOUT)
    print(f"  {action:4s} STOPMARKET @ {stop:.2f}   {r.status_code}  {r.text}")
    return r


s = compute_setup(args.or_close)            # (2) -> or_plus_1, or_minus_1, tradeable/category

# Refuse to trade off a stale pool: today's clusters would be built from old OR
# levels. daily_setup only warns at this threshold; on the live path it's fatal.
today = datetime.now(NY).date()
lag = (today - s.last_session).days
if lag > STALE_DAYS:
    sys.exit(f"data is stale ({lag}d behind {s.last_session}); "
             f"regenerate the parquet before trading")

print(f"OR_close={s.or_close:.2f}  category={s.category}  "
      f"data through {s.last_session} ({lag}d behind)"
      + ("   [DRY RUN]" if DRY else ""))

if not s.tradeable:                         # (3) within_200/cluster gate: only BOTH is live
    print(f"no-trade day: {s.category}  "
          f"(LONG-ONLY/SHORT-ONLY are paper-only, NEITHER is flat — standing down)")
    raise SystemExit

oco = f"orb-{today:%Y%m%d}"
print(f"placing OCO straddle  ocoId={oco}  {ACCOUNT} / {INSTR}  qty={QTY}  ATM={STRATEGY!r}")

buy = place_bracket(action="BUY", stop=s.or_plus_1, oco_id=oco, strategy=STRATEGY, qty=QTY)
if not DRY and (buy is None or not buy.ok):
    sys.exit("BUY leg failed — nothing else placed, account is flat. Investigate before retrying.")

sell = place_bracket(action="SELL", stop=s.or_minus_1, oco_id=oco, strategy=STRATEGY, qty=QTY)
if not DRY and (sell is None or not sell.ok):
    sys.exit("*** SELL leg failed but the BUY-STOP is RESTING (one-sided exposure). "
             "Run force_flat.py NOW to cancel the lone buy-stop. ***")

print("placed both legs. 11:30 ET force-flat is step 5 (force_flat.py).")
