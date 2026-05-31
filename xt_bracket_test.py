import os, requests

token = os.environ.get("CROSSTRADE_TOKEN")
if not token:
    raise SystemExit("CROSSTRADE_TOKEN not set")

BASE = "https://app.crosstrade.io/v1/api"
HEAD = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

ACCOUNT = "Sim101"
INSTRUMENT = "MNQ 06-26"
ATM = "ORB 20-30"


def get_last():
    for path in (f"/accounts/{ACCOUNT}/quote", "/market/quote"):
        url = BASE + path
        r = requests.get(url, headers=HEAD, params={"instrument": INSTRUMENT}, timeout=15)
        print(f"QUOTE GET {url} -> HTTP {r.status_code}: {r.text}")
        if r.status_code == 200:
            try:
                v = r.json().get("last")
                if v is not None:
                    return float(v)
            except Exception:
                pass
    return None


def place(label, order):
    print(label)
    url = f"{BASE}/accounts/{ACCOUNT}/orders/place"
    r = requests.post(url, headers=HEAD, json=order, timeout=15)
    print(f"  HTTP {r.status_code}: {r.text}")


last = get_last()
if last is None:
    raise SystemExit("Could not read a last price. Paste the QUOTE output above.")

buy_stop = round(last + 300)
sell_stop = round(last - 300)
oco = "orb-test-oco"
print(f"\nlast={last}  buy_stop={buy_stop}  sell_stop={sell_stop}  oco={oco}\n")

place("BUY-STOP entry (above market):", {
    "instrument": INSTRUMENT, "action": "BUY", "quantity": 1,
    "orderType": "STOPMARKET", "stopPrice": buy_stop,
    "timeInForce": "DAY", "ocoId": oco, "strategy": ATM,
})

place("SELL-STOP entry (below market):", {
    "instrument": INSTRUMENT, "action": "SELL", "quantity": 1,
    "orderType": "STOPMARKET", "stopPrice": sell_stop,
    "timeInForce": "DAY", "ocoId": oco, "strategy": ATM,
})

print("\nDone. Two working stops sharing one OCO id should appear on Sim101.")
