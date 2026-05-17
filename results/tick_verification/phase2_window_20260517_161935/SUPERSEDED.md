# SUPERSEDED — Phase 2 window run 20260517_161935

**Status:** Headline numbers in this directory's `report.md` and `summary.json` are **price-frame artifacts, not measurements.**

## What went wrong

The verifier in this run compared the bar simulator's **Panama back-adjusted** trade prices (from `data/processed/mnq_adjusted_1m.parquet`) against the tick cache's **raw front-month** prices (built via `src/build_tick_cache_databento.py` from a Databento `MNQ.c.0` continuous download). The two series differ by per-contract Panama offsets (single source of truth: `src/data_prep.build_adjustments` on `data/processed/rolls.parquet`).

For the Tight-window subset (2026-01-01 → 2026-05-01):

- **2026-01-01 → 2026-03-16** (MNQH6 era): Panama offset = **+213.75 pts** → raw ticks were 213.75 pts *below* the price frame the verifier compared them against. For "cluster above market" setups (limit `cluster.low`, trigger condition `bar.high >= limit`), no raw tick ever reached the Panama-shifted limit → **false PHANTOM_ENTRY**. For "cluster below market" setups (limit `cluster.high`, trigger `bar.low <= limit`), raw ticks were already past the limit at minute open → **false gap-fill** classified as BUG_B_NEXT_BAR or OTHER.
- **2026-03-23 → 2026-04-30** (MNQM6 era): Panama offset = 0 → verifier was correct for this subset.

## How we discovered it

While running Investigation 1 (phantom mechanism — bar.high vs tick.last_max) in `investigation_notes.md`, the gap was suspiciously constant across all 56 phantoms (range 212.75 – 219.50, mean **+213.93 pts**). A real phantom-print effect would show variable per-trade gaps; a constant ~213 pt gap is a single offset. Direct cross-check confirmed: `bar.open − first_tick.last` is exactly +213.75 on every pre-roll sampled minute and exactly 0 on every post-roll minute. The boundary aligns with the MNQH6 → MNQM6 rollover in `rolls.parquet`.

## Magnitude of artifact

| Metric | This run (artifact) | Corrected run | Swing |
|---|---:|---:|---:|
| MATCH (in-window) | 14 (12.7%) | 99 (90.0%) | +85 |
| PHANTOM_ENTRY | 56 (50.9%) | 3 (2.7%) | −53 |
| BUG_B_NEXT_BAR | 16 | 0 | −16 |
| OTHER | 23 | 0 | −23 |
| P&L Δ | −$340 | −$720 | — |

**~85% of this run's classification bucket distribution was artifact.** The remaining 15% (8 BUG_B_SAME_BAR + 14 MATCH + a few real items) is broadly consistent with the corrected run, but should not be cited from this directory.

## Forward-link to corrected run

**Authoritative Phase 2 window result:** [`results/tick_verification/phase2_window_20260517_165641/`](../phase2_window_20260517_165641/)

The corrected run uses the same trades parquet, the same DBN raw payload, the same verifier code — only the tick cache builder changed (`src/build_tick_cache_databento.py` now applies the Panama offset table from `data_prep.build_adjustments` per active contract derived from `rolls.parquet`).

## Reproducibility

This directory is **kept as a historical artifact** and **not deleted**. The (uncommitted) `investigation_notes.md` written during diagnosis is now an offset-detection record rather than a phantom-mechanism investigation; we may repurpose or drop it separately.

The diff that landed the fix is in the commit that adds this file. The corrected run lands in a separate commit immediately after this one.

## Cross-references

- `_databento_acquisition_brief.md` — OQ-6 records the broader lesson about tick acquisition needing price-frame compatibility with simulator bars.
- `src/build_tick_cache_databento.py` — fixed cache builder.
- `docs/decisions.md:D-001` — Panama back-adjustment, the underlying mechanic.
