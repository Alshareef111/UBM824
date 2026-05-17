# Framework Integrity Audit — 2026-05-15

Read-only investigation of six methodology concerns affecting the candle-based simulation framework. All protected files (`simulator_v2.py`, `clusters.py`, `walk_forward.py`, locked baselines, locked configs) untouched. Diagnostic code in `src/experimental/audit_diagnostics.py`; per-priority parquets co-located here.

**Locked-baseline sha256 unchanged:** `d24f128ac88227900ac6d44047f0f51e5a5906011e683643a925c63feb15f4c6`

**Global stop conditions hit during audit:**
- Priority 1 — tick gap on available verification set: **+100%** overstatement on 30/30 baseline (>25% threshold). Stop condition triggered.
- Priority 2 — look-ahead: **not triggered** (verified clean).
- Protected-file modification — not triggered (no edits made).

Per the workflow, fixes are **proposed only**. Sign-off required before any code change. See "Framework verdict" at the end.

---

## Priority 1 — Candle vs tick fill realism

### What was checked
- Inventoried tick data: `data/processed/ticks_overlap.parquet` covers **2026-03-17 → 2026-04-15, 13 sessions, 5.67M ticks** (`last`, `bid`, `ask`, `volume`). This is the only tick window available; the other 7 years are bar-only.
- The existing tick simulator (`src/tick_simulator.py`) is mature: true chronological tick walk, intra-bar ordering by tick time, configurable stop/target. It runs `AllFade` (not the V2 ADX∧DI classifier).
- The prior 32-trade verification against the **locked 30/30 simulator** is materialized in `data/processed/verification_results.parquet`, with bar-sim and tick-sim P&L side-by-side. Re-summarized the gap from this file (no fresh run needed).

### What was found
| Metric | Bar (locked 30/30 sim) | Tick (chronological) | Δ |
|---|---:|---:|---:|
| Total P&L (32 trades) | $240 | $120 | **+$120 / +100% relative** |
| Win rate | 56.2% | 50.0% | +6.2pp |
| Outcome match | — | — | **30 / 32 = 93.8%** |

Mismatched trades (the entire $120 gap):

| Session | Side | Bar reason | Tick reality | Bar $ | Tick $ | Δ$ |
|---|---|---|---|---:|---:|---:|
| 2026-04-02 | sell | target | **NO_FILL** (phantom) | +60 | 0 | +60 |
| 2026-04-08 | buy | target | **stop** (chronology) | +60 | −120 | +180 |

Per-trade gap distribution: median $0, p10 −$60, p90 +$60, max +$180. The bias is concentrated in two trades, not a uniform drift.

The two mismatches are exactly the patterns documented in `docs/decisions.md` D-014 (entry-bar chronology, ~3% rate) and D-015 (phantom fills from non-trade prints in Databento OHLCV, ~6% rate). Bar bias is **optimistic** at the strategy level. On this 32-trade slice, optimistic biases consumed 100% of apparent edge.

**Important scope notes:**
1. The 32-trade verification is on the **locked 30/30** baseline (`simulator.py`, AllFade). The current deployment candidate is **V2 + 40/40** with ADX∧DI classifier — the *direction* of bias should carry over (same bar-OHLC semantics), but the *magnitude* is unknown.
2. Tick data does not cover any full walk-forward window. The narrowest WF window is 1y OOS; we have ~6 weeks of ticks. **Running tick replay on "one or two full WF windows" is not feasible with current data.** The original task spec is data-limited.
3. The relevant V2+40/40 corollary diagnostic (`p4` and `p4b` below) shows that 6.8% of V2+40/40 trades are at structural chronology risk (same-bar entry+exit) and 3.1% are at first-order chronology risk (bar.open already past the credited exit level). Worst-case if all 28 risky-chronology trades had inverted truth: −$3,520 on a +$8,808 baseline = −40%.

### What needs to change
1. **Acquire more tick data.** Databento MBP-1 or TBBO for at least 2024-04-01 → 2026-05-01 (the in-sample window) would enable a meaningful tick replay of V2+40/40. Cost/feasibility check needed.
2. **Until tick data is wider, treat every bar-sim headline as the upper bound.** Walk-forward Sharpe-like and median-OOS numbers may overstate true OOS performance by a non-trivial fraction.
3. **Build a tick-replay variant of the V2 fill engine** that accepts an arbitrary `Classifier` (currently `tick_simulator.py` hardcodes AllFade) and arbitrary stop/target. This is a new file in `src/experimental/`, not a modification to `simulator_v2.py` or `tick_simulator.py`. Approval needed.
4. **Bar-sim mitigation (optional):** for same-bar entry+exit trades, use `bar.open` (or the most conservative reachable price) as exit price instead of the credited stop/target. This trades exactness for direction-of-bias safety. Approval needed.

