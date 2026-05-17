# V2 + 40/40 tick replayer — Phase 2 run 20260517_140110

Per-trade reconciliation of V2 + 40/40 bar-sim trades against tick truth, with Bug B (D-014) and phantom-fill (D-015) attribution. Design: `results/tick_verification/_phase2_replayer_design.md`.

## Inputs

- Trades parquet sha256: `1ccf859e3a580d78eb85cbc37a2cfa7159c3af59c3eb4bb58b5443d0aaf54feb`
- Phase 1 sample CSV sha256: `2ebd7512ef115d0a68e1c3a0cd4b9a05841f0c0b1ae97a12514833369f791484`
- Tick coverage: 2026-03-17 13:45:00.028000+00:00 → 2026-04-15 15:31:59.912000+00:00  (5,673,131 ticks)
- Bracket: 40 / 40

## Counts

| Mechanism | Count |
|---|---:|
| MATCH | 2 |
| BUG_B_SAME_BAR | 0 |
| BUG_B_NEXT_BAR | 0 |
| PHANTOM_ENTRY | 0 |
| OTHER | 0 |
| **Verified subtotal** | **2** |
| OUT_OF_COVERAGE | 105 |

## P&L reconciliation (verified trades only)

| Metric | Value |
|---|---:|
| Sim P&L  | $+160.00 |
| Tick P&L | $+160.00 |
| Δ (tick − sim) | $+0.00 |
| Δ % of sim | +0.0% |

## Per-trade table (verified)

| session_date | side | entry | sim outcome | tick outcome | sim $ | tick $ | mechanism |
|---|---|---:|---|---|---:|---:|---|
| 2026-04-02 | buy | 23956.75 | target | target | $+80.00 | $+80.00 | MATCH |
| 2026-04-13 | buy | 25174.50 | target | target | $+80.00 | $+80.00 | MATCH |

## Out-of-coverage (sample but no local tick data)

Total OOF trades: 105 across 38 dates.

- 2020-03-03: 2 trades
- 2020-03-13: 3 trades
- 2020-04-21: 3 trades
- 2020-05-08: 1 trades
- 2020-10-29: 1 trades
- 2021-03-15: 1 trades
- 2021-10-14: 1 trades
- 2021-12-07: 1 trades
- 2022-01-03: 5 trades
- 2022-01-04: 8 trades
- 2022-01-07: 3 trades
- 2022-01-19: 2 trades
- 2022-02-07: 2 trades
- 2022-10-18: 2 trades
- 2022-11-29: 2 trades
- 2022-12-08: 5 trades
- 2023-03-15: 3 trades
- 2023-03-16: 3 trades
- 2023-08-24: 3 trades
- 2023-11-06: 1 trades
- 2024-08-12: 3 trades
- 2024-09-11: 5 trades
- 2024-11-19: 1 trades
- 2025-01-08: 3 trades
- 2025-02-03: 6 trades
- 2025-02-27: 4 trades
- 2025-05-19: 3 trades
- 2025-06-12: 1 trades
- 2025-08-06: 1 trades
- 2025-10-22: 1 trades
- 2025-12-19: 1 trades
- 2026-01-02: 2 trades
- 2026-01-29: 10 trades
- 2026-02-12: 3 trades
- 2026-02-20: 3 trades
- 2026-02-27: 1 trades
- 2026-03-03: 2 trades
- 2026-03-04: 3 trades

## Coverage caveat

Local tick data covers 2026-03-17 → 2026-04-15 (a ~6-week window). The canonical Phase 1 sample spans 7 years. Of 40 sample dates, only those within the tick window are verifiable here; the rest are reported as OUT_OF_COVERAGE pending wider tick acquisition (see `results/tick_verification/_databento_acquisition_brief.md`).
