# 40/40 Stop/Target Variant — Research Log

**Date:** 2026-05-11
**Scope:** Test whether widening the locked 30-point stop and 30-point target to 40/40 on the hybrid simulator produces a meaningful improvement on the 7-year extended dataset.
**Locked baseline preserved.** sha256 `d24f128a…f4c6` before and after.

---

## Variant construction

`src/simulator_hybrid_4040.py` — sibling of `simulator_hybrid.py`, minimum 3-line diff:

```diff
-TRADES_PARQUET = ARCHIVE_DIR / "trades_hybrid.parquet"
+TRADES_PARQUET = ARCHIVE_DIR / "trades_hybrid_4040_20260511.parquet"
-STOP_POINTS = 30.0
-TARGET_POINTS = 30.0
+STOP_POINTS = 40.0
+TARGET_POINTS = 40.0
```

All other parameters identical (LOOKBACK=200, CLUSTER_GAP=3.0, MIN_CLUSTER_SIZE=3, ATR_LOOKBACK=10, HYBRID_FLAT_THRESHOLD=0.09).

Output: `results/archive/trades_hybrid_4040_20260511.parquet`. Locked baseline path never touched.

---

## Headline result

```
1,600 trades  /  48.7% WR  /  -$3,216.00 total
exits: target=666  stop=704  force_close=230
routing: directional=1,005 (-$6,994.50)  flat=593 (+$3,938.50)  UNLABELED=2 (-$160)
```

vs hybrid 30/30 (1,693 / 49.9% / +$62.50):

| Period | 30/30 | 40/40 | Δ |
|---|---:|---:|---:|
| Historical OOS | −$2,232 / 1,080 | −$2,666 / 1,000 | −$433 / −80 |
| In-sample | +$2,295 / 613 | **−$550** / 600 | **−$2,846** / −13 |
| Forward | $0 / 0 | $0 / 0 | $0 / 0 |
| Combined | **+$62 / 1,693** | **−$3,216 / 1,600** | **−$3,278 / −93** |

**40/40 is materially worse, not noise.** The in-sample collapse (+$2,295 → −$550) is the dominant driver.

---

## Year-by-year

| Year | Trades (40/40) | WR | P&L (40/40) | P&L (30/30) | Δ |
|---|---:|---:|---:|---:|---:|
| 2019 | 126 | 46.0% | −$202.00 | −$455.50 | +$253.50 |
| 2020 | 168 | 50.6% | +$137.00 | +$386.00 | −$249.00 |
| 2021 | 162 | 49.4% | −$482.00 | −$671.50 | +$189.50 |
| 2022 | 240 | 47.5% | −$1,006.00 | −$392.00 | **−$614.00** |
| 2023 | 297 | 47.5% | −$1,032.50 | −$1,039.50 | +$7.00 |
| 2024 | 186 | 45.7% | −$1,257.50 | +$107.00 | **−$1,364.50** |
| 2025 | 235 | 53.6% | +$1,317.50 | +$982.50 | +$335.00 |
| 2026 | 186 | 48.4% | −$690.50 | +$1,145.50 | **−$1,836.00** |

The biggest damage hits **2024 and 2026** — exactly the years where 30/30 was doing well. Modest improvements in 2019/2021 (hostile years) are not enough.

---

## Exit-reason breakdown

|  | target n / total P&L / per-trade | stop n / total P&L / per-trade | force_close n |
|---|---|---|---:|
| 30/30 | 768 / +$46,080 / +$60 | 766 / −$45,960 / −$60 | 159 |
| 40/40 | 666 / +$53,280 / +$80 | 704 / −$56,320 / −$80 | 230 |

Two key shifts:
1. **Target rate worsened in proportion:** 30/30 target/stop ratio 768/766 ≈ 50.07% target; 40/40 only 666/704 = 48.6%. Wider targets are harder to reach.
2. **Force-closes jumped +45%** (159 → 230). Wider levels delay resolution past the 11:30 force-close; more positions end at the day's close-price-as-proxy.

---

## Regime breakdown — central mechanism

| Regime | 30/30 P&L | 40/40 P&L | Δ |
|---|---:|---:|---:|
| directional (fade) | −$1,477.50 | **−$6,994.50** | **−$5,517** |
| flat (breakout-routed) | +$1,540.00 | **+$3,938.50** | **+$2,399** |

The wider stop/target hurt fade direction badly and helped breakout direction. The amounts don't cancel — net −$3,118 deterioration from the regime split.

**Mechanism interpretation:**
- **Fade in trending markets** (the failure case where fade is wrong): wider stop = bigger losses when the trend continues. Wider target = often not reached before the trend reasserts.
- **Fade in mean-reverting markets** (the success case): wider target often missed because the natural reversion magnitude is closer to 30 points; price bounces 30, reverses, and the wider target never prints.
- **Breakout in flat/sideways regimes**: wider stop tolerates whipsaw; wider target captures occasional momentum. Net favorable.

**30 points appears to reflect MNQ's natural reversion magnitude at the strategy's 9:46–11:30 timeframe.** Widening doesn't add free safety — it amplifies losses in the regime where the strategy is structurally wrong and misses the natural mean-reversion target in the regime where it's right.

---

## Trade-level overlap

| Bucket | n |
|---|---:|
| Shared exactly (session + entry_time + entry_price) | 1,248 |
| Dropped (in 30/30, not 40/40) | 445 |
| Added (in 40/40, not 30/30) | 352 |
| Shared with different exit reason | 190 |

Outcome transitions on shared trades (30/30 → 40/40):

| Transition | n | Net Δ P&L |
|---|---:|---:|
| target → stop (won at 30, kept running to lose at 40) | 63 | **−$8,820** |
| stop → target (lost at 30, reversed back to win at 40) | 53 | +$7,420 |
| target → force_close (won at 30, couldn't reach 40 by 11:30) | 38 | −$1,398.50 |
| stop → force_close | 36 | +$1,630.00 |
| **Net on outcome-flipped shared trades** | **190** | **−$1,168.50** |

The remaining −$2,110 of the −$3,278 deterioration comes from the 352-added vs 445-dropped trade swap.

---

## Visualizations

10 chart PNGs at `results/charts/40_40_examples/` covering trades with `cluster_size >= 4` (stronger-confluence signals than the minimum-3 threshold). Coverage: all 8 years 2019–2026, both regimes (5/5 directional/flat), 3 exit types (6 target / 3 stop / 1 force_close), both sides (5/5 buy/sell), cluster sizes 4–10. Generated via `src/visualize_trade_4040.py` (sibling of `visualize_trade.py`; original unchanged).

---

## Verdict

40/40 is materially worse, not noise. Combined drops by $3,278 / 49 trades; in-sample collapses by $2,846. The wider risk reveals what 30/30 was hiding: the strategy's edge in mean-reverting markets is *bounded by the natural reversion magnitude* (~30 pts on MNQ at this timeframe), so widening the target leaves money on the table; in trending markets the wider stop just amplifies losses. The flat (breakout-routed) cell gets meaningfully better, suggesting that breakout strategies *do* benefit from wider risk — but the hybrid relies on the fade cell as the larger contributor, and that cell collapses.

Implication: future R:R variants should be tested asymmetrically (e.g. 30-stop / 50-target) rather than symmetric widening. The locked 30/30 R:R is closer to optimal than 40/40 for this strategy on this data.
