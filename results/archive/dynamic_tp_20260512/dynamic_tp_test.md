# Dynamic-TP variant — ADX(15,30) ∧ DI(15,8) Unanimous

**Date:** 2026-05-12

## Strategy modification

- **Stop:** 30 pts fixed (unchanged)
- **Take profit:** nearest cluster boundary in trade direction at entry, regardless of touched/untouched
- **Fallback:** 30 pts fixed if no cluster in trade direction
- All other geometry locked: 3-pt clusters, first-touch, C2, 9:46-11:30 NY, force-close at 11:30 open

ADX∧DI parameters NOT re-swept per directive. Locked at N=15 / thr=30 (ADX) and thr=8 (DI).

## 1+3+4+6. Headline + walk-forward — side-by-side vs fixed 30/30

| Metric | dynamic-TP (this test) | fixed 30/30 (prior) | Δ |
|---|---:|---:|---:|
| Trades | 985 | 949 | +36 |
| Win rate | 50.5% | 55.2% | -4.8pp |
| Total P&L | **$5,080** | $5,803 | **$-722** |
| Mean / trade | $5.16 | $6.11 | $-0.96 |
| Avg winner | $65.63 | $56.71 | — |
| Avg loser | $-56.43 | $-56.26 | — |
| Profit factor | **1.184** | 1.243 | — |
| Max drawdown | $-1,428 | $-1,103 | $-325 |
| Max-DD duration (days) | 566 | 596 | — |
| Annualized Sharpe | **1.38** | 2.04 | -0.67 |
| Annualized Sortino | **2.60** | 3.35 | -0.75 |
| Walk-forward Sharpe-like | **0.48** | 5.32 | -4.83 |
| Walk-forward median OOS | $443 | $1,082 | $-638 |
| Walk-forward sign | 5/7 | 7/7 | — |
| 4-gate deploy qualify | NO | ✓ | — |

## 1. Per-window OOS P&L

| Strategy | W1 | W2 | W3 | W4 | W5 | W6 | W7 | Sharpe-like |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **dynamic-TP** | $1,046 | $2,196 | $1,495 | $443 | $-154 | $-328 | $278 | 0.48 |
| fixed 30/30 | $763 | $1,082 | $1,266 | $1,325 | $1,340 | $1,048 | $1,067 | 5.32 |
| Δ | +284 | +1,115 | +230 | -882 | -1,494 | -1,376 | -790 | — |

## 2. Exit-type breakdown (dynamic-TP)

| Exit type | trades | % of total | mean P&L | total P&L | win rate | mean TP dist (pts) |
|---|---:|---:|---:|---:|---:|---:|
| **cluster-target** | 366 | 37.2% | $61.02 | $22,334 | 100.0% | 30.5 |
| **fallback-30pt target** | 31 | 3.1% | $60.00 | $1,860 | 100.0% | 30.0 |
| **stop** | 440 | 44.7% | $-60.00 | $-26,400 | 0.0% | 128.1 |
| **force-close** | 148 | 15.0% | $49.23 | $7,286 | 67.6% | 162.5 |

## 5. TP-distance distribution (set-at-entry)

Summary stats:

| min | p5 | p25 | median | mean | p75 | p95 | max |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3.2 | 7.2 | 21.5 | 38.5 | 93.9 | 92.5 | 378.8 | 2093.5 |

Compare to old fixed TP = 30.0 pts. Mean TP distance under dynamic rule = 93.9 pts; median = 38.5 pts.

Histogram of TP distance (pts) at entry:

| bucket (pts) | trades | % |
|---|---:|---:|
| 0-5 | 15 | 1.5% |
| 5-10 | 74 | 7.5% |
| 10-15 | 72 | 7.3% |
| 15-20 | 72 | 7.3% |
| 20-25 | 50 | 5.1% |
| 25-30 | 51 | 5.2% |
| 30-35 | 118 | 12.0% |
| 35-40 | 49 | 5.0% |
| 40-50 | 94 | 9.5% |
| 50-75 | 95 | 9.6% |
| 75-100 | 62 | 6.3% |
| 100-150 | 83 | 8.4% |
| 150-200 | 41 | 4.2% |
| 200+ | 109 | 11.1% |

## Calendar-year P&L

| Year | dyntp trades | dyntp P&L | fixed trades | fixed P&L | Δ |
|---:|---:|---:|---:|---:|---:|
| 2019 | 115 | $968 | 105 | $1,155 | **$-187** |
| 2020 | 98 | $767 | 94 | $198 | **$568** |
| 2021 | 100 | $902 | 97 | $337 | **$564** |
| 2022 | 145 | $423 | 138 | $370 | **$52** |
| 2023 | 157 | $1,844 | 145 | $1,180 | **$663** |
| 2024 | 117 | $364 | 115 | $954 | **$-591** |
| 2025 | 141 | $-638 | 142 | $1,408 | **$-2,046** |
| 2026 | 112 | $452 | 113 | $199 | **$254** |

## Re-sweep flag

Under the dynamic-TP rule, the effective R:R varies per trade. The ADX/DI thresholds were
locked under the original fixed 30/30 R:R. Some considerations for whether to re-sweep:

- Sharpe Δ -4.83, P&L Δ $-722.
- Mixed or negative result under current ADX/DI thresholds.
- A re-sweep under dynamic-TP could potentially restore or exceed the fixed-TP edge.
- **Recommendation:** propose re-sweep as a follow-up. Do not run without explicit approval.

## Files

- `dynamic_tp_test.md` — this report
- `trades_v2_dyntp.parquet` — ADX∧DI unanimous trades under dynamic-TP rule
- `exit_breakdown.parquet` — exit-type stats (cluster-target / fallback / stop / force-close)
- `tp_distance_histogram.parquet` — TP distance bucket distribution