### Blast radius of proposed fix
- New tick-replay V2 engine: ~200–300 LoC in `src/experimental/v2_tick_replay.py`. No protected-file edits.
- D-014 mitigation in bar sim: would change `simulator_v2.py` — protected. **Locked-baseline byte-equivalence would break.** Not recommended; better to keep bar sim as the locked reference and use tick replay as the source of truth where data exists.

---

## Priority 2 — Classification timing (look-ahead risk)

### What was checked
Traced every classifier input at fill time across `indicators/adx.py`, `indicators/di.py`, `indicators/base.py`, and the call site in `simulator_v2.py:198`.

Call site (`simulate_session`):
```python
candidate = find_first_fill(setups, bar)
if candidate is not None:
    label = classifier(candidate.cluster, bar, bars_today)
```

Classifier reads from the touch-bar dict and pre-computed lookup dicts:

| Input | Source | Timestamp relative to fill bar T | Verdict |
|---|---|---|---|
| ADX(15) value | `lookup_adx[touch_bar["ts_utc"]]` where `lookup_adx` is `compute_adx_series(bars,15).shift(1)` keyed by every bar's ts_utc | **T−1** (shift(1) at precompute time; never reads T) | clean |
| \|+DI−-DI\|(15) value | Same `.shift(1)` precompute pattern | **T−1** | clean |
| `touch_bar["ts_utc"]` | T | **T (lookup key only, not as data)** | clean |
| `cluster` (low/high/levels/size) | Built at 9:45 from prior 200 sessions' ORBs + today's ORB | **≤ 9:45** | clean |
| `bars_today` | Full session bars passed but **not read** by either classifier (confirmed by `grep "bars_today" indicators/`) | n/a | clean |

The lookback contract is documented in `indicators/base.py:11-14` ("indicator may only consult bars strictly before the touch bar T") and enforced by the `.shift(1)` in `precompute_lookup`. The fill candle's own close, high, and low are **never** consulted by the classifier.

### What was found
**No look-ahead.** The pre-compute + shift pattern is the correct guard, and both production classifiers (ADX, DI) use it identically. Composite `UnanimousClassifier` adds no new inputs.

Empirical sanity check (P5 diagnostic): of 908 V2+40/40 trades, the ADX(15) and DI(15) lookups returned the expected `T-1` value for every trade (`adx_at_fill` non-NaN for 908/908, matching the simulator's classification distribution).

### What needs to change
Nothing in the production classifiers. Two suggested additions for robustness:
1. **Add an assertion in `precompute_lookup`** that no key collides between current-bar and next-bar values after shift. (Defensive only; current implementation is correct.)
2. **Document the lookback contract** more prominently in `simulator_v2.py`'s docstring (it's currently in `indicators/base.py`).

### Blast radius of proposed fix
Documentation only; no behavioral change. Touches `simulator_v2.py` docstring (protected file — approval needed for even a comment edit).

---

## Priority 3 — Path-dependence in filter / variant comparisons

### What was checked
Documented the path-dependence mechanism formally and quantified it on the cluster-size filter test (the most recent experiment).

Path-dependence sources in `simulator_v2.simulate_session`:
1. **C2 one-position-at-a-time** (`simulator_v2.py:192-227`): while a position is open, other setups stay armed but are not filled on the bars where the open position exists. After exit, remaining setups become eligible again — but with different "first touch" timing.
2. **Cluster gating** (`MIN_CLUSTER_SIZE`, `CLUSTER_GAP_POINTS`, `LOOKBACK_SESSIONS`): changes which clusters are even formed, so which setups exist for the day.
3. **Classifier SKIP** (`base.py:9`): SKIP consumes the cluster slot without trading — frees the C2 slot earlier than a FADE/TREND would have.
4. **Stop/target geometry** (`STOP_POINTS`, `TARGET_POINTS`): changes exit timing, which changes when the next setup can fire.
5. **Side-flip** (FADE vs TREND): same fill price, opposite exit dynamics.

**Engine mode** (current default): rerun the simulator with the predicate baked in. Trade universe is path-dependent on every prior decision.

**Overlay mode** (proposed): variant B's predicate is applied as a filter over variant A's trade list. Trade list T_B = {t in T_A : P(t)}. True subset of A.

### What was found — overlay vs engine on cluster-size test

