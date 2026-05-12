# Strategy Performance Report — ADX(15,30) ∧ DI(15,8) Unanimous (Deployment Winner)

**Date:** 2026-05-12
**Period:** 2019-05-15 → 2026-04-15 (~7 years)
**Geometry:** locked baseline (3-pt clusters, 30-pt bracket, first-touch, C2, 9:46-11:30 NY, force-close at 11:30 open)
**Regime gate:** ADX(15,30) ∧ DI(15,8) unanimous AND-gate at touch bar T-1
**Comparison:** locked AllFade baseline on the same 7-year dataset (R-006).

## 1. Headline stats

Cluster-touch event counts (v2 only — AllFade has no SKIP path):

- **Total cluster-touch events:** 1,736
- **FADE:** 410 (23.6%)
- **TREND:** 539 (31.0%)
- **SKIP:** 787 (45.3%)
- **Trades fired:** 949 (54.7%)

Performance metrics — v2 vs AllFade side-by-side:

| Metric | ADX∧DI v2 | AllFade baseline | Δ |
|---|---:|---:|---:|
| Trades | 949 | 1,693 | -744 |
| Wins / Losses / Flat | 524 / 425 / 0 | 824 / 867 / 2 | — |
| Win rate | 55.2% | 48.7% | +6.5pp |
| Total P&L | **$5,803.00** | $-3,377.50 | **$9,180.50** |
| Mean per trade | $6.11 | $-1.99 | $8.11 |
| Median per trade | $60.00 | $-12.00 | — |
| Avg winner | $56.71 | $55.75 | — |
| Avg loser | $-56.26 | $-56.89 | — |
| Profit factor | 1.243 | 0.932 | — |
| Max drawdown | **$-1,103.00** | $-6,156.50 | — |
| Max-DD duration (days, peak → recovery) | 596 | 2525 | — |
| Annualized Sharpe (daily P&L, sqrt(252)) | **1.76** | -0.74 | — |
| Annualized Sortino (MAR=0) | **2.88** | -0.95 | — |

v2 max-DD episode: peak 2022-01-10 → trough 2022-08-25 → recovery 2023-08-29.
AllFade max-DD episode: peak 2019-05-17 → trough 2024-07-22 → recovery no recovery.

## 2. Equity curve

![Equity curve](equity_curve.png)

Cumulative P&L over the full 7-year window, summed per session_date and cumulated daily.
Drawdown shaded in blue beneath the v2 line. AllFade overlay in red for direct comparison.

Underlying data: `equity_data.parquet` / `equity_data.csv` (one row per active session,
with v2 and AllFade daily P&L and cumulative columns).

## 3. Calendar-year comparison

| Year | v2 trades | v2 P&L | v2 WR | v2 max DD | AllFade trades | AllFade P&L | AllFade WR | AllFade max DD | Δ P&L |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 105 | $1,155.00 | 59.0% | $-211.00 | 157 | $-1,731.50 | 43.3% | $-1,738.00 | **$2,886.50** |
| 2020 | 94 | $198.50 | 50.0% | $-377.50 | 184 | $-972.00 | 45.1% | $-1,780.00 | **$1,170.50** |
| 2021 | 97 | $337.00 | 53.6% | $-300.00 | 171 | $85.50 | 52.0% | $-775.50 | **$251.50** |
| 2022 | 138 | $370.50 | 52.9% | $-1,103.00 | 245 | $-1,898.00 | 43.7% | $-1,846.50 | **$2,268.50** |
| 2023 | 145 | $1,180.50 | 57.2% | $-457.00 | 316 | $-958.50 | 47.5% | $-1,645.00 | **$2,139.00** |
| 2024 | 115 | $954.50 | 57.4% | $-480.00 | 192 | $558.00 | 52.1% | $-742.00 | **$396.50** |
| 2025 | 142 | $1,408.00 | 58.5% | $-513.50 | 239 | $-81.50 | 49.4% | $-1,289.50 | **$1,489.50** |
| 2026 | 113 | $199.00 | 51.3% | $-420.00 | 189 | $1,620.50 | 57.7% | $-240.00 | **$-1,421.50** |

Underlying data: `yearly_compare.parquet`.

## 4. FADE vs TREND breakdown

Which mode does the work? FADE = locked-baseline-direction trades; TREND = inverted-direction trades.

| Label | trades | wins / losses | win rate | total P&L | mean | avg winner | avg loser | profit factor |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| **FADE** | 410 | 237 / 173 | 57.8% | **$3,665.50** | $8.94 | $57.22 | $-57.20 | 1.370 |
| **TREND** | 539 | 287 / 252 | 53.2% | **$2,137.50** | $3.97 | $56.28 | $-55.62 | 1.153 |

Underlying data: `label_breakdown.parquet`.

## 5. Exit-type breakdown

| Exit reason | trades | % of total | mean P&L | total P&L | win rate |
|---|---:|---:|---:|---:|---:|
| **target** | 480 | 50.6% | $60.00 | $28,800.00 | 100.0% |
| **stop** | 382 | 40.3% | $-60.00 | $-22,920.00 | 0.0% |
| **force_close** | 87 | 9.2% | $-0.89 | $-77.00 | 50.6% |

Underlying data: `exit_breakdown.parquet`.

## Files in this directory

- `strategy_report.md` — this report
- `equity_curve.png` — plotted equity + drawdown
- `equity_data.parquet` / `.csv` — full daily P&L and cumulative series (both v2 and AllFade)
- `yearly_compare.parquet` — calendar-year side-by-side table
- `label_breakdown.parquet` — FADE vs TREND stats
- `exit_breakdown.parquet` — exit-type stats
- `skip_analysis.{md,parquet}` — SKIP analysis from prior step