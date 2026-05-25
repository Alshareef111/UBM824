# Cluster-size filter test — V2 + 40/40 with MIN_CLUSTER_SIZE = {4, 5}

**Date:** 2026-05-15
**Change tested:** raise `MIN_CLUSTER_SIZE` from baseline 3 to 4 (F1) and 5 (F2).
**All other rules unchanged from V2 + 40/40 baseline:**
- ADX(15,30) ∧ DI(15,8) unanimous classifier, FADE/TREND side-flip
- 1 contract, 40-pt stop / 40-pt target, 1:1 R:R
- Near-border entry (cluster.low for short, cluster.high for long)
- 9:46–11:30 NY window, force-close at 11:30 bar open
- 3-pt cluster gap, 200-session lookback, C2 one-position-at-a-time, stop-first conservative

Baseline column copied from `results/archive/strategy_report_20260512/strategy_4040_test.md` (v2 40/40). F1 and F2 freshly run; baseline NOT re-run.

## Headline stats — baseline vs F1 vs F2

| Metric | Baseline (size ≥ 3) | F1: size ≥ 4 | F2: size ≥ 5 |
|---|---:|---:|---:|
| Trades | 908 | 374 | 196 |
| WR% | 56.2% | 54.3% | 55.1% |
| Total P&L | **$8,808** | **$2,204** | **$1,199** |
| Mean per entry | $9.70 | $5.89 | $6.12 |
| Avg winner | $73 | $70 | $66 |
| Avg loser | $-72 | $-70 | $-68 |
| PF | 1.309 | 1.184 | 1.200 |
| Max DD | $-1,228 | $-1,264 | $-884 |
| DD duration (days) | 380 | 948 | 1562 |
| DD recovered | yes | yes | no |
| Ann. Sharpe | 2.15 | 1.00 | 0.78 |
| Ann. Sortino | 3.61 | 1.58 | 1.20 |
| WF Sharpe-like | **6.86** | **0.33** | **-0.26** |
| Median per-window OOS | $1,688 | $150 | $-70 |
| Sign stability k/7 | 7/7 | 5/7 | 3/7 |
| Sum per-window OOS | $11,956 | $1,820 | $-156 |
| 4-gate qualified | ✓ |   |   |

## F1 — MIN_CLUSTER_SIZE = 4

### Walk-forward per-window OOS

| W1 | W2 | W3 | W4 | W5 | W6 | W7 | Sharpe-like | Sign |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| $-451 | $-20 | $671 | $582 | $150 | $50 | $838 | 0.33 | 5/7 |

### Calendar-year P&L

| Year | Trades | P&L | WR% |
|---:|---:|---:|---:|
| 2019 | 59 | $982 | 62.7% |
| 2020 | 42 | $214 | 54.8% |
| 2021 | 39 | $139 | 51.3% |
| 2022 | 54 | $-604 | 42.6% |
| 2023 | 43 | $244 | 53.5% |
| 2024 | 45 | $406 | 57.8% |
| 2025 | 60 | $370 | 55.0% |
| 2026 | 32 | $453 | 56.2% |

### Exit-type breakdown

| Exit | Count | Mean P&L | Total P&L |
|---|---:|---:|---:|
| target | 165 | $80.00 | $13,200 |
| stop | 141 | $-80.00 | $-11,280 |
| force_close | 68 | $4.18 | $284 |

### FADE/TREND label split

- Baseline: 391 FADE / 517 TREND
- F1 — MIN_CLUSTER_SIZE = 4: 160 FADE / 214 TREND

### Cluster-size distribution (3 / 4 / 5 / 6 / 7+)

| Size | Count | Mean P&L | Total P&L |
|---:|---:|---:|---:|
| 3 | 0 | — | — |
| 4 | 189 | $6.09 | $1,150 |
| 5 | 77 | $2.34 | $180 |
| 6 | 51 | $10.56 | $538 |
| 7+ | 57 | $5.88 | $335 |

### Filter-effect diagnostic vs baseline (matched by session_date + cluster_low + cluster_high)

- Baseline trades that do NOT appear in this variant: **586**
- Total P&L of those filtered-out trades (in baseline): **$7,326**
- WR% of filtered-out trades: **57.7%**
- Of those, cluster_size < 4 (filter-explained): 576
- Of those, cluster_size >= 4 (C2-reorder displaced): 10

Exit-type breakdown of filtered-out trades:

| Exit | Count | Mean P&L | Total P&L |
|---|---:|---:|---:|
| target | 300 | $80.00 | $24,000 |
| stop | 209 | $-80.00 | $-16,720 |
| force_close | 77 | $0.59 | $46 |

Filtered-out trades by cluster_size (raw):

| Size | Count |
|---:|---:|
| 3 | 576 |
| 4 | 3 |
| 5 | 3 |
| 6 | 2 |
| 8 | 2 |

## F2 — MIN_CLUSTER_SIZE = 5

### Walk-forward per-window OOS

| W1 | W2 | W3 | W4 | W5 | W6 | W7 | Sharpe-like | Sign |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| $-456 | $54 | $351 | $-70 | $-180 | $-95 | $240 | -0.26 | 3/7 |

### Calendar-year P&L

| Year | Trades | P&L | WR% |
|---:|---:|---:|---:|
| 2019 | 49 | $1,238 | 71.4% |
| 2020 | 23 | $10 | 52.2% |
| 2021 | 19 | $24 | 47.4% |
| 2022 | 30 | $-340 | 40.0% |
| 2023 | 22 | $206 | 59.1% |
| 2024 | 22 | $-86 | 50.0% |
| 2025 | 22 | $-95 | 45.5% |
| 2026 | 9 | $240 | 66.7% |

### Exit-type breakdown

| Exit | Count | Mean P&L | Total P&L |
|---|---:|---:|---:|
| target | 81 | $80.00 | $6,480 |
| stop | 69 | $-80.00 | $-5,520 |
| force_close | 46 | $5.20 | $239 |

### FADE/TREND label split

- Baseline: 391 FADE / 517 TREND
- F2 — MIN_CLUSTER_SIZE = 5: 85 FADE / 111 TREND

### Cluster-size distribution (3 / 4 / 5 / 6 / 7+)

| Size | Count | Mean P&L | Total P&L |
|---:|---:|---:|---:|
| 3 | 0 | — | — |
| 4 | 0 | — | — |
| 5 | 80 | $2.42 | $194 |
| 6 | 55 | $11.15 | $613 |
| 7+ | 61 | $6.43 | $392 |

### Filter-effect diagnostic vs baseline (matched by session_date + cluster_low + cluster_high)

- Baseline trades that do NOT appear in this variant: **750**
- Total P&L of those filtered-out trades (in baseline): **$8,125**
- WR% of filtered-out trades: **56.8%**
- Of those, cluster_size < 5 (filter-explained): 743
- Of those, cluster_size >= 5 (C2-reorder displaced): 7

Exit-type breakdown of filtered-out trades:

| Exit | Count | Mean P&L | Total P&L |
|---|---:|---:|---:|
| target | 375 | $80.00 | $30,000 |
| stop | 276 | $-80.00 | $-22,080 |
| force_close | 99 | $2.07 | $205 |

Filtered-out trades by cluster_size (raw):

| Size | Count |
|---:|---:|
| 3 | 576 |
| 4 | 167 |
| 5 | 3 |
| 6 | 2 |
| 8 | 2 |

## Files

- `report.md` — this report
- `trades_v2_4040_size4.parquet` — F1 trades
- `trades_v2_4040_size5.parquet` — F2 trades
