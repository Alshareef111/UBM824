# V2 + 40/40 modifications — partial-exit + runner-BE

**Date:** 2026-05-15

**Scope:** test 2 modifications to the V2 + 40/40 deployment candidate.
Both variants use 2-contract sizing (p1 + p2), partial-exit at p1 = +40, and a runner-BE rule that moves p2's stop to entry from bar X+1 after p1 exits at +40 on bar X. Variant B uses an initial −40 stop; Variant C uses −25.

**Baseline column** = V2 + 40/40 (single-contract) numbers from `strategy_report_20260512/strategy_4040_test.md` algebraically scaled to 2-contract sizing. Dollar quantities ×2; ratio metrics (PF, Sharpe, Sortino, WF Sharpe-like) and sign-stability are scale-invariant and unchanged. No re-run performed.

**Locked geometry preserved:** 3-pt cluster gap, MIN_SIZE=3, lookback=200, first-touch entry, C2 one-position-at-a-time, 9:46–11:30 NY trading window, force-close at 11:30 bar OPEN, stop-first conservative applied independently per leg.

**Resolved ambiguities (documented):**
- Entry cluster always excluded from runner-target candidates (both FADE and TREND inversions).
- Same-bar leg ordering: stop-first conservative applied **independently per leg**. Both legs can exit on the same bar at different reasons (e.g., p1 stops, p2 target_cluster). If a bar covers stop AND target for a given leg, that leg stops.
- BE-stop on the bar p1 exits (bar X): p2 still uses initial stop on bar X; BE-stop at entry becomes active on bar X+1.
- Entry-bar (i = bar of first fill): both legs evaluate exits on the entry bar itself (consistent with existing simulator_v2 behavior); the existing D-014 entry-bar chronology bias is inherited unchanged.
- If p1 hits +40 on the same bar p2 already exited (e.g., p2 cluster target closer than +40), no BE state is tracked for p2 (already closed).
- If a session has NO clusters in trade direction at session open, p2 has `p2_target_price = NaN` and rides to 11:30 force-close (subject to stop).

---

## Side-by-side comparison

| Metric | V2+40/40 baseline (×2c, scaled) | B: Partial (−40 + runner-BE) | C: Tight+Partial (−25 + runner-BE) |
|---|---:|---:|---:|
| Trades (entries) | 908 | 899 | 917 |
| WR% | 56.2% | 56.0% | 44.6% |
| Total P&L | $17,616 | $16,591 | $8,938 |
| Mean per entry | $19.40 | $18.45 | $9.75 |
| PF | 1.309 | 1.323 | 1.197 |
| Max DD | $-2,456 | $-2,080 | $-1,680 |
| DD duration (days) | 380 | 379 | 311 |
| DD recovered | yes | yes | yes |
| Ann. Sharpe | 2.15 | 2.42 | 1.45 |
| Ann. Sortino | 3.61 | 4.20 | 2.68 |
| WF Sharpe-like | 6.86 | 4.83 | 1.89 |
| Sign stability k/7 | 7/7 | 7/7 | 7/7 |
| Sum per-window OOS | $23,912 | $23,376 | $13,240 |
| 4-gate qualify | ✓ | ✓ | ✓ |

---

## Variant B — partial-exit + runner-BE, initial stop −40

**Parameters:** stop=−40, p1 target=+40, p2 target=next cluster level
**Output:** `results/archive/v2_4040_modifications_20260514/trades_variant_b_partial_runnerBE.parquet`

### Walk-forward per-window OOS (W1–W7)

| W1 | W2 | W3 | W4 | W5 | W6 | W7 |
|---:|---:|---:|---:|---:|---:|---:|
| $2,150 | $4,152 | $3,754 | $2,660 | $2,895 | $3,716 | $4,048 |

Median per-window OOS: $3,716 · Sharpe-like: 4.831 · Sign-stable: 7/7 · Sum: $23,376 · 4-gate: ✓

### Calendar-year P&L

| Year | Trades | P&L | WR% |
|---:|---:|---:|---:|
| 2019 | 88 | $1,992 | 59.1% |
| 2020 | 87 | $1,212 | 51.7% |
| 2021 | 94 | $1,430 | 53.2% |
| 2022 | 134 | $599 | 51.5% |
| 2023 | 145 | $3,711 | 57.9% |
| 2024 | 105 | $2,650 | 59.0% |
| 2025 | 138 | $3,588 | 60.9% |
| 2026 | 108 | $1,408 | 52.8% |

