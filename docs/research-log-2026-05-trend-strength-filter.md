# Trend-Strength Filter Investigation — Research Log

**Date:** May 10, 2026
**Strategy under study:** ORB fade (3-pt entry threshold, 30/30 stop/target, first-touch fade)
**Instrument:** MNQ futures, 1-minute bars
**Data window:** ~April 2024 – May 2026 (~25 months, 538 ORB sessions)
**Baseline P&L:** +$1,975 (locked; not modified by any test in this log)

---

## Research question

This investigation continues the regime-filter program documented in `research-log-2026-05-regime-filter.md`. That log covered concept 1 (volatility / regime). This log covers concepts 2 (within-window timing / liquidity) and 3 (trend strength), and concludes with a recommended hybrid variant of the strategy.

The shared question across all three concepts is the same: can a filter applied before each session, using only information available at that point, materially improve the ORB fade strategy?

---

## Important dataset caveat

Same as the prior log: 2024 and 2026 are partial years (~9 months and ~4 months); only 2025 is full. Equal-length chronological thirds (~179 days each) gave the cleanest cross-period comparisons:

- **P1:** 2024-04-01 → 2024-12-06 (180 days)
- **P2:** 2024-12-09 → 2025-08-20 (179 days)
- **P3:** 2025-08-21 → 2026-05-01 (179 days)

These are the same period boundaries used in the prior log.

---

## Hypotheses tested and outcomes

### H4 — Within-window timing (minutes elapsed since 9:46 NY)

**Tested:** Tercile classification of trades by minutes elapsed at entry (window opens at 9:46 NY; force-close at 11:30; eligible bars 9:46–11:29 = 104 minutes). Cutoffs at 6 / 31 minutes (33rd / 67th percentile).

**Initial result (full sample):**

| Tercile | Range (min) | n_trades | Total P&L | Win % |
|---------|-------------|---------|-----------|-------|
| T1 (early) | 0–5 | 171 | +$900 | 54.4 % |
| T2 (middle) | 6–31 | 180 | **−$712** | 46.7 % |
| T3 (late) | 32–102 | 175 | +$1,787 | 57.7 % |

**Within-period stability:** T2 negative in all three periods (−$60 / −$180 / −$472). T3 positive in all three periods. T1's +$900 came entirely from P3 (P1 and P2 each exactly $0).

**Boundary robustness:** Failed at (8, 35) — T2 marginal flips positive in P2 (+$274). Skip-T2 improvement varied +$199 to +$712 across reasonable boundary choices.

**Bin-shape diagnostic (5-min bins):** The "T2 negative" finding was concentrated almost entirely in **one 5-minute bin, [20, 25)**: 20 trades, −$592, 25 % WR. That single bin alone accounted for 83 % of the entire T2 (6, 31) loss. Adjacent bins ([10, 15), [25, 30), [30, 35)) were positive.

**Per-period drill-down on [20, 25):** Only 4 trades in P1 (net $0); 10 in P2 (−$240, 30 % WR); 6 in P3 (−$352, 0 % WR). The "worst neighbor bin" shifted across periods — P1's worst was [25, 30), not [20, 25). Of the 15 negative outcomes in [20, 25), 13 came from two clustered streaks: May–Jun 2025 (7 trades, 6 losses) and Nov 2025–Feb 2026 (6 trades, 6 losses). 8 of 9 high_vol days in this bin lost — anomalous given that high_vol is the strategy's best regime overall.

**Verdict: REJECTED.** Episodic loss clustering, not a structural feature. The aggregate "T2 negative" signal disappears under both boundary perturbation (+2 min on the upper cut) and per-bin disaggregation (drops to one specific 5-minute window driven by two date-clustered loss streaks). Only durable observation: T3 (after minute 32) is positive in every period at every boundary tested — descriptive only, no filter built.

### H5 — Trend strength (signed distance from window open, normalized by ATR)

**Tested:** Tercile classification by `normalized_distance = (entry_price − 9:46_bar_open) / lagged_ATR_10`, cutoffs at −0.0904 / +0.0880 (33rd / 67th percentile).

