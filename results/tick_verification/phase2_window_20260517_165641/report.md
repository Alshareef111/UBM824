# V2 + 40/40 tick replayer (Window variant) — run 20260517_165641

Per-trade reconciliation of V2 + 40/40 bar-sim trades against tick truth, over the FULL trade population whose entry_time falls in the tick coverage window. Phase 1 sample membership is reported as a metric, not used as a filter. Bug B (D-014) and phantom-fill (D-015) attribution per the design doc: `results/tick_verification/_phase2_replayer_design.md`.

## Inputs

- Trades parquet sha256: `1ccf859e3a580d78eb85cbc37a2cfa7159c3af59c3eb4bb58b5443d0aaf54feb`
- Phase 1 sample CSV sha256: `2ebd7512ef115d0a68e1c3a0cd4b9a05841f0c0b1ae97a12514833369f791484`  (cross-reference only)
- Tick parquet: `data/processed/ticks_databento_2026-01-01_to_2026-05-01.parquet`
- Tick coverage: 2026-01-01 23:00:00+00:00 → 2026-04-30 23:59:59.879767529+00:00  (83,586,999 ticks)
- Bracket: 40 / 40

## Counts (all trades in window)

| Mechanism | Count |
|---|---:|
| MATCH | 99 |
| BUG_B_SAME_BAR | 8 |
| BUG_B_NEXT_BAR | 0 |
| PHANTOM_ENTRY | 3 |
| OTHER | 0 |
| **Verified subtotal** | **110** |
| OUT_OF_COVERAGE | 798 |

## Stop-out subset (audit-relevant — Bug B is a stop-side concept)

| Metric | Value |
|---|---:|
| Verified stop-outs | 49 |
| Stop-outs in 09:46–10:55 NY band | 47 |
| Stop-outs with BUG_B_SAME_BAR | 2 |
| Stop-outs with BUG_B_NEXT_BAR | 0 |
| Stop-outs flagged bug_b_pre_fill_stop | 2 |
| Stop-outs FADE / TREND | 18 / 31 |

## Phase 1 sample cross-reference

| Metric | Value |
|---|---:|
| Phase 1 dates in window | 9 / 40 |
| Verified trades on Phase 1 dates | 26 |
| Verified stops on Phase 1 dates | 13 |

## P&L reconciliation (verified trades only)

| Metric | Value |
|---|---:|
| Sim P&L  | $+592.50 |
| Tick P&L | $-128.00 |
| Δ (tick − sim) | $-720.50 |
| Δ % of sim | -121.6% |

## Per-trade table (verified, sorted by entry_time)

