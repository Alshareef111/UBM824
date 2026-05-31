import os, requests
token = os.environ.get("CROSSTRADE_TOKEN")
if not token:
    raise SystemExit("CROSSTRADE_TOKEN not set")
r = requests.get(
    "https://app.crosstrade.io/v1/api/accounts",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    timeout=15,
)
print("HTTP", r.status_code)
print(r.text)