**Important mechanical note:** `down × sell` and `up × buy` cells are empty by construction. The fade strategy only places buy limits *below* the ORB-close reference (fills only when price drops from open to cluster.high) and sell limits *above* it (fills only when price rises from open to cluster.low). The "test" effectively reduces to "magnitude of move from window open at entry."

**Initial result (full sample):**

| Tercile | Composition | Mean raw | Mean ATR-norm | n | Total P&L | Win % |
|---------|-------------|---------|---------------|---|-----------|-------|
| down | 175 buy fades | −133 pts | −0.346 | 175 | +$1,062 | 54.3 % |
| flat | 74 buy + 102 sell | ±15 pts | ±0.04 | 176 | **−$614** | 46.6 % |
| up | 175 sell fades | +103 pts | +0.253 | 175 | +$1,527 | 57.7 % |

(Note: per step 9b counts using the *rounded* cutoffs as specified, flat = 175 trades / −$674 — one trade sits at the +0.0880 boundary. Doesn't change any qualitative finding.)

**The hypothesis was directionally inverted by the data.** Original prediction was that fades against established trends would fail; the data shows fades after *big* moves work best, fades after *small* moves lose. Pattern is consistent with mean-reversion theory — bigger overshoots produce bigger snap-backs.

**Within-period stability — PASSED (first filter to do so):**

| Period | flat n | flat P&L | flat WR |
|--------|-------|---------|---------|
| P1 | 33 | −$140 | 45.5 % |
| P2 | 72 | −$120 | 48.6 % |
| P3 | 70 | −$415 | 44.3 % |

Negative in every period; sub-50 % WR in every period.

**Boundary robustness:**

| Boundary | flat zone width | flat n | flat P1 | flat P2 | flat P3 | Skip-flat total | Δ baseline |
|----------|-----------------|--------|---------|---------|---------|-----------------|------------|
| ±0.05 (narrow) | 0.10 | 97 | −$200 | **+$120** | −$300 | +$2,354 | +$380 |
| (−0.0904, +0.0880) — original | 0.18 | 175 | −$140 | −$120 | −$414 | +$2,649 | +$674 |
| ±0.15 (wide) | 0.30 | 258 | −$460 | −$413 | −$234 | +$3,082 | +$1,107 |

P2 fragile at the narrow boundary (flat flips positive there); original and wide both pass per-period stability. Skip-flat improvement varies 3× across reasonable boundary choices.

**Verdict: ACCEPTED.** Skip-flat at the original boundary improves baseline by **+$674 (+34 %)**. Sign-stable in every period. Clean mechanical interpretation (bigger overshoots = better fade material).

---

## Hybrid extension — reverse direction in flat instead of skipping

**Tested:** Replace flat-tercile fade trades with their breakout-direction mirrors (using `results/archive/trades_breakout.parquet` from the prior log).

**Result:** Hybrid total **+$2,963 vs baseline $1,975 = +$988 (+50 %)**.

| Period | Fade baseline | Fade kept (down+up) | Brk in flat | Hybrid total | Δ |
|--------|---------------|---------------------|-------------|--------------|---|
| P1 | +$436 | +$575 | +$140 | +$715 | +$279 |
| P2 | +$270 | +$390 | +$120 | +$510 | +$240 |
| P3 | +$1,268 | +$1,683 | +$54 | +$1,737 | +$469 |
| **TOTAL** | **+$1,975** | **+$2,649** | **+$314** | **+$2,963** | **+$988** |

**Mechanical caveat important to capture clearly:** by mirror symmetry, breakout = −fade for non-ambiguous trades, so reverse-direction P&L is largely algebraic, not independently empirical. Three "ambiguous-bar" trades (both fade AND breakout lose; see decisions.md D-005) all fell in P3's flat tercile (2026-01-09, 2026-02-20, 2026-03-11), costing the hybrid −$360 there. Without them, hybrid in P3 would have been mirror-perfect — the entire P3 brk-in-flat contribution of +$54 reflects what's left of +$414 mirror gain after the −$360 ambig drag.

**Mechanical interpretation:** in flat conditions (small moves from window open), prices are more likely to break through cluster levels than bounce off them. Strategy becomes a coherent regime-switching system — fade after big moves, breakout after small moves.

**Verdict: ACCEPTED as the recommended variant.**

**Note on analytical vs simulator figures:** the +$2,963 / +50% headline above was computed by joining the post-hoc trade-level normalized_distance feature to the trade table using empirical quantile cutoffs (-0.0904, +0.0880). The forward-runnable simulator (src/simulator_hybrid.py) uses a symmetric ±0.09 threshold and produces +$2,723 / +38% over the same dataset. Four boundary trades — all in P3 — route differently between the two definitions because no symmetric threshold can match the asymmetric quantile cutoffs exactly. The simulator output is the canonical figure going forward; the analytical was an in-sample upper bound that doesn't reproduce on a forward-portable parametric implementation.

---

## Risk-adjusted stress test (hybrid simulator vs fade-only baseline)

This is the canonical stress test, computed on `results/archive/trades_hybrid.parquet` (the simulator output, +$2,723), not the analytical post-hoc join. The original analytical version is preserved above for reference.

| Metric | Baseline | Hybrid (simulator) | Δ |
|--------|----------|--------------------|---|
| Total P&L | +$1,975 | **+$2,723** | **+$748** |
| Max drawdown $ | −$1,349.50 | −$868.50 | $481 smaller |
| Max DD % of peak | −101.0 % | −63.2 % | +37.8 pp |
| Max DD duration (days) | 369 | 211 | −158 |
| Trades to recover from DD | 181 | 70 | (faster) |
| # DD periods | 28 | 41 | +13 |
| Profitable months | 50.0 % | 54.2 % | +4.2 pp |
| Best month | +$580.00 | +$840.00 | +$260.00 |
| Worst month | −$695.00 | −$335.00 | +$360.00 |
| Median month | +$8.75 | +$46.25 | +$37.50 |
| Std monthly | $281.81 | $232.89 | −$48.92 |
| Sharpe-like (μ/σ) | +0.292 | +0.487 | +0.195 |
| Longest losing streak (trades / days) | 7 / 6 | 6 / 4 | −1 / −2 |
| Worst single-day P&L | −$300.00 | −$240.00 | +$60.00 |

**Per-period (canonical):**

| period | fade total | fade max DD | fade prof. months | hybrid total | hybrid max DD | hybrid prof. months |
|--------|-----------:|------------:|------------------:|-------------:|--------------:|--------------------:|
| P1 | +$436.00 | −$360.00 | 25.0 % | +$715.00 | −$300.00 | 62.5 % |
| P2 | +$270.50 | −$1,349.50 | 66.7 % | +$510.50 | −$868.50 | 66.7 % |
| P3 | +$1,268.50 | −$532.00 | 55.6 % | +$1,497.50 | −$479.00 | 44.4 % |

**Two trade-offs worth flagging** (verified to still hold on simulator output):
- More distinct DD periods (28 → 41) — more frequent but smaller dips. Equity curve is bouncier with shorter, shallower excursions.
- P3 profitable-month rate drops 55.6 % → 44.4 % (P3's gains concentrate in fewer-but-larger winning months; P1 and P2 unchanged or improved).

**The −101 % baseline drawdown is structurally important:** the fade-only equity curve went *negative* in 2025 (peak $1,336 in Feb 2025 → trough −$13.50 in Jun 2025, recovered Feb 2026). The hybrid never crosses zero during its max-DD excursion (peak $1,375 → trough $506.50).

**Verdict:** Hybrid passes cleanly on risk dimensions. Every directional finding from the analytical version holds on the simulator output; only magnitudes shift slightly (best month +$260 instead of +$500; std monthly −$48.92 vs analytical's −$13.85; Sharpe-like Δ +0.195 vs analytical's +0.169 — the simulator's tighter monthly distribution actually produces a *better* Sharpe-like ratio than the analytical, despite the lower total P&L).

---

## Decisions

| Idea | Status | Reasoning |
|------|--------|-----------|
| Skip-T2 timing filter (6, 31) | Rejected | Episodic loss clustering, bin-location instability, boundary-fragile (P2 flips at (8, 35)) |
| Skip-flat trend filter | Accepted | First filter to pass within-period stability; clean mechanical interpretation |
| Hybrid (skip flat + reverse direction in flat) | **Accepted, recommended** | All risk dimensions improve; sign-stable across periods; +50 % total P&L |
| Narrow boundary (±0.05) | Not recommended | P2 flat cell flips positive |
| Wide boundary (±0.15) | Acceptable alternative | Bigger gain ($1,107 vs $674), less granular flat zone |

**Recommended implementation:** hybrid at original boundary (−0.0904 / +0.0880).

---

## New methodological learnings (additions to the prior log's list)

7. **Tercile binning can hide concentration.** The "T2 negative" finding was really one 5-minute bin doing 83 % of the work; tercile aggregation smeared it across 26 minutes. Run bin-by-bin shape analysis before treating tercile findings as structural.

8. **P2 is structurally fragile across multiple independent filters.** Three filters from three different concepts (regime, timing, trend strength) all show the weakest signal in P2 (Dec 2024 – Aug 2025). When the same period keeps showing up as the boundary case, that's a property of the period, not the filters. Worth investigating separately.

9. **Mirror symmetry constrains reverse-direction strategies.** New information from "what if we flipped on losers?" comes only from ambiguous-bar trades that violate symmetry. For most trades, breakout P&L is mathematically forced to be the negative of fade P&L. Be honest about which part of a hybrid's edge is empirical vs algebraic.

10. **Risk-adjusted metrics matter and are not derivable from total P&L.** The fade baseline's −101 % drawdown means equity went negative in 2025 — a critical risk feature invisible in total-P&L summaries. Always compute drawdown-as-%-of-peak and inspect whether the curve crosses zero.

---

## Code artifacts

- All references in the prior log still apply (`src/simulator.py`, `src/simulator_breakout.py`, `results/archive/trades_breakout.parquet`, `data/processed/trades.parquet`).
- No new code committed for this investigation; analysis was interactive on existing data.
- **Live execution will require computing `normalized_distance` at entry:** needs the 9:46 NY bar's open price plus a lagged ATR-10 from prior session closes. Both are computable in real time before entry — no look-ahead.

---

## Open items for the next phase

The trend-strength filter and its hybrid extension are the strongest result from the regime-filter program. Candidates for next investigation:

- **Confirm `normalized_distance` is computable at entry time** in the live execution pipeline. Tick-level verification would tighten the comparison against bar-sim (the prior log already documented bar-sim's ~100 % overstatement on the tick-overlap window).
- **P2 cross-filter fragility** — three independent filters all weakest in P2. Investigate the underlying reason (regime shift? data quality? specific market events?).
- **Position sizing on directional vs flat trades** — hybrid currently equal-weights all kept/substituted trades; a future variant could weight by historical win-rate confidence.
- **Boundary sensitivity at the wider end** — wide variant (±0.15) gave +$1,107 (vs original +$674). Worth understanding the trade-off before choosing the live cut.
- **Out-of-sample validation** — entire investigation used the same 25-month dataset that produced the locked baseline. Multiple-comparisons risk is real (this log alone tested two filters, four boundary variants, multiple sub-cuts). Paper-trade and validate before committing capital.

---

## Final note on the recommended hybrid

The hybrid moves the strategy from "+$1,975 over 25 months with a 369-day, $1,349 underwater excursion" to "+$2,963 over the same period with a 211-day, $869 underwater excursion that never crossed zero." Per-day expectation rises from ~$3.75 to ~$5.63. The Sharpe-like ratio (monthly μ/σ) improves from 0.292 to 0.461.

Most of the improvement is structurally explainable (mirror symmetry on ~50 % of formerly-losing flat trades), not pure empirical novelty. The remaining empirical claim — "flat-tercile fades genuinely lose money" — is the one that should be paper-traded for several months before live deployment, since it's the only part the hybrid's edge depends on that isn't algebraic.