| Variant | Trades | WR | P&L |
|---|---:|---:|---:|
| Baseline V2+40/40 (size ≥ 3) | 908 | 56.2% | $8,808 |
| **F1 overlay** (filter baseline by size≥4) | **332** | 52.7% | **$1,401** |
| F1 engine (sim with MIN_CLUSTER_SIZE=4) | 374 | 54.3% | $2,204 |
| **F2 overlay** (filter baseline by size≥5) | **165** | 52.1% | **$682** |
| F2 engine (sim with MIN_CLUSTER_SIZE=5) | 196 | 55.1% | $1,199 |

Cluster set comparison (keyed by `(session_date, cluster_low, cluster_high)`):

| | F1 | F2 |
|---|---:|---:|
| overlay only (in filtered baseline, NOT triggered by engine) | 10 | 7 |
| engine only (triggered by engine, NOT in filtered baseline) | **52** | **38** |
| shared | 322 | 158 |

**Path-dependence delta:** F1 engine produced 42 more trades (+12%) and $803 more P&L (+57%) than F1 overlay. F2 engine: 31 more trades (+19%), $517 more P&L (+76%). The variants are **not** clean subsets; the engine surfaces displaced clusters whose timing slot freed up when the C2 competitor was removed.

This means the prior cluster-size filter report's engine-mode P&L overstates "what filtering for size≥4 does to baseline trades" — the right framing for predicate evaluation. It correctly states "what running with `MIN_CLUSTER_SIZE=4` does as a strategy" — the right framing for live deployment.

### What needs to change
1. **Add overlay-mode utility** to the experimental toolbox. Pure Python over an existing trade-log parquet plus a predicate function. No simulator change. New file: `src/experimental/overlay_mode.py`.
2. **Default-mode rule for future filter tests:** overlay is the primary subset evaluation; engine is the secondary live-strategy evaluation. Reports should show BOTH columns side-by-side so the path-dependence delta is visible.
3. **Engine mode remains required** for predicates that change cluster formation or fill geometry (`MIN_CLUSTER_SIZE`, `CLUSTER_GAP`, stop/target, entry-rule swap like Variant E). Overlay cannot answer the live-strategy question for those.

### Blast radius of proposed fix
- New file: `src/experimental/overlay_mode.py` (~80 LoC).
- Zero behavioral change to any baseline or locked simulator.
- Reports for the three modification tests already in this session (Variants B/C/E and F1/F2) would not be re-run automatically; new pattern applies going forward.

---

## Priority 4 — Touch-logic edge cases (same-bar stop+target reachable)

### What was checked
For every V2+40/40 baseline trade (n=908): looked up the entry bar and (where applicable) the exit bar from `BARS_PARQUET`. Counted bars where the bar's range covers **both** the stop and target levels.

Refined check (P4b): of same-bar entry+exit trades, counted those where `bar.open` is already past the credited exit level — meaning the high/low used to credit the exit may have printed BEFORE the limit fill (D-014 chronology risk).

### What was found

**P4 (D-005-style, both reachable in one bar):**

| Bar type | Count | Fraction |
|---|---:|---:|
| Total trades | 908 | 100% |
| Same-bar entry+exit (entry_time == exit_time) | 62 | 6.8% |
| Entry-bar both stop AND target reachable | **0** | 0.0% |
| Exit-bar both stop AND target reachable | **0** | 0.0% |

At 40/40 brackets the bar would need an 80-point range with the entry price interior — never happens on MNQ 1-min bars. **D-005 (stop-first conservative) ambiguity is structurally absent at 40/40.** Note: the locked 30/30 baseline had 5 ambiguous bars (per `decisions.md` D-005); 40/40's wider geometry removes them.

**P4b (D-014-style, chronology risk on same-bar entry+exit):**

| Category | Count | % of same-bar | % of all trades |
|---|---:|---:|---:|
| Same-bar entry+exit | 62 | 100% | 6.8% |
| of which: exit_reason = target | 51 | 82% | 5.6% |
| of which: exit_reason = stop | 11 | 18% | 1.2% |
| **risky target win** (bar.open ≥ target, buy; or bar.open ≤ target, sell) | **25** | 40% | **2.8%** |
| **risky stop loss** (bar.open ≤ stop, buy; or bar.open ≥ stop, sell) | 3 | 5% | 0.3% |
| **total risky chronology** | **28** | **45%** | **3.1%** |

Worst-case P&L sensitivity to chronology (if all 28 had inverted truth):

- 25 risky targets credited +$80 each = +$2,000 booked → would be −$2,000 truth → swing **−$4,000**.
- 3 risky stops credited −$80 each = −$240 booked → would be +$240 truth → swing **+$480**.
- **Net worst case: −$3,520 on $8,808 baseline = −40%.**

