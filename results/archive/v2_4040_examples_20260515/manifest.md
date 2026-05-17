# V2 + 40/40 example trades — manifest

Date generated: 2026-05-15
Source: `results/archive/strategy_report_20260512/trades_v2_4040.parquet` (908 trades)
Selection: 2 each of FADE win / TREND win / FADE loss / TREND loss, plus 2 force-close (one +, one −). Preferred 2024-2026.

| # | Date | Side | Label | Outcome | P&L | File |
|---:|---|---|---|---|---:|---|
| 1 | 2025-02-03 | BUY | FADE | FADE win | $+80 | `trade_01_20250203_FADE_win.png` |
| 2 | 2026-02-04 | SELL | FADE | FADE win | $+80 | `trade_02_20260204_FADE_win.png` |
| 3 | 2024-05-10 | SELL | TREND | TREND win | $+80 | `trade_03_20240510_TREND_win.png` |
| 4 | 2026-02-25 | BUY | TREND | TREND win | $+80 | `trade_04_20260225_TREND_win.png` |
| 5 | 2024-06-03 | BUY | FADE | FADE loss | $-80 | `trade_05_20240603_FADE_loss.png` |
| 6 | 2026-03-04 | SELL | FADE | FADE loss | $-80 | `trade_06_20260304_FADE_loss.png` |
| 7 | 2024-08-01 | SELL | TREND | TREND loss | $-80 | `trade_07_20240801_TREND_loss.png` |
| 8 | 2025-06-20 | SELL | TREND | TREND loss | $-80 | `trade_08_20250620_TREND_loss.png` |
| 9 | 2025-05-15 | BUY | TREND | force-close win | $+30 | `trade_09_20250515_force_close_win.png` |
| 10 | 2025-05-28 | SELL | TREND | force-close loss | $-30 | `trade_10_20250528_force_close_loss.png` |

## Notes

1. **2025-02-03 (FADE win)** — target hit in 7 minutes
2. **2026-02-04 (FADE win)** — fast target hit (0 min after entry)
3. **2024-05-10 (TREND win)** — fast target hit (5 min after entry)
4. **2026-02-25 (TREND win)** — fast target hit (1 min after entry)
5. **2024-06-03 (FADE loss)** — stopped within 5 minutes of entry
6. **2026-03-04 (FADE loss)** — stopped within 2 minutes of entry
7. **2024-08-01 (TREND loss)** — stopped within 5 minutes of entry
8. **2025-06-20 (TREND loss)** — slow-grind stop after 23 minutes
9. **2025-05-15 (force-close win)** — held through 11:30 force-close, small winner (+30$ over 7 min)
10. **2025-05-28 (force-close loss)** — ranged sideways until force-close, loser (-30$ over 68 min)