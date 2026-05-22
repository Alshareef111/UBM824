# ADX/DI Classifier — Port Proposal

**Status:** proposal only — no code written.
**Source:** `/Users/hashim/Desktop/MNQ-Strategy/src/indicators/{base,adx,di}.py` and `simulator_v2_4040.py`.
**Target:** `src/vbt_backtest.py` in this project, gating entries in `generate_signals`.

---

## 1. Indicator specs (verified from source)

### ADX
- **Period (N):** 15 — `AdxClassifier(adx_lk, n=15, threshold=30)` in `run_4040_v2_full.py:199`.
- **Threshold:** 30 — same line.
- **Smoothing:** Wilder, approximated as `pandas.Series.ewm(alpha=1/N, adjust=False).mean()` (`adx.py:43-54`). Two passes: first to smooth TR/+DM/-DM, second to smooth DX into ADX.
- **Warm-up:** first ~N bars are NaN. QC defaults NaN → `FADE`.

### ±DI spread
- **Period (N):** 15 — `DiClassifier(di_lk, n=15, threshold=8)`.
- **Threshold:** 8 (points of |+DI − -DI|).
- **Same Wilder smoothing as ADX**, no second pass (no DX/ADX step).
- **Metric:** `|+DI(N) − -DI(N)|` — magnitude of directional imbalance, sign-agnostic.

### Timeframe
- Both indicators are computed on the **same 1-minute bars** the strategy trades. No higher-timeframe aggregation. Both functions accept a single `bars` DataFrame with `high`/`low`/`close` columns.

### Sampling moment (the critical detail)
- The QC simulator calls the classifier **at the entry bar T** (where the first cluster touch fires), **but the classifier reads the indicator value as of bar T-1** — enforced by `precompute_lookup` which calls `adx_series.shift(1)` (`adx.py:67`).
- **No look-ahead** is the locked invariant: the classifier "may only consult bars strictly before the touch bar T" (`base.py:12-14`).
- Indicators are precomputed for the entire series once, then looked up per touch — O(1) at trade time.

---

## 2. QC classifier decision logic

### Per-indicator (`AdxClassifier`, `DiClassifier`)
```
val = lookup[touch_bar["ts_utc"]]
if isnan(val):          return FADE   # warm-up
if val >= threshold:    return TREND
else:                   return FADE
```

### Composite (`UnanimousClassifier` — what QC actually deploys)
```
labels = [ADX_label, DI_label]
if all(l == FADE):  return FADE   # both indicators say weak regime
if all(l == TREND): return TREND  # both indicators say strong regime
else:               return SKIP   # mixed → uncertain → skip
```

### Where in the trade flow
From `simulator_v2_4040.py` (lines 180-199):
```python
for bar in bar_records:
    if open_pos is None:
        candidate = find_first_fill(setups, bar)         # bar that touches a cluster boundary
        if candidate is not None:
            label = classifier(candidate.cluster, bar, bars_today)
            if label == Label.SKIP:
                candidate.triggered = True
                continue                                  # consume cluster, no trade
            if label == Label.FADE:
                side = candidate.fade_side                # mean-revert (QC's baseline)
            else:                                         # TREND
                side = "buy" if candidate.fade_side == "sell" else "sell"  # invert
```
Classifier is **only consulted at the touch bar**, on the cluster that's about to fill. Per-bar gating, not per-session.

---

## 3. Label semantics — QC vs us

The labels mean *opposite things* in the two strategies because the baselines are opposite.

| Label | QC (mean-reversion baseline) | Our breakout strategy |
|-------|------------------------------|------------------------|
| `FADE` | Low ADX/DI → quiet regime → **trade the mean-reversion (baseline)**. | Low ADX/DI → breakout likely to fail → **skip or take the counter (fade) trade** |
| `TREND` | High ADX/DI → strong regime → **invert** to a trend-following trade. | High ADX/DI → breakout likely to follow through → **keep the breakout (baseline)** |
| `SKIP` | Mixed → no trade. | Mixed → no trade. |

The classifier itself doesn't change — it still emits FADE/TREND/SKIP based on ADX/DI. **What changes is the gate that maps label → action.**

### Proposed mapping for our breakout
```
QC label  →  our action
FADE      →  SKIP             (or INVERT — see open question #1)
TREND     →  TAKE_BREAKOUT    (the baseline direction)
SKIP      →  SKIP
```

This is the cleanest reading: the indicators are telling us "is there a directional regime right now?" and we want to be in our breakout *only when* there is one. When there isn't, we don't trade. The QC labels carry over unchanged; only the action-mapping flips.

---

## 4. Open questions (decide before coding)

### Q1 — INVERT or SKIP-only on `FADE`?
- **SKIP-only (recommended start):** `FADE → SKIP, TREND → TAKE, SKIP → SKIP`. Cleanest, smallest behavior change, easiest to reason about. Drops trades where ADX/DI is weak.
- **With INVERT:** `FADE → take counter-trade (fade the breakout), TREND → TAKE, SKIP → SKIP`. Matches QC's three-state semantics exactly. Doubles potential setups but introduces a *different* strategy (fading breakouts vs taking them) when ADX is low.
- **Risk of INVERT:** in our breakout context, going against a breakout in low-ADX conditions could just chop us out the other way. The QC INVERT logic was tuned for a mean-reversion baseline — its counter-trade is a breakout, which has natural stop levels at the cluster. Our counter-trade would be a fade with no obvious stop reference.
- **My recommendation:** start with SKIP-only. Add INVERT as a separate variant only after the SKIP version validates.

