# 2-pt clusters + dynamic-TP — STACKED variant test

**Date:** 2026-05-12

## Strategy modification (stacked)

- **Cluster geometry:** CLUSTER_GAP = 2.0 (was 3.0). Chain rule (Option B) unchanged; MIN_CLUSTER_SIZE = 3.
- **Stop:** 30 pts fixed
- **TP:** nearest cluster boundary in trade direction at entry (touched or untouched); 30-pt fallback if no cluster in trade direction
- All other geometry locked: first-touch entry, C2, 9:46-11:30 NY trading window, force-close at 11:30 open
- ADX(15,30) ∧ DI(15,8) parameters LOCKED per directive — no re-sweep

**Interpretation note:** user wrote 'max pairwise distance ≤ 2 pts' but also 'cluster_gap unchanged'.
Those describe different cluster rules. Per locked spec D-002 (Option B chain rule) and R-002 precedent
(tested gap=2.0 with chain rule), this run uses CLUSTER_GAP=2.0 with chain-rule semantics. If the
intended rule was diameter (max pairwise distance) at 2 pts, the test needs to be rerun.

## 1. Cluster count per session — 2-pt vs 3-pt

| Statistic | 2-pt clusters | 3-pt clusters | Δ |
|---|---:|---:|---:|
| Mean / session | 19.2 | 28.5 | -9.4 |
| Median / session | 18.0 | 29.0 | -11.0 |
| p75 / session | 23.0 | 35.0 | -12.0 |
| Max / session | 43.0 | 46.0 | -3.0 |
| % sessions with 0 clusters | 0.4% | 0.4% | +0.0pp |
| Total clusters across all sessions | 34604.0 | 51483.0 | -16879.0 |

## 2. Trade counts — new-geometry reference triad

| Strategy | trades | total P&L | win rate |
|---|---:|---:|---:|
| ADX∧DI 2pt+dyntp | 652 | $3,367 | 48.2% |
| AllFade 2pt+dyntp | 1,118 | $-5,994 | 40.7% |
| AllTrend 2pt+dyntp | 1,143 | $2,172 | 46.5% |

## 3. Per-window OOS P&L — same-geometry triad

| Strategy | W1 | W2 | W3 | W4 | W5 | W6 | W7 | Sharpe-like |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ADX∧DI 2pt+dyntp | $1,742 | $2,222 | $1,424 | $1,626 | $166 | $-1,400 | $-712 | 1.03 |
| AllFade 2pt+dyntp | $56 | $256 | $-474 | $-474 | $-1,056 | $-1,212 | $-1,096 | -0.82 |
| AllTrend 2pt+dyntp | $2,298 | $1,769 | $-257 | $131 | $333 | $-616 | $-1,846 | 0.09 |

## 4. Exit-type breakdown — ADX∧DI 2pt+dyntp

| Exit type | trades | % of total | mean P&L | total P&L | win rate | mean TP dist (pts) |
|---|---:|---:|---:|---:|---:|---:|
| **cluster-target** | 220 | 33.7% | $66.28 | $14,582 | 100.0% | 33.1 |
| **fallback-30pt target** | 18 | 2.8% | $60.00 | $1,080 | 100.0% | 30.0 |
| **stop** | 304 | 46.6% | $-60.00 | $-18,240 | 0.0% | 167.7 |
| **force-close** | 110 | 16.9% | $54.05 | $5,946 | 69.1% | 183.9 |

## 5+6. ADX∧DI 2pt+dyntp — headline + walk-forward

| Metric | Value |
|---|---:|
| Trades | 652 |
| Win rate | 48.2% |
| Total P&L | $3,367 |
| Mean / trade | $5.16 |
| Avg winner | $71.40 |
| Avg loser | $-56.37 |
| Profit factor | 1.177 |
| Max drawdown | $-1,852 (duration 499 days, recovered: False) |
| Annualized Sharpe | 0.96 |
| Annualized Sortino | 1.90 |
| Walk-forward Sharpe-like | **1.03** |
| Walk-forward median OOS | $1,424 |
| Walk-forward sign | 5/7 |
| **4-gate deploy qualify** | **NO** |

## 7. Comparisons

### (a) ADX∧DI new geometry vs locked baseline (3-pt + 30/30 fixed) — combined effect

