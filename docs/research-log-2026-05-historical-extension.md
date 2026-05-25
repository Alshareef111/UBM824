# Historical + Forward Extension — Research Log

**Date:** 2026-05-11
**Scope:** Extended the dataset from 2024-04-01–2026-05-01 (locked baseline window) to 2019-05-06–2026-05-10, then re-ran the locked baseline simulator and the hybrid simulator over the full 7 years to test out-of-sample (OOS) generalization.
**Locked baseline preserved throughout:** `data/processed/trades.parquet` sha256 `d24f128a…f4c6` before AND after this investigation.

---

## Infrastructure: multi-CSV concatenation

Prior `data_prep.py` consumed exactly one raw Databento CSV via the hardcoded `RAW_CSV` path constant. Extension required reading multiple CSVs as a single chronological stream while keeping the existing single-CSV behavior byte-identical.

**Changes (committed as one infra chunk):**

`src/paths.py`:
```diff
-RAW_CSV = RAW_DIR / "glbx-mdp3-20240401-20260501.ohlcv-1m.csv"
+RAW_CSV_FILES = sorted(RAW_DIR.glob("glbx-mdp3-*.ohlcv-1m.csv"))
+RAW_CSV = RAW_CSV_FILES[0] if RAW_CSV_FILES else RAW_DIR / "glbx-mdp3-20240401-20260501.ohlcv-1m.csv"
```

`src/data_prep.py` `main()`: replaced the single `load_and_filter_csv(RAW_CSV)` call with a loop over `RAW_CSV_FILES`, concatenating each batch's outright bars, deduplicating on `(ts_event, symbol)`, and resorting by `ts_event` ascending. Per-file row counts are now logged for visibility.

**Regression test:** with only the baseline CSV present, the new pipeline produced `mnq_adjusted_1m.parquet` byte-identical (via `pandas.testing.assert_frame_equal(check_exact=True)`) to the locked backup; same for `rolls.parquet`. Multi-file behavior is therefore additive — no change to the single-CSV path.

Future extensions: drop a new `glbx-mdp3-<start>-<end>.ohlcv-1m.csv` into `data/raw/` and re-run `python3 src/data_prep.py`.

---

## Databento extensions

Two batch jobs run today (2026-05-11):

| Job ID | Window | Schema | Symbols | Cost | Size | sha256 (CSV) |
|---|---|---|---|---:|---:|---|
| `GLBX-20260511-GT47USGRME` | 2019-05-06 → 2024-03-31 | `ohlcv-1m` | `["MNQ.FUT"]` | $9.03 | 281 MB | `226ed061…1512` |
| `GLBX-20260511-PNRUBG8AXT` | 2026-05-02 → 2026-05-10 | `ohlcv-1m` | `["MNQ.FUT"]` | $0.04 | 1.3 MB | `4cf78a54…e29b` |

Both: `stype_in=parent`, `stype_out=instrument_id`, `pretty_px=true`, `pretty_ts=true`, `map_symbols=true`, `split_symbols=false` (identical specs to the baseline job `GLBX-20260502-E83DUNFPLV`). Both manifests preserved at `data/raw/extensions/historical_20260511/` and `data/raw/extensions/forward_20260511/`. CSVs are at `data/raw/glbx-mdp3-*.ohlcv-1m.csv`.

CSV-hash verification (manifest vs computed) passed in both cases before any move.

---

## Extended dataset (post data_prep)

```
2,467,393 1-min bars
1,814 session days  (1,805 with complete ORB; 9 excluded as partial/missing)
2019-05-06 → 2026-05-11
29 front-month contracts used
28 rolls
```

Cumulative Panama back-adjustment now anchors MNQM4 at +1,912.50 pts (unchanged — Panama math invariant under prepending data) and MNQM9 (new earliest contract) at +3,089.00 pts.

---

## Acknowledged boundary effects

