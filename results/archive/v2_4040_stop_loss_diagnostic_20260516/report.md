# V2 + 40/40 stop-loss diagnostic — Bug A / Bug B / phantom-suspect flagging

**Date:** 2026-05-16
**Scope:** All 336 stop-outs in `results/40_40_v2_full/20260514_125349/trades.parquet` (sha256 `1ccf859e…feb`).
**Locked baseline preserved:** `data/processed/trades.parquet` sha256 `d24f128a…f4c6` unchanged.
**Bars source:** `data/processed/mnq_adjusted_1m.parquet` sha256 `9c14cfac…e299` (60 MB, 2,467,393 1-min bars).
**Bug definitions:** `docs/decisions.md:D-005` (Bug A — same-bar stop+target ambiguity, pessimistic), `D-014` (Bug B — entry-bar chronology, optimistic), `D-015` (phantom fills — unconfirmed without tick data).

---

## Summary table — counts and prevalence

| Flag | Count | % of 336 stop-outs | Doc estimate (32-trade slice at 30/30) |
|---|---:|---:|---|
| **Bug A** (exit-bar range spans both stop and target) | **0** | **0.00%** | ~1% across all trades |
| **Bug B** (entry and exit on the same minute bar)    | **11** | **3.27%** | ~3% across all trades |
| **Both A and B**                                      | 0 | 0.00% | — |
| **Phantom-suspect** (wick ≥ 8pt past body, heuristic) | 100 | 29.76% | ~6% on tick-confirmed slice |
| Neither A nor B                                       | 325 | 96.73% | — |

**Bug A on stop-outs at 40/40 is zero by geometry.** The check requires the exit bar to span ≥80 points symmetric around the entry price. The 40/40 bracket *is* that 80-point window; for a stop-out bar to also reach the target, a single 1-min MNQ bar would have to traverse 80+ points — well outside normal range. The 30/30 bracket only requires a 60-point span and so has materially higher Bug A exposure. **At 40/40, widening the bracket essentially eliminates Bug A on stop-outs.**

**Bug B on stop-outs at 40/40 matches the doc estimate almost exactly** (3.27% observed vs ~3% documented at 30/30). These are entry-bar chronology suspects — the same 1-minute bar that triggered the entry also took out the 40-point stop. Without tick data we can't tell whether the bar's path was *entry → stop* (real stop-out) or *stop level → entry → stop* (Bug B: simulator credits stop hit when the extreme actually preceded the limit fill).

**Phantom-suspect is a loose heuristic.** It flags stop-outs where the stop-triggering extreme is ≥8 points past the bar's body. 30% of stops have this property, but most are likely just volatile bars, not non-trade prints. Confirming requires tick data on the Mac mini (D-015). Treat as advisory only.

---

## Sensitivity bounds — what if flagged stops resolved differently?

| Scenario | Stop-out P&L | Total strategy P&L (baseline +$8,808) |
|---|---:|---:|
| **Current (no correction)**                                | −$26,880.00 | +$8,808.00 |
| Bug A flipped to targets (×0 trades)                       | −$26,880.00 | +$8,808.00 |
| Bug B trades → flat ($0)                                   | −$26,000.00 | +$9,688.00 |
| Bug B trades → force-close (avg +$2.52)                    | −$25,972.25 | +$9,715.75 |
| BOTH (A→target + B→flat)                                   | −$26,000.00 | +$9,688.00 |
| BOTH (A→target + B→force-close)                            | −$25,972.25 | +$9,715.75 |

**Upper-bound recovery: ~$908** if every Bug B candidate resolved as a force-close instead of a stop. That is **10.3% of the stop-out loss** and **3.3% of the headline +$8,808 strategy P&L**.

**These are strict upper bounds.** The reality is between current and corrected:

- Bug B trades whose tick path was genuinely *entry → stop* are correctly logged as stop-outs in the bar simulator and would stay losses.
- Bug B trades whose tick path was *stop-level extreme → entry → opposite-favorable-move* would not have been entered in the first place at the limit (the price gapped past); they'd be no-trades, not flats.
- The "flat $0" and "force-close avg $2.52" scenarios are framing devices, not predictions.

---

## Distributions

### Wick-distance histogram (stop-outs)

| Wick distance from body (pts) | Count | % |
|---|---:|---:|
| 0–2   | 58 | 17.3% |
| 2–4   | 84 | 25.0% |
| 4–8   | 94 | 28.0% |
| 8–12  | 57 | 17.0% |
| 12–20 | 27 |  8.0% |
| 20–50 | 16 |  4.8% |
| 50+   |  0 |  0.0% |

Median wick distance is ~4 pts; the tail at 8–50 (30% of stops) is what the heuristic flags. No extreme outliers (50+ pt wicks).

### Per-year breakdown

