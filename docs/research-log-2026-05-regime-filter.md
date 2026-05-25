# Regime Filter Investigation — Research Log

**Date:** May 10, 2026
**Strategy under study:** ORB fade (3-pt entry threshold, 30/30 stop/target, first-touch fade)
**Instrument:** MNQ futures, 1-minute bars
**Data window:** ~April 2024 – May 2026 (~25 months, 538 ORB sessions)
**Baseline P&L:** +$1,975 (locked; not modified by any test in this log)

---

## Research question

Can a regime filter — applied before each session, using only information available at that point — improve the ORB fade strategy?

The original framing was directional ("use a regime indicator to decide whether to take long or short fades at clusters"). Through investigation this evolved into a volatility-regime question ("are some volatility regimes systematically better for the strategy than others?") because no directional signal could be found in prior price action.

---

## Important dataset caveat

Calendar-year boundaries are misleading:

| Year | Trading days | Effective period | Status |
|------|--------------|------------------|--------|
| 2024 | 196 | ~April–December | Partial (~9 months) |
| 2025 | 257 | January–December | Full year |
| 2026 | 85 | ~January–early May | Partial (~4 months) |

Only 2025 is a full calendar year. Equal-length chronological thirds (~179 days each) gave the cleanest cross-period comparisons:

- **P1:** 2024-04-01 → 2024-12-06 (180 days)
- **P2:** 2024-12-09 → 2025-08-20 (179 days)
- **P3:** 2025-08-21 → 2026-05-01 (179 days)

---

## Hypotheses tested and outcomes

### H1 — ORB size predicts strategy regime

**Tested:** Quartile breakdown of fade vs breakout strategy P&L by daily ORB size, cross-year and within-year.

**Result:** The relationship was unstable and confounded with calendar position.

- 2024 large-ORB days: fade strongly best (+$300 in Q4)
- 2025 large-ORB days: breakout slightly better (small effect, ~$5/day differential)
- 2026 large-ORB days: fade strongly best again (+$481 in Q4 on 21 days)

ORB sizes also trended upward across the dataset (Q1 was 60% 2024 days; Q4 was 51% 2025 + 31% 2026), so quartile comparisons were partly time comparisons.

**Verdict: rejected.** ORB size is not a stable regime indicator on its own.

### H2 — Lagged 10-day return as regime indicator

**Tested:** Tercile classification of sessions (downtrend / chop / uptrend) using lagged 10-day MNQ return. Look-ahead bias identified and fixed (using prior session's close).

**Behavioral check (key finding):** The label captures **volatility, not direction**.

| Label | Mean range (pts) | % close > open |
|-------|------------------|----------------|
| Downtrend | 498 | 53.4% |
| Chop | 353 | 58.2% |
| Uptrend | 321 | 53.4% |

All three regimes had positive mean and median session moves. The label has no directional content; it captures the leverage effect (declines come with high volatility).

**Strategy-level result (10d):**

| Regime | Days | P&L | $/day | WR |
|--------|------|-----|-------|----|
| Downtrend (high-vol) | 174 | +$1,562 | +$8.97 | 56.5% |
| Chop | 177 | +$716 | +$4.05 | 52.6% |
| Uptrend (low-vol) | 176 | −$303 | −$1.72 | 46.7% |

**Robustness across lookbacks (8/10/12 day):**

| Lookback | high-vol $ | low-vol $ |
|----------|-----------|-----------|
| 8d | +$1,943 | −$483 |
| 10d | +$1,562 | −$303 |
| 12d | +$1,050 | **+$267** (sign flip) |

High-vol regime sign stable; low-vol regime sign fragile.

**Verdicts:**
- Directional filter (long-vs-short by regime): **rejected.** No directional content.
- Volatility filter (skip low-vol days): **rejected.** Parameter-fragile.

### H3 — ATR-based volatility regime indicator

**Tested:** Tercile classification (low_vol / mid_vol / high_vol) using lagged ATR-N for N ∈ {8, 10, 12}.

**Why ATR over return:** Direct measurement of range vs. proxy via leverage effect. Agreement between ATR and return labels was only 44% — they capture overlapping but distinct phenomena (ATR catches high-vol up-days that return-labels miss).

**Result across lookbacks:**

| Lookback | high_vol $ | high_vol $/day | high_vol WR |
|----------|-----------|----------------|-------------|
| 8d | +$2,694 | +$15.39 | 59.5% |
| 10d | +$2,034 | +$11.55 | 57.7% |
| 12d | +$2,608 | +$14.99 | 59.6% |

High_vol cell positive at every lookback. Cutoffs remarkably stable across lookbacks (~313 / ~417 pts).

**Cross-year stability (10d ATR):**

| Regime × Year | 2024 | 2025 | 2026 | Total |
|---------------|------|------|------|-------|
| low_vol | −$245 | +$60 | +$262 | +$77 |
| mid_vol | −$20 | −$334 | +$218 | −$136 |
| high_vol | +$700 | +$192 | +$1,141 | +$2,034 |
| **Year total** | **+$436** | **−$82** | **+$1,621** | **+$1,975** |

**Cross-period stability (chronological thirds, 10d ATR):**

| Regime × Period | P1 | P2 | P3 | Total |
|-----------------|------|------|------|-------|
| low_vol | −$245 | −$60 | +$382 | +$77 |
| mid_vol | +$161 | −$214 | −$82 | −$136 |
| high_vol | +$520 | +$544 | +$969 | +$2,034 |
| **Period total** | **+$436** | **+$270** | **+$1,268** | **+$1,975** |

| Period | high_vol days | $/day | Reliability |
|--------|---------------|-------|-------------|
| P1 | 18 | +$28.89 | Small sample — noisy |
| P2 | 65 | +$8.38 | Reliable |
| P3 | 93 | +$10.42 | Reliable |

**Reliable expected per-day rate from a high_vol day: +$8 to +$10.**

**Verdict on ATR regime indicator:** Real, sign-stable signal. The 2025 calendar weakness was partly a partial-year artifact — P2 (mostly 2025) shows healthy +$8.38/day.

---

## Filter performance summary

If the filter "trade only high_vol days" is applied at 10d ATR:

| Period | Baseline | Filtered | Δ |
|--------|----------|----------|---|
| P1 | +$436 | +$520 | +$84 |
| P2 | +$270 | +$544 | +$274 |
| P3 | +$1,268 | +$969 | **−$299** |
| **Total** | **+$1,975** | **+$2,033** | **+$59 (+3%)** |

The filter helps early and middle periods but **hurts the most recent period (P3)** because P3's low_vol days became profitable (+$382 vs P1's −$245). Net aggregate improvement is small.