| Metric | ADX∧DI 2pt+dyntp | v2 3pt+30/30 fixed (locked) | Δ |
|---|---:|---:|---:|
| Trades | 652 | 949 | -297 |
| Win rate | 48.2% | 55.2% | -7.1pp |
| Total P&L | $3,367 | $5,803 | $-2,436 |
| Profit factor | 1.177 | 1.243 | — |
| Max drawdown | $-1,852 | $-1,103 | $-749 |
| Ann Sharpe | 0.96 | 1.85 | -0.89 |
| WF Sharpe-like | 1.03 | 5.32 | -4.29 |
| WF median OOS | $1,424 | $1,082 | $343 |
| WF sign | 5/7 | 7/7 | — |
| 4-gate deploy | NO | ✓ | — |

### (b) ADX∧DI new geometry vs AllFade new geometry — classifier value at new geom

| Metric | ADX∧DI 2pt+dyntp | AllFade 2pt+dyntp | Δ |
|---|---:|---:|---:|
| Trades | 652 | 1,118 | -466 |
| Win rate | 48.2% | 40.7% | +7.5pp |
| Total P&L | $3,367 | $-5,994 | $9,362 |
| Profit factor | 1.177 | 0.840 | — |
| Max drawdown | $-1,852 | $-6,096 | $4,244 |
| Ann Sharpe | 0.96 | -1.37 | +2.33 |
| WF Sharpe-like | 1.03 | -0.82 | +1.85 |
| WF median OOS | $1,424 | $-474 | $1,899 |
| WF sign | 5/7 | 2/7 | — |
| 4-gate deploy | NO | NO | — |

### (c) ADX∧DI new geometry vs ADX∧DI 3-pt + dynamic-TP — cluster-isolated effect

Cleanest cluster-only read: holds TP rule constant; changes only cluster_gap 3→2.

| Metric | ADX∧DI 2pt+dyntp | v2 3pt+dyntp | Δ |
|---|---:|---:|---:|
| Trades | 652 | 985 | -333 |
| Win rate | 48.2% | 50.5% | -2.3pp |
| Total P&L | $3,367 | $5,080 | $-1,714 |
| Profit factor | 1.177 | 1.184 | — |
| Max drawdown | $-1,852 | $-1,428 | $-424 |
| Ann Sharpe | 0.96 | 1.24 | -0.28 |
| WF Sharpe-like | 1.03 | 0.48 | +0.55 |
| WF median OOS | $1,424 | $443 | $982 |
| WF sign | 5/7 | 5/7 | — |
| 4-gate deploy | NO | NO | — |

## 8. TP-distance distribution under 2-pt clusters (ADX∧DI)

| min | p5 | p25 | median | mean | p75 | p95 | max |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.2 | 7.8 | 25.0 | 46.6 | 121.3 | 119.4 | 541.2 | 1305.5 |

Histogram:

| bucket (pts) | trades | % |
|---|---:|---:|
| 0-5 | 17 | 2.6% |
| 5-10 | 36 | 5.5% |
| 10-15 | 46 | 7.1% |
| 15-20 | 41 | 6.3% |
| 20-25 | 21 | 3.2% |
| 25-30 | 37 | 5.7% |
| 30-35 | 72 | 11.0% |
| 35-40 | 23 | 3.5% |
| 40-50 | 53 | 8.1% |
| 50-75 | 73 | 11.2% |
| 75-100 | 43 | 6.6% |
| 100-150 | 49 | 7.5% |
| 150-200 | 28 | 4.3% |
| 200+ | 113 | 17.3% |

## Files

- `clusters_2pt_dynamic_tp_test.md` — this report
- `trades_ADXANDDI_2pt_dyntp.parquet` — ADX∧DI new geometry trades
- `trades_AllFade_2pt_dyntp.parquet` — AllFade same-geometry reference
- `trades_AllTrend_2pt_dyntp.parquet` — AllTrend same-geometry reference
- `cluster_counts.parquet` — per-session cluster counts 2pt vs 3pt
- `exit_breakdown.parquet` — exit-type stats for ADX∧DI new geometry
- `tp_distance_histogram.parquet` — TP distance distribution
- `headlines.parquet` — all 5 configs side-by-side