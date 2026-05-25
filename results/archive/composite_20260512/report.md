# Phase 6 — LOO + Composite Runs

**Date:** 2026-05-12
**Null p95 Sharpe-like threshold:** 1.06

## Deployment qualification gates (4-gate, locked 2026-05-12)

1. median(per-window OOS P&L) > 0
2. ≥ 6 of 7 OOS windows positive
3. sharpe_like > 1.06 (null p95)
4. total_pnl > 0 (sum of all trade P&L over full 7-year dataset)

## All configs (12 unique)

| Config | trades | F / T | median OOS | sharpe | sign | total | DEPLOY |
|---|---:|---|---:|---:|:---:|---:|:---:|
| A solo ADX | 1693 | 1089 / 604 | $1,174 | 4.02 | 7/7 | $4,058 | ✓ |
| A solo DI | 1693 | 456 / 1237 | $1,510 | 2.30 | 7/7 | $7,426 | ✓ |
| A solo ROC | 1693 | 1087 / 606 | $708 | 1.43 | 6/7 | $-1,430 |  3g |
| A solo ATR | 1693 | 302 / 1391 | $479 | 0.43 | 5/7 | $3,342 |   |
| A solo VWAP | 1693 | 805 / 888 | $704 | 0.70 | 4/7 | $1,348 |   |
| A LOO-ADX | 353 | 20 / 333 | $221 | 0.48 | 5/7 | $1,296 |   |
| A LOO-DI | 312 | 71 / 241 | $247 | 1.37 | 6/7 | $940 | ✓ |
| A LOO-ROC | 312 | 21 / 291 | $300 | 1.15 | 6/7 | $2,116 | ✓ |
| A LOO-ATR | 538 | 246 / 292 | $658 | 2.00 | 7/7 | $2,790 | ✓ |
| A LOO-VWAP | 312 | 40 / 272 | $281 | 0.78 | 5/7 | $953 |   |
| A Full5 unanimous | 255 | 20 / 235 | $180 | 0.87 | 6/7 | $1,096 |  4g |
| B ADX∧DI unanimous | 949 | 410 / 539 | $1,082 | 5.32 | 7/7 | $5,803 | ✓ |

## Comparison 1 — ADX solo vs DI solo vs ADX∧DI unanimous

Variant B's central question: does requiring agreement improve over either alone?

| Config | trades | F / T | median OOS | sharpe | sign | total | DEPLOY |
|---|---:|---|---:|---:|:---:|---:|:---:|
| A solo ADX | 1693 | 1089 / 604 | $1,174 | 4.02 | 7/7 | $4,058 | ✓ |
| A solo DI | 1693 | 456 / 1237 | $1,510 | 2.30 | 7/7 | $7,426 | ✓ |
| B ADX∧DI unanimous | 949 | 410 / 539 | $1,082 | 5.32 | 7/7 | $5,803 | ✓ |

**Verdict:** unanimous beats the better solo (A solo ADX, sharpe 4.02) — outcome 3 (unanimous wins).

- ADX solo:        sharpe=4.02, median=$1,174, sign=7/7, trades=1693
- DI solo:         sharpe=2.30, median=$1,510, sign=7/7, trades=1693
- ADX∧DI unanimous: sharpe=5.32, median=$1,082, sign=7/7, trades=949

## Comparison 2 — Variant A LOOs ranked by improvement from removing each indicator

Δsharpe = LOO sharpe − Full5 sharpe. Positive = removing this indicator HELPS (it was a drag).
Full5 baseline: sharpe=0.87, median=$180, sign=6/7, trades=255

| Removed | LOO trades | LOO sharpe | Δsharpe vs Full5 | LOO median | Δmedian | LOO total | Δtotal | DEPLOY |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| **ATR** | 538 | 2.00 | +1.13 | $658 | $+478 | $2,790 | $+1,695 | ✓ |
| **DI** | 312 | 1.37 | +0.50 | $247 | $+67 | $940 | $-156 | ✓ |
| **ROC** | 312 | 1.15 | +0.28 | $300 | $+120 | $2,116 | $+1,020 | ✓ |
| **VWAP** | 312 | 0.78 | -0.09 | $281 | $+101 | $953 | $-142 |    |
| **ADX** | 353 | 0.48 | -0.39 | $221 | $+41 | $1,296 | $+200 |    |

**Biggest drag on Full5:** removing **ATR** improved sharpe by +1.13.

## Comparison 3 — Variant B (ADX∧DI) vs best Variant A LOO

Best A LOO by sharpe: **A LOO-ATR**

| Config | trades | F / T | median OOS | sharpe | sign | total | DEPLOY |
|---|---:|---|---:|---:|:---:|---:|:---:|
| B ADX∧DI unanimous | 949 | 410 / 539 | $1,082 | 5.32 | 7/7 | $5,803 | ✓ |
| A LOO-ATR | 538 | 246 / 292 | $658 | 2.00 | 7/7 | $2,790 | ✓ |

**Verdict:** Variant B (tight 2-corner stack) beats the best Variant A LOO by sharpe.

## Per-window OOS P&L for all 12 configs

| Config | W1 | W2 | W3 | W4 | W5 | W6 | W7 | sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A solo ADX | $496 | $1,174 | $1,213 | $976 | $1,144 | $1,250 | $1,398 | 4.02 |
| A solo DI | $1,510 | $1,829 | $2,000 | $1,996 | $1,416 | $676 | $325 | 2.30 |
| A solo ROC | $256 | $880 | $919 | $256 | $774 | $708 | $-452 | 1.43 |
| A solo ATR | $2,216 | $1,588 | $479 | $707 | $-542 | $-930 | $360 | 0.43 |
| A solo VWAP | $796 | $724 | $1,423 | $-904 | $-1,176 | $704 | $-549 | 0.70 |
| A LOO-ADX | $683 | $1,062 | $720 | $221 | $120 | $-120 | $-120 | 0.48 |
| A LOO-DI | $468 | $330 | $322 | $22 | $-20 | $247 | $107 | 1.37 |
| A LOO-ROC | $503 | $696 | $654 | $221 | $180 | $300 | $0 | 1.15 |
| A LOO-ATR | $598 | $736 | $1,247 | $624 | $658 | $968 | $188 | 2.00 |
| A LOO-VWAP | $766 | $764 | $400 | $281 | $60 | $-127 | $-7 | 0.78 |
| A Full5 unanimous | $443 | $502 | $460 | $161 | $180 | $180 | $-60 | 0.87 |
| B ADX∧DI unanimous | $763 | $1,082 | $1,266 | $1,325 | $1,340 | $1,048 | $1,067 | 5.32 |

## Deployment-qualifying configs (4-gate)

| Rank | Config | sharpe | median | sign | total |
|---:|---|---:|---:|:---:|---:|
| 1 | B ADX∧DI unanimous | 5.32 | $1,082 | 7/7 | $5,803 |
| 2 | A solo ADX | 4.02 | $1,174 | 7/7 | $4,058 |
| 3 | A solo DI | 2.30 | $1,510 | 7/7 | $7,426 |
| 4 | A LOO-ATR | 2.00 | $658 | 7/7 | $2,790 |
| 5 | A LOO-DI | 1.37 | $247 | 6/7 | $940 |
| 6 | A LOO-ROC | 1.15 | $300 | 6/7 | $2,116 |

**Deployment winner candidate:** B ADX∧DI unanimous
