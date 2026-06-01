#!/usr/bin/env python3
"""
Step 5 — 11:30 ET force-flat for MNQ ORB (account Sim101).

Closes any open position and cancels any remaining working orders for ONE
account + ONE instrument, then verifies flat. Run standalone, or call
force_flat() from your scheduler at 11:30 ET. Use --dry-run to preview the
calls without sending anything.

CrossTrade REST endpoints (confirmed from docs.crosstrade.io):
  POST /v1/api/positions/flatten                 body: {account, instrument}
       -> flattens the position AND cancels the orders associated with it
          (e.g. the ATM "ORB 20-30" target/stop). account goes in the BODY.
  POST /v1/api/accounts/{account}/orders/cancel  body: {instrument}
       -> cancels remaining working orders for that instrument. account in PATH.
          (Needed for the NO-FILL case: a resting OCO entry stop with no
           position is NOT touched by flatten.)
  GET  /v1/api/accounts/{account}/orders?activeOnly=true   -> verify none working
  GET  /v1/api/accounts/{account}/positions                -> verify qty 0
       (^ confirm this exact path against your dashboard; if 404, the
        flatten 'success' + empty active-orders check is still authoritative.)

SAFETY: an EMPTY flatten body flattens every position in EVERY account. This
script always sends account + instrument and refuses to run if either is blank.
"""
import os
import sys
import argparse
import requests

BASE = "https://app.crosstrade.io/v1/api"
DEFAULT_ACCOUNT = "Sim101"
DEFAULT_INSTRUMENT = "MNQ 06-26"   # confirm matches your NT8 instrument string + the mid-June roll
TIMEOUT = 10


def _headers():
    token = os.environ.get("CROSSTRADE_TOKEN")
    if not token:
        sys.exit("CROSSTRADE_TOKEN env var not set")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def flatten(account, instrument, dry):
    # guard: never send empty filters (empty == flatten ALL accounts)
    if not account or not instrument:
        sys.exit("refusing to flatten: account and instrument are both required")
    url = f"{BASE}/positions/flatten"
    body = {"account": account, "instrument": instrument}
    if dry:
        print(f"[dry] POST {url}  {body}")
        return None
    r = requests.post(url, headers=_headers(), json=body, timeout=TIMEOUT)
    print(f"flatten      {r.status_code}  {r.text}")
    return r


def cancel_orders(account, instrument, dry):
    url = f"{BASE}/accounts/{account}/orders/cancel"
    body = {"instrument": instrument}   # omit instrument -> cancels ALL orders in the account
    if dry:
        print(f"[dry] POST {url}  {body}")
        return None
    r = requests.post(url, headers=_headers(), json=body, timeout=TIMEOUT)
    print(f"cancel       {r.status_code}  {r.text}")
    return r


def verify(account, dry):
    if dry:
        print(f"[dry] GET  {BASE}/accounts/{account}/orders?activeOnly=true")
        print(f"[dry] GET  {BASE}/accounts/{account}/positions")
        return
    o = requests.get(f"{BASE}/accounts/{account}/orders",
                     headers=_headers(), params={"activeOnly": "true"}, timeout=TIMEOUT)
    p = requests.get(f"{BASE}/accounts/{account}/positions",
                     headers=_headers(), timeout=TIMEOUT)
    print(f"orders(active) {o.status_code}  {o.text}")
    print(f"positions      {p.status_code}  {p.text}")


def force_flat(account=DEFAULT_ACCOUNT, instrument=DEFAULT_INSTRUMENT, dry=False):
    # flatten first (closes position + cancels its ATM bracket atomically),
    # then cancel mops up any standalone resting entry stop (the no-fill case).
    flatten(account, instrument, dry)
    cancel_orders(account, instrument, dry)
    verify(account, dry)
    print(f"READ: pass when orders(active) is empty AND position qty == 0 for "
          f"{account} / {instrument}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Force-flat one account+instrument")
    ap.add_argument("--account", default=DEFAULT_ACCOUNT)
    ap.add_argument("--instrument", default=DEFAULT_INSTRUMENT)
    ap.add_argument("--dry-run", action="store_true", help="preview calls, send nothing")
    a = ap.parse_args()
    force_flat(a.account, a.instrument, a.dry_run)
