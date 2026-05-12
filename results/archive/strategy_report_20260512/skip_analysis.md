# SKIP analysis — ADX(15,30) ∧ DI(15,8) unanimous (deployment winner)

**Date:** 2026-05-12
**Source:** R-012 deployment configuration. SKIPs captured via classifier instrumentation.

SKIPs are cluster touches where ADX and DI emitted opposite labels (one FADE, one TREND).
Under unanimous AND-gate, these clusters are consumed without firing a trade.

## Headline counts (7 years, 1,805 ORB-eligible sessions)

- **Trades fired:** 949 (FADE=410, TREND=539)
- **SKIPs:** 787
- **Total cluster-touch events:** 1,736
- **Overall SKIP rate:** 45.3%

## Daily metrics

Over 777 trading sessions:

| Statistic | Value |
|---|---:|
| Mean SKIPs per session | 1.01 |
| Median SKIPs per session | 1 |
| p75 SKIPs per session | 1 |
| Max SKIPs per session | 9 |
| % sessions with 0 SKIPs | 40.0% |
| % sessions with whole-day skip (touches > 0, trades = 0) | 25.9% |

## Monthly SKIP counts (7y × 12mo grid)

| Year | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | Total |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **2019** | — | — | — | — | 1 | 1 | 1 | 27 | 14 | 17 | 2 | 4 | **67** |
| **2020** | 1 | 4 | 32 | 23 | 10 | 1 | 2 | — | 6 | 4 | 13 | 1 | **97** |
| **2021** | 3 | 1 | 14 | 3 | 12 | 9 | 1 | 2 | 8 | 12 | 2 | 10 | **77** |
| **2022** | 11 | 17 | 21 | 19 | — | — | 1 | 2 | 4 | 6 | 11 | 19 | **111** |
| **2023** | 30 | 23 | 37 | 5 | 11 | — | 1 | 6 | 17 | 24 | 14 | 13 | **181** |
| **2024** | — | — | 3 | 12 | 8 | — | 3 | 25 | 8 | 6 | 6 | 7 | **78** |
| **2025** | 20 | 15 | 10 | 1 | 19 | 19 | 1 | 1 | 1 | — | 7 | 4 | **98** |
| **2026** | 31 | 15 | 16 | 16 | — | — | — | — | — | — | — | — | **78** |

## Monthly SKIP rate % (skips / total touches)

| Year | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | Avg |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **2019** | — | — | — | — | 25% | 17% | 11% | 49% | 42% | 31% | 40% | 67% | **35%** |
| **2020** | 33% | 57% | 54% | 48% | 62% | 11% | 67% | 0% | 55% | 33% | 65% | 50% | **45%** |
| **2021** | 50% | 25% | 42% | 75% | 55% | 45% | 50% | 25% | 44% | 46% | 33% | 40% | **44%** |
| **2022** | 29% | 45% | 58% | 61% | — | — | 50% | 40% | 40% | 29% | 39% | 48% | **44%** |
| **2023** | 54% | 55% | 59% | 36% | 65% | — | 100% | 35% | 57% | 67% | 47% | 65% | **58%** |
| **2024** | — | 0% | 50% | 48% | 36% | 0% | 50% | 51% | 24% | 27% | 30% | 88% | **37%** |
| **2025** | 48% | 34% | 40% | 100% | 45% | 45% | 25% | 12% | 50% | 0% | 47% | 31% | **40%** |
| **2026** | 45% | 27% | 40% | 62% | — | — | — | — | — | — | — | — | **43%** |

## Trend analysis — is the monthly SKIP rate stable, rising, or falling?

Linear regression of monthly SKIP rate (%) vs month index (1..80).

| Metric | Value |
|---|---:|
| Slope | **+0.010 pp / month** |
| Intercept | 43.10% |
| r² | 0.000 |
| t-statistic | +0.11 (df=78, \|t\|>2 ≈ p<0.05) |
| Fitted month-1 | 43.1% |
| Fitted month-80 | 43.9% |

**Verdict:** **STABLE.** Slope not significantly different from zero (|t| < 2). SKIP rate fluctuates month-to-month but no time trend.

**Interpretation context:**
- Phase 7 flagged 2026 Jan-Apr underperformance vs AllFade (−$1,422 over 4 months).
- A *rising* skip rate would mean: ADX and DI disagree more often in recent months → less filtering value → more trades getting through with conflicting signals.
- A *stable* or *falling* skip rate means: the filter's restrictiveness is consistent or tightening → 2026 underperformance is more likely sample noise than systemic.

## Recent months (last 12)

| Month | n_skips | n_clusters | skip rate % |
|---|---:|---:|---:|
| 2025-05 | 19 | 42 | 45.2% |
| 2025-06 | 19 | 42 | 45.2% |
| 2025-07 | 1 | 4 | 25.0% |
| 2025-08 | 1 | 8 | 12.5% |
| 2025-09 | 1 | 2 | 50.0% |
| 2025-10 | 0 | 2 | 0.0% |
| 2025-11 | 7 | 15 | 46.7% |
| 2025-12 | 4 | 13 | 30.8% |
| 2026-01 | 31 | 69 | 44.9% |
| 2026-02 | 15 | 56 | 26.8% |
| 2026-03 | 16 | 40 | 40.0% |
| 2026-04 | 16 | 26 | 61.5% |

## Artifacts

- `skip_analysis.parquet` — raw SKIP events (one row per SKIP, with session_date, ts_utc, cluster_low/high/size)
- `skip_analysis_daily.parquet` — per-session aggregates (n_trades, n_skips, n_clusters, skip_rate)
- `skip_analysis_monthly.parquet` — per-month time series (n_skips, n_clusters, skip_rate)