import os, requests

token = os.environ.get("CROSSTRADE_TOKEN")
if not token:
    raise SystemExit("CROSSTRADE_TOKEN not set")

BASE = "https://app.crosstrade.io/v1/api"
HEAD = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

ACCOUNT = "Sim101"
order = {
    "instrument": "MNQ 06-26",
    "action": "BUY",
    "quantity": 1,
    "orderType": "LIMIT",
    "timeInForce": "DAY",
    "limitPrice": 29000.0,
}

for path in (f"/accounts/{ACCOUNT}/orders/place", f"/accounts/{ACCOUNT}/orders"):
    url = BASE + path
    print(f"POST {url}")
    r = requests.post(url, headers=HEAD, json=order, timeout=15)
    print(f"  HTTP {r.status_code}: {r.text}")
    if r.status_code not in (404, 405):
        break
