# Phase 0 supplement — null-distribution baseline

**Date:** 2026-05-12
**Seeds:** 1–50
**Classifier:** RandomBinary (per-cluster 50/50 FADE/TREND, hash-keyed)

Random labeling per cluster, deterministic via seed. Acts as the null
comparison — any real indicator must clearly exceed this distribution,
not just clear the qualification gates.

## Qualification rate under null

**2 of 50 = 4.0%** seeds qualify under the spec gates
(>=6/7 OOS windows positive AND median OOS > 0).

If this rate is non-trivial (say > 5%), then 'qualifies = true' for a
real indicator is by itself weak evidence of edge — the indicator's
score must beat the null's percentile distribution.

## Distribution of scores

| Statistic | min | p5 | p25 | median | p75 | p95 | max | mean | stdev |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sharpe_like | -1.31 | -0.89 | -0.49 | -0.07 | 0.26 | 1.06 | 1.21 | -0.06 | 0.60 |
| sign_count | 1.00 | 1.45 | 2.00 | 3.00 | 4.00 | 5.00 | 6.00 | 3.36 | 1.29 |
| median_oos | -738 | -731 | -393 | -31.25 | 225 | 646 | 1,193 | -37.82 | 441 |

## How to use this in Phase 1+

For an indicator parameter config X with score (sharpe_like, sign_count, median_oos):

- **Weak evidence:** X qualifies under the gates. (Some non-trivial fraction of random
  seeds also qualify, so qualifying alone is not strong.)
- **Moderate evidence:** X's sharpe_like exceeds the null distribution's 75th percentile.
- **Strong evidence:** X's sharpe_like exceeds the null's 95th percentile AND median_oos
  exceeds null's 95th percentile.
- **Almost certainly noise:** X scores below the null's median across all three stats.

## Top 5 seeds by Sharpe-like

| Seed | trades | fade_frac | median OOS | sharpe_like | sign | qualifies | total |
|---:|---:|---:|---:|---:|:---:|:---:|---:|
| 50 | 1693 | 49.7% | $392 | 1.214 | 6/7 | ✓ | $-952 |
| 22 | 1693 | 50.3% | $688 | 1.178 | 6/7 | ✓ | $1,270 |
| 33 | 1693 | 49.4% | $724 | 1.135 | 5/7 |   | $3,994 |
| 15 | 1693 | 49.4% | $1,193 | 0.979 | 5/7 |   | $3,696 |
| 47 | 1693 | 49.9% | $594 | 0.849 | 5/7 |   | $1,268 |

## Bottom 5 seeds by Sharpe-like

| Seed | trades | fade_frac | median OOS | sharpe_like | sign | qualifies | total |
|---:|---:|---:|---:|---:|:---:|:---:|---:|
| 18 | 1693 | 49.7% | $-604 | -1.307 | 2/7 |   | $-1,614 |
| 23 | 1693 | 48.1% | $-738 | -1.042 | 2/7 |   | $-1,308 |
| 27 | 1693 | 50.4% | $-614 | -0.892 | 3/7 |   | $-2,928 |
| 49 | 1693 | 49.1% | $-734 | -0.882 | 2/7 |   | $-3,102 |
| 30 | 1693 | 48.6% | $-728 | -0.871 | 1/7 |   | $-1,966 |

## Per-window OOS P&L by seed (first 10 + last 5)

| Seed | W1 | W2 | W3 | W4 | W5 | W6 | W7 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | $-388 | $-1,097 | $268 | $462 | $-136 | $-44 | $-57 |
| 2 | $528 | $276 | $248 | $-699 | $-618 | $462 | $155 |
| 3 | $-162 | $194 | $293 | $-218 | $-30 | $-236 | $429 |
| 4 | $930 | $754 | $200 | $746 | $122 | $-604 | $-2,084 |
| 5 | $38 | $-751 | $101 | $1,971 | $1,894 | $1,020 | $-958 |
| 6 | $-714 | $-1,648 | $428 | $38 | $-822 | $-408 | $-416 |
| 7 | $-486 | $508 | $986 | $-1,576 | $-1,466 | $150 | $239 |
| 8 | $580 | $823 | $991 | $983 | $94 | $-620 | $-533 |
| 9 | $-264 | $-1,101 | $247 | $-308 | $-440 | $-486 | $-325 |
| 10 | $458 | $-749 | $-297 | $1,025 | $1,658 | $204 | $-1,745 |
| 46 | $862 | $79 | $-69 | $-11 | $-1,196 | $-984 | $-268 |
| 47 | $594 | $644 | $327 | $1,043 | $1,598 | $-276 | $-383 |
| 48 | $1,182 | $412 | $-210 | $-276 | $-720 | $-4 | $2,635 |
| 49 | $498 | $-453 | $-1,285 | $-1,219 | $-734 | $576 | $-1,421 |
| 50 | $348 | $543 | $-394 | $132 | $392 | $402 | $502 |
