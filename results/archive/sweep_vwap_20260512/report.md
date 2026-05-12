# Phase 5 — VWAP-distance solo sweep

**Date:** 2026-05-12
**Sweep:** 2 anchors × 7 thresholds = 14 configs
**Anchors:** ['session', '9:30_ny']
**Thresholds:** [5, 10, 20, 30, 50, 80, 120]  (|close - VWAP| in raw points)

## Decision rule

Per cluster touch at bar T: look up |close_{T-1} - VWAP(anchor)_{T-1}| in points.
- distance ≥ threshold → TREND (far from VWAP → momentum, invert direction)
- distance < threshold → FADE (close to VWAP → mean-reversion likely)

VWAP uses typical price (H+L+C)/3 weighted by volume, cumulative from anchor.

## Qualifying under 4-gate: 0

**No configs qualify under all 4 gates.**

## Top 5 by Sharpe-like score

| anchor | thr | trades | median OOS | sharpe_like | sign | qual_4g | total_pnl |
|---|---:|---:|---:|---:|:---:|:---:|---:|
| 9:30_ny | 50 | 1693 | $704 | 0.702 | 4/7 |   | $1,348 |
| session | 50 | 1693 | $788 | 0.658 | 4/7 |   | $3,314 |
| session | 20 | 1693 | $570 | 0.423 | 4/7 |   | $1,620 |
| session | 30 | 1693 | $542 | 0.405 | 4/7 |   | $2,746 |
| session | 10 | 1693 | $210 | 0.159 | 4/7 |   | $4,210 |

## Full surface (anchor × threshold)

### Sharpe-like

| anchor \ thr | 5 | 10 | 20 | 30 | 50 | 80 | 120 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **9:30_ny** | -0.54 | -0.34 | -0.02 | 0.04 | 0.70 | -1.11 | -0.49 |
| **session** | -0.27 | 0.16 | 0.42 | 0.41 | 0.66 | -0.15 | -0.78 |

### Median OOS

| anchor \ thr | 5 | 10 | 20 | 30 | 50 | 80 | 120 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **9:30_ny** | $-870 | $-630 | $-30 | $71 | $704 | $-237 | $-427 |
| **session** | $-390 | $210 | $570 | $542 | $788 | $-64 | $-450 |

### Sign k/7

| anchor \ thr | 5 | 10 | 20 | 30 | 50 | 80 | 120 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **9:30_ny** | 3 | 3 | 3 | 4 | 4 | 1 | 2 |
| **session** | 3 | 4 | 4 | 4 | 4 | 3 | 1 |

### Total P&L

| anchor \ thr | 5 | 10 | 20 | 30 | 50 | 80 | 120 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **9:30_ny** | $2328 | $2734 | $3662 | $2738 | $1348 | $-2356 | $-3990 |
| **session** | $3360 | $4210 | $1620 | $2746 | $3314 | $-736 | $-3934 |

## Per-window OOS P&L for top-5 by Sharpe-like

| Config | W1 | W2 | W3 | W4 | W5 | W6 | W7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| VWAP(9:30_ny,50) | $796 | $724 | $1,423 | $-904 | $-1,176 | $704 | $-549 |
| VWAP(session,50) | $788 | $1,491 | $2,437 | $-314 | $-826 | $1,064 | $-554 |
| VWAP(session,20) | $1,296 | $1,751 | $1,801 | $-783 | $-1,268 | $570 | $-1,043 |
| VWAP(session,30) | $542 | $1,586 | $2,633 | $-301 | $-1,268 | $810 | $-563 |
| VWAP(session,10) | $2,028 | $1,762 | $841 | $-739 | $-1,224 | $210 | $-939 |
