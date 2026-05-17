# V2 + 40/40 example trades (with 9:45 cluster pool) — manifest

Date generated: 2026-05-15
Same 10 trades as `v2_4040_examples_20260515/`, now annotated with the full 9:45 cluster pool.

**Cluster fate categories (legend in the figures):**
- TRADED: purple, the cluster the simulator actually traded
- TOUCHED_NOT_TRADED: medium gray, near-border crossed by a bar's range during 09:46-11:30 but blocked by C2 or by classifier SKIP
- UNTOUCHED: faint gray, near-border never crossed during 09:46-11:30
- SPANS_CLOSE: light amber, cluster spans the 9:45 ORB close — SKIP per D-003

Y-axis on every figure is zoomed to entry ± 60 points, so the cluster density near the trade is visible. Clusters outside that band exist but are not visualized.

| # | Date | Side | Label | Outcome | P&L | Total clusters | Above | Below | Spans | Touched-not-traded | Untouched | File |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2025-02-03 | BUY | FADE | FADE win | $+80 | 30 | 7 | 23 | 0 | 8 | 21 | `trade_01_20250203_FADE_win_with_clusters.png` |
| 2 | 2026-02-04 | SELL | FADE | FADE win | $+80 | 26 | 14 | 12 | 0 | 2 | 23 | `trade_02_20260204_FADE_win_with_clusters.png` |
| 3 | 2024-05-10 | SELL | TREND | TREND win | $+80 | 29 | 2 | 27 | 0 | 4 | 24 | `trade_03_20240510_TREND_win_with_clusters.png` |
| 4 | 2026-02-25 | BUY | TREND | TREND win | $+80 | 30 | 17 | 13 | 0 | 1 | 28 | `trade_04_20260225_TREND_win_with_clusters.png` |
| 5 | 2024-06-03 | BUY | FADE | FADE loss | $-80 | 28 | 0 | 28 | 0 | 0 | 27 | `trade_05_20240603_FADE_loss_with_clusters.png` |
| 6 | 2026-03-04 | SELL | FADE | FADE loss | $-80 | 32 | 24 | 8 | 0 | 4 | 27 | `trade_06_20260304_FADE_loss_with_clusters.png` |
| 7 | 2024-08-01 | SELL | TREND | TREND loss | $-80 | 22 | 1 | 21 | 0 | 0 | 21 | `trade_07_20240801_TREND_loss_with_clusters.png` |
| 8 | 2025-06-20 | SELL | TREND | TREND loss | $-80 | 23 | 3 | 19 | 1 | 5 | 16 | `trade_08_20250620_TREND_loss_with_clusters.png` |
| 9 | 2025-05-15 | BUY | TREND | force-close win | $+30 | 20 | 11 | 9 | 0 | 2 | 17 | `trade_09_20250515_force_close_win_with_clusters.png` |
| 10 | 2025-05-28 | SELL | TREND | force-close loss | $-30 | 22 | 8 | 14 | 0 | 1 | 20 | `trade_10_20250528_force_close_loss_with_clusters.png` |

## Per-trade landscape notes

1. **2025-02-03 (FADE win)** — pool of 30 clusters at 9:45 (7 above ORB close, 23 below, 0 spanning). During 09:46-11:30: 1 traded, 8 touched-not-traded, 21 untouched.
2. **2026-02-04 (FADE win)** — pool of 26 clusters at 9:45 (14 above ORB close, 12 below, 0 spanning). During 09:46-11:30: 1 traded, 2 touched-not-traded, 23 untouched.
3. **2024-05-10 (TREND win)** — pool of 29 clusters at 9:45 (2 above ORB close, 27 below, 0 spanning). During 09:46-11:30: 1 traded, 4 touched-not-traded, 24 untouched.
4. **2026-02-25 (TREND win)** — pool of 30 clusters at 9:45 (17 above ORB close, 13 below, 0 spanning). During 09:46-11:30: 1 traded, 1 touched-not-traded, 28 untouched.
5. **2024-06-03 (FADE loss)** — pool of 28 clusters at 9:45 (0 above ORB close, 28 below, 0 spanning). During 09:46-11:30: 1 traded, 0 touched-not-traded, 27 untouched.
6. **2026-03-04 (FADE loss)** — pool of 32 clusters at 9:45 (24 above ORB close, 8 below, 0 spanning). During 09:46-11:30: 1 traded, 4 touched-not-traded, 27 untouched.
7. **2024-08-01 (TREND loss)** — pool of 22 clusters at 9:45 (1 above ORB close, 21 below, 0 spanning). During 09:46-11:30: 1 traded, 0 touched-not-traded, 21 untouched.
8. **2025-06-20 (TREND loss)** — pool of 23 clusters at 9:45 (3 above ORB close, 19 below, 1 spanning). During 09:46-11:30: 1 traded, 5 touched-not-traded, 16 untouched.
9. **2025-05-15 (force-close win)** — pool of 20 clusters at 9:45 (11 above ORB close, 9 below, 0 spanning). During 09:46-11:30: 1 traded, 2 touched-not-traded, 17 untouched.
10. **2025-05-28 (force-close loss)** — pool of 22 clusters at 9:45 (8 above ORB close, 14 below, 0 spanning). During 09:46-11:30: 1 traded, 1 touched-not-traded, 20 untouched.