| year | stops | bug_a | bug_b | phantom-suspect | stop P&L |
|---:|---:|---:|---:|---:|---:|
| 2019 | 13 | 0 | 0 |  2 | −$1,040 |
| 2020 | 33 | 0 | 1 |  4 | −$2,640 |
| 2021 | 35 | 0 | 0 |  7 | −$2,800 |
| 2022 | 59 | 0 | 0 | 22 | −$4,720 |
| 2023 | 52 | 0 | 1 | 11 | −$4,160 |
| 2024 | 43 | 0 | 2 | 11 | −$3,440 |
| 2025 | 52 | 0 | 3 | 18 | −$4,160 |
| 2026 | 49 | 0 | 4 | 25 | −$3,920 |

Bug B incidence is **rising** in recent years (4 in 2026 partial vs 0–1 in 2019–2023). Phantom-suspect is heavily concentrated in 2022 (22 stops) and 2026 partial (25 stops, on track for highest annual rate) — both correspond to higher-volatility periods. Phantom-suspect rate tracks bar-range volatility, not necessarily phantom-print prevalence.

### Bug B time-of-day (NY)

All 11 Bug B candidates fired between **9:46 and 10:55 NY** — the first hour of the trading window:

| NY time | count |
|---|---:|
| 09:46 | 4 |
| 09:50 | 1 |
| 09:54 | 1 |
| 10:01 | 1 |
| 10:03 | 1 |
| 10:20 | 1 |
| 10:41 | 1 |
| 10:55 | 1 |

**4 of 11 fired at 09:46 itself** — the very first bar of the trading window. This is consistent with post-ORB volatility being elevated and limits closer to ORB extremes being more likely to fill on a single fast-moving bar.

### Bug × cluster_label cross-tab

|  | Bug B = True | Bug B = False | total |
|---|---:|---:|---:|
| FADE  | 3 | 151 | 154 |
| TREND | 8 | 174 | 182 |
| **total** | **11** | **325** | **336** |

Bug B is over-represented in TREND label trades (8/11 = 73% of bug B, vs TREND's overall 54% share of stops). TREND trades trade *with* the prior direction, so a fast-moving bar that fills the limit and continues past the stop is the most direct mechanism — supports Bug B being a real chronology effect rather than random labeling noise.

Phantom-suspect distribution is closer to even (51 FADE / 49 TREND vs the overall 154/182 split) — consistent with the phantom heuristic mostly capturing volatility, not regime-correlated bug exposure.

---

## Concluding interpretation

**Stop-outs at V2 + 40/40 are credible.** The maximum recoverable P&L under bar-bug correction is at most **~$908** (10.3% of the −$26,880 stop-out loss, 3.3% of the +$8,808 headline). The 40/40 bracket essentially eliminates Bug A exposure on stop-outs by widening past the typical 1-min bar range; Bug B exposure tracks the documented ~3% rate exactly. The headline +$8,808 is not at meaningful risk from these two known bar-data biases on the stop-out side.

**Caveats:**

1. **Phantom fills (D-015) are unconfirmed without tick data.** The 30% phantom-suspect rate here is a loose heuristic (wick ≥ 8pt past body) and most of those are likely volatile-bar wicks, not non-trade prints. Real phantom-fill incidence at the doc-estimated ~6% rate could move the figure either direction, but without tick reconciliation on the Mac mini it cannot be quantified. The 8–50pt wick population (100 trades, 30% of stops) is the upper bound of trades worth re-running through the tick simulator.

2. **This diagnostic covers the stop-out column only.** Bug A pessimistic bias is symmetric — it could also be marking trades as stops that tick-truth would call targets. But the same-bar-spans-80pts requirement (Bug A) returned 0 hits on stop-outs at 40/40, so by the same logic it would also return ~0 hits on the 442 target-outs (no bar simultaneously spans both). The 40/40 geometry self-protects.

3. **Bug B's optimistic direction means the 11 flagged stops are *not* recoverable wins under correction — they are recoverable losses.** If tick-truth shows the bar's range actually preceded entry, the simulator over-credited the stop hit. Under correction, those trades either don't enter (the limit doesn't fill because price gapped past) or they exit at a different price entirely. The "$880 → $908" upper-bound recovery is a hypothetical, not a guarantee.

4. **The 4 Bug B candidates at 09:46 NY** (the very first bar of each trading window) deserve a tick-level look on the Mac mini — they are the cleanest cases for direct chronology verification.

5. **The diagnostic does NOT modify any source code or strategy. The locked baseline `trades.parquet` is unchanged. The V2 + 40/40 run output is unchanged.** Findings should be referenced from §8 (Known caveats) of `docs/strategy-reference.md` in a separate edit if the user chooses.

---

## Artifacts

- `stop_outs_flagged.parquet` — 336 rows × 24 columns, per-trade flagging with `bug_a`, `bug_b`, `phantom_suspect`, `body_edge`, `wick_distance`, plus all exit-bar OHLC and original trade fields.
- `summary.json` — machine-readable counts, percentages, P&L deltas, per-year breakdown.
- `_run.py` — diagnostic script (re-runnable; idempotent on inputs).
- `report.md` — this file.

---

## Reproducibility

```
python results/archive/v2_4040_stop_loss_diagnostic_20260516/_run.py
```

Reads from `results/40_40_v2_full/20260514_125349/trades.parquet` and `data/processed/mnq_adjusted_1m.parquet`. Writes to the same directory only. No mutations to source data or other artifacts.
