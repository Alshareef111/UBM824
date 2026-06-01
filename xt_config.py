"""xt_config.py -- single source of truth for CrossTrade execution config.

Centralized so the quarterly MNQ roll is a ONE-LINE change here (INSTRUMENT),
not a hunt across run_session.py / step4_run_live.py / force_flat.py -- where a
missed file means run_session arms the new contract while force_flat tries to
flatten the old one and silently fails to close a live position.

Kept at repo ROOT (not under src/) so the execution scripts, which run as
top-level scripts rather than as part of the src package, import it cleanly.
"""

ACCOUNT = "Sim101"
INSTRUMENT = "MNQ 06-26"   # <-- ROLL HERE: MNQ 06-26 -> MNQ 09-26 at the mid-June roll (expiry 2026-06-19)
BASE = "https://app.crosstrade.io/v1/api"   # CrossTrade REST API base
ATM_TEMPLATE = "ORB 20-30"  # NinjaTrader ATM template: +20 target / -30 stop attached on fill