1. **120-bar overnight fill at 2024-04-01.** The historical CSV ends 2024-03-31 23:59 UTC; baseline starts 2024-04-01 00:00 UTC. Bars in NY 18:00–19:59 on Sun 2024-03-31 (= UTC 22:00–23:59) belong to session_date 2024-04-01 by the +6h overnight rule. The combined dataset thus has 120 extra bars on session 2024-04-01 vs the locked backup. **Benign with respect to downstream pipeline:** these overnight bars fall outside the 9:30–9:45 ORB window AND the 9:46–11:30 trading window, so `orb.py`, `simulator.py`, and `simulator_hybrid.py` never consult them. In-sample ORB table is byte-identical to the backup.

2. **ATR-uses-all-hours behavior.** `simulator_hybrid.compute_session_features` (lines 242–263) aggregates `sess_high/sess_low/sess_close` over **all** bars per `session_date`, not just intra-trading-window. Acknowledged as a documented property: the boundary effect on ATR-10 lasts ~4 weeks (until 2024-04-01's TR ages out of the 10-day rolling window), which sits well within the larger 200-session cluster-lookback boundary.

3. **Cluster lookback boundary at ~2025-01-23.** The 200-session deque was empty at 2024-04-01 under the locked baseline; under the extended dataset it's pre-warmed with 200 historical sessions. Both pipelines produce identical deque contents from ~2025-01-23 onward (200 in-sample sessions for both). Phase 4 cross-validation confirmed: trades with `entry_time >= 2025-02-01` are byte-identical to the locked baseline for the fade-only simulator and byte-identical to the prior hybrid backup for the hybrid simulator.

---

## Extended fade-only locked baseline result (`results/archive/trades_baseline_extended_20260511.parquet`)

```
1,693 trades  /  48.7% WR  /  -$3,377.50 total
exits: target=736  stop=798  force_close=159
```

### By period

| Period | Trades | WR | P&L |
|---|---:|---:|---:|
| Historical OOS [2019-05-06, 2024-03-31] | 1,080 | 46.3% | **−$5,534.50** |
| In-sample [2024-04-01, 2026-05-01] | 613 | 52.9% | +$2,157.00 |
| Forward [2026-05-04, 2026-05-08] | 0 | n/a | $0.00 |
| Combined (7-year) | **1,693** | **48.7%** | **−$3,377.50** |

In-sample +$2,157 vs locked-frozen +$1,975 = +$182 from 87 extra trades produced by the pre-warmed deque in the first 10 in-sample months.

### Yearly P&L (fade-only)

| Year | Trades | WR | P&L |
|---|---:|---:|---:|
| 2019 (May–Dec) | 157 | 43.3% | −$1,731.50 |
| 2020 | 184 | 45.1% | −$972.00 |
| 2021 | 171 | 52.0% | +$85.50 |
| 2022 | 245 | 43.7% | −$1,898.00 |
| 2023 | 316 | 47.5% | −$958.50 |
| 2024 Q1 | 7 | 42.9% | −$60.00 |
| 2024 (Apr+) | 185 | 50.3% (Apr-Dec) | included in in-sample |
| 2025 | full year | 53.1% | included in in-sample |
| 2026 (Jan–May 1) | full | 57.7% | included in in-sample |

**Loses money in 5 of 6 historical years; 2021 is breakeven-noise.**

---

## Extended hybrid 30/30 result (`results/archive/trades_hybrid.parquet` — overwritten in-place)

```
1,693 trades  /  49.9% WR  /  +$62.50 total
exits: target=768  stop=766  force_close=159
routing: directional=1,072 (-$1,477.50)  flat=619 (+$1,540.00)  UNLABELED=2 ($0)
```

### By period

| Period | Trades | WR | P&L |
|---|---:|---:|---:|
| Historical OOS | 1,080 | 48.0% | **−$2,232.50** |
| In-sample | 613 | 53.2% | +$2,295.00 |
| Forward | 0 | n/a | $0.00 |
| Combined (7-year) | **1,693** | **49.9%** | **+$62.50** |

In-sample +$2,295 sits between the locked baseline (+$1,975) and the prior hybrid (+$2,723 from the in-sample-only research log). Most of the gap-vs-prior-hybrid is concentrated in the first 10 in-sample months where the pre-warmed deque produces 87 extra trades worth −$428 on aggregate.

### Yearly P&L (hybrid 30/30)

| Year | Trades | WR | P&L |
|---|---:|---:|---:|
| 2019 | 157 | 45.9% | −$455.50 |
| 2020 | 184 | 51.6% | +$386.00 |
| 2021 | 171 | 47.4% | −$671.50 |
| 2022 | 245 | 48.2% | −$392.00 |
| 2023 | 316 | 47.2% | −$1,039.50 |
| 2024 | 192 | 49.6% (combined Q1+rest) | +$107.00 |
| 2025 | 239 | 53.1% | +$982.50 |
| 2026 | 189 | 56.1% | +$1,145.50 |

---

## Regime sign-flip — the dominant finding

The hybrid regime classifier (`|expected_normalized_distance| <= 0.09` → flat → reverse to breakout) was fit on the in-sample window and produces **opposite signs across periods**:

| Regime cell | Historical OOS | In-sample | Sign flip |
|---|---:|---:|:---:|
| directional (fade) | **−$3,884** | +$2,406 | YES |
| flat (breakout-routed) | +$1,651 | −$111 | YES |

Both cells flip sign between periods. The +$3,884 historical bleed in the directional cell is the largest single contributor to the OOS deterioration. The "edge" of the regime classifier in-sample (+$2,406 fade contribution) does not survive: the same classification rule applied to OOS data produces the opposite outcome.

This is consistent with the hybrid having been tuned to a specific market regime (the in-sample window) rather than identifying a structural feature. Same indicator, opposite payoff: not generalizable.

---

## Forward OOS (5 sessions, 2026-05-04 to 2026-05-08)

**Both simulators produced 0 trades** over the 5-session forward window.

Diagnosis: MNQ has rallied above the entire 200-session level pool. Pool stats just before 2026-05-04:
- Range: 23,374 – 27,795 (Panama-adjusted)
- p99: 27,355
- Today's ORB_close: 27,856 (above pool max)

All clusters that form (32/session) fall entirely below current price (BUY-side setups under fade direction). Limits sit 1,614 – 2,917 pts below the 9:46 NY open. Trading-window range each day: 100–300 pts. No limit was ever touched. The strategy correctly stood aside under a strong post-pool-high rally; the design is structurally locked out of this regime.

**The forward extension produced no new signals to validate against.**

---

## Verdict

**Neither strategy survives OOS testing.** Hybrid 30/30 combined +$62 over 7 years (1,693 trades) is statistically indistinguishable from breakeven. The fade-only locked baseline is materially worse at combined −$3,378. The +$1,975 / +$2,723 in-sample numbers that anchored the original research were not edge — they were a regime-specific favorable period (Apr 2024 – May 2026). The regime classifier sign-flips between periods, the fade cell loses every historical year, and the forward week produced no signals.

**Implications:**
- Future variants should be evaluated on the full 7-year combined view, not in-sample.
- The 2024-Q2 onwards period appears favorable to fade strategies on MNQ; the multi-year sample shows that's not a stable property.
- Multi-CSV concat infrastructure is in place — future extensions are drop-in operations.

---

## Artifacts produced

- `data/processed/mnq_adjusted_1m.parquet` — 2.47M bars, 7-year span (regenerable; not committed due to size)
- `data/processed/rolls.parquet` — 28 rolls
- `data/processed/orb_table.parquet` — 1,805 sessions with ORB
- `data/processed/orb_excluded.parquet` — 9 sessions excluded (holidays, partial windows, 2026-05-11)
- `results/archive/trades_baseline_extended_20260511.parquet` — fade-only 7-year output
- `results/archive/trades_hybrid.parquet` — hybrid 30/30 7-year output (overwritten from prior version)
- `results/archive/trades_breakout.parquet` — breakout 7-year output (overwritten)
- 7 `.pre-extend-20260511` safety-net backups kept locally (not committed; ignored)
