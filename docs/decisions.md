# Design Decisions Log

This document records WHY each design choice was made, with the alternatives considered and the reasoning. Before proposing a change to any rule or parameter, READ the relevant entry below. Many decisions involved trade-offs that are not obvious from the code alone.

Format: each entry has Date, Decision, Alternatives considered, Reasoning, and Status (locked / open / superseded).

---

## D-001: Panama back-adjustment for continuous price series

- Date: 2026-04 (project setup)
- Decision: Use Panama back-adjustment to build a continuous MNQ price series across rollovers.
- Alternatives considered:
  - Ratio adjustment (multiplicative): preserves percentage moves but distorts absolute point distances, which would break a fixed 30-point stop.
  - No adjustment (raw contracts): would scatter ORB levels by 200+ points across rollovers, preventing meaningful clustering.
- Reasoning: Strategy uses fixed point-distance stops and targets. Panama preserves point distances exactly, which is what the strategy depends on. Trade-off: absolute prices in the backtest do NOT match TradingView quotes for older periods. Verified the cumulative offset for the earliest contract MNQM4 was +1,912 points (a real price of 18,605 stored as 20,517).
- Status: locked

---

## D-002: Cluster definition Option B (chain rule, not diameter)

- Date: 2026-04 (during simulator design)
- Decision: A cluster is N or more levels (N >= 3) where every adjacent pair (after sorting) is within 3 points. Total span can exceed 3 points.
- Alternatives considered:
  - Option A (diameter rule): all levels must fit in any 3-point window. Stricter, fewer clusters.
- Reasoning: The original verbal spec was "3 levels within 3 points" which was ambiguous. User confirmed Option B was intended: a chain of nearby levels represents a meaningful price zone even if the chain is long. Verified by clusters.py test 2: 5 levels at 2.5-point gaps spanning 10 total points form one cluster under Option B.
- Status: locked. Note: this means clusters can be quite wide. In practice the largest cluster observed was 12 points wide. This is acceptable but worth remembering when interpreting "cluster zones".

---

## D-003: Cluster classification skips clusters spanning the 9:45 close

- Date: 2026-04 (during simulator design)
- Decision: If a cluster's range straddles the 9:45 close (cluster.low < close < cluster.high), the cluster is skipped (no trade).
- Alternatives considered:
  - Trade based on which side has more levels: more aggressive but introduces an extra parameter.
  - Trade both sides simultaneously with two limits: violates the one-trade-per-cluster rule and complicates risk management.
- Reasoning: When the cluster contains the price, the directional hypothesis (mean reversion from above or below) is undefined. Safer to skip. In the visualization tool, skipped clusters are rendered in gray.
- Status: locked

---

## D-004: One position at a time (C2 rule)

- Date: 2026-04 (during simulator design)
- Decision: Only one position open at any time across all clusters in a session.
- Alternatives considered:
  - Allow simultaneous long and short from different clusters.
  - Pyramiding into the same cluster.
- Reasoning: Simplest risk profile. Avoids hedge-like situations where one cluster's stop is another cluster's target. Backtest results would otherwise be driven by uncontrolled exposure stacking. Easier to interpret expectancy per trade.
- Status: locked

---

## D-005: Stop-first conservative for ambiguous same-bar stop and target

- Date: 2026-04 (during simulator design)
- Decision: When a 1-min bar's range contains both stop and target, count as a stop-out (loss).
- Alternatives considered:
  - Target-first optimistic: would overstate edge.
  - 50/50 random: unrealistic, adds noise.
  - Tick-level resolution: not available for the full backtest period.
- Reasoning: Industry standard for bar-based backtests. Underestimates rather than overestimates strategy performance. Ambiguous bars are flagged in src/ambig_check.py. In the baseline, 5 trades were affected. Tick verification on the March to May 2026 overlap confirmed the conservative bias is small in absolute terms (~$240 across 5 affected trades).
- Status: locked for bar-based simulation. Tick simulator uses chronological truth.

---

## D-006: First-touch entry on cluster boundary

- Date: 2026-04 (during simulator design)
- Decision: Sell entry at cluster.low; buy entry at cluster.high. (The boundary closest to the prevailing price.)
- Alternatives considered:
  - Last-touch (after price traverses entire cluster): tested in a sweep, performed worse.
  - Midpoint of cluster: arbitrary and untested.
- Reasoning: First-touch is the standard interpretation of mean reversion: as soon as price enters the zone, attempt to fade. Last-touch (breakout entry on cluster.high for buys above price) was also tested and lost money in 2024 and 2026 while winning in 2025 (results-log.md, config "reverse-entry").
- Status: locked. Tested alternative: superseded by baseline.

---

## D-007: 200-session lookback for level pool

- Date: 2026-04 (during simulator design)
- Decision: Use the previous 200 trading sessions' ORB highs and lows, plus today's, for the level pool.
- Alternatives considered:
  - 50, 100, 500 sessions.
