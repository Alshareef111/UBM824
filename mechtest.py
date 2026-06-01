#!/usr/bin/env python3
"""
mechtest.py -- LIVE execution-mechanics test on the PAPER account (Sim101).

NOT a strategy test: the prices are arbitrary and the P&L is meaningless. It
validates the order lifecycle the weekend (no feed) could not: entry orders
reaching WORKING, a fill, the ATM bracket attaching, and OCO cancelling the
other leg. Bypasses step4's category gate -- execution layer only.

Reuses the PROVEN request body (identical fields/endpoint to step4.place_bracket
and xt_bracket_test) and xt_config for ACCOUNT/INSTRUMENT/BASE/ATM_TEMPLATE, so
force_flat.py cleans up the exact same contract. Cleanup (force_flat.py) is run
right after this; this script only places + observes + reports.
"""
import sys
import time
from datetime import datetime

import requests

from xt_config import ACCOUNT, INSTRUMENT, BASE, ATM_TEMPLATE
from run_session import _headers, fetch_bars  # proven token handling + bars fetch

TIMEOUT = 10


def place_leg(action, stop, oco_id):
    """Proven request body -- identical to step4.place_bracket / xt_bracket_test."""
    order = {
        "instrument": INSTRUMENT, "action": action, "quantity": 1,
        "orderType": "STOPMARKET", "stopPrice": stop,
        "timeInForce": "DAY", "ocoId": oco_id, "strategy": ATM_TEMPLATE,
    }
    r = requests.post(f"{BASE}/accounts/{ACCOUNT}/orders/place",
                      headers=_headers(), json=order, timeout=TIMEOUT)
    print(f"  place {action:4s} STOPMARKET @ {stop:.2f}  -> {r.status_code} {r.text}", flush=True)
    return r


def get_orders(active_only=True):
    r = requests.get(f"{BASE}/accounts/{ACCOUNT}/orders", headers=_headers(),
                     params={"activeOnly": "true" if active_only else "false"}, timeout=TIMEOUT)
    try:
        return r.json().get("orders", [])
    except Exception:
        print(f"  (orders parse failed: {r.status_code} {r.text})", flush=True)
        return []


def print_orders(orders, label):
    print(f"  [{label}] {len(orders)} order(s):", flush=True)
    for o in orders:
        print(f"    {str(o.get('orderAction')):4} {str(o.get('orderType')):11} "
              f"state={o.get('orderState')} stop={o.get('stopPrice')} "
              f"limit={o.get('limitPrice')} oco={o.get('ocoId')!r} id={o.get('id')}", flush=True)


def positions_text():
    r = requests.get(f"{BASE}/accounts/{ACCOUNT}/positions", headers=_headers(), timeout=TIMEOUT)
    return f"{r.status_code} {r.text}"


def main():
    print(f"=== LIVE MECHANICS TEST -- PAPER {ACCOUNT} / {INSTRUMENT} (arbitrary prices) ===", flush=True)

    # 1) current price (latest close from /market/bars)
    bars = fetch_bars(limit=5)
    if not bars:
        sys.exit("no bars from /market/bars -- aborting, NOTHING placed")
    price = float(bars[-1]["close"])
    oco = f"mechtest-{datetime.now():%H%M%S}"
    buy_stop, sell_stop = price + 1, price - 1
    print(f"[1] price={price:.2f}  -> BUY-stop {buy_stop:.2f} / SELL-stop {sell_stop:.2f}  "
          f"ocoId={oco}  ATM={ATM_TEMPLATE!r}", flush=True)

    # 2) place both legs (proven shape, shared ocoId)
    print("\n[2] placing OCO straddle:", flush=True)
    place_leg("BUY", buy_stop, oco)
    place_leg("SELL", sell_stop, oco)

    # 3) KEY CHECK: both legs reach Working
    time.sleep(1.0)
    orders = get_orders(active_only=True)
    print("\n[3] post-place active orders (KEY CHECK: expect 2x Working):", flush=True)
    print_orders(orders, "submitted")
    working = sum(1 for o in orders if o.get("orderState") == "Working")
    print(f"  -> Working: {working} of {len(orders)} active", flush=True)

    # 4) watch ~30s: fill -> position + ATM 20/30 bracket + opposite leg Cancelled
    print("\n[4] watching <=30s for fill / ATM attach / OCO cancel:", flush=True)
    filled = False
    for i in range(0, 30, 3):
        orders = get_orders(active_only=True)
        compact = [(str(o.get("orderAction")), str(o.get("orderType")),
                    o.get("orderState"), o.get("stopPrice"), o.get("limitPrice")) for o in orders]
        print(f"  t+{i:02d}s active={len(orders)} {compact}", flush=True)
        print(f"        positions: {positions_text()}", flush=True)
        has_limit = any(str(o.get("orderType")).upper().startswith("LIMIT") for o in orders)
        ours_left = [o for o in orders if o.get("ocoId") == oco]
        if has_limit or (len(orders) > 0 and not ours_left):
            print("  -> a leg FILLED: ATM bracket present / entry legs gone (OCO).", flush=True)
            filled = True
            break
        time.sleep(3)
    if not filled:
        print("  -> NO fill / bracket detected in 30s. (force_flat runs next regardless.)", flush=True)

    # 5) final all-states snapshot (to show Filled/Cancelled if the API returns them)
    print("\n[final] all-orders snapshot (activeOnly=false):", flush=True)
    try:
        print_orders(get_orders(active_only=False), "all")
    except Exception as e:
        print(f"  (all-orders snapshot unavailable: {e})", flush=True)
    print(f"  final positions: {positions_text()}", flush=True)
    print("\nNEXT: force_flat.py (cleanup) runs now.", flush=True)


if __name__ == "__main__":
    main()
