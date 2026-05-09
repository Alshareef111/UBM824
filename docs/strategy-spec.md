# Strategy Specification

This document defines the EXACT rules of the MNQ ORB-Cluster mean-reversion strategy. Any change to logic must be reflected here BEFORE code is modified. The current baseline (526 trades, +$1,975) was produced by the rules below — changing them invalidates the baseline.

## Instrument

- Symbol: MNQ (Micro E-mini Nasdaq-100 futures, CME)
- Tick size: 0.25 points
- Tick value: 0.50 dollars
- Point value: 2 dollars per point per contract
- Position size for backtest: 1 contract

## Data

- Source: Databento, schema OHLCV-1m
- Period: 2024-04-01 to 2026-05-01
- Timezone of source: UTC
- Timezone after processing: America/New_York (DST-aware)
- All MNQ contract months are downloaded; calendar spreads are filtered out
- Front-month selection: highest-volume outright contract per session
- Rollover policy: sticky forward-only (only roll when a contract further forward has higher volume)
- Continuous price series: Panama back-adjusted (cumulative gap accumulation in reverse)

## Session and trading window

- Trading session: NY regular hours
- ORB window: 9:30 to 9:45 NY time inclusive (15 one-minute bars)
- Trading window: 9:46 to 11:30 NY time
- Trading window inclusive: bars timestamped 9:46 through 11:29 are eligible for entry and exit
- Force-close: any open position at end of bar 11:29 is closed at the OPEN price of the bar timestamped 11:30
- The 11:30 bar's high and low are NOT consulted for stop or target

## ORB calculation

- ORB high: maximum of all 1-min highs in the 9:30 to 9:45 window
- ORB low: minimum of all 1-min lows in the 9:30 to 9:45 window
- ORB close: close of the 9:45 bar (used as price reference for cluster classification)
- A session is excluded from the backtest if the ORB window has fewer than 15 complete bars (e.g. holidays, half-days). Excluded sessions are written to orb_excluded.parquet with the reason.

## Level pool

- For each session T, the level pool consists of:
  - 200 prior sessions' ORB highs and lows (400 levels)
  - Today's ORB high and low (2 levels)
  - Total: 402 levels
- Today's ORB is added to the pool BEFORE cluster detection at 9:45, so today's levels can participate in clusters that get traded the same session.
- After session T closes, today's ORB is appended to the deque for use in session T+1.

## Cluster definition

- A cluster is a set of N levels where N is at least 3, sorted ascending, where every adjacent pair has a gap of 3 points or less.
- This is Option B (chain rule). The total span (high minus low) of a cluster can exceed 3 points, as long as no adjacent pair gap exceeds 3.
- Boundary: exactly 3.0 points apart counts as adjacent (inclusive).
- Algorithm: sort all 402 levels ascending; walk through them building a current cluster; whenever the gap to the next level exceeds 3 points, close the current cluster (keep it only if it has 3 or more levels) and start a new one.
- Each cluster exposes: low (lowest level), high (highest level), levels (the actual values), size (count).

## Cluster classification

At 9:45, after ORB close is known, each cluster is classified versus the 9:45 close:

- All cluster levels strictly above ORB close: SELL setup. Entry limit at cluster.low. Direction: short. Hypothesis: price rises into the zone and reverts down.
- All cluster levels strictly below ORB close: BUY setup. Entry limit at cluster.high. Direction: long. Hypothesis: price falls into the zone and reverts up.
- Cluster spans the close (ORB close is between cluster.low and cluster.high): SKIP. No trade.

## Order placement and fills

- All cluster setups become resting limit orders at 9:46 (start of trading window).
- One position at a time (C2 rule). While a position is open, all other limits are inactive but remain armed.
- Within a single bar, multiple limits could fill. Tiebreaker: the limit with entry price closest to the bar's OPEN fills first (NinjaTrader convention).
- A bar fills a limit if the bar's range covers the limit price:
  - Buy limit at L: fills when bar's low is less than or equal to L
  - Sell limit at L: fills when bar's high is greater than or equal to L
- Fill price equals limit price (no slippage modeled in bar simulator)
- Once a setup fills, that cluster is consumed for the day (rule: one trade per cluster per day).
- After exit, remaining unfilled limits stay armed for the rest of the trading window.

## Stop and target

- Stop loss: 30 points fixed
- Take profit: 30 points fixed
- Risk-reward: 1 to 1
- Breakeven win rate: 50.0%
- For long entries:
  - Stop price = entry - 30
  - Target price = entry + 30
- For short entries:
  - Stop price = entry + 30
  - Target price = entry - 30

## Same-bar stop and target ambiguity

- A bar may have both stop and target inside its range. From 1-min OHLC alone, we cannot know which hit first.
- Rule: stop-first conservative. Such bars are counted as stop-outs (loss).
- Applied uniformly including the entry bar.
- Tick-based verification (when available, March to May 2026 overlap) replaces this with chronological truth.
- Ambig audit (src/ambig_check.py) flags affected trades. In the baseline: 5 ambiguous stop exits.

## Trade exit priority within a bar

Order of checks each bar while a position is open:

1. If stop is in bar range, exit at stop (stop-first rule).
2. Else if target is in bar range, exit at target.
3. Else continue holding into next bar.
4. At end of bar 11:29, if still open, force-close at the 11:30 bar OPEN price. Exit reason: force_close.

## P and L computation

- For long: pnl_points = exit_price - entry_price
- For short: pnl_points = entry_price - exit_price
- pnl_dollars = pnl_points * 2
- No commissions in backtest. Real commissions estimated at 0.85 dollars round-trip per MNQ contract (subtract approximately 447 dollars from total over 526 trades).
- No slippage modeled on limit fills. Force-close exits use bar open as a proxy for market order.

## Reset rules

- Cluster pool rebuilt from scratch each session at 9:45.
- One trade per cluster per day. Cluster zones reset for the next session.
- Levels deque updates after session close (FIFO, max length 200 sessions).

## Excluded conditions

- No exclusions by day of week.
- No exclusions by economic calendar (FOMC, NFP, etc.).
- No exclusions by ORB width or volatility.
- Holidays and half-days with fewer than 15 ORB bars are excluded automatically.
- This is intentional: keep the strategy simple. Filters are deferred to a separate research phase.

## Locked parameters (baseline)

These produce the locked baseline of 526 trades, 52.9% win rate, +$1,975:

- LOOKBACK_SESSIONS = 200
- ORB_START_NY = 09:30
- ORB_END_NY = 09:45
- TRADING_WINDOW_START_NY = 09:46
- TRADING_WINDOW_END_NY = 11:30 (force-close at 11:30 bar open)
- CLUSTER_GAP_POINTS = 3.0 (inclusive)
- CLUSTER_MIN_SIZE = 3
- STOP_POINTS = 30
- TARGET_POINTS = 30
- POSITION_SIZE = 1 contract
- SAME_BAR_RULE = stop_first_conservative

## Versioning

When parameters are changed for an experiment, do NOT overwrite the locked baseline outputs. Save new outputs to results/archive/ with a descriptive prefix (e.g. trades_2pt_gap.parquet, trades_50pt_stop.parquet) and log the result in docs/results-log.md.