- Reasoning: 200 was the user's specified value, roughly 10 months of trading days. Long enough to capture seasonality, short enough that ancient levels do not pollute current clusters. Not yet sensitivity-tested.
- Status: locked, sensitivity test pending.

---

## D-008: 30-point fixed stop and target (1 to 1 R:R)

- Date: 2026-04 (initial spec)
- Decision: Stop and target both 30 points.
- Alternatives considered (all tested, see results-log.md):
  - 20 stop / 40 target (1 to 2 R:R, last-touch entry): -$1,267
  - 45 stop / 45 target: -$4,329
  - 30 stop / 40 target (1 to 1.33, breakout direction): -$1,569 (but +$794 in 2025)
- Reasoning: 30 / 30 is the only configuration tested that produced a positive bar-based result over the full period. Other configs lost money. R:R alternatives also flipped the strategy direction (mean reversion vs breakout) which may explain the year-by-year inversion observed.
- Status: locked. Open question: whether a regime detector could allow switching between 30/30 reversion (good for 2024, 2026) and 30/40 breakout (good for 2025).

---

## D-009: Sticky forward-only rollover

- Date: 2026-04 (during data_prep design)
- Decision: Switch to a new front-month contract only when a contract further forward in the cycle has higher daily volume than the current one. Never switch backward.
- Alternatives considered:
  - Calendar-based rollover (8 days before expiry): simpler but rigid.
  - Pure max-volume per day: causes contract flickering near rollover dates.
- Reasoning: Sticky logic prevents oscillating between contracts when volumes are close. Forward-only matches real trader behavior (you never roll back to an earlier contract). Confirmed 8 rollovers across 25 months, all in the H to M to U to Z cycle, all timing-reasonable.
- Status: locked

---

## D-010: Force-close at 11:30 bar OPEN, not high or low

- Date: 2026-04 (during simulator design)
- Decision: Trades still open at end of bar 11:29 are closed at the OPEN price of the bar timestamped 11:30. The 11:30 bar's high and low are NOT consulted.
- Alternatives considered:
  - Use 11:30 bar high/low for stop/target check first, then close at close.
  - Close at 11:30 bar's close.
- Reasoning: Closest analogue to a market order placed at 11:30. Avoids ambiguity (did the stop hit at 11:30:15 or did the position survive to 11:30:45?). Cleaner accounting. In the baseline, 18 of 526 trades (3.4%) ended in force-close.
- Status: locked

---

## D-011: Trading window 9:46 to 11:30 NY time

- Date: 2026-04 (initial spec)
- Decision: Allow new entries on bars 9:46 through 11:29. Force-close on 11:30.
- Alternatives considered:
  - Earlier start (9:30 to 9:45 alongside ORB calculation): impossible because the ORB itself is being measured.
  - Later end (12:00, 16:00): expands trade time but adds noise from lunch period.
- Reasoning: User-specified. The 9:46 start ensures the ORB is fully formed and today's levels are in the pool before any trade is placed. The 11:30 end captures the morning session's primary liquidity window.
- Status: locked

---

## D-012: Calendar spread filtering

- Date: 2026-04 (during data_prep design)
- Decision: Exclude all symbols matching the calendar-spread pattern (symbols containing a hyphen, indicating MNQXY-MNQAB style). Keep only outright contracts (single contract symbols like MNQM4).
- Reasoning: Spreads are price differentials (~227 points), not real instrument prices. Including them would corrupt the price series with non-tradeable rows. Verified during raw data inspection.
- Status: locked

---

## D-013: NY timezone for all session logic

- Date: 2026-04 (during data_prep design)
- Decision: Convert UTC source data to America/New_York and use this consistently for ORB calculation, trading window, force-close.
- Alternatives considered:
  - Chicago time (CME local).
  - UTC throughout.
- Reasoning: Strategy is defined in NY equity-market terms (9:30 to 9:45 cash open). DST handling is automatic via pytz/zoneinfo. Verified summer and winter sessions both produce ORB at the correct local time.
- Status: locked

---

## Open questions (unresolved)

- OQ-1: Regime detection. Strategy is profitable in 2024 (+$436) and 2026 YTD (+$1,620), flat in 2025 (-$81). Breakout variant inverted: profitable in 2025, lost in others. Possible regime indicators to test: 20-day ATR, ADX, ORB width relative to recent average. Risk: overfitting.
- OQ-2: Lookback sensitivity. Have not tested 100 or 500-session lookbacks.
- OQ-3: Cluster minimum size. Currently 3. Have not tested 4 or 5.
- OQ-4: Commission impact. ~$447 over 526 trades reduces net to ~$1,475 over 2 years. Not yet incorporated into reporting.
- OQ-5: Slippage model. Limit fills assume zero slippage. Force-close uses bar open. Real fills may be worse, especially for force-close in fast markets.
- OQ-6: Walk-forward / out-of-sample. Strategy was tuned on the same data it was tested on. Need a true out-of-sample period.
