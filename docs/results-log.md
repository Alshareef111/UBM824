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
- Tick-truth caveat: Bar-sim result +$1,975 confirmed mechanically, but tick verification on 2026-03-17 to 2026-04-15 (32 trades) showed bar-sim overstated P&L by ~100% on that slice. Full-period tick verification not yet performed; projected true P&L could be near breakeven or modestly negative. See "Tick-based verification" section below and decisions.md D-014, D-015.

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

## Tick-based verification (overlap period 2026-03-17 to 2026-04-15)

- Period covered: 4 weeks of overlap with the M26 contract tick file
- Bar-based result for same period (Config R-001): +$240 / 32 trades
- Tick-based result for same period (Config R-001): $0 / 32 trades — a 100% overstatement of edge by the bar simulator on this slice.
- Three distinct bias mechanisms identified:
  - Bug A (D-005): Same-bar stop+target ambiguity. When both stop and target lie within a single bar's range, the simulator applies the stop-first conservative rule. Affects ~1% of trades; flipping to target-first only changes total P&L by +$600. Direction: pessimistic.
  - Bug B (D-014): Entry-bar chronology. On the entry bar, the simulator counts target/stop hit if bar.high/low crosses the level, even when that extreme occurred BEFORE the limit fill within the minute. Verified on 2026-04-08: bar opened above target (25128.75 > 25115.50), then fell to fill the buy limit at 25085.50, then continued down to stop at 25055.50. Simulator credited target; tick reality was stop. ~3% rate. Direction: optimistic.
  - Phantom fills (D-015): ~6% rate (2 of 32 overlap trades). Cause: Databento OHLCV bar high includes non-trade prints (implied levels, RFQ quotes); NinjaTrader Last shows only executed trades. So the bar high can exceed any actually-traded price, making a limit appear filled in bar-sim when no real trade occurred at that price. Direction: optimistic.
- Conclusion: Bar simulator has multiple known biases that net optimistic and compound to ~100% overstatement on this slice. Full-period tick verification remains pending. Tick verification is required for any production deployment.
- Other R:R configs tested on ticks for the overlap period:
  - 30/30 (Config A, baseline): see above
  - 10/30 (1:3 R:R): tested, results in tick_simulator output
  - 15/30 (1:2 R:R): tested
  - 5/20 (1:4 R:R): tested
- Notes on tick configs: with only 4 weeks and ~32 trades for Config A (fewer for tighter-stop configs), statistical significance is very low. Treat as exploratory only. Full-history tick data not available.

---

## Robustness checks on baseline

- Yearly P&L (see R-001 above): edge concentrated in 2024 and 2026 YTD; 2025 was flat-to-negative.
- Visual market-regime finding: across 6 chart reviews (2024-08-02, 2024-12-20, 2025-01-08, 2025-02-27, 2026-04-02, 2026-04-08), the strategy clearly succeeds in range-bound days and fails in trending days. The 2025 weakness aligns with this — likely a more trending year than 2024 or 2026. Open research question (OQ-1) is whether a regime indicator (ATR / ADX / ORB-width-relative) can identify trending sessions before entry; risk: overfitting on a small sample.
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

---

## R-006: Historical + forward dataset extension — fade-only 7-year OOS

- Date tested: 2026-05-11
- Config: 3.0 / 30 / 30 / MR-first (same as locked baseline), but on 7-year dataset (2019-05-06 → 2026-05-10)
- Trades: 1,693
- Win rate: 48.7% (824 W / 867 L / 2 flat)
- P&L: −$3,377.50
- Exits: target 736 / stop 798 / force_close 159
- Period split:
  - Historical OOS [2019-05-06, 2024-03-31]: 1,080 trades / 46.3% / **−$5,534.50** (loses in 5 of 6 years)
  - In-sample [2024-04-01, 2026-05-01]: 613 trades / 52.9% / +$2,157.00 (+$182 vs locked baseline, from 87 extra trades during deque warm-up)
  - Forward [2026-05-04, 2026-05-08]: 0 trades (MNQ rallied above 200-session level pool)