### Q2 — sample at OR close (9:45) or at entry bar T-1?
- **Per-entry (QC port, recommended):** look up ADX/DI at bar T-1 where T is the entry bar. Indicators stay fresh — if a regime shift happens at 10:30, the 10:31 entry sees the new value. This is what QC does.
- **At OR close (9:45):** one read per session, applied to all entries that day. Deterministic per-session, easier to inspect ("today is a TREND day; took the trades"). But less adaptive.
- **My recommendation:** per-entry (Q2's per-entry option = direct QC port). Lower risk of deviating from a validated method.

### Q3 — keep QC thresholds (30, 8) or re-tune?
- QC tuned `(N=15, ADX_thr=30, DI_thr=8)` on the **back-adjusted** MNQ continuous series for a **mean-reversion** strategy with **30/30 brackets**. Our context is different on all three counts (unadjusted, breakout, 40/40).
- The unanimous AND-gate makes thresholds somewhat robust — both gates moving together is the signal, and the absolute threshold matters less than the relative response.
- **My recommendation:** port at QC defaults first, then run a small grid (`ADX_thr ∈ {20, 25, 30, 35}`, `DI_thr ∈ {5, 8, 12, 16}`) to confirm or re-tune on our data + breakout context. Treat the QC thresholds as priors, not laws.

### Q4 — any data-feed quirks?
Checked our `bars` schema (`ts_utc`, `session_date`, `contract`, `open/high/low/close`, `volume`, indexed by `ts_ny`):
- `ts_utc` column is present and tz-aware UTC. The QC `precompute_lookup` keys by `ts_utc` — direct port works.
- `high/low/close` columns are present. `compute_adx_series` only needs these three.
- Our bars are 1-min, contiguous through the session-break (no per-session reset). QC's Wilder EWM is across the entire continuous series, which matches.
- **One thing to verify on first port:** QC builds the lookup once over the *entire* bars history including overnight bars (18:00-09:29 NY). If we want the indicator to "reset" each RTH session (so the 9:45 ADX reflects only that morning's structure), we'd need to chunk by session. **My read of the QC code is they don't chunk — they smooth across the full continuous series.** This is the simplest port. If a session-local ADX is wanted, that's a strategic change, not a port detail.

---

## 5. Ready-to-code checklist (when questions are answered)

Once Q1-Q4 are decided, implementing the port is small.

- [ ] **Add `src/indicators/` package** (mirror QC layout for clarity)
  - [ ] `src/indicators/__init__.py`
  - [ ] `src/indicators/base.py` — `Label` enum (TAKE / SKIP / INVERT) — note: rename from QC's FADE/TREND to action-oriented names to avoid the semantic-flip confusion documented in §3
  - [ ] `src/indicators/adx.py` — `compute_adx_series(bars, n)` and `AdxClassifier(lookup, n, threshold)` (verbatim port from QC; only change: import paths)
  - [ ] `src/indicators/di.py` — same for DI spread
  - [ ] `src/indicators/composite.py` — `UnanimousClassifier` (verbatim port)
- [ ] **Wire into `src/vbt_backtest.py`**
  - [ ] Add `use_adx_di: bool = False` kwarg to `generate_signals` (default off — preserves all existing validation)
  - [ ] When on, pre-compute ADX(15) and DI(15) lookups once at signal-generation time
  - [ ] At each candidate entry bar, look up label
  - [ ] Per the chosen mapping (Q1), gate the long/short entry signal to True / False / inverted
  - [ ] If `INVERT` is allowed (Q1 = yes), flip the long↔short for that bar
- [ ] **Add CLI command** `run_adx_di` (or extend `run` with a flag) that runs the validated pipeline at defaults but with the gate ON; prints the same summary block as `run`, plus a label-distribution breakdown (how many entries SKIP / TAKE / INVERT)
- [ ] **Validate on candidate C (lb=200, gap=7, ms=2, entry_location=center)**
  - [ ] Run gated vs un-gated, compare net / PF / max_dd
  - [ ] Check that SKIP-rate is meaningful but not catastrophic (should land between 20-50% of original entries if thresholds are calibrated)
  - [ ] Yearly breakdown comparison — does the gate kill the bad 2024 drawdown that the risk audit flagged?
- [ ] **Threshold mini-sweep** (Q3): 4×4 = 16 combos on candidate C, ADX_thr × DI_thr; save to CSV
- [ ] **Walk-forward gated-C** against the same train/test split used in `walkforward_candidates` — does the gate generalize?

---

## Summary

Port is mechanically small (~150 lines of indicator code + ~30 lines of signal-gating glue). The hard decisions are semantic (Q1, Q2) and statistical (Q3), not engineering. Recommend the following defaults absent other input:

- **Q1:** SKIP-only mapping (FADE→SKIP, TREND→TAKE, SKIP→SKIP)
- **Q2:** per-entry lookup at bar T-1 (direct QC port)
- **Q3:** start at QC defaults (15/30, 15/8); mini-sweep after baseline validates

Open these questions to the user before any code is written.
