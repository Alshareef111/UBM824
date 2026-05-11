# Priors-Only Variant — Research Log

**Date:** 2026-05-11
**Scope:** Test whether excluding today's own ORB from today's cluster pool meaningfully changes results vs the locked fade-only baseline.
**Locked baseline preserved.** sha256 `d24f128a…f4c6` before and after.

---

## Rationale

The locked baseline (spec D-002) includes today's ORB high and low in the same pool that prior sessions' ORBs build, giving up to 402 levels for cluster detection. The hypothesis being tested: does today's ORB act as load-bearing structure or as noise that creates marginal trade signals which are not real?

If today's ORB is a useful signal-anchor, removing it should hurt P&L. If it acts as noise, removing it should reduce trade count and improve P&L.

---

## Variant construction

`src/simulator_priors_only.py` — sibling of `simulator.py` (the locked fade-only baseline). Minimum diff: 3 lines added, 2 deleted.

```diff
-from paths import BARS_PARQUET, ORB_TABLE_PARQUET, TRADES_PARQUET, ensure_dirs
+from paths import BARS_PARQUET, ORB_TABLE_PARQUET, ARCHIVE_DIR, ensure_dirs
+
+TRADES_PARQUET = ARCHIVE_DIR / "trades_priors_only_20260511.parquet"
@@
-        levels.append(orb_row["orb_high"])
-        levels.append(orb_row["orb_low"])
```

The deque-write at end of session loop (which propagates today's ORB into *future* sessions' pools) is **unchanged**. Only today's own ORB is excluded from today's clustering. All other parameters identical to `simulator.py`.

Output: `results/archive/trades_priors_only_20260511.parquet`.

---

## Headline result

```
1,491 trades  /  49.0% WR  /  -$2,373.00 total
exits: target=652  stop=696  force_close=143
```

vs extended fade-only baseline (1,693 / 48.7% / −$3,378) and locked-frozen baseline (526 / 52.9% / +$1,975 — different scope):

| Period | Baseline-extended | Priors-only | Δ |
|---|---:|---:|---:|
| Historical OOS | −$5,534 / 1,080 | −$4,640 / 941 | +$894 / −139 |
| In-sample | +$2,157 / 613 | +$2,267 / 550 | +$110 / −63 |
| Forward | $0 / 0 | $0 / 0 | $0 / 0 |
| Combined (7y) | **−$3,378 / 1,693** | **−$2,373 / 1,491** | **+$1,004 / −202** |

---

## Year-by-year

| Year | Trades | WR | P&L (priors-only) | P&L (baseline-extended) | Δ |
|---|---:|---:|---:|---:|---:|
| 2019 | 143 | 44.1% | −$1,442.00 | −$1,731.50 | +$289.50 |
| 2020 | 153 | 43.8% | −$1,058.00 | −$972.00 | −$86.00 |
| 2021 | 146 | 52.1% | +$25.50 | +$85.50 | −$60.00 |
| 2022 | 219 | 44.7% | −$1,418.00 | −$1,898.00 | **+$480.00** |
| 2023 | 274 | 47.4% | −$747.50 | −$958.50 | +$211.00 |
| 2024 | 167 | 51.5% | +$436.00 | +$558.00 | −$122.00 |
| 2025 | 213 | 50.7% | +$270.50 | −$81.50 | **+$352.00** |
| 2026 | 176 | 58.0% | +$1,560.50 | +$1,620.50 | −$60.00 |

Improvement is concentrated in three historically weaker years: 2019 (+$290), 2022 (+$480), 2025 (+$352). Slight degradation in friendlier years (2020, 2021, 2026) is small.

---

## Trade-level overlap

| Bucket | n |
|---|---:|
| Trades shared exactly (session + entry_time + entry_price) | 1,393 |
| Trades dropped (in baseline, not priors-only) | 300 |
| Trades added (in priors-only, not baseline) | 98 |
| Same session+minute, different entry price (cluster boundary shifted) | 45 |
| Net trade-count change | **−202** |

So removing today's ORB:
- Eliminated **300 trades** that the baseline took because today's ORB was load-bearing for some cluster's formation (either as a member level or as a boundary). Aggregate P&L of these dropped trades was net negative (driving most of the +$1,004 improvement).
- Created **98 new trades** because today's ORB had previously pulled a cluster off price-relevant areas; without it, prior-session levels formed different clusters at different limit prices.
- Shifted entry on **45 trades** (same session+minute, different limit) because today's ORB was the boundary level of an existing cluster.

---

## Verdict

**Modest improvement, same qualitative result.** Combined P&L improves by +$1,004 / +30% reduction in loss magnitude, but the strategy still loses $2,373 over 7 years. The mechanism is clear and consistent with the hypothesis: today's ORB participates in ~300 baseline-only trades whose aggregate is slightly negative, making it act more as a noise-introducer than a structural anchor for the fade.

Notably, improvement is concentrated in historically weak years (2019, 2022, 2025) where reducing trade frequency simply means fewer chances to lose. In favorable years (2024, 2026) priors-only marginally underperforms — consistent with "today's ORB removes signals that were net-helpful in friendly regimes and net-harmful in hostile regimes."

Forward OOS: identical to baseline (0 trades). Today's-ORB exclusion can't fix the structural lockout — clusters form below price regardless of today's ORB inclusion.

**Not a meaningful strategy improvement.** Reduces loss but doesn't flip the strategy from net-loser to net-winner. Worth keeping the file around for future composition with other variants, but no standalone case for adopting it.
