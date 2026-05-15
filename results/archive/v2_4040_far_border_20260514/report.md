# V2 + 40/40 — FAR-BORDER entry test

**Date:** 2026-05-15

**Change tested (only this):** limit price moved from the NEAR edge of each cluster to the FAR edge. Cluster above 9:45 ORB close → limit at `cluster_high` (was `cluster_low`). Cluster below close → limit at `cluster_low` (was `cluster_high`). Applies uniformly to both FADE and TREND. Trigger direction unchanged. Classifier (ADX(15,30) ∧ DI(15,8) unanimous) unchanged but evaluated at the LATER bar where price reaches the far edge.

**Locked geometry preserved:** 3-pt cluster gap, MIN_SIZE=3, lookback=200, 40-pt stop/target, 9:46–11:30 NY window, C2 one-position-at-a-time, force-close at 11:30 bar OPEN, stop-first conservative.

**Sub-classifier setups same as R-012:** ADX N=15 threshold=30, DI N=15 threshold=8, unanimous AND-gate. Side-flip on TREND keeps entry_price unchanged (same convention as baseline).

---

## Side-by-side comparison

| Metric | V2 + 40/40 (near border, baseline) | V2 + 40/40 + far border |
|---|---:|---:|
| Trades | 908 | 848 |
| WR% | 56.2% | 55.5% |
| Total P&L | $8,808 | $7,554 |
| Mean per entry | $9.70 | $8.91 |
| Avg winner | $73 | $73 |
| Avg loser | $-72 | $-71 |
| PF | 1.309 | 1.282 |
| Max DD | $-1,228 | $-910 |
| DD duration (days) | 380 | 278 |
| DD recovered (y/n) | y | y |
| Ann. Sharpe | 2.15 | 2.18 |
| Ann. Sortino | 3.61 | 3.79 |
| WF Sharpe-like | 6.86 | 5.72 |
| Median per-window OOS | $1,688 | $1,339 |
| Sign stability k/7 | 7/7 | 7/7 |
| Sum per-window OOS | $11,956 | $9,297 |
| 4-gate qualified | ✓ | ✓ |

---

## 1. Walk-forward per-window OOS (far border)

| W1 | W2 | W3 | W4 | W5 | W6 | W7 |
|---:|---:|---:|---:|---:|---:|---:|
| $1,339 | $1,023 | $1,054 | $1,428 | $1,528 | $1,270 | $1,654 |

Median per-window OOS: $1,339 · Sharpe-like: 5.724 · Sign-stable: 7/7 · Sum: $9,297 · 4-gate: ✓

## 2. Calendar-year P&L (far border)

| Year | Trades | P&L | WR% |
|---:|---:|---:|---:|
| 2019 | 79 | $628 | 54.4% |
| 2020 | 77 | $32 | 50.6% |
| 2021 | 86 | $412 | 52.3% |
| 2022 | 132 | $2,307 | 59.8% |
| 2023 | 138 | $834 | 53.6% |
| 2024 | 93 | $1,144 | 59.1% |
| 2025 | 137 | $1,670 | 58.4% |
| 2026 | 106 | $528 | 52.8% |

## 3. Exit-type breakdown (far border)

| Exit reason | n | Mean P&L |
|---|---:|---:|
| target | 406 | $80.00 |
| stop | 315 | $-80.00 |
| force_close | 127 | $2.16 |

## 4. Filter-effect diagnostic

- Baseline clusters fired: **908**
- Far-border clusters fired: **848**
- Shared (both fire on same cluster identity): **745**
- Filtered out (baseline fires, far-border does not): **163**
- New in far-border (far-border fires, baseline does not — C2 timing reorderings): **103**

### Filtered-out trades (baseline P&L of clusters not entered in far-border):

- Total baseline P&L of filtered-out: **$48**
- Mean P&L of filtered-out: $0.29
- WR of filtered-out (in baseline): 50.3%
- Exit breakdown of filtered-out (in baseline): target=61, stop=64, force_close=38

### Label split (FADE / TREND):

- Baseline:    FADE = 391, TREND = 517 (total 908)
- Far border:  FADE = 354, TREND = 494 (total 848)

### Label flips on shared clusters:

- Shared clusters where FADE/TREND label differs between baseline and far border: **9** of 745
- Shared clusters where SIDE (buy/sell) differs (consequence of label flip): **9** of 745

### Cluster-size distribution:

- Baseline trades:        mean cluster_size = 3.74, median = 3.0
- Far-border trades:      mean cluster_size = 3.68, median = 3.0
- Filtered-out (baseline P&L): mean cluster_size = 4.23, median = 3.0

---

## Files

- `report.md` — this report
- `trades_v2_4040_far_border.parquet` — far-border trade log

Locked baseline `data/processed/trades.parquet` sha256 unchanged.