# Phase 7 — Quantitative Analyses

**Date:** 2026-05-12

## Analysis 1 — Window-trend regression on deploy-qualifying configs

Linear regression of OOS P&L vs window index (W1..W7).
Slope ≥ 0 = healthy / no decay. Significantly negative = signal weakening across time.

Note: 7 windows give df=5 for OLS. |t| > 2.57 ≈ p<0.05 two-tailed; |t| > 4.03 ≈ p<0.01.

| Config | sharpe | slope $/window | r² | t-stat | W1 P&L | W7 P&L | drift |
|---|---:|---:|---:|---:|---:|---:|---:|
| B ADX∧DI unanimous | 5.32 | +33 | 0.12 | +0.83 | $763 | $1,067 | $+304 |
| A solo ADX | 4.02 | +100 | 0.54 | +2.44 | $496 | $1,398 | $+902 |
| A solo DI | 2.30 | -230 | 0.57 | -2.59 | $1,510 | $325 | $-1,186 |
| A LOO-ATR | 2.00 | -48 | 0.10 | -0.75 | $598 | $188 | $-409 |
| A LOO-DI | 1.37 | -57 | 0.47 | -2.09 | $468 | $107 | $-362 |
| A LOO-ROC | 1.15 | -99 | 0.68 | -3.26 | $503 | $0 | $-503 |

**Interpretation:**
- **B ADX∧DI unanimous** (deployment winner): slope `$+33/window`, r²=0.12, t=+0.83. Drift W1→W7: $+304.
- **3 of 6 configs** show healthy slope (>-$50/window).
- **Severe-decay configs** (slope < -$150/window): A solo DI

## Analysis 2 — DI(15,8) discrimination check

Comparing DI(15,8) actual scores against 30 BiasedRandom(trend_prob=0.73) seeds.
Random labeling preserves DI's TREND bias (73%) but otherwise selects clusters randomly.
If DI is genuinely *selecting* high-conviction clusters, its scores should exceed this null.
If DI is merely *imposing* a 73% TREND bias that happens to fit, scores should be average.

| Metric | DI(15,8) actual | Random p50 | Random p95 | Random max | DI percentile |
|---|---:|---:|---:|---:|---:|
| Sharpe-like | **2.30** | -0.11 | 0.66 | 0.90 | **100.0%** |
| Median OOS | **$1,510** | $-216 | $708 | $889 | **100.0%** |
| Total P&L | **$7,426** | $778 | $3,844 | $4,256 | **100.0%** |

**Interpretation:**
- DI's scores exceed the 95th percentile of the same-bias random distribution on both
  Sharpe-like and median. **Strong evidence that DI is selecting good clusters,**
  not just imposing a directional bias.

## Analysis 3 — AllFade vs ADX∧DI on 2026 partial (Jan-Apr 2026)

Tests whether the unanimous composite preserves edge in the most recent unverified period.

| | trades | total P&L | win rate |
|---|---:|---:|---:|
| **AllFade (locked baseline)** | 189 | $1,620 | 57.7% |
| **ADX∧DI unanimous (deployment)** | 113 | $199 | 51.3% |

### Monthly breakdown

| Month | AllFade trades | AllFade P&L | AllFade WR | ADX∧DI trades | ADX∧DI P&L | ADX∧DI WR |
|---|---:|---:|---:|---:|---:|---:|
| 2026-01 | 67 | $480 | 57% | 38 | $139 | 53% |
| 2026-02 | 56 | $541 | 59% | 41 | $-60 | 49% |
| 2026-03 | 40 | $360 | 57% | 24 | $-120 | 46% |
| 2026-04 | 26 | $240 | 58% | 10 | $240 | 70% |

**ADX∧DI underperforms AllFade in 2026-partial by $1,422.** Recent regime may diverge — deployment concern.