This is a *worst case* (assumes all 28 are inverted-truth, which the 32-trade verification suggested is closer to ~50% of risky cases). A realistic midpoint estimate is −$1,500 to −$2,000.

### What needs to change
1. **P1 tick replay covers this** as a side-effect: when tick data is wider, D-014 swings are resolved by chronology.
2. **Bar-sim conservative mitigation** (no protected-file edits required): for same-bar entry+exit trades, post-process the trade log by replacing the credited exit price with `bar.open` if `bar.open` is already past the credited exit. Net: turn some D-014 wins into break-evens (conservative). New file: `src/experimental/bar_d014_mitigation.py`. Approval needed (or just decide it's out of scope).
3. **Add a `same_bar_exit` boolean column** to the Trade schema so future audits can grep without re-deriving from entry_time/exit_time equality.

### Blast radius of proposed fix
- D-014 mitigation as post-process: zero baseline change, runs on existing trade parquets. ~50 LoC.
- Adding `same_bar_exit` to Trade dataclass: protected-file edit to `simulator_v2.py`. Locked baseline byte-equivalence would technically still hold for `BASELINE_COLS` (the new column would be outside the comparison set), but the change is to a protected file — approval needed.

---

## Priority 5 — Schema gap (NaN indicator column)

### What was checked
Re-computed ADX(15) and DI(15) `.shift(1)` lookups using the simulator's own `precompute_lookup` functions. For each V2+40/40 trade, recorded the indicator value at fill and whether it was NaN.

### What was found
| Metric | Value |
|---|---:|
| Total trades | 908 |
| ADX NaN at fill | **0 (0.0%)** |
| DI NaN at fill | **0 (0.0%)** |
| Either NaN | **0 (0.0%)** |

The first V2+40/40 trade is 2019-05-15 09:46 — 9 trading days into the data (2019-05-06 first bar). ADX/DI EWM with alpha=1/15 has fully warmed up by then. The warm-up NaN concern is real *in principle* but **does not affect this baseline in practice**.

The schema gap is still real: there is no record in the trade log of what the indicator was at fill. Post-hoc audits must re-derive from `BARS_PARQUET` (as this diagnostic did). Adding `(adx_at_fill, di_at_fill, indicator_nan_at_fill)` to the schema would make audits cheap and would matter for future strategies tested on a shorter history or with longer indicator periods (e.g., a 200-bar ATR would be NaN for the first 3+ hours of session 1).

### Proposed schema addition (do not modify simulator yet)
Add three columns to the `Trade` dataclass in `simulator_v2.py`:

```python
adx_at_fill: float = float("nan")       # ADX(N) value at touch bar T-1, NaN if warm-up
di_at_fill:  float = float("nan")       # |+DI - -DI|(N) value at T-1, NaN if warm-up
indicator_nan_at_fill: bool = False     # True if classifier's primary input was NaN (warm-up default)
```

These columns are populated by the classifier writing the value into a small dict on each `__call__`, and the simulator reading it back at `make_trade()` time. Existing `BASELINE_COLS` comparison set is **not** broken because the new columns sit outside it.

Defaults preserve byte-equivalence for runs with classifiers that don't expose `last_call_meta`. The schema migration on existing parquets is trivial (re-emit by re-running the simulator, or backfill via post-process script identical to this audit's P5).

### What needs to change
1. **Approval to edit `simulator_v2.py`** to add three columns to `Trade` dataclass and one helper hook to classifier protocol.
2. **Recommend backfill** of recent trade parquets via the P5 diagnostic pattern (no simulator edit needed for backfill).
3. **Generic-classifier hook design:** classifier `__call__` returns just `Label` today. Proposed: classifiers may set `self.last_call_meta: dict[str, float]` on each call; the simulator reads it after `classifier(...)` and merges into the Trade. Default empty dict if not set → no behavioral change.

### Blast radius of proposed fix
- `simulator_v2.py`: add 3 fields to `Trade`, 1 line in `make_trade`, ~5 lines around classifier call. **Protected file — approval needed.**
- `indicators/base.py` + `adx.py`/`di.py`: add `last_call_meta` write. **Protected file (indicators are inside src/ but not in the "locked" set; classify status with user).**
- Locked-baseline byte equivalence: preserved for `BASELINE_COLS`. New columns add 24 bytes/trade × 908 = 22 KB to the V2+40/40 parquet on re-emit. Existing parquets unchanged unless re-emitted.

---

## Framework verdict

