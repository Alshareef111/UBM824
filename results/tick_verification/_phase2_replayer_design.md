# Phase 2 design — V2-classifier tick replayer

**Status:** DESIGN (not built). Author: 2026-05-17 Mac mini orientation. Greenlight required before implementation.

**Scope:** Defines the script that turns the canonical Phase 1 sample (`phase1_sample_20260516.csv`, 40 dates) into a per-trade reconciliation of V2 + 40/40 bar-sim outcomes against tick truth, with explicit Bug B (D-014) and phantom-fill (D-015) attribution.

---

## 1. Goal & non-goals

### Goal
For each V2 + 40/40 trade whose `entry_time` falls inside available tick coverage:
1. Confirm a real fill tick exists in the entry minute (else flag `NO_FILL` / phantom-suspect).
2. Determine the **chronological** outcome by walking ticks from the fill onward (stop / target / force-close).
3. Compare to the bar simulator's recorded outcome.
4. Attribute mismatches by mechanism: **Bug B (entry-bar chronology)**, **phantom fill (D-015)**, or **other**.
5. Aggregate to a Phase-2 verdict: how much of the +$8,808 V2 + 40/40 headline survives tick reconciliation on the verifiable subset?

### Non-goals (explicitly out of v1)
- **Full tick-driven V2 re-run from scratch.** That's the audit SUMMARY.md fix #3 (a different script — accepts a `Classifier`, rebuilds clusters/setups, walks ticks chronologically end-to-end). v1 verifies the existing bar-sim trade list; it does not re-classify clusters.
- **Bracket-width sweeps on tick data.** `src/tick_simulator.py` already does that for AllFade 30/30 et al. v1 stays focused on V2 + 40/40 only.
- **Walk-forward / cost-adjusted analysis.** That's §9.2 of `strategy-reference.md`; orthogonal to Phase 2.

---

## 2. The Classifier question

The audit SUMMARY.md fix #3 reads: *"Build a tick-replay variant of the V2 fill engine that accepts an arbitrary Classifier."* For **per-trade verification** of an existing trade list, a Classifier is not needed at runtime: each input trade already carries `side` and `cluster_label` from the bar sim, so the verifier simply replays the trade's intent (limit fill, then chronological tick walk to exit). v1 therefore **does not** take a Classifier parameter.

The "accepts an arbitrary Classifier" variant is a separate script (Approach B in the orientation note) — needed eventually for a true tick-driven V2 + 40/40 *re-simulation* but not for Phase 2's verification need. Recommend deferring B to its own design pass once v1 lands. Splitting them keeps each script focused, testable, and cheap.

---

## 3. Inputs

Defaults in parens; all overridable via CLI or top-of-file constants:

| Input | Default | Notes |
|---|---|---|
| Trades parquet | `results/40_40_v2_full/20260514_125349/trades.parquet` (908 rows, sha256 `1ccf859e…feb`) | sha256-pinned at startup; abort if mismatch |
| Tick data parquet | `data/processed/ticks_overlap.parquet` (5.67M ticks, 2026-03-17 → 2026-04-15) | columns: `ts_utc`, `last`, `bid`, `ask`, `volume` |
| Stop / target points | 40.0 / 40.0 | matches V2 + 40/40 deployment candidate |
| Date filter (optional) | derived: trades whose `entry_time` falls in tick coverage AND whose `session_date` is in `phase1_sample_20260516.csv` | configurable to relax either constraint |
| Sample CSV | `results/tick_verification/phase1_sample_20260516.csv` (canonical, sha256 `2ebd7512…`) | sha256-pinned at startup |
| Phantom-fill epsilon | 0.0 (exact-match) | default: a "real fill tick" means `last == entry_price` exactly; broaden to ±epsilon for tick-size tolerance |
| Output dir | `results/tick_verification/phase2_<YYYYMMDD_HHMMSS>/` | new timestamped dir per run |

---

## 4. Per-trade algorithm

For each input trade `t`:

1. **Coverage gate.** Skip if `t.entry_time` is outside `[ticks.ts_utc.min(), ticks.ts_utc.max()]`. Record as `OUT_OF_COVERAGE` (not a mismatch — just unverifiable).
2. **Entry-minute fill detection.** Walk ticks in `[t.entry_time, t.entry_time + 60s)`:
   - For BUY: find first tick with `last <= t.entry_price`. For SELL: first with `last >= t.entry_price`.
   - If no such tick: `tick_outcome = NO_FILL`, also flag `phantom_suspect = True` (the bar sim filled at this price but no real trade tick reached it).
3. **Bug B chronology check (entry minute, before fill).** Within `[t.entry_time, fill_ts)`:
   - For BUY: did any tick reach stop (`last <= entry - 40`) or target (`last >= entry + 40`)?
   - For SELL: did any tick reach stop (`last >= entry + 40`) or target (`last <= entry - 40`)?
   - If yes → `bug_b_pre_fill = True` and record which level + tick timestamp. (Pre-fill stop/target ticks the bar sim would have credited if they fell on the entry bar.)
4. **Chronological exit walk.** From `fill_ts` onward, walk ticks until first of:
   - Stop or target tick → `tick_outcome ∈ {stop, target}`, `tick_exit_price = limit`, `tick_exit_ts = tick.ts_utc`.
   - Force-close threshold (`session_date 15:30 UTC`) reached → `tick_outcome = force_close`, `tick_exit_price = first tick at or after 15:30`.
   - End of session ticks (no FC tick available) → `tick_outcome = force_close`, `tick_exit_price = last available tick`.
5. **Reconcile.** Compare to bar sim's `t.exit_reason` and `t.pnl_dollars`. Emit:
   - `match` (bool): `sim_outcome == tick_outcome`.
   - `pnl_delta`: `tick_pnl − sim_pnl` (signed).
   - `mechanism` (categorical): one of `MATCH`, `BUG_B`, `PHANTOM_ENTRY`, `PHANTOM_EXIT`, `OTHER`. Bug B and phantom are attributable via the flags from steps 2-3; OTHER catches residual mismatches (shouldn't happen often).

---

## 5. Bug B reporting specifically

Two distinct Bug B sub-cases need to be reported separately:

**Bug B (same-bar pre-fill stop/target):** The bar sim's `exit_time == entry_time` AND the bar sim's `exit_reason ∈ {stop, target}`. Tick truth shows the credited extreme occurred *before* the fill within the entry minute, so the bar sim's "instant exit on entry bar" was anachronistic. This is the canonical Bug B from D-014.

**Bug B (next-bar chronology):** Bar sim's `exit_time > entry_time` BUT the credited extreme on the exit bar preceded — at the tick level — a different extreme that should have hit first. This is a generalization noted in the audit SUMMARY.md p4b ("first-order chronology risk: `bar.open` already past the credited exit level"). Less common, but the replayer detects it for free via step 4.

**Aggregate Bug B output (in `report.md`):**

- N trades with Bug B (same-bar, doc-canonical)
- N trades with Bug B (next-bar generalization)
- Per-side: BUY vs SELL incidence
- Per-label: FADE vs TREND incidence (mirror the 8/11 TREND skew from the 2026-05-15 audit)
- Time-of-day distribution: hour-bucket counts (the audit found all 11 fired 09:46-10:55)
- P&L recovered under Bug B correction (lower-bound: assume all Bug B candidates would have NOT stopped/targeted; recompute tick-truth P&L)

This is the deliverable that closes the §8.1 *"Full bidirectional Bug B effect (target side too) NOT computed; queued in §9"* caveat.

---

## 6. Outputs

In `results/tick_verification/phase2_<TS>/`:

| File | Content |
|---|---|
| `report.md` | Headline summary, mismatch table, Bug B section per §5, phantom-fill section, coverage caveats |
| `reconciliation.parquet` | Per-trade rows: original 14 trade cols + `tick_outcome`, `fill_ts`, `tick_exit_ts`, `tick_exit_price`, `tick_pnl_dollars`, `match`, `pnl_delta`, `mechanism`, `bug_b_pre_fill`, `phantom_suspect`, `out_of_coverage` |
| `summary.json` | Machine-readable headline: `n_verified`, `n_out_of_coverage`, `n_match`, `n_bug_b_pre_fill`, `n_phantom_entry`, `sim_pnl_total`, `tick_pnl_total`, `pnl_delta_total`, `delta_pct_of_sim` |
| `_run.py` (optional) | Self-contained per-run snapshot of the script + invocation args, mirroring `results/archive/v2_4040_stop_loss_diagnostic_20260516/_run.py` convention |

---

## 7. Reuse vs new

| Component | Source | Status |
|---|---|---|
| Entry-minute fill detection (chronological tick scan within `[entry_time, entry_time+60s)`) | `src/verify_ticks.py:46-69` | **Reuse, generalized** — strip STOP_POINTS/TARGET_POINTS/date hardcoding |
| Chronological exit walk after fill | `src/verify_ticks.py:77-125` | **Reuse, generalized** — same parameterization fix |
| Force-close handling | `src/verify_ticks.py:91-115` | **Reuse** — already correct (15:30 UTC) |
| Trade I/O and parquet load/save | `src/verify_ticks.py:139-167` | **Reuse, generalized** |
| Per-trade comparison + mismatch table formatting | `src/verify_ticks.py:170-229` | **Reuse, extended** with mechanism column |
| **Bug B pre-fill chronology check (steps 2-3 in §4)** | — | **NEW** — verify_ticks.py just compares outcomes; it doesn't isolate Bug B mechanism |
| **Phantom-fill detection (no exact-match `last` tick at limit price)** | — | **NEW** — verify_ticks.py treats NO_FILL as a single category; we want to distinguish "limit unreachable by any tick" vs "fill exists but bar said stop/target hit first" |
| **Mechanism attribution column + summary breakdowns** | — | **NEW** — see §5 |
| **Coverage gate + OUT_OF_COVERAGE handling** | — | **NEW** — verify_ticks.py assumes all input trades fall in the overlap window; we'll have trades that don't |
| **sha256-pinned input verification** | `results/tick_verification/_phase1_sample_design.py:43-45,299` | **Reuse pattern** |

`src/tick_simulator.py` is **not reused** — it's a different abstraction (full re-simulation from clusters). Some of its tick-segment vectorization (`np.searchsorted` / `np.flatnonzero` on numpy arrays of nanosecond timestamps) is worth borrowing for performance if the per-trade Python loop turns out slow, but premature for v1.

---

## 8. File location

**Primary script:** `src/experimental/tick_replay_v2.py`.

Convention precedent:
- `src/experimental/` is for non-protected experiment runners (see `run_cluster_size_filter.py`, `audit_diagnostics.py`).
- The audit SUMMARY.md explicitly recommends `src/experimental/v2_tick_replay.py` (close enough — using `tick_replay_v2.py` mirrors the `simulator_v2_*.py` naming family).
- Locked files (`simulator.py`, `simulator_v2.py`, `tick_simulator.py`, `verify_ticks.py`) untouched — the replayer is a *new* file, not a modification.

**Per-run outputs:** `results/tick_verification/phase2_<YYYYMMDD_HHMMSS>/`.

**Why not under `results/archive/`:** Phase 2 outputs are part of the active tick-verification workstream (Phase 1 already lives at `results/tick_verification/`); they only migrate to `results/archive/` if/when the workstream concludes. Matches the directory's existing semantics.

---

## 9. Coverage limitation (the elephant)

Tick data on this Mac mini: 2026-03-17 → 2026-04-15 (13 sessions, 5.67M ticks).

Phase 1 sample (40 dates): spans 2020-03-03 → 2026-04-13.

**Verifiable subset by inspection of canonical CSV:**

| Sample dates falling in tick coverage | Count |
|---|---|
| 2026-03-04 (S3 tight_stop_touch) | 1 — actually pre-coverage, outside window |
| 2026-04-02 (S3 high_vol_day) | 1 |
| 2026-04-13 (S3 gap_day) | 1 |

Only **2 of 40** Phase 1 dates fall inside the local tick window (2026-04-02 and 2026-04-13). That's a usable lower bound but nowhere near a deployment-grade verification.

**Three paths forward** (decision needed before build):

1. **Build now against overlap-only.** Run the replayer on the 2 in-coverage dates immediately. Methodology gets validated, Bug B incidence on V2 + 40/40 gets measured on a tiny sample, scoping for future expansion is locked in. Cheapest path. Verifiable trade count: ~2-5 trades.

2. **Expand the verifiable window first via Databento.** Per `strategy-reference.md` §9.2: acquire MBP-1 or TBBO for 2024-04-01 → 2026-05-01 (the V2 + 40/40 in-sample window). Then build the replayer against the wider window. Best methodology; biggest cost (Databento ingest + a separate tick cache builder generalized for non-overlap data).

3. **Pivot Phase 1 sampling to be coverage-aware.** Resample Phase 1 only over the dates with tick coverage (~13 sessions). Defeats the stratification design (S1/S2/S3 over 7y) but maximizes verifiable-coverage of the tiny window.

**Recommended:** path 1 followed by path 2. Path 3 throws away the stratified design and isn't worth it.

---

## 10. Sizing

Comparable existing scripts:
- `src/verify_ticks.py` — 237 LoC
- `src/tick_simulator.py` — 294 LoC
- `src/experimental/audit_diagnostics.py` — 444 LoC
- `src/experimental/run_cluster_size_filter.py` — 515 LoC

Phase 2 replayer expected size: **~350-450 LoC** Python, broken down approximately:

| Section | LoC |
|---|---:|
| I/O, sha256 verification, CLI/constants | ~60 |
| Coverage gate + per-trade loop scaffolding | ~40 |
| Entry-minute fill + Bug B pre-fill detection | ~80 |
| Chronological exit walk | ~70 |
| Mechanism attribution (match / Bug B / phantom / other) | ~50 |
| Aggregation: report.md, summary.json, parquet | ~80 |
| Error handling, edge cases (DST, sparse sessions) | ~30 |

Time estimate: **half a day focused (4-6 hours)** to first working version on the 2 in-coverage dates. Add ~1 day if path 2 is selected (Databento ingest + cache-builder generalization).

---

## 11. Open questions before build

1. **Phantom-fill epsilon.** Default = 0.0 (exact `last == limit_price` match). Should it be ±1 tick (±0.25) to allow for tick-aggregation in the parquet? Affects phantom-fill count substantially.
2. **Output dir naming.** `phase2_<TS>/` per-run, or fixed `phase2/` with overwrite-on-rerun? `_phase1_sample_design.py` uses a fixed name; per-run timestamping matches `results/40_40_v2_full/20260514_125349/`'s convention. Recommend timestamped.
3. **What goes in the audit trail.** Should Phase 2 results land an R-### in `docs/results-log.md`, a D-### in `docs/decisions.md` (if Bug B attribution changes any deployment-relevant number), or a new `docs/research-log-2026-XX-tick-verification.md`? Recommend the research-log pattern — matches the V2 investigation precedent.

---

## 12. Build plan (if greenlit)

1. Scaffold `src/experimental/tick_replay_v2.py` with constants, I/O, sha256 checks, coverage gate.
2. Port entry-fill + exit-walk from `verify_ticks.py`, parameterized.
3. Add Bug B pre-fill chronology detector.
4. Add phantom-fill flag.
5. Run on the 2 in-coverage dates from canonical Phase 1, verify outputs hand-checkable.
6. Sanity-check against the existing R-001 verification (`data/processed/verification_results.parquet`) — same trades on the overlap window should reproduce the audit's "+$240 bar / $0 tick" numbers IF we relax to 30/30 brackets.
7. Lock the script, write the first Phase 2 report.md, commit per the phased-refactor workflow.

End of design. Awaiting greenlight + path-1/path-2 decision.