---

## Side asymmetry within high_vol (post-hoc, unconfirmed)

Noticed during analysis, not tested as a deliberate hypothesis. Treat as a candidate finding for future work, not a confirmed signal.

| Period | high_vol BUY | high_vol SELL |
|--------|--------------|----------------|
| P1 | +$420 (88.9% WR, 9 trades) | +$100 (55.6% WR, 9 trades) |
| P2 | +$287 (55.6% WR, 27 trades) | +$257 (58.6% WR, 29 trades) |
| P3 | +$660 (60.0% WR, 55 trades) | +$309 (53.6% WR, 84 trades) |

high_vol BUY is positive in every period. high_vol SELL is mixed. Note: this **reverses** the aggregate "sell-side dominance" finding from the return-based labeling — that turned out to be year-specific (2024 was buy-dominant).

---

## Decisions

| Idea | Status | Reasoning |
|------|--------|-----------|
| ORB-size regime filter | Rejected | Not stable across years; year-confounded |
| Direction filter from prior price action | Rejected | No directional signal |
| Hard ATR-tercile filter (trade only high_vol) | Not recommended | +3% aggregate; hurts most recent period |
| Soft position sizing by volatility regime | **Open candidate** | Not tested; preserves trades, weights toward profitable regime |
| Acknowledge "strategy works best in high-vol" without filtering | Recommended for now | Conservative; preserves baseline; avoids overfit |

---

## Methodological learnings

1. **Look-ahead bias is easy to introduce by accident.** The 10-day return was originally computed using same-day close — a small but real leak. Fix: lag indicators by at least one session before using them as filters.

2. **Calendar years can hide structure.** 2024 and 2026 are partial years. Equal-length chronological thirds gave cleaner cross-period comparisons than calendar-year buckets.

3. **Tercile labels on continuous indicators have boundary instability.** ~25% of days flip regime when changing the lookback by 2 days. Tercile filters are inherently sensitive at the boundaries.

4. **Volatility regimes drift over time.** Across the 25-month dataset, the share of high_vol days went from 18/180 (P1) to 93/179 (P3). Fixed-cutoff regime classifications partly classify calendar position, partly market state.

5. **Direct measurements beat proxies.** ATR (direct range) outperformed 10-day return (proxy via leverage effect) as a volatility regime indicator. Switching from return-based to ATR-based labels lifted the high_vol cell from +$1,562 to +$2,034 at the same lookback.

6. **Each new test on the same data raises multiple-comparisons risk.** This investigation ran ~7 distinct tests. Some surviving patterns may still be artifacts. Paper-trade and out-of-sample-validate before committing capital.

---

## Code artifacts produced

- `src/simulator_breakout.py` — copy of `simulator.py` with the breakout direction implemented (used in H1 quartile analysis). Required adding a `trigger_above` field to `Setup` to decouple trigger condition from trade side.
- `results/archive/trades_breakout.parquet` — 526 breakout-strategy trades, mirror-side of the locked baseline.
- Locked baseline `data/processed/trades.parquet` — **untouched throughout this investigation.**

---

## Open items for the next phase of strategy development

The regime question has been studied to diminishing returns. Candidates for the next building block:

- **Time-of-day filtering.** Do clusters fired at certain hours perform differently? Cheap to test, clean structure.
- **Cluster-quality filtering.** Are some clusters structurally weaker (very tight, near previous-day levels, etc.) and worth excluding?
- **Stop/target asymmetry.** The 30/30 was a starting choice. Explore alternatives (with overfit guards).
- **News/event awareness.** Avoid FOMC days, CPI days, etc., or apply different parameters.
- **Position sizing on conviction.** Some setups may warrant larger size.
- **Soft volatility-based position sizing** (carry-over from this investigation).

---

## Final note on the baseline

After 25 months and 538 sessions, the baseline ORB fade strategy made **+$1,975**, or roughly **+$80 per month** before any filter. Per-day expectation is ~$3.75. Against MNQ tick value, the strategy's edge is real but small in absolute terms. Future filtering or refinement should be evaluated not just by total P&L but by per-day rate, drawdown profile, and risk-adjusted performance — none of which were measured in this investigation.