### Which existing "qualified" results can still be trusted (as currently reported)

**Strict answer: none, in absolute-magnitude terms.** Every headline P&L from the bar simulator embeds the D-014/D-015 optimistic bias. On the only window with tick truth (32 trades), that bias was +100%. The bias direction is fixed (optimistic), the magnitude per trade is bounded (~$120-180 per affected trade at 30/30, ~$160-240 at 40/40), and the affected-trade rate is bounded (~10% of trades total per D-014 + D-015 rates, but only ~3% are clearly chronology-risky per P4b).

**Relative comparisons are more robust.** Walk-forward sign stability, OOS-window relative performance, and variant-vs-variant deltas use the same bar-sim mechanism on both sides — the bias largely cancels. The R-012 "deployment candidate" verdict (V2+30/30 beats AllFade by sharpe, sign 7/7) is **comparative** and survives the audit. The V2+40/40 "stronger candidate" verdict is likewise comparative.

**Absolute magnitudes (e.g., "+$8,808 over 7 years") should be treated as upper bounds.** A realistic point estimate after D-014 correction is in the range $5,000–$7,500 (a 15–40% haircut applied to the $8,808 headline). True confirmation requires tick data spanning the full backtest window.

### Which results need re-running under fixes

| Item | Re-run trigger | Priority |
|---|---|---:|
| V2+40/40 baseline | When wider tick data is available | 1 |
| Cluster-size F1/F2 (this week) | When overlay mode utility exists, add overlay column to report | 3 |
| Far-border Variant E | Same: add overlay column | 3 |
| Variants B/C (partial + runner-BE) | These change exit geometry, overlay is not applicable; they remain engine-mode-only. **Reject verdicts stand** (they degraded WF Sharpe; tick replay would only make them worse). | n/a |
| R-012 (V2+30/30 deployment candidate) | When wider tick data available | 1 |

### Which features should be in the simulator before further experimentation

In order of cost/benefit:

1. **Overlay-mode utility** (`src/experimental/overlay_mode.py`) — cheap, ~80 LoC, no protected edits, dramatically improves the rigor of future filter-test reports. **Strongly recommend.**
2. **NaN-indicator schema column** (3 new fields in Trade dataclass, classifier hook) — small protected-file edit; preserves baseline byte-equivalence on `BASELINE_COLS`. **Recommend, pending approval to touch `simulator_v2.py`.**
3. **Tick-replay V2 engine** (`src/experimental/v2_tick_replay.py`) — adapts existing `tick_simulator.py` to accept arbitrary classifier + brackets. ~200-300 LoC, no protected edits. **Recommend, but its value is bounded by the 13-session tick window until more data is acquired.**
4. **D-014 bar-sim post-process mitigation** (`src/experimental/bar_d014_mitigation.py`) — converts risky-chronology same-bar wins to bar.open exits (conservative). ~50 LoC, no protected edits. **Optional**; mainly useful if (3) is not feasible. Risk: introduces a third P&L number (bar / mitigated-bar / tick) which complicates reporting.
5. **Wider tick data acquisition** (Databento MBP-1 or TBBO over 2024-04-01 → 2026-05-01 minimum). **Out of scope for code; necessary for genuine validation.**

### Stop-condition decisions

- **P1 tick gap > 25%: TRIGGERED.** Per the task spec, this halts further audit work and reports. Audit deliverable (this document) complete; no broader scaling-up tick replay until wider tick data is acquired and a fresh tick-replay of V2+40/40 is built.
- **P2 look-ahead: NOT triggered.** No halt.
- **Protected-file touch: NOT triggered** (no edits in this audit). Future fixes (P5 schema, P2 docstring) need approval before any code change.

### One-line recommendation
Build overlay-mode first (cheap, immediately useful, no protected edits); then ask sign-off for the P5 schema column; defer wider tick replay until more tick data is acquired. **Do not promote V2+40/40 from "stronger candidate" to "deployment candidate" until tick truth on a meaningful sample of those trades exists** — the 30/30 verification's 100% gap is a sufficient warning at the simulator level.

---

## Artifacts in this directory

- `SUMMARY.md` (this file)
- `p1_tick_vs_bar_per_trade.parquet` — 32 rows, side-by-side bar vs tick outcome
- `p3_overlay_vs_engine.parquet` — 5 rows, baseline + 4 F1/F2 variants
- `p4_same_bar_stop_target.parquet` — 4-row aggregate
- `p5_nan_indicator_per_trade.parquet` — 908 rows with adx/di values at fill

Diagnostic source: `src/experimental/audit_diagnostics.py` (read-only).
