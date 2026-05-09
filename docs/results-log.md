# Results Log

This document records every parameter configuration tested, with the resulting performance metrics. Before proposing a new experiment, check this log to avoid repeating tests already done. Add new entries at the bottom with date, config, full metrics, and notes.

## Reading guide

- Config encoded as: gap / stop / target / direction-entry
  - gap: cluster gap in points (CLUSTER_GAP)
  - stop: stop-loss in points
  - target: take-profit in points
  - direction-entry: MR-first (mean reversion, first-touch on near boundary), MR-last (mean reversion, last-touch after traversal), BO-first (breakout, first-touch), BO-last (breakout, last-touch on far boundary)
- All tests use the same data window (2024-04-01 to 2026-05-01), same lookback (200), same min cluster size (3), same trading window (9:46 to 11:30), same C2 rule, same stop-first conservative.
- All P&L is gross (no commissions, no slippage).
- Breakeven WR for 1:R is 1 / (1 + R). E.g. 1:1 -> 50%, 1:1.33 -> 42.9%, 1:2 -> 33.3%, 1:3 -> 25%, 1:4 -> 20%.

---

## R-001: BASELINE — 3.0 / 30 / 30 / MR-first (LOCKED)

- Date tested: 2026-04
- Config: gap 3.0, stop 30, target 30, mean-reversion first-touch
- Trades: 526
- Win rate: 52.9% (278 W / 247 L / 1 flat)
- P&L: +987.5 pts = +$1,975
- Expectancy: +1.88 pts/trade = +$3.75/trade
- Exits: 271 target / 237 stop / 18 force-close
- Yearly: 2024 (May to Dec) +$436, 2025 -$81.50, 2026 (Jan to Apr) +$1,620.50
- Max drawdown: -$1,349.50 over 369 days
- Best month: 2024-08 +$580
- Worst month: 2025-05 -$695 (41 trades, 34.1% WR)
- Profitable months: 12 of 24
- Notes: This is the locked baseline. trades.parquet in data/processed/ corresponds to this config.

---

## R-002: Tighter cluster gap — 2.0 / 30 / 30 / MR-first

- Date tested: 2026-04
- Config: gap 2.0, stop 30, target 30, mean-reversion first-touch
- Trades: 313
- Win rate: 51.8%
- P&L: +$882
- Expectancy: +1.41 pts/trade
- Notes: Profitable but weaker than baseline. Tighter gap means fewer, stricter clusters but does not improve edge.

---

## R-003: Last-touch entry with 1 to 2 R:R — 2.0 / 20 / 40 / MR-last

- Date tested: 2026-04
- Config: gap 2.0, stop 20, target 40, mean-reversion last-touch
- Trades: 307
- Win rate: 30.9%
- P&L: -$1,267
- Breakeven WR: 33.3% (achieved 30.9%)
- Notes: Last-touch entry (waiting until price traverses entire cluster before entering at far boundary) significantly underperformed first-touch. Wider stops and targets did not compensate.

---

## R-004: Wider stop and target — 3.0 / 45 / 45 / MR-first

- Date tested: 2026-04
- Config: gap 3.0, stop 45, target 45, mean-reversion first-touch
- Trades: 511
- Win rate: 45.4%
- P&L: -$4,329
- Breakeven WR: 50%
- Notes: Wider risk-reward at 1:1 made the strategy unprofitable. Suggests the 30-point distances are tuned to typical noise levels; widening them captures less directional edge.

---

## R-005: Breakout reversal — 3.0 / 30 / 40 / BO-last

- Date tested: 2026-04
- Config: gap 3.0, stop 30, target 40, breakout last-touch (entry on far boundary after traversal, in direction of breakout)
- Trades: 463 (approx)
- Win rate: 40.8%
- P&L: -$1,569
- Breakeven WR: 42.9%
- Yearly inversion: 2024 -$494, 2025 +$794, 2026 -$1,869
- Notes: CRITICAL FINDING. Breakout direction was profitable in 2025 (the year MR-first was flat-to-negative) and lost money in 2024 and 2026 (the years MR-first won). This year-by-year inversion suggests market regime alternated between mean-reverting and trending. Open question OQ-1: can a regime detector switch between MR and BO modes?

---

## Tick-based verification (overlap period 2026-03-12 to 2026-05-01)

- Period covered: 7 weeks of overlap with the M26 contract tick file
- Bar-based result for same period (Config R-001): +$240 / 12 trades
- Tick-based result for same period (Config R-001): different P&L due to:
  - 2 phantom fills (limit appeared filled in bars but ticks show price never reached the limit)
  - 5 same-bar chronology bugs (ambiguous bars where stop-first conservative was wrong)
- Net effect: tick simulator showed strategy still profitable but ~$240 lower than bar simulator on the overlap.
- Conclusion: bar-based backtest has small but real biases. Direction of bias: optimistic by ~$120 per phantom fill. Tick verification recommended for any production deployment.
- Other R:R configs tested on ticks for the overlap period:
  - 30/30 (Config A, baseline): see above
  - 10/30 (1:3 R:R): tested, results in tick_simulator output
  - 15/30 (1:2 R:R): tested
  - 5/20 (1:4 R:R): tested
- Notes on tick configs: with only 7 weeks and approximately 12 trades per config, statistical significance is very low. Treat as exploratory only. Full-history tick data not available.

---

## Robustness checks on baseline

- Yearly P&L (see R-001 above): edge concentrated in 2024 and 2026 YTD; 2025 was flat-to-negative.
- Profit concentration: removing top 5 days reduced P&L significantly (specific number to be re-computed and added).
- Look-ahead bias audit: passed. Today's ORB is computed at 9:45 from 9:30 to 9:45 bars only; trading begins at 9:46; no future information used.
- Statistical significance: ~1.3 sigma above breakeven, p approximately 0.09. Edge cannot be distinguished from random noise at conventional thresholds.
- Cluster width distribution: median 3.5 pts, 90th percentile 6 pts, max observed 12 pts.
- Cluster size distribution: vast majority are exactly 3 levels (the minimum). Larger clusters (5+ levels) are rare and did not show meaningfully different performance.

---

## Test template (for future experiments)

When adding a new entry, use this template:

R-XXX: short title — gap / stop / target / direction-entry

- Date tested: YYYY-MM
- Config: gap X.X, stop X, target X, direction-entry
- Trades: N
- Win rate: XX.X% (W / L / flat)
- P&L: $ (or pts)
- Expectancy: pts/trade
- Exits: target / stop / force-close
- Yearly split: 2024, 2025, 2026
- Max drawdown: $ over N days
- Notes: hypothesis tested, result interpretation, follow-up actions
- Output file: results/archive/trades_<descriptor>.parquet