- Yearly: 2019 −$1,732 / 2020 −$972 / 2021 +$86 / 2022 −$1,898 / 2023 −$959 / 2024 Q1 −$60 / 2024 Apr+ +$618 / 2025 −$82 / 2026 +$1,621
- Output: `results/archive/trades_baseline_extended_20260511.parquet`
- Cross-validation: trades with `entry_time >= 2025-02-01` byte-identical to locked baseline (`assert_frame_equal(check_exact=True)`); confirms multi-CSV pipeline is sound, OOS results are believable.
- Verdict: locked baseline does not survive historical OOS. +$1,975 in-sample is regime-specific, not generalizable edge. Full details: `docs/research-log-2026-05-historical-extension.md`.

---

## R-007: Hybrid 30/30 — re-run on 7-year extended dataset

- Date tested: 2026-05-11
- Config: 3.0 / 30 / 30 / hybrid (fade if `|expected_norm_dist| > 0.09`, else reverse to breakout)
- Trades: 1,693
- Win rate: 49.9% (844 W / 847 L / 2 flat)
- P&L: +$62.50
- Exits: target 768 / stop 766 / force_close 159
- Routing: directional 1,072 (−$1,477.50) / flat 619 (+$1,540.00)
- Period split:
  - Historical OOS: 1,080 / 48.0% / **−$2,232.50** (regime classifier inverts: directional −$3,884, flat +$1,651)
  - In-sample: 613 / 53.2% / +$2,295.00 (directional +$2,406, flat −$111)
  - Forward: 0 trades
- Output: `results/archive/trades_hybrid.parquet` (overwritten — prior version backed up locally at `trades_hybrid.parquet.pre-extend-20260511`)
- Key finding: **regime classifier sign-flips between periods**. Same indicator produces opposite payoffs across historical/in-sample. The +$2,723 in-sample-only hybrid figure from the prior research log was regime-specific.
- Verdict: combined +$62 over 7 years is statistically indistinguishable from breakeven; the in-sample edge does not generalize. Full details: `docs/research-log-2026-05-historical-extension.md`.

---

## R-008: Hybrid 40/40 variant — wider stop and target

- Date tested: 2026-05-11
- Config: 3.0 / 40 / 40 / hybrid (otherwise identical to R-007)
- Trades: 1,600
- Win rate: 48.7% (779 W / 819 L / 2 flat)
- P&L: **−$3,216.00**
- Exits: target 666 / stop 704 / force_close 230 (force-close rate up 45% vs 30/30)
- Routing: directional 1,005 (**−$6,994.50**) / flat 593 (**+$3,938.50**)
- Period split:
  - Historical OOS: 1,000 trades / −$2,666 (Δ −$433 vs 30/30)
  - In-sample: 600 trades / **−$550** (Δ −$2,846 vs 30/30 — collapse)
  - Forward: 0 trades
- Yearly Δ vs hybrid 30/30: 2019 +$254 / 2020 −$249 / 2021 +$190 / 2022 **−$614** / 2023 +$7 / 2024 **−$1,365** / 2025 +$335 / 2026 **−$1,836**
- Output: `results/archive/trades_hybrid_4040_20260511.parquet`, variant src: `src/simulator_hybrid_4040.py`, charts: `results/charts/40_40_examples/*.png` (10 examples)
- Verdict: 40/40 is materially worse than 30/30. 30 points reflects MNQ's natural mean-reversion magnitude at this strategy's timeframe; wider stop amplifies trending losses while wider target misses the natural reversion bounce. Flat (breakout-routed) cell partially benefits (+$2,399) but doesn't offset the fade cell collapse (−$5,517). Full details: `docs/research-log-2026-05-variant-4040.md`.

---

## R-009: Priors-only fade variant — today's ORB excluded from clustering

