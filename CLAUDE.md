# IMPORTANT — read these files NOW before responding to anything

Before answering ANY user request in this project, read these files in order:
1. docs/strategy-spec.md (the locked rules)
2. docs/decisions.md (why each rule exists)
3. docs/results-log.md (what has already been tested)

After reading, internalize:
- The locked baseline is 526 trades, 52.9% win rate, +$1,975. Do NOT overwrite data/processed/trades.parquet.
- All paths come from src/paths.py. Never use Path(__file__).parent.
- New experiments save to results/archive/ with descriptive names.
- After any experiment, append an R-XXX entry to docs/results-log.md.

Only after reading those three files should you respond to the user's actual request. Do not skip this step even if the request seems simple.

---

# MNQ ORB-Cluster Mean-Reversion Strategy Backtest

## What this project is

A backtest of a futures trading strategy on MNQ (Micro E-mini Nasdaq-100). The strategy enters limit orders at clusters of historical Opening Range Breakout (ORB) levels, expecting mean reversion. Built on 2 years of 1-minute bars from Databento (April 2024 to May 2026), with optional tick-level verification on a 7-week overlap (March to May 2026).

## Strategy in one paragraph

Each NY trading session, compute the Opening Range from 9:30 to 9:45 AM (high and low). Maintain a rolling pool of the last 200 sessions' ORB highs and lows, plus today's (402 levels total). Find clusters where 3 or more levels have every adjacent pair within 3 points (Option B, chain rule, not diameter). Classify each cluster vs the 9:45 close: above price equals sell setup, below price equals buy setup, spanning price equals skip. During 9:46 to 11:30 NY, place resting limit orders at the cluster boundary closest to the price. First-touch entry. 30-point fixed stop, 30-point fixed target (1:1 R:R). One position at a time. Force close any open position at the 11:30 bar open.

## Current results (baseline, locked)

- 526 trades over 540 sessions (Apr 2024 to May 2026)
- 52.9% win rate (278 W / 247 L / 1 flat)
- +987.5 points = +$1,975 gross (no commissions)
- Exits: 271 target / 237 stop / 18 force-close
- Yearly: 2024 +$436 / 2025 -$81.50 / 2026 +$1,620.50
- Max drawdown: -$1,349.50 over 369 days
- Worst month: 2025-05 (-$695)
- Edge is statistically weak (~1.3 sigma above breakeven, p approx 0.09)

## Repository layout

MNQ-Strategy/
- CLAUDE.md (this file)
- README.md (human-facing intro)
- docs/strategy-spec.md (full strategy rules and all decisions)
- docs/decisions.md (why we chose each option)
- docs/results-log.md (all configs tested and outcomes)
- data/raw/ (Databento CSV, JSONs, tick file symlink)
- data/processed/ (parquet outputs, regenerable)
- src/paths.py (all file paths centralized, import from here)
- src/clusters.py (pure module, find_clusters)
- src/data_prep.py (raw CSV to BARS_PARQUET and ROLLS_PARQUET)
- src/orb.py (BARS_PARQUET to ORB_TABLE_PARQUET)
- src/simulator.py (bar-based backtest to TRADES_PARQUET)
- src/visualize_trade.py (session charts to results/charts/)
- src/ambig_check.py (flags same-bar stop and target)
- src/robustness.py (yearly, monthly, drawdown stats)
- src/build_tick_cache.py (tick text to TICKS_OVERLAP_PARQUET)
- src/tick_simulator.py (tick-based backtest verification)
- src/verify_ticks.py (bar vs tick discrepancy report)
- results/charts/ (all PNGs)
- results/archive/ (orphaned, historical outputs)

## How to run

All commands from project root (~/Desktop/MNQ-Strategy/):

- python3 src/data_prep.py (raw CSV to adjusted bars)
- python3 src/orb.py (compute ORB table)
- python3 src/simulator.py (run backtest, writes trades.parquet)
- python3 src/robustness.py (yearly, monthly stats)
- python3 src/ambig_check.py (ambiguous-bar audit)
- python3 src/visualize_trade.py (generate session charts)

Tick verification pipeline (requires Google Drive synced for the tick file symlink):

- python3 src/build_tick_cache.py
- python3 src/verify_ticks.py
- python3 src/tick_simulator.py

## Working conventions

- All file paths come from src/paths.py. NEVER use Path(__file__).parent in new scripts.
- All timestamps in NY timezone after data_prep, America/New_York, DST-aware.
- All prices are Panama back-adjusted continuous series. They will NOT match raw market quotes (e.g. TradingView) exactly. Point distances and dollar P&L are correct; absolute prices are not.
- 2 dollars per point per MNQ contract.
- Calendar spreads filtered out via regex matching outright contracts only in data_prep.
- Sticky forward-only rollover based on volume.
- One position at a time (C2 rule).
- Stop-first conservative for ambiguous same-bar stop and target.
- Force-close at the 11:30 bar's OPEN price (the 11:30 bar's high and low are NOT consulted).
- Trading window inclusive: 9:46 through 11:29 bars; force-close on 11:30 open.

## When making changes

1. READ docs/strategy-spec.md and docs/decisions.md BEFORE proposing any change to logic.
2. NEVER modify the strategy rules without explicit user approval, this baseline is locked.
3. For experiments, branch the config (don't overwrite trades.parquet). Save new outputs with descriptive names in results/archive/.
4. Always back up any parquet before regenerating.
5. After any code change, run the full pipeline and verify the headline results match (526 / 52.9% / +$1,975) unless an intentional change is being made.

## Current status

- Bar-based backtest: locked baseline, fully verified.
- Tick-based verification: built, identified approximately 240 dollars discrepancy in overlap period due to bar-level chronology errors (5 ambiguous bars). Strategy still profitable on ticks.
- Multiple parameter sweeps tested (see docs/results-log.md). Original 3pt/30/30/MR-first remains the only profitable config.
- 2025 was a flat-to-negative regime; 2024 and 2026 carried the edge.
- Open question: regime detection (ATR or volatility filter) to skip 2025-like environments.
