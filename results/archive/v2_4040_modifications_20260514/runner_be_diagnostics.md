# Variant B — runner-BE diagnostics

Source: `trades_variant_b_partial_runnerBE.parquet` (899 entries).

---

## 1. p1 contracts (target = +40)

| p1 exit reason | n | Mean P&L | Total P&L |
|---|---:|---:|---:|
| target_40 | 436 | $80.00 | $34,880.00 |
| stop | 334 | $-80.00 | $-26,720.00 |
| force_close | 129 | $1.82 | $235.00 |
| **TOTAL p1** | **899** | $9.34 | **$8,395.00** |

---

## 2. p2 contracts (runner)

**Runner-BE state activated** = p1 reached +40 AND p2 was still open at bar X+1.

In the parquet, `runner_be_fired` is set whenever p1 exits at +40 (n=436). Of those 436, **203 had p2 already exit at cluster_target on the same bar X** (BE flag True but never effective — counted separately in 2c below). The strict count of cases where BE actually carried into bar X+1 with p2 open is therefore **233**.

### 2a. BE-activated (strict): n = 233

| p2 exit reason | n | Avg P&L | Total P&L |
|---|---:|---:|---:|
| target_cluster (later bar > X) | 55 | $162.83 | $8,955.50 |
| stop_be (BE-stop at entry hit) | 113 | $0.00 | $0.00 |
| force_close (held to 11:30) | 65 | $156.10 | $10,146.50 |
| **Subtotal** | **233** | $82.02 | **$19,102.00** |

### 2b. BE never activated — p1 hit −40 stop OR p1 force-closed: n = 463

| p2 exit reason | n | Avg P&L | Total P&L |
|---|---:|---:|---:|
| a) force_close at 11:30 (p1=force_close, both close together) | 129 | $1.82 | $235.00 |
| b) −40 stop | 286 | $-80.00 | $-22,880.00 |
| c) cluster target (p2 won, p1 later stopped) | 48 | $30.44 | $1,461.00 |
| **Subtotal** | **463** | $-45.97 | **$-21,184.00** |

### 2c. BE flag True but never effective (p1=target_40, p2=cluster_target same bar): n = 203

| p2 exit reason | n | Avg P&L | Total P&L |
|---|---:|---:|---:|
| target_cluster (hit same bar as p1's +40) | 203 | $50.63 | $10,278.00 |

### 2d. p2 grand totals (all 899 entries)

| p2 exit reason | n | Total P&L |
|---|---:|---:|
| target_cluster | 306 | $20,694.50 |
| stop_be | 113 | $0.00 |
| stop (initial −40) | 286 | $-22,880.00 |
| force_close | 194 | $10,381.50 |
| **TOTAL p2** | **899** | **$8,196.00** |

**Combined (p1 + p2) = $8,395.00 + $8,196.00 = $16,591.00** — matches parquet `pnl_dollars` sum exactly.

Full p1 × p2 cross-tabulation (counts):

| p1 \ p2 | force_close | stop | stop_be | target_cluster | Total |
|---|---:|---:|---:|---:|---:|
| force_close | 129 | 0 | 0 | 0 | 129 |
| stop | 0 | 286 | 0 | 48 | 334 |
| target_40 | 65 | 0 | 113 | 258 | 436 |
| **Total** | **194** | **286** | **113** | **306** | **899** |

---

## 3. Year-by-year P&L — Variant B vs V2+40/40 baseline ×2

| Year | B P&L | Baseline ×2 | Δ |
|---:|---:|---:|---:|
| 2019 | $1,992 | $2,248 | $-256 |
| 2020 | $1,212 | $1,006 | $+206 |
| 2021 | $1,430 | $1,308 | $+122 |
| 2022 | $599 | $1,586 | $-987 |
| 2023 | $3,711 | $3,138 | $+573 |
| 2024 | $2,650 | $2,452 | $+198 |
| 2025 | $3,588 | $4,696 | $-1,108 |
| 2026 | $1,408 | $1,184 | $+224 |
| **TOTAL** | **$16,591** | **$17,618** | **$-1,027** |

Baseline ×2 figures = `v2 40/40` column from `strategy_report_20260512/strategy_4040_test.md` calendar-year table, each value multiplied by 2.
