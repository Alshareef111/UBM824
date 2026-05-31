import os, requests

token = os.environ.get("CROSSTRADE_TOKEN")
if not token:
    raise SystemExit("CROSSTRADE_TOKEN not set")

BASE = "https://app.crosstrade.io/v1/api"
HEAD = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

ACCOUNT = "Sim101"
INSTRUMENT = "MNQ 06-26"
ATM = "ORB 20-30"

# Fixed straddle (no quote needed): far from any plausible MNQ level so both rest.
BUY_STOP = 33000
SELL_STOP = 27000
OCO = "orb-test-oco"


def place(label, order):
    print(label)
    r = requests.post(f"{BASE}/accounts/{ACCOUNT}/orders/place",
                      headers=HEAD, json=order, timeout=15)
    print(f"  HTTP {r.status_code}: {r.text}")


place("BUY-STOP entry (above market):", {
    "instrument": INSTRUMENT, "action": "BUY", "quantity": 1,
    "orderType": "STOPMARKET", "stopPrice": BUY_STOP,
    "timeInForce": "DAY", "ocoId": OCO, "strategy": ATM,
})

place("SELL-STOP entry (below market):", {
    "instrument": INSTRUMENT, "action": "SELL", "quantity": 1,
    "orderType": "STOPMARKET", "stopPrice": SELL_STOP,
    "timeInForce": "DAY", "ocoId": OCO, "strategy": ATM,
})

print(f"\nWorking orders on {ACCOUNT}:")
r = requests.get(f"{BASE}/accounts/{ACCOUNT}/orders",
                 headers=HEAD, params={"activeOnly": True}, timeout=15)
print(f"  HTTP {r.status_code}")
try:
    for o in r.json().get("orders", []):
        print(f"  {o.get('orderAction')} {o.get('orderType')} "
              f"state={o.get('orderState')} "
              f"stop={o.get('stopPrice')} limit={o.get('limitPrice')} "
              f"ocoId={o.get('ocoId')!r} id={o.get('id')}")
except Exception as e:
    print(f"  (could not parse orders: {e}; raw: {r.text})")
