# Phase 4 — ATR ratio solo sweep

**Date:** 2026-05-12
**Sweep:** 4 N_short × 4 thresholds = 16 configs
**N_short values:** [15, 30, 60, 120]  (1-min bars)
**N_long values:** [60, 120, 240, 480]  (= 4 × N_short)
**Thresholds:** [0.7, 1.0, 1.3, 1.6]  (ATR(N_short)/ATR(N_long) ratio)

## Decision rule

Per cluster touch at bar T: look up ATR(N_short)/ATR(N_long) at T-1.
- ratio ≥ threshold → TREND (vol expanding → invert direction)
- ratio < threshold → FADE (vol contracting → locked-baseline direction)

## Qualification gates (4-gate, locked 2026-05-12)

1. median(per-window OOS P&L) > 0
2. ≥ 6 of 7 OOS windows positive (sign stability)
3. (OOS Sharpe-like used for deployment rank, not a gate)
4. total_pnl > 0 (sum of all trade P&L over full 7-year dataset)

## Qualifying under 4-gate: 0

**No configs qualify under all 4 gates.**

## Top 5 by Sharpe-like score (regardless of qualification)

| N_short | thr | trades | median OOS | sharpe_like | sign | qual_4g | total_pnl |
|---:|---:|---:|---:|---:|:---:|:---:|---:|
| 30 | 1.3 | 1693 | $479 | 0.434 | 5/7 |   | $3,342 |
| 15 | 1.6 | 1693 | $419 | 0.338 | 4/7 |   | $-1,020 |
| 60 | 1.3 | 1693 | $221 | 0.205 | 4/7 |   | $3,010 |
| 15 | 1.0 | 1693 | $267 | 0.183 | 4/7 |   | $5,026 |
| 15 | 1.3 | 1693 | $78 | 0.102 | 4/7 |   | $38 |

## Full surface (N_short × threshold)

### Sharpe-like

| Ns \ thr | 0.7 | 1.0 | 1.3 | 1.6 |
|---:|---:|---:|---:|---:|
| **15** | -0.38 | 0.18 | 0.10 | 0.34 |
| **30** | -0.38 | -0.31 | 0.43 | -0.17 |
| **60** | -0.38 | -0.38 | 0.21 | -0.57 |
| **120** | -0.38 | -0.37 | -0.13 | -0.01 |

### Median OOS

| Ns \ thr | 0.7 | 1.0 | 1.3 | 1.6 |
|---:|---:|---:|---:|---:|
| **15** | $-568 | $267 | $78 | $419 |
| **30** | $-568 | $-448 | $479 | $-210 |
| **60** | $-568 | $-568 | $221 | $-600 |
| **120** | $-568 | $-568 | $-198 | $-9 |

### Sign k/7

| Ns \ thr | 0.7 | 1.0 | 1.3 | 1.6 |
|---:|---:|---:|---:|---:|
| **15** | 3 | 4 | 4 | 4 |
| **30** | 3 | 3 | 5 | 2 |
| **60** | 3 | 3 | 4 | 3 |
| **120** | 3 | 3 | 3 | 3 |

### Total P&L

| Ns \ thr | 0.7 | 1.0 | 1.3 | 1.6 |
|---:|---:|---:|---:|---:|
| **15** | $2778 | $5026 | $38 | $-1020 |
| **30** | $2778 | $2888 | $3342 | $-882 |
| **60** | $2778 | $2670 | $3010 | $-1516 |
| **120** | $2778 | $2304 | $154 | $-2572 |

## Per-window OOS P&L for top-5 by Sharpe-like

| Config | W1 | W2 | W3 | W4 | W5 | W6 | W7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ATR(Ns=30,thr=1.3) | $2,216 | $1,588 | $479 | $707 | $-542 | $-930 | $360 |
| ATR(Ns=15,thr=1.6) | $-228 | $-1,057 | $-1,147 | $808 | $2,424 | $750 | $419 |
| ATR(Ns=60,thr=1.3) | $1,972 | $1,436 | $691 | $221 | $-984 | $-404 | $-470 |
| ATR(Ns=15,thr=1.0) | $2,632 | $2,342 | $938 | $267 | $-1,102 | $-860 | $-10 |
| ATR(Ns=15,thr=1.3) | $1,724 | $1,014 | $-307 | $78 | $-226 | $-210 | $419 |