- Date tested: 2026-05-11
- Config: 3.0 / 30 / 30 / MR-first, but today's ORB high/low NOT added to today's cluster pool (still propagates to tomorrow's deque)
- Trades: 1,491 (Δ −202 vs R-006)
- Win rate: 49.0% (730 W / 759 L / 2 flat)
- P&L: **−$2,373.00** (Δ +$1,004 vs R-006)
- Exits: target 652 / stop 696 / force_close 143
- Period split:
  - Historical OOS: 941 trades / −$4,640 (Δ +$894 vs R-006)
  - In-sample: 550 trades / +$2,267 (Δ +$110 vs R-006)
  - Forward: 0 trades
- Yearly Δ vs R-006: 2019 +$290 / 2020 −$86 / 2021 −$60 / 2022 **+$480** / 2023 +$211 / 2024 −$122 / 2025 **+$352** / 2026 −$60
- Trade overlap with R-006 baseline: 1,393 shared exactly / 300 dropped / 98 added / 45 entry-price shifted
- Output: `results/archive/trades_priors_only_20260511.parquet`, variant src: `src/simulator_priors_only.py`
- Verdict: modest improvement (~30% reduction in loss magnitude), same qualitative result. Today's ORB acts more as noise-introducer than structural anchor — eliminating it removes 300 net-negative-EV trade signals. Improvement concentrated in historically weak years where reducing trade frequency simply means fewer chances to lose. Full details: `docs/research-log-2026-05-variant-priors-only.md`.

---

## R-010: C2 one-position-rule diagnostic (not a new config — design property)

- Date investigated: 2026-05-11
- Diagnostic case: 2024-08-12 (chart #08 of 40/40 examples)
- Finding: the C2 rule (`if open_pos is None:` gate at `simulator_hybrid.py` line 202) permanently skips higher-quality cluster setups when a lower-quality one fires first. On 2024-08-12: a size-4 cluster fired at 09:46 and locked the engine until 10:06; during that lockout, a size-7 cluster and another size-4 were touched and **never re-touched after exit** → permanent skip.
- The strategy fires setups in temporal-touch order, not quality order. Tiebreaker on same-bar multi-touch is `closest limit to bar.open`, which is geometry-driven, not signal-quality-driven.
- No code bug; C2 is correctly implemented per spec D-004. The design itself has a known cost worth flagging.
- Possible future variants: (1) quality-prioritized C2 on candidate scan, (2) raise `MIN_CLUSTER_SIZE` from 3 to 4 or 5, (3) sequential entry with risk capping.
- No simulator output; documentation-only entry. Full details: `docs/research-log-2026-05-c2-rule-diagnostic.md`.

---

## R-011: V2 regime classifier — design spec (NOT IMPLEMENTED YET)

- Date drafted: 2026-05-11
- Status: **SPEC ONLY. No code, no simulator runs, no parquet output.**
- Motivation: the current `expected_norm_dist` hybrid classifier sign-flips across periods (see R-007). A v2 classifier should use proper trend-strength indicators (ADX/+DI/-DI/VWAP/ROC/ATR-expansion) at the daily timeframe.
- Proposed regime taxonomy: TRENDING_UP (long-side fades only) / TRENDING_DOWN (short-side fades only) / SIDEWAYS (both directions, current locked behavior) / MIXED (skip session).
- Six open design decisions pending: timeframe choice, VWAP anchor, filter aggressiveness, sideways behavior, mixed-regime handling, code structure.
- Caveat: even with a perfect regime classifier, the strategy still has the same geometry (fixed 30-pt bracket, ORB-anchored entries, C2). Today's findings suggest the bottleneck may not be regime detection — see R-010 (cluster-quality skipping), R-008 (geometry-aware R:R), and forward lockout (200-session pool below price).
- Full spec: `docs/research-log-2026-05-regime-v2-spec.md`. Resume from the six decisions tomorrow.
