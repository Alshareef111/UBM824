# Phase 0 Validation Report

**Date:** 2026-05-12
**Status:** PASS

Two non-negotiable validations per user spec:
1. simulator_v2 with AllFade classifier byte-identical to locked extended baseline
2. Walk-forward harness sanity with synthetic classifiers

## Summary

| Test | Result | Detail |
|---|---|---|
| V1 byte-equivalence | PASS | baseline rows: 1,693  sum_pnl: $-3,377.50 |
| V2a windows | PASS |   W1: IS [2019-05-06, 2022-05-06)  OOS [2022-05-06, 2023-05-06) |
| V2b SKIP path | PASS | AllSkip produced 0 trades — SKIP path works |
| V2c TREND inversion | PASS | trade count match: 1693 |
| V2d RandomBinary mix | PASS | RandomBinary labels: FADE=845 (49.9%)  TREND=848 (50.1%)  (within 40-60% — OK) |
| V2e bucketing AllFade | PASS | AllFade: all 7 windows match direct-sum  [W1: $-2,148, W2: $-1,777, W3: $-667, W4: $568, W |
| V2f bucketing AllTrend | PASS | AllTrend: all 7 windows match direct-sum  [W1: $2,148, W2: $1,777, W3: $667, W4: $-568, W5 |
| V2g scoring finite | PASS | AllFade   sharpe_like=0.368  median=$510.50  sign=4/7  qualified=False |

## Validation 1 — Byte-equivalence

**Status:** PASS

```
baseline rows: 1,693  sum_pnl: $-3,377.50
v2 AllFade rows: 1,693  sum_pnl: $-3,377.50
assert_frame_equal(check_exact=True) PASSED
```

## Validation 2 — Walk-forward harness sanity

### Window definitions

| Window | IS start | IS end | OOS start | OOS end |
|---|---|---|---|---|
| W1 | 2019-05-06 | 2022-05-06 | 2022-05-06 | 2023-05-06 |
| W2 | 2019-11-06 | 2022-11-06 | 2022-11-06 | 2023-11-06 |
| W3 | 2020-05-06 | 2023-05-06 | 2023-05-06 | 2024-05-06 |
| W4 | 2020-11-06 | 2023-11-06 | 2023-11-06 | 2024-11-06 |
| W5 | 2021-05-06 | 2024-05-06 | 2024-05-06 | 2025-05-06 |
| W6 | 2021-11-06 | 2024-11-06 | 2024-11-06 | 2025-11-06 |
| W7 | 2022-05-06 | 2025-05-06 | 2025-05-06 | 2026-05-06 |

### Classifier outputs

| Classifier | Trades | Total P&L | Win/Loss/Force |
|---|---:|---:|---|
| AllFade | 1,693 | $-3,377.50 | target=736 / stop=798 / fc=159 |
| AllTrend | 1,693 | $2,777.50 | target=793 / stop=741 / fc=159 |
| RandomBinary(0) | 1,693 | $2,491.50 | target=787 / stop=747 / fc=159 |

### Per-window OOS P&L

| Window | AllFade | AllTrend | RandomBinary(0) |
|---|---:|---:|---:|
| W1 | $-2,148 | $2,148 | $434 |
| W2 | $-1,777 | $1,777 | $534 |
| W3 | $-667 | $667 | $182 |
| W4 | $568 | $-568 | $154 |
| W5 | $1,464 | $-1,584 | $214 |
| W6 | $510 | $-750 | $192 |
| W7 | $899 | $-1,379 | $61 |

Scoring per classifier:

```
AllFade                  median=$      510  sharpe_like=  0.368  sign=4/7  REJECTED 
AllTrend                 median=$     -568  sharpe_like= -0.379  sign=3/7  REJECTED 
RandomBinary(0)          median=$      192  sharpe_like=  1.148  sign=7/7  QUALIFIED
```

### Detailed sanity check results

**V2a windows** — PASS

```
  W1: IS [2019-05-06, 2022-05-06)  OOS [2022-05-06, 2023-05-06)
  W2: IS [2019-11-06, 2022-11-06)  OOS [2022-11-06, 2023-11-06)
  W3: IS [2020-05-06, 2023-05-06)  OOS [2023-05-06, 2024-05-06)
  W4: IS [2020-11-06, 2023-11-06)  OOS [2023-11-06, 2024-11-06)
  W5: IS [2021-05-06, 2024-05-06)  OOS [2024-05-06, 2025-05-06)
  W6: IS [2021-11-06, 2024-11-06)  OOS [2024-11-06, 2025-11-06)
  W7: IS [2022-05-06, 2025-05-06)  OOS [2025-05-06, 2026-05-06)
```

**V2b SKIP path** — PASS

```
AllSkip produced 0 trades — SKIP path works
```

**V2c TREND inversion** — PASS

```
trade count match: 1693
fill keys (session_date, entry_time, entry_price) match in order
sides inverted at every row (833 buy<->sell pairs flipped)
AllFade labels: {'FADE': 1693}
AllTrend labels: {'TREND': 1693}
```

**V2d RandomBinary mix** — PASS

```
RandomBinary labels: FADE=845 (49.9%)  TREND=848 (50.1%)  (within 40-60% — OK)
```

**V2e bucketing AllFade** — PASS

```
AllFade: all 7 windows match direct-sum  [W1: $-2,148, W2: $-1,777, W3: $-667, W4: $568, W5: $1,464, W6: $510, W7: $899]
```

**V2f bucketing AllTrend** — PASS

```
AllTrend: all 7 windows match direct-sum  [W1: $2,148, W2: $1,777, W3: $667, W4: $-568, W5: $-1,584, W6: $-750, W7: $-1,379]
```

**V2g scoring finite** — PASS

```
AllFade   sharpe_like=0.368  median=$510.50  sign=4/7  qualified=False
AllTrend  sharpe_like=-0.379  median=$-568.00  sign=3/7  qualified=False
RandomBin sharpe_like=1.148  median=$192.50  sign=7/7  qualified=True
```

## Artifacts

- `trades_v2_allfade.parquet` — for inspection; should byte-match baseline
- `trades_v2_alltrend.parquet` — TREND-inverted variant
- `trades_v2_randombinary.parquet` — 50/50 mix