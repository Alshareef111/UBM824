# 40/40 R:R variant test — ADX(15,30) ∧ DI(15,8) Unanimous

**Date:** 2026-05-12
**Change tested:** stop/target widened from locked 30 points to 40 points (still 1:1 R:R).
**All other geometry locked:** 3-pt clusters, first-touch, C2, 9:46-11:30 NY, force-close at 11:30 open.

Comparison set: deployment winner ADX∧DI (30/30 from prior step, 40/40 from this test)
plus AllFade baseline (locked 30/30, 40/40 freshly computed for like-for-like).

## Headline stats — 4-way comparison

| Metric | v2 30/30 | v2 40/40 | AllFade 30/30 | AllFade 40/40 |
|---|---:|---:|---:|---:|
| Trades | 949 | 908 | 1,693 | 1,600 |
| Win rate | 55.2% | 56.2% | 48.7% | 45.7% |
| Total P&L | **$5,803** | **$8,808** | **$-3,378** | **$-11,253** |
| Mean / trade | $6.11 | $9.70 | $-1.99 | $-7.03 |
| Avg winner | $57 | $73 | $56 | $71 |
| Avg loser | $-56 | $-72 | $-57 | $-73 |
| Profit factor | 1.243 | 1.309 | 0.932 | 0.823 |
| Max drawdown | $-1,103 | $-1,228 | $-6,156 | $-11,694 |
| Max-DD duration (days) | 596 | 380 | 2525 | 2527 |
| Max-DD recovered? | yes | yes | no | no |
| Annualized Sharpe | 1.76 | 2.15 | -0.74 | -1.90 |
| Annualized Sortino | 2.88 | 3.61 | -0.95 | -2.34 |
| Target exits | 480 | 442 | 736 | 617 |
| Stop exits | 382 | 336 | 798 | 753 |
| Force-close exits | 87 | 130 | 159 | 230 |

## Walk-forward — 7 OOS windows (3y IS + 1y OOS, advance 6mo)

| Metric | v2 30/30 | v2 40/40 | AllFade 30/30 | AllFade 40/40 |
|---|---:|---:|---:|---:|
| Sharpe-like (median/stdev) | **5.32** | **6.86** | **0.37** | **-2.00** |
| Median per-window OOS P&L | $1,082 | $1,688 | $510 | $-1,413 |
| Sign-stability (k/7) | 7/7 | 7/7 | 4/7 | 0/7 |
| Sum per-window OOS P&L | $7,890 | $11,956 | $-1,150 | $-10,992 |
| Qualifies 4-gate deploy | ✓ | ✓ |   |   |

## Per-window OOS P&L

| Strategy | W1 | W2 | W3 | W4 | W5 | W6 | W7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| v2 30/30 | $763 | $1,082 | $1,266 | $1,325 | $1,340 | $1,048 | $1,067 |
| v2 40/40 | $1,304 | $1,644 | $1,688 | $1,538 | $1,936 | $2,028 | $1,820 |
| AllFade 30/30 | $-2,148 | $-1,777 | $-667 | $568 | $1,464 | $510 | $899 |
| AllFade 40/40 | $-2,850 | $-2,184 | $-1,456 | $-1,022 | $-852 | $-1,214 | $-1,413 |

## Calendar-year P&L (4-way)

| Year | v2 30/30 | v2 40/40 | AllFade 30/30 | AllFade 40/40 |
|---:|---:|---:|---:|---:|
| 2019 | $1,155 | $1,124 | $-1,732 | $-1,367 |
| 2020 | $198 | $503 | $-972 | $-1,635 |
| 2021 | $337 | $654 | $86 | $-1,130 |
| 2022 | $370 | $793 | $-1,898 | $-2,648 |
| 2023 | $1,180 | $1,569 | $-958 | $-1,658 |
| 2024 | $954 | $1,226 | $558 | $-716 |
| 2025 | $1,408 | $2,348 | $-82 | $-1,986 |
| 2026 | $199 | $592 | $1,620 | $-112 |

## Δ analysis: does widening the bracket help v2?

| Metric | 30/30 | 40/40 | Δ |
|---|---:|---:|---:|
| Trades | 949 | 908 | -41 |
| Win rate | 55.2% | 56.2% | +1.0pp |
| Total P&L | $5,803 | $8,808 | **$3,005** |
| Mean / trade | $6.11 | $9.70 | $+3.59 |
| Profit factor | 1.243 | 1.309 | +0.066 |
| Max drawdown | $-1,103 | $-1,228 | $-125 |
| Annualized Sharpe | 1.76 | 2.15 | +0.39 |
| Walk-forward sharpe-like | 5.32 | 6.86 | +1.54 |
| Walk-forward sign | 7/7 | 7/7 | — |
| Force-close exits | 87 | 130 | +43 |

**Verdict:** 40/40 IMPROVES the deployment winner on both absolute P&L and walk-forward Sharpe. Worth considering as the actual deployment configuration.

## Files

- `strategy_4040_test.md` — this report
- `trades_v2_4040.parquet` — ADX∧DI unanimous with 40/40 brackets
- `trades_allfade_4040.parquet` — AllFade locked behavior with 40/40 brackets
- `headlines_4040.parquet` — 4-way headline + walk-forward stats