### Exit-type breakdown per contract leg

**p1 (target = +40):**
- target_40: 436
- stop: 334
- force_close: 129

**p2 (target = next cluster level):**
- target_cluster: 306
- stop: 286
- force_close: 194
- stop_be: 113

### Runner audit

- Runner-target source: 842 entries had a cluster-derived target (93.7%); 57 entries had NO cluster in trade direction (force-close fallback).
- Runner-BE fired (p1 hit +40, p2 still open after): 436 entries (48.5%).
- p1 leg total: $8,395 · p2 leg total: $8,196 · p2 median per entry: $0.00 · p2 mean per entry: $9.12

### Methodological caveats

- Entry cluster is excluded from runner-target candidates by Python object identity. For TREND inversions where entry sits at cluster_low (BUY) or cluster_high (SELL), the entry cluster's other extreme is NOT used as a runner target (judgment call; documented in confirmation).
- Same-bar exit ordering: each leg evaluated independently using existing stop-first conservative (D-005). If bar range covers stop AND target for that leg, the leg stops.
- Entry bar can exit both legs at any combination (target/stop) using the same per-leg stop-first rule. This inherits the known D-014 entry-bar chronology bias (~3% optimistic) and D-015 phantom-fill bias (~6% optimistic) from the bar simulator.
- Runner-BE state is tracked in column `runner_be_fired`. Column `p2_stop_history` describes p2's stop lifecycle for audit.

## Variant C — partial-exit + runner-BE, initial stop −25

**Parameters:** stop=−25, p1 target=+40, p2 target=next cluster level
**Output:** `results/archive/v2_4040_modifications_20260514/trades_variant_c_tight_partial_runnerBE.parquet`

### Walk-forward per-window OOS (W1–W7)

| W1 | W2 | W3 | W4 | W5 | W6 | W7 |
|---:|---:|---:|---:|---:|---:|---:|
| $968 | $3,685 | $2,690 | $2,143 | $2,076 | $1,140 | $537 |

Median per-window OOS: $2,076 · Sharpe-like: 1.895 · Sign-stable: 7/7 · Sum: $13,240 · 4-gate: ✓

### Calendar-year P&L

| Year | Trades | P&L | WR% |
|---:|---:|---:|---:|
| 2019 | 90 | $1,446 | 54.4% |
| 2020 | 91 | $160 | 38.5% |
| 2021 | 97 | $598 | 40.2% |
| 2022 | 138 | $917 | 44.2% |
| 2023 | 142 | $3,147 | 49.3% |
| 2024 | 109 | $2,082 | 46.8% |
| 2025 | 143 | $1,072 | 43.4% |
| 2026 | 107 | $-486 | 39.3% |

### Exit-type breakdown per contract leg

**p1 (target = +40):**
- stop: 484
- target_40: 346
- force_close: 87

**p2 (target = next cluster level):**
- stop: 430
- target_cluster: 275
- force_close: 136
- stop_be: 76

### Runner audit

- Runner-target source: 861 entries had a cluster-derived target (93.9%); 56 entries had NO cluster in trade direction (force-close fallback).
- Runner-BE fired (p1 hit +40, p2 still open after): 346 entries (37.7%).
- p1 leg total: $4,576 · p2 leg total: $4,362 · p2 median per entry: $-1.50 · p2 mean per entry: $4.76

### Methodological caveats

- Entry cluster is excluded from runner-target candidates by Python object identity. For TREND inversions where entry sits at cluster_low (BUY) or cluster_high (SELL), the entry cluster's other extreme is NOT used as a runner target (judgment call; documented in confirmation).
- Same-bar exit ordering: each leg evaluated independently using existing stop-first conservative (D-005). If bar range covers stop AND target for that leg, the leg stops.
- Entry bar can exit both legs at any combination (target/stop) using the same per-leg stop-first rule. This inherits the known D-014 entry-bar chronology bias (~3% optimistic) and D-015 phantom-fill bias (~6% optimistic) from the bar simulator.
- Runner-BE state is tracked in column `runner_be_fired`. Column `p2_stop_history` describes p2's stop lifecycle for audit.

---

## Files

- `report.md` — this report
- `trades_variant_b_partial_runnerBE.parquet` — Variant B trade log (one row per entry, 2-contract aggregate P&L, runner-BE audit columns)
- `trades_variant_c_tight_partial_runnerBE.parquet` — Variant C trade log (same schema, −25 stop)

**No project files modified outside this directory and `src/experimental/`. Locked baseline sha256 unchanged.**