| session_date | side | label | entry | sim | tick | sim $ | tick $ | mech | P1 |
|---|---|---|---:|---|---|---:|---:|---|:-:|
| 2026-01-02 | sell | TREND | 25746.50 | stop | target | $-80.00 | $+80.00 | BUG_B_SAME_BAR | ✓ |
| 2026-01-02 | sell | TREND | 25576.50 | target | target | $+80.00 | $+80.00 | MATCH | ✓ |
| 2026-01-05 | sell | FADE | 25884.75 | force_close | force_close | $-24.50 | $-24.50 | MATCH |  |
| 2026-01-06 | buy | TREND | 25946.75 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-01-07 | buy | TREND | 26078.00 | stop | stop | $-80.00 | $-82.00 | MATCH |  |
| 2026-01-07 | sell | FADE | 26120.00 | force_close | force_close | $+21.50 | $+21.50 | MATCH |  |
| 2026-01-08 | buy | TREND | 25884.75 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-01-09 | sell | FADE | 25981.50 | target | target | $+80.00 | $+83.50 | MATCH |  |
| 2026-01-09 | sell | FADE | 26015.25 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-01-12 | buy | TREND | 26105.50 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-01-13 | buy | FADE | 26146.25 | stop | stop | $-80.00 | $-79.00 | MATCH |  |
| 2026-01-13 | sell | TREND | 26045.25 | stop | stop | $-80.00 | $-81.00 | MATCH |  |
| 2026-01-15 | sell | FADE | 26144.25 | force_close | force_close | $+51.50 | $+51.50 | MATCH |  |
| 2026-01-16 | sell | TREND | 25947.25 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-01-16 | sell | TREND | 25889.50 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-01-21 | buy | TREND | 25570.00 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-01-22 | sell | FADE | 25884.75 | force_close | force_close | $-2.50 | $-2.50 | MATCH |  |
| 2026-01-23 | buy | TREND | 25946.00 | target | target | $+80.00 | $+79.50 | MATCH |  |
| 2026-01-23 | buy | TREND | 25981.50 | target | target | $+80.00 | $+71.00 | MATCH |  |
| 2026-01-23 | buy | TREND | 26015.25 | target | target | $+80.00 | $+62.00 | MATCH |  |
| 2026-01-23 | buy | TREND | 26041.25 | stop | stop | $-80.00 | $-113.50 | MATCH |  |
| 2026-01-26 | buy | FADE | 26019.50 | target | target | $+80.00 | $+82.00 | MATCH |  |
| 2026-01-26 | sell | FADE | 26078.00 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-01-29 | sell | TREND | 26146.25 | stop | stop | $-80.00 | $-80.00 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 26122.75 | stop | stop | $-80.00 | $-80.50 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 26109.25 | target | target | $+80.00 | $+80.00 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 26019.50 | target | target | $+80.00 | $+80.00 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 25984.50 | stop | stop | $-80.00 | $-93.00 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 26045.25 | target | target | $+80.00 | $+13.50 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 26080.00 | target | target | $+80.00 | $-1.00 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 25947.25 | stop | stop | $-80.00 | $-81.00 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 25889.50 | target | target | $+80.00 | $+80.00 | MATCH | ✓ |
| 2026-01-29 | sell | TREND | 25779.25 | stop | stop | $-80.00 | $-80.50 | MATCH | ✓ |
| 2026-01-30 | buy | FADE | 26080.00 | target | target | $+80.00 | $+96.50 | MATCH |  |
| 2026-01-30 | buy | FADE | 26045.25 | target | target | $+80.00 | $+81.00 | MATCH |  |
| 2026-02-02 | buy | TREND | 25946.00 | target | target | $+80.00 | $+75.50 | MATCH |  |
| 2026-02-02 | buy | TREND | 25981.50 | stop | stop | $-80.00 | $-136.50 | MATCH |  |
| 2026-02-02 | buy | TREND | 26015.25 | target | target | $+80.00 | $+79.50 | MATCH |  |
| 2026-02-02 | buy | TREND | 26041.00 | target | target | $+80.00 | $+39.50 | MATCH |  |
| 2026-02-02 | buy | TREND | 26078.00 | target | target | $+80.00 | $+59.00 | MATCH |  |
| 2026-02-02 | buy | TREND | 26120.00 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-02-02 | buy | TREND | 26105.00 | stop | stop | $-80.00 | $-82.00 | MATCH |  |
| 2026-02-03 | buy | TREND | 25981.50 | target | target | $+80.00 | $+79.50 | MATCH |  |
| 2026-02-03 | buy | TREND | 26015.25 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-02-03 | sell | TREND | 25947.75 | stop | target | $-80.00 | $+80.00 | BUG_B_SAME_BAR |  |
| 2026-02-03 | sell | TREND | 25889.50 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-02-03 | sell | TREND | 25779.25 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-02-03 | sell | TREND | 25754.00 | stop | stop | $-80.00 | $-81.50 | MATCH |  |
| 2026-02-03 | sell | TREND | 25746.50 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-02-04 | sell | FADE | 25570.00 | target | target | $+80.00 | $+80.00 | BUG_B_SAME_BAR |  |
| 2026-02-04 | buy | FADE | 25304.25 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-02-06 | sell | FADE | 25179.00 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-02-10 | sell | FADE | 25570.00 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-02-10 | sell | FADE | 25624.00 | target | target | $+80.00 | $+81.00 | MATCH |  |
| 2026-02-11 | buy | FADE | 25576.50 | target | stop | $+80.00 | $-80.50 | BUG_B_SAME_BAR |  |
| 2026-02-11 | sell | TREND | 25304.25 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-02-12 | buy | FADE | 25380.00 | stop | stop | $-80.00 | $-79.50 | MATCH | ✓ |
| 2026-02-12 | sell | TREND | 25184.00 | target | target | $+80.00 | $+80.00 | MATCH | ✓ |
| 2026-02-12 | sell | TREND | 25173.00 | target | target | $+80.00 | $+61.50 | MATCH | ✓ |
| 2026-02-17 | sell | TREND | 24703.75 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-02-18 | buy | TREND | 25179.00 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-02-18 | sell | FADE | 25301.00 | force_close | force_close | $-13.50 | $-6.50 | MATCH |  |
| 2026-02-19 | sell | FADE | 25082.50 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-02-20 | buy | TREND | 25169.25 | stop | stop | $-80.00 | $-80.00 | MATCH | ✓ |
| 2026-02-20 | sell | TREND | 25085.50 | stop | stop | $-80.00 | $-80.00 | MATCH | ✓ |
| 2026-02-20 | sell | FADE | 25301.00 | stop | stop | $-80.00 | $-80.00 | MATCH | ✓ |
| 2026-02-23 | sell | FADE | 25169.25 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-02-24 | buy | TREND | 25169.25 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-02-25 | buy | TREND | 25493.50 | target | target | $+80.00 | $+42.50 | MATCH |  |
| 2026-02-25 | buy | TREND | 25570.00 | stop | stop | $-80.00 | $-81.50 | MATCH |  |
| 2026-02-26 | sell | TREND | 25380.00 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-02-26 | sell | TREND | 25304.25 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-02-26 | sell | TREND | 25184.00 | target | target | $+80.00 | $+80.50 | MATCH |  |
| 2026-02-26 | sell | TREND | 25173.00 | target | target | $+80.00 | $+6.50 | MATCH |  |
| 2026-02-26 | sell | TREND | 25085.50 | stop | stop | $-80.00 | $-81.50 | MATCH |  |
| 2026-02-27 | sell | FADE | 25082.50 | stop | stop | $-80.00 | $-80.00 | MATCH | ✓ |
| 2026-03-02 | buy | TREND | 25082.50 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-03-02 | sell | FADE | 25094.00 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-03-02 | sell | FADE | 25179.00 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-03-03 | buy | FADE | 24703.75 | target | target | $+80.00 | $+82.00 | MATCH | ✓ |
| 2026-03-03 | buy | FADE | 24613.25 | stop | stop | $-80.00 | $-79.50 | MATCH | ✓ |
| 2026-03-04 | sell | FADE | 25094.00 | stop | stop | $-80.00 | $-81.50 | MATCH | ✓ |
| 2026-03-04 | sell | FADE | 25169.25 | target | target | $+80.00 | $+81.00 | MATCH | ✓ |
| 2026-03-04 | sell | FADE | 25179.00 | target | stop | $+80.00 | $-79.50 | BUG_B_SAME_BAR | ✓ |
| 2026-03-05 | sell | FADE | 25301.00 | stop | stop | $-80.00 | $-82.00 | MATCH |  |
| 2026-03-05 | sell | FADE | 25339.00 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-03-05 | sell | TREND | 25203.00 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-03-05 | sell | TREND | 25173.00 | stop | stop | $-80.00 | $-92.00 | MATCH |  |
| 2026-03-09 | sell | FADE | 24699.50 | target | stop | $+80.00 | $-80.00 | BUG_B_SAME_BAR |  |
| 2026-03-10 | buy | FADE | 25203.00 | stop | stop | $-80.00 | $-79.00 | MATCH |  |
| 2026-03-10 | buy | TREND | 25339.00 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-03-10 | buy | TREND | 25375.50 | stop | stop | $-80.00 | $-86.00 | MATCH |  |
| 2026-03-11 | buy | TREND | 25301.00 | stop | stop | $-80.00 | $-80.00 | MATCH |  |
| 2026-03-11 | buy | TREND | 25339.00 | target | target | $+80.00 | $+79.50 | MATCH |  |
| 2026-03-11 | buy | TREND | 25375.50 | stop | stop | $-80.00 | $-103.00 | MATCH |  |
| 2026-03-11 | buy | FADE | 25173.25 | target | target | $+80.00 | $+80.00 | BUG_B_SAME_BAR |  |
| 2026-03-17 | buy | TREND | 25082.50 | stop | NO_FILL | $-80.00 | $+0.00 | PHANTOM_ENTRY |  |
| 2026-03-18 | sell | FADE | 24990.50 | target | NO_FILL | $+80.00 | $+0.00 | PHANTOM_ENTRY |  |
| 2026-03-19 | sell | FADE | 24469.50 | stop | NO_FILL | $-80.00 | $+0.00 | PHANTOM_ENTRY |  |
| 2026-03-23 | sell | FADE | 24612.25 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-03-25 | sell | FADE | 24469.50 | stop | stop | $-80.00 | $-80.50 | MATCH |  |
| 2026-04-02 | buy | TREND | 23956.75 | target | target | $+80.00 | $+80.00 | MATCH | ✓ |
| 2026-04-08 | buy | FADE | 25085.50 | target | stop | $+80.00 | $-80.50 | BUG_B_SAME_BAR |  |
| 2026-04-08 | sell | TREND | 24993.75 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-04-09 | buy | FADE | 24993.75 | target | target | $+80.00 | $+80.00 | MATCH |  |
| 2026-04-10 | sell | FADE | 25339.00 | target | target | $+80.00 | $+84.00 | MATCH |  |
| 2026-04-10 | buy | FADE | 25304.25 | target | target | $+80.00 | $+84.50 | MATCH |  |
| 2026-04-13 | buy | FADE | 25174.50 | target | target | $+80.00 | $+87.00 | MATCH | ✓ |
| 2026-04-15 | sell | FADE | 26041.00 | stop | stop | $-80.00 | $-81.50 | MATCH |  |
| 2026-04-15 | sell | FADE | 26078.00 | stop | stop | $-80.00 | $-80.00 | MATCH |  |

## Out-of-coverage (trades on dates outside the tick window)

Total OOF trades: 798 across 526 dates.

## Coverage caveat

Tick coverage: 2026-01-01 → 2026-04-30. The trade population verified here is **all V2+40/40 trades** whose entry_time falls in this window — not restricted to the Phase 1 sample. The original `tick_replay_v2.py` is the canonical Phase 1-only verifier; this variant trades the stratified-sample audit-trail for full in-window coverage.
