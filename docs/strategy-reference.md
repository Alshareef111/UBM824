# V2 + 40/40 Strategy Reference

> **Status:** Skeleton only — sections to be filled progressively. Last updated: 2026-05-15.
> **Purpose:** Single comprehensive reference for the V2 + 40/40 strategy, pulling together concept, mechanics, performance, caveats, and history. Different from CLAUDE.md (session primer), strategy-spec.md (formal narrow spec), and research-logs (chronological per-test).

## 1. Status & deployment readiness

Executive summary. Read this section first to know the project's current state; then drill into §2–§10 for full detail. Each subsection here points at the section(s) that own the canonical version of every claim made.

### 1.1 Current candidate — V2 + 40/40

**Working candidate:** V2 + 40/40 — the regime-classified (ADX(15,30) ∧ DI(15,8) unanimous AND-gate) strategy with 40-point symmetric brackets, locked-baseline geometry otherwise (§3 setup, §4 entry, §5 management).

**Headline numbers** (7-year walk-forward 2019-05-15 → 2026-04-15; source `results/40_40_v2_full/20260514_125349/`):

| Metric | Value |
|---|---:|
| Trades | **908** (510 W / 398 L / 0 flat) |
| Win rate | **56.17%** |
| Total P&L (gross) | **+$8,808** |
| Walk-forward Sharpe-like | **6.86** |
| Sign stability across 7 OOS windows | **7/7 positive** |
| Calendar-year sign stability | **8/8 positive** |
| 4-gate deployment qualification | **all four passed** |
| Max drawdown (recovered in 380 days) | −$1,228 |
| Profit factor | 1.309 |

Full performance detail → §6. Caveats on these figures (bar-vs-tick biases, gross-vs-cost-adjusted) → §8.1, §8.2.

**Why "candidate" not "canonized."** This document advances V2 + 40/40 ahead of the previously canonized V2 + 30/30. `CLAUDE.md` and `docs/decisions.md:D-008` as of 2026-05-16 both still list 30/30 as the deployment-strict choice. The 40/40 fork outperforms 30/30 on every metric except a slightly wider max DD that recovers faster (380 vs 596 days; §6.8). **Formal canonization of 40/40 is pending the operational items in §1.3.**

### 1.2 What is verified

Through R-012 and the post-R-012 work documented in this file:

- ✓ **The V2 classifier is genuine signal, not noise.** WF Sharpe-like 6.86 vs the 50-seed RandomBinary null p95 of 1.06 — **6.5× margin**. 0 of 50 random seeds achieved 7/7 sign stability; V2 + 40/40 is 7/7. DI discrimination check: DI's actual scores at 100th percentile of 30 same-bias (73% TREND) random labelings on all three metrics (§6.2, §8.3).
- ✓ **The bracket-classifier interaction is causal, not coincidental.** V2: 30/30 → 40/40 = **+$3,005 (+52%)**. AllFade: 30/30 → 40/40 = **−$7,875 (−233%)**. Wider brackets only help when an upstream regime gate has filtered the wrong-regime touches (§6.8).
- ✓ **All four mechanics-side modifications rejected.** Variants B, C, E (run) and D (cancelled) all failed to improve on V2 + 40/40 on the deployment-critical WF Sharpe-like. The strategy appears at a local optimum for tested levers (§7.6).
- ✓ **Bracket widening eliminated Bug A entirely at 40/40.** 0 of 336 stop-outs flagged (the 80-pt symmetric span needed for Bug A is outside typical 1-min MNQ bar range). The same geometric argument applies to target exits (§5.2, §8.1, today's diagnostic).
- ✓ **Force-close is P&L-neutral.** 130/908 trades (14.32%), mean +$2.52, 68 pos / 62 neg — not a hidden drain (§5.4, §8.4 RESOLVED).
- ✓ **2026 Jan–April underperformance concern softened by bracket widening.** At 40/40 V2 outperforms AllFade by +$704 ($592 vs −$112); at 30/30 the gap was −$1,421. The bracket flip resolves the headline R-012 deployment concern at the candidate bracket width (§2.4, §8.5 PARTIALLY RESOLVED).
- ✓ **Locked baseline reproducibility maintained.** `data/processed/trades.parquet` sha256 `d24f128a…f4c6` unchanged across all work in this document and all upstream R-### research (§10.2).

### 1.3 What is pending

**Deployment blockers and high-priority work** (full backlog in §9.6):

| Priority | Item | Section |
|---|---|---|
| **BLOCKER** | Forward paper-test (≥ 6 months) — R-012's specified gate with explicit pass/fail criteria | §9.2 |
| **HIGH** | Cost-adjusted re-run (commission + slippage). Commission-only floor +$8,036. Slippage gap unquantified. | §9.2 |
| **HIGH** | F1 / F2 cluster-size filter — first selection-side lever; interrupted by API 529 on 2026-05-14 | §9.1 |
| **HIGH** | Full-period tick verification — current verified slice is only 32 trades at 30/30 | §9.2 |

**Investigative leads worth pursuing** (no deployment blocker, but cheap to evaluate):

- MEDIUM — Intraday cluster-touch density as regime indicator (new lead from 10-trade audit 2026-05-15) (§9.3)
- MEDIUM — Asymmetric R:R variants (the only untested bracket axis at V2) (§9.4)
- MEDIUM — Lookback sensitivity (OQ-2) (§9.4)
- MEDIUM — Target-side Bug B mirror diagnostic (closes the bar-vs-tick picture begun on 2026-05-16) (§9.1)
- MEDIUM — Disjoint-OOS walk-forward replication (confirms the §8.8 overlap isn't an artifact) (§9.5)

**Deferred** (after MNQ deployment-readiness sign-off): cross-instrument validation (§9.5).

**Total backlog: 16 items** — 1 BLOCKER · 3 HIGH · 5 MEDIUM · 6 LOW · 1 AFTER MNQ (§9.6 priority table).

### 1.4 Authority map — which document says what

Different docs serve different purposes; the canonical answer to any specific question lives in the doc most narrowly focused on it.

| Document | Canonical for |
|---|---|
| `CLAUDE.md` | Session-start primer for Claude Code agents. Current operational state. Last canonized strategy. |
| `docs/strategy-spec.md` | Formal narrow specification of the locked baseline (V2 + 30/30). Implementation reference. |
| **`docs/strategy-reference.md`** (this file) | **Comprehensive cross-cutting reference.** Synthesis of concept, mechanics, performance, caveats, and open questions for the working candidate (V2 + 40/40). Read sections 2–10 for detail. |
| `docs/decisions.md` | Chronological D-### decision rationale and OQ-### open questions. "Why this choice" canonical source (§10.3, §10.4). |
| `docs/results-log.md` | R-### research entries (R-001 through R-012). Chronological per-investigation summary. |
| `docs/research-log-2026-05-*.md` | Per-investigation detailed working logs. Hypothesis, methodology, raw findings. |
| `results/40_40_v2_full/20260514_125349/` | **V2 + 40/40 canonical run output** (trades.parquet sha256 `1ccf859e…feb`, summary.md / .json, equity_curve.png). Source for all §6 numbers. |
| `results/archive/strategy_report_20260512/` | Earlier V2 + 40/40 report with 4-strategy comparison table (basis for §6.8). |
| `results/archive/v2_4040_modifications_20260514/` | Variant B and C source artifacts (basis for §7.1, §7.2). |
| `results/archive/v2_4040_far_border_20260514/` | Variant E source artifact (basis for §7.4). |
| `results/archive/v2_4040_stop_loss_diagnostic_20260516/` | Bug A / B / phantom-suspect incidence at V2 + 40/40 (basis for §5.2, §8.1, today's report). |

**Resolving conflicts between docs.** Where this reference document conflicts with `CLAUDE.md` or `docs/decisions.md` (because V2 + 40/40 is not yet canonized), the more recent date wins for the *working candidate's current state* — this document supersedes. For the *locked baseline's* canonical state, `docs/strategy-spec.md` and `data/processed/trades.parquet` (sha256-pinned) are authoritative. `CLAUDE.md` and `docs/decisions.md` should be updated when V2 + 40/40 is formally canonized post-forward-test.

### 1.5 Document maintenance

- **Last updated:** 2026-05-16 (document creation date — all 10 sections written 2026-05-16 in this Claude Code session).
- **Length:** ~1,600+ lines after all 10 sections expanded (exact: see `wc -l docs/strategy-reference.md`).
- **Maintained by:** human-led, AI-assisted via Claude Code. Each section written section-by-section with source-grounded extraction from code, parquets, and research logs; every numerical claim was cross-checked against the canonical source artifact.
- **Update protocol:** when material new findings emerge (F1/F2 results, forward-test results, cost-adjusted re-run, tick-verification completion), update the relevant § AND the authority map (§1.4) AND this status section (§1.1–§1.3). Avoid silent updates — every material change deserves a date stamp here and should propagate cross-references throughout the doc.
- **Surviving `[UNVERIFIED]` tags:** **zero** (verified across all 10 sections).

## 2. Strategy concept

This section is the strategy's "why" — the theoretical and empirical foundations for trading at ORB-cluster zones with a regime gate. Implementation lives in §3 (setup), §4 (entry), §5 (management). For empirical results see §6; for caveats see §8.

### 2.1 Core hypothesis

The original (pre-V2) hypothesis was **pure mean-reversion**: prices tend to revert when they reach zones where historical opening-range levels cluster. A "cluster" is operationally defined as three or more ORB highs/lows from the prior 200 sessions where every adjacent pair (after sorting) sits within three points of the next — the chain rule, not a fixed-diameter rule (see `docs/decisions.md:D-002` and §3.3 for the exact definition). The locked baseline reading is `MIN_CLUSTER_SIZE = 3`, `CLUSTER_GAP = 3.0`, `LOOKBACK = 200` (`docs/decisions.md:D-002, D-007`).

**Empirical reality on 7 years (2019–2026) showed the always-fade version is unprofitable out-of-sample.** R-006 (the historical-extension test) produced **−$3,378 across 1,693 trades**, with the original 2-year in-sample +$1,975 (R-001 locked baseline, 2024-04-01 → 2026-05-01) revealed as regime-specific rather than generalizable edge (`docs/results-log.md:R-001, R-006`; `docs/research-log-2026-05-historical-extension.md`). The historical OOS slice alone bled **−$5,534** across 1,080 trades, losing money in 5 of 6 historical years.

**The refined hypothesis (V2)** is that the right action at a cluster touch depends on current market regime:

- In ranging conditions → fade (mean-revert against the price action).
- In trending conditions → invert direction and trade with the move.
- When regime indicators disagree → skip the cluster entirely.

Empirically (R-012, on the 30/30 locked geometry): the regime gate filtered out **744 of 1,693 cluster touches (~44%)**, and the surviving **949 trades** produced **+$5,803** over 7 years at 55.2% WR, with **7/7 OOS walk-forward windows positive** and **8/8 calendar years positive** (`docs/research-log-2026-05-regime-v2-investigation.md`; `docs/results-log.md:R-012`).

The deployment candidate this document covers is the **40/40 fork** of that classifier on the same locked geometry: **908 trades, 56.2% WR, +$8,808** over the same 7-year window, WF Sharpe-like 6.86, sign 7/7, 8/8 positive years (`docs/research-log-2026-05-14-modifications.md`; §4.7 for empirical splits).

The honest framing: **this is conditional mean-reversion gated by a regime classifier, not pure mean-reversion.** Without the V2 classifier, the cluster geometry alone is unprofitable over 7 years. The V2 classifier *is* the strategy.

### 2.2 Why ORB clusters as support/resistance

The 9:30–9:45 NY opening range is one of the most-watched 15-minute windows in intraday futures trading. Many participants set reference levels relative to this window: stops outside it, scale entries against it, mean-reversion targets at its edges.

ORB highs and lows are anchor prices that accumulate order flow on subsequent days. When multiple prior sessions' ORB extremes cluster at the same price area, that zone has been "tested" repeatedly and accumulates layered orders — stops, limits, scale-ins. When current price returns to such a zone, those resting orders are triggered. The resulting reaction can go two ways:

- **Mean-reversion** — opposing-side liquidity absorbs the move; price reverses.
- **Breakout** — stops cascade through the level; momentum continues.

The strategy bets on mean-reversion by default. V2's classifier identifies conditions where breakout is more likely and inverts direction (§2.3).

**Honest framing on parameter choices.** The specific cluster construction (`MIN_SIZE = 3`, `CLUSTER_GAP = 3.0`) and the 200-session lookback were chosen empirically and have not been independently validated through sensitivity analysis. `docs/decisions.md:D-007` records 200 sessions as the user-specified value, "roughly 10 months of trading days," status `locked, sensitivity test pending`. Open questions:

- **OQ-2** (`docs/decisions.md`): Lookback sensitivity at 100 and 500 sessions — untested.
- **OQ-3** (`docs/decisions.md`): Cluster minimum size at 4 or 5 — queued as F1 / F2 tests (`docs/research-log-2026-05-14-modifications.md:45-46`), pending execution after the 2026-05-14 API-529 interruption. See §7 and §9.

### 2.3 The V2 contribution — FADE / TREND / SKIP gating

**Before V2:** every cluster touch became a fade entry. The strategy lost money out-of-sample across 7 years (R-006).

**V2 (R-012):** at each cluster touch, evaluate two indicators on the last N bars before the touch bar:

- **ADX(N=15, threshold=30)** — trend-strength magnitude (standard Wilder ADX).
- **±DI(N=15, threshold=8)** — directional spread magnitude (`|+DI − −DI|`, *not* signed direction).

Both indicators must agree:

| ADX | DI spread | label | action |
|---|---|---|---|
| < 30 | < 8 | FADE | trade locked-baseline (mean-reversion) direction |
| ≥ 30 | ≥ 8 | TREND | invert direction (breakout entry, same fill price) |
| disagreement | — | SKIP | no trade — cluster is consumed without entering |

See §4.3–§4.5 for the exact computations and AND-gate code.

The classifier doesn't add edge by predicting direction perfectly — it adds edge by **filtering out the wrong-regime cluster touches that would lose money under always-fade**. R-012's discrimination check confirmed this: DI(15,8)'s actual scores landed at the **100th percentile** of 30 same-bias (73% TREND) random-labeling seeds on Sharpe-like, median OOS, and total P&L — DI is genuinely selecting clusters, not just imposing a directional bias (`docs/research-log-2026-05-regime-v2-investigation.md:158-170`).

The window-trend regression on the unanimous composite shows **+$33/window with r²=0.12 and t=+0.83** — no statistical decay across the 7 walk-forward windows, despite DI solo showing a significant negative slope (−$230/window, t=−2.59) when measured alone. The unanimous filter fixes DI's solo decay (`docs/research-log-2026-05-regime-v2-investigation.md:141-156`).

**Warm-up note.** ADX and DI are precomputed once over the entire multi-year 1-min bar stream, so the ~15-bar warm-up only affects the very start of the dataset (mid-May 2019). Within each trading session the indicators are already fully warmed and the regime gate is active from the first cluster touch. (See §4.3, §4.4 for `precompute_lookup`'s `.shift(1)` no-look-ahead enforcement.)

**Cross-reference §7.** Four post-V2 modifications — Variants B, C, E plus the cancelled D — were tested on the V2 + 40/40 baseline. All failed to improve on it; the three with real results all regressed WF Sharpe-like even when modestly improving headline Sharpe or max DD (`docs/research-log-2026-05-14-modifications.md`). "V2 classifier on locked geometry with 40-point brackets" appears to be at or near a local optimum for the levers tested.

### 2.4 Edge sources and known limits

**What the strategy bets on:**

- **Order-book asymmetry** around well-tested historical levels — the cluster premise (§2.2).
- **Short-term regime persistence** — the 15-bar ADX/DI lookback assumes regime persists at least that long.
- **Intraday tendencies** expressing themselves in the 9:46–11:30 window before midday consolidation (`docs/decisions.md:D-011`).
- **The C2 one-position-at-a-time rule** preventing overexposure and naturally enforcing selectivity (`docs/decisions.md:D-004`).
- **Force-close at 11:30 bar OPEN** capping risk before afternoon noise (`docs/decisions.md:D-010`).

**Known limits (honest acknowledgment):**

**Original-baseline statistical thinness.** R-001's robustness check on the 2-year in-sample window: edge is **~1.3σ above breakeven, p ≈ 0.09** — cannot be distinguished from random noise at conventional thresholds (`docs/results-log.md:111`). The 7-year V2 numbers improve on this materially, but the deployment candidate has not been forward-tested.

**OOS generalization risk.** The original always-fade strategy didn't generalize OOS — the 7-year R-006 extension was the strongest evidence (5 of 6 historical years negative). V2 may face similar regime risk in market conditions outside the 2019–2026 window. R-012 acknowledges this explicitly: *"This is **good evidence** of signal, not **proof**. The composite was selected from the data; deployment confidence must come from forward validation."* (`docs/research-log-2026-05-regime-v2-investigation.md:225`).

**Force-close rate 14.3%.** 130 of 908 V2 + 40/40 trades exit at the 11:30 bar OPEN rather than at target or stop — about one in seven. The force-close P&L distribution has not been fully characterized; queued as a §9 follow-up.

**Bar simulator biases (R-001 tick-verification on a 32-trade slice, `docs/results-log.md:86-101`, `docs/decisions.md:D-005, D-014, D-015`):**

- **Bug A (D-005)** — same-bar stop+target ambiguity, **~1% of trades**, **pessimistic** (stop-first conservative).
- **Bug B (D-014)** — entry-bar chronology (target/stop credited even when the bar's extreme preceded the limit fill), **~3% of trades**, **optimistic**.
- **Phantom fills (D-015)** — Databento bar high includes non-trade prints (implied levels, RFQ quotes), so the simulator can fill a limit that never executed at that price, **~6% of trades**, **optimistic**.

Net on that 4-week slice (2026-03-17 → 2026-04-15, 32 trades on R-001 config): **bar +$240 vs tick $0 — bar simulator overstated edge by ~100% on that overlap**. Full-period tick verification has not been done; real edge may be materially lower than the +$8,808 headline suggests. See §8 for the full caveat list.

**No commissions or slippage applied to headline figures.** `docs/decisions.md:OQ-4` records the commission impact estimate at the time of the locked baseline: "~$447 over 526 trades reduces net to ~$1,475 over 2 years" — i.e. roughly **$0.85/trade in commission**. Slippage is acknowledged separately at `OQ-5` ("Limit fills assume zero slippage. Force-close uses bar open. Real fills may be worse, especially for force-close in fast markets.") but is **not quantified anywhere in project docs**. A documented commission-only adjustment would reduce expectancy from $9.70/trade to roughly **$8.85/trade**; the full cost-adjusted re-run including a slippage model is queued in §9.

**Tested only on MNQ futures.** Generalization to other instruments (ES, NQ, RTY, agricultural, currencies) is unknown and untested.

**2026 Jan–April: the apples-to-apples 40/40 comparison softens the concern.** At 30/30 brackets, V2 underperforms AllFade by **$1,421** ($199 vs $1,620; `docs/research-log-2026-05-regime-v2-investigation.md`). At 40/40 brackets — the deployment candidate — **V2 outperforms AllFade by $704** ($592 vs −$112; `results/archive/strategy_report_20260512/strategy_4040_test.md` calendar-year table). The widened bracket flips the sign of the recent-period gap. The 2026 sample is only 4 months; distinguishing genuine classifier decay from random variation requires more forward data.

The deployment readiness of this strategy depends on these limits being acceptable in light of intended position sizing and capital base. They are not deal-breakers, but they are real.

## 3. Setup mechanics

Setup happens **once per session at 9:45 NY**, immediately after the opening range closes. The session's ORB high, low, and close are added to a rolling 200-session level pool; the pool is grouped into clusters; each qualifying cluster becomes a candidate trade with a fixed limit price, fade-side direction, and trigger-side flag. The rest of the trading day (see §4) only fires entries against this fixed list — no new setups are created intraday.

### 3.1 Opening range (9:30–9:45 NY)

The ORB is computed offline by `src/orb.py` and stored in `data/processed/orb_table.parquet` (path constant `ORB_TABLE_PARQUET` at `src/paths.py:36`). It is loaded once at backtest start by the runner (`src/run_4040_v2_full.py:193`).

The window is defined on the bars' `ts_ny` (NY-local) timestamp using `ORB_START_HM = (9, 30)` and `ORB_END_HM = (9, 45)` (`src/orb.py:20-21`). `in_orb_window` (`src/orb.py:26-31`) is inclusive at the start and **strict at the end**, so the 9:45 bar is **excluded**:

```python
# src/orb.py:18-19
# 1-minute bar timestamped HH:MM represents the interval [HH:MM, HH:MM+1).
# 9:30-9:45 NY = 15 bars timestamped 9:30 ... 9:44 (last bar's close = 9:45:00).
```

The 15 bars in the window aggregate to three values per session (`src/orb.py:39-44`):

- **`orb_high`** = `max(high)` over the 15 bars
- **`orb_low`** = `min(low)` over the 15 bars
- **`orb_close`** = `close` of the **last** bar in the window — i.e., the 9:44 bar's close, which is the price at 9:45:00 NY exactly

This `orb_close` is the **reference price** used downstream to classify clusters as above / below / spanning (see §3.4).

**Session completeness.** Sessions missing more than one ORB bar are excluded (`MIN_BARS_REQUIRED = 14`, `EXPECTED_BARS = 15`; `src/orb.py:22-23, 50-55`). Excluded sessions get written to `data/processed/orb_excluded.parquet` with a `reason` of `no_bars_in_window` or `partial_window` and never participate in clustering or trading — they also never enter the historical level pool.

### 3.2 Historical level pool (200-session lookback)

The level pool is constructed online by the simulator (`src/simulator_v2.py:248-270`). It is a `deque(maxlen=LOOKBACK)` where `LOOKBACK = 200` (`src/simulator_v2.py:33`). Each entry is a `(orb_high, orb_low)` tuple — **two levels per session**, no other prices (no close, no prior-day extremes, no settlement levels).

The per-session loop:

```python
# src/simulator_v2.py:256-270
levels = []
for hist_high, hist_low in level_pool:
    levels.append(hist_high)
    levels.append(hist_low)
levels.append(orb_row["orb_high"])
levels.append(orb_row["orb_low"])

clusters_today = find_clusters(levels, max_gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE)
setups = classify_setups(clusters_today, float(orb_row["orb_close"]))

bars_today = bars_by_session[session_date]
trades = simulate_session(bars_today, setups, session_date, classifier)
all_trades.extend(trades)

level_pool.append((float(orb_row["orb_high"]), float(orb_row["orb_low"])))
```

Notes on the construction:

- **Today's ORB is included.** `orb_high` and `orb_low` for *this* session are appended to `levels` before clustering, so the cluster pool can include today's opening-range extremes.
- **Steady-state size.** Past day 200 the deque is full; each clustering pass sees `200 × 2 + 2 = 402` levels.
- **Warm-up.** Day 1 sees only 2 levels (today's ORB high+low) — below `MIN_CLUSTER_SIZE`, so no setups form. The pool grows session-by-session until it saturates.
- **Holiday / partial-session handling.** The iteration is over rows of `orb_table` (the *complete* sessions; partials and missing days were filtered out in §3.1). The deque rolls per ORB-complete session, **not** per calendar day. "200-session lookback" therefore means *the 200 most-recent sessions with a valid ORB* — weekends, holidays, and excluded partials are skipped without affecting the count.
- **Order of operations.** Today's `(orb_high, orb_low)` is appended to the deque **after** `simulate_session` returns. The pool used for clustering on day *n* contains entries from days [n−200, n−1] (in steady state), and today's ORB is added separately above.

### 3.3 Cluster construction

`find_clusters` (`src/clusters.py:20-43`) is a pure function — one greedy walk over the sorted level list:

```python
# src/clusters.py:28-43
sorted_levels = sorted(levels)
clusters: list[Cluster] = []
current: list[float] = [sorted_levels[0]]

for lvl in sorted_levels[1:]:
    if lvl - current[-1] <= max_gap:
        current.append(lvl)
    else:
        if len(current) >= min_size:
            clusters.append(_build(current))
        current = [lvl]

if len(current) >= min_size:
    clusters.append(_build(current))
```

Constants used by V2 + 40/40 are `CLUSTER_GAP = 3.0` and `MIN_CLUSTER_SIZE = 3` (`src/simulator_v2.py:34-35`).

**The gap rule applies to adjacent pairs, not total span.** A cluster grows as long as each consecutive sorted gap is `≤ max_gap`; total width is therefore bounded by `(size − 1) × max_gap` but is not directly checked. With `max_gap = 3.0`, a size-3 cluster has width ≤ 6pt, a size-5 cluster ≤ 12pt, etc. (See empirical confirmation below.)

The `Cluster` dataclass (`src/clusters.py:12-17`) is frozen with four fields:

```python
@dataclass(frozen=True)
class Cluster:
    low: float
    high: float
    levels: tuple
    size: int
```

where `low = sorted_chain[0]`, `high = sorted_chain[-1]`, `levels` is the tuple of the constituent sorted levels, `size = len(sorted_chain)` (`src/clusters.py:46-52`).

**Worked example.** Input `[100.0, 102.5, 105.0, 107.5, 120.0, 121.0]`:

| step | candidate | gap from prev | action |
|---|---|---|---|
| init | 100.0 | — | `current = [100.0]` |
| 1 | 102.5 | 2.5 | grow: `[100.0, 102.5]` |
| 2 | 105.0 | 2.5 | grow: `[…, 105.0]` |
| 3 | 107.5 | 2.5 | grow: `[…, 107.5]` |
| 4 | 120.0 | 12.5 | break — emit `Cluster(size=4, low=100.0, high=107.5)`; `current = [120.0]` |
| 5 | 121.0 | 1.0 | grow: `[120.0, 121.0]` |
| end | — | — | `len(current) = 2 < 3` → drop, no emit |

Result: one cluster of size 4 (low 100.0, high 107.5, span 7.5pt). Verified by `clusters.py`'s own test harness (`src/clusters.py:65-87`).

**Edge cases:**

- **Two chains exactly 3.0 apart MERGE.** Levels `[100, 101, 102, 105, 106, 107]` produce *one* cluster of size 6 (span 7pt), not two of size 3. The greedy walk sees each pairwise gap as ≤ 3 and never breaks. This is by design — the boundary is `<=`, not `<` (`src/clusters.py:33`; test #5 at `src/clusters.py:84-87`).
- **Duplicate level values.** Two sessions sharing an ORB extreme (e.g. both at 18000.00) appear twice in the pool and contribute two distinct entries to the chain — gap of 0 always grows. This is *not* deduplicated.

**Empirical cluster shape (from `results/40_40_v2_full/20260514_125349/trades.parquet`, 908 traded clusters):**

| cluster_size | count | share | mean width (pts) | max width (pts) |
|---:|---:|---:|---:|---:|
| 3  | 576 | 63.4% | 3.00 | 6.00 |
| 4  | 167 | 18.4% | 4.29 | 7.50 |
| 5  |  69 |  7.6% | 5.23 | 9.25 |
| 6  |  49 |  5.4% | 7.59 | 12.00 |
| 7  |  27 |  3.0% | 9.18 | 12.00 |
| 8  |  13 |  1.4% | 11.06 | 14.50 |
| 9  |   2 |  0.2% | 13.25 | 14.50 |
| 10 |   4 |  0.4% | 12.00 | 12.00 |
| 11 |   1 |  0.1% | 12.00 | 12.00 |
| **all** | **908** | 100% | **4.03** (median 3.50) | 14.50 |

Mean cluster size **3.74**; the size distribution is heavily right-skewed (≈63% are bare minimum size-3). Width invariant `width ≤ (size − 1) × 3` checked end-to-end against the parquet — **0 / 908 violations**.

(For a per-session sense of pool density, an informal 10-trade visual audit on 2026-05-15 observed roughly **20–32 clusters per session, mean ~26**; archives queued for commit under `results/archive/v2_4040_examples_*_20260515/`.)

**Forward cross-reference.** Cluster size is what the queued F1 / F2 filter tests modify — see §7 ("Cluster-size filter F1/F2 (pending)") and §9.

### 3.4 Cluster classification vs ORB close

After clustering, `classify_setups` (`src/simulator_v2.py:90-105`) walks the clusters and converts each into a `Setup` based on its position relative to the session's `orb_close`:

```python
# src/simulator_v2.py:94-104
for c in clusters_today:
    if c.low > reference_price:
        setups.append(Setup(
            fade_side="sell", cluster=c, limit_price=c.low, trigger_above=True,
        ))
    elif c.high < reference_price:
        setups.append(Setup(
            fade_side="buy", cluster=c, limit_price=c.high, trigger_above=False,
        ))
    # cluster spans reference -> skip (no setup created)
```

Three branches:

| condition | branch | `fade_side` | `limit_price` | `trigger_above` |
|---|---|---|---|---|
| `cluster.low > orb_close` | **Above** the close | `"sell"` | `cluster.low` | `True` |
| `cluster.high < orb_close` | **Below** the close | `"buy"` | `cluster.high` | `False` |
| `cluster.low ≤ orb_close ≤ cluster.high` | **Spans** the close | — | — | **SKIPPED at setup time, no candidate created** |

The `fade_side` is the **mean-reversion direction** the original (pre-V2) strategy would have traded — sell into resistance from below, buy into support from above. V2 may *flip* this at the moment of entry based on the classifier output; see §4.6.

**Spans-close clusters get no setup.** This is an unconditional setup-time skip — distinct from the runtime `Label.SKIP` (which consumes a touched cluster without trading; see §4.5). A spans-close cluster is removed from candidacy before the trading window even opens, so the simulator never inspects it again.

**Empirical position split (908 traded clusters):**

| cluster position | trades | share |
|---|---:|---:|
| Above `orb_close` (limit at `cluster.low`) | 444 | 48.9% |
| Below `orb_close` (limit at `cluster.high`) | 464 | 51.1% |
| Spans (no setup created) | — | — |

Verified empirically: `entry_price == cluster_low` for all 444 above-close trades and `entry_price == cluster_high` for all 464 below-close trades — **0 / 908 mismatches**.

The 10-trade visual audit on 2026-05-15 observed only one spans-close cluster across 10 sessions, suggesting these are rare in MNQ's typical opening-range geometry but the absolute frequency is not tracked in the trades parquet by design.

### 3.5 Limit-order placement

The limit price is fixed at 9:45 by the same `classify_setups` call quoted in §3.4 — it is the cluster's **near border**: the edge that price would touch *first* when approaching the cluster from the ORB close.

| cluster position | limit at | meaning |
|---|---|---|
| Above `orb_close` | `cluster.low` | the lower edge — touched as price rises into the cluster from below |
| Below `orb_close` | `cluster.high` | the upper edge — touched as price falls into the cluster from above |

The `trigger_above` boolean on `Setup` (`src/simulator_v2.py:60`) is derived from the same branch: `True` for above-close clusters (the entry fires when `bar.high ≥ limit_price`), `False` for below-close (fires when `bar.low ≤ limit_price`). See §4.1 for how `trigger_above` is consumed at fill time.

**The limit does not move during the session.** It is set at 9:45 and stays at the cluster's near border for the entire trading window. There is no trailing logic, no cluster re-fitting intraday, and no adjustment if price moves away or other clusters are touched first.

**Empirical verification.** Every one of the 908 trades in the parquet has its `entry_price` exactly equal to its cluster's near border per the position rule above — verified end-to-end with **0 / 908 violations** (consistent with the prior reference audit).

**Cross-reference.** The near-border rule is the *opposite* of the far-border entry tested in **Variant E** (rejected; see §7 and `src/experimental/simulator_v2_farborder.py`). Near-border entry is also why the same-bar stop-first conservative rule in §5 matters: the entry bar can simultaneously cross the limit, the stop, *and* potentially the target, and the precedence rule decides the outcome.

## 4. Entry & classifier

Once clusters and their near borders are fixed at the 9:45 ORB close (see §3), entry is a two-stage decision evaluated bar by bar. **Stage 1** (geometry) — when a bar's range crosses the near border of an eligible cluster, that touch is a candidate fill. **Stage 2** (regime) — at the same bar, the V2 classifier reads ADX and ±DI from the lookback window and emits `FADE` / `TREND` / `SKIP`, which decides whether to enter and in which direction. The fill price is fixed at the near border; only the trade *direction* depends on the classifier output.

### 4.1 Trigger logic — first touch of near border

Each `Setup` carries a `trigger_above: bool` fixed at session start (`src/simulator_v2.py:60`). It is `True` for clusters above the 9:45 close (limit at `cluster.low`) and `False` for clusters below (limit at `cluster.high`) — set in `classify_setups` (`src/simulator_v2.py:90-105`). A touch fires the first time a bar's range crosses the limit:

```python
# src/simulator_v2.py:114-117
if s.trigger_above and bar["high"] >= s.limit_price:
    candidates.append(s)
elif (not s.trigger_above) and bar["low"] <= s.limit_price:
    candidates.append(s)
```

If multiple eligible setups would fill on the same bar, the closest-to-bar-open limit wins (`src/simulator_v2.py:120`). The touched setup is marked `triggered = True` even when the classifier returns `SKIP` (`src/simulator_v2.py:201`), so a cluster is consumed by its first touch regardless of whether a trade is opened.

On the touch bar itself, `simulate_session` immediately calls `check_exit` against the same bar (`src/simulator_v2.py:215-220`), so a stop or target can fill on the entry bar. Same-bar tie-break is stop-first conservative — see §5 and `check_exit` at `src/simulator_v2.py:123-139`.

### 4.2 Trading window — 9:46–11:30 NY

Window constants (`src/simulator_v2.py:40-42`):

```python
TRADE_OPEN_HM = (9, 46)
TRADE_CLOSE_HM = (11, 30)
FORCE_CLOSE_HM = (11, 30)
```

The filter `in_trade_window` (`src/simulator_v2.py:82-87`) operates on `bars_today["ts_ny"]` — every bar carries both a UTC stamp (`ts_utc`) and a NY-local stamp (`ts_ny`); the window check uses the latter. The `before_end` predicate is strict (`m < 30`), so the 11:30 bar itself is **excluded** from the entry/exit scan — it is reserved for the force-close path, which exits any still-open position at the **11:30 bar OPEN** (`src/simulator_v2.py:229-239`, `find_force_close_bar` at `:166-173`). Stored `entry_time` and `exit_time` are UTC (`src/simulator_v2.py:211`).

- **Lower bound 9:46.** The ORB is the 9:30–9:45 NY window; 9:45 is the close bar of the ORB and 9:46 is the first bar after it. The lower-bound predicate is inclusive (`m >= 46`).
- **Upper bound 11:30 at OPEN.** No new entries on the 11:30 bar; any open position exits at that bar's open price. If no 11:30 bar exists in the session, force-close falls back to the last in-window bar's close (`src/simulator_v2.py:234-237`).

### 4.3 ADX indicator (N=15, threshold=30)

Standard Wilder ADX over N consecutive 1-min bars (`src/indicators/adx.py:22-56`). Wilder smoothing is approximated via pandas EWM with `alpha = 1/N`, `adjust=False` — equivalent to Wilder's recursive smoother after the warm-up. The computation chain:

- `TR = max(high − low, |high − prev_close|, |low − prev_close|)` (`:32-36`)
- `+DM = up_move if up_move > down_move and up_move > 0 else 0` (`:40`)
- `−DM = down_move if down_move > up_move and down_move > 0 else 0` (`:41`)
- Smoothed `TR_s`, `+DM_s`, `−DM_s` via EWM α=1/N (`:43-46`)
- `+DI = 100 · +DM_s / TR_s` ; `−DI = 100 · −DM_s / TR_s` (`:48-49`)
- `DX = 100 · |+DI − −DI| / (+DI + −DI)` (`:52`)
- `ADX = EWM(DX, α=1/N)` (`:54`)

**Evaluation point.** `precompute_lookup` (`src/indicators/adx.py:59-67`) `.shift(1)`s the series so the value returned for touch bar T is computed from bars strictly before T — i.e., the lookback `[…, T−1]`. This enforces no look-ahead by construction.

**Output.** `AdxClassifier.__call__` (`src/indicators/adx.py:79-83`) returns `Label.TREND` when `val ≥ threshold`, else `Label.FADE`. NaN during warm-up defaults to `FADE` (it never emits `SKIP`).

Parameters `N=15`, `threshold=30` are the R-012 deployment-winner choices; rationale and sweep evidence live in `docs/research-log-2026-05-regime-v2-investigation.md`.

### 4.4 ±DI indicator (N=15, threshold=8)

Same TR / DM / DI computation chain as ADX (`src/indicators/di.py:21-52`), but the indicator stops at the spread — no DX/ADX final smoothing. The signal is the **absolute** directional spread:

```python
# src/indicators/di.py:50
spread = (plus_di - minus_di).abs()
```

This measures the magnitude of directional pressure, regardless of sign. A large +DI vs small −DI and a large −DI vs small +DI both raise the spread; the indicator does not by itself decide which way is "with the trend" — it only judges that *some* direction has the upper hand.

Evaluation point and output rule are identical to ADX: `.shift(1)` lookup at touch bar T → strictly pre-T bars; `spread ≥ threshold` → `Label.TREND`, else `Label.FADE`; warm-up NaN defaults to `FADE`; never emits `SKIP` (`src/indicators/di.py:55-75`).

Parameters `N=15`, `threshold=8` are again the R-012 choices.

### 4.5 AND-gate logic — unanimous composition

`UnanimousClassifier` (`src/indicators/base.py:111-133`) composes the two solo indicators:

```python
# src/indicators/base.py:127-133
def __call__(self, cluster, touch_bar, bars_today) -> Label:
    labels = [c(cluster, touch_bar, bars_today) for c in self.classifiers]
    if all(l == Label.FADE for l in labels):
        return Label.FADE
    if all(l == Label.TREND for l in labels):
        return Label.TREND
    return Label.SKIP
```

The V2 + 40/40 runner wires it as `UnanimousClassifier([clf_adx, clf_di], name="V2 ADX(15,30) AND DI(15,8) unanimous @ 40/40")` (`src/run_4040_v2_full.py:201-204`). The gate is evaluated **per cluster, at the touch bar T** — the simulator invokes `classifier(candidate.cluster, bar, bars_today)` at `src/simulator_v2.py:198`.

Label semantics:

- **`FADE`** — both ADX < 30 *and* DI-spread < 8 (low directional conviction → mean-reversion trade in locked-baseline direction).
- **`TREND`** — both ADX ≥ 30 *and* DI-spread ≥ 8 (high directional conviction → invert direction).
- **`SKIP`** — any disagreement between the two (one says FADE, the other TREND). Since neither solo indicator emits `SKIP`, the gate's SKIPs come exclusively from this disagreement path. The cluster is consumed (`triggered = True`) but no trade opens.

During warm-up both solos return `FADE`, so the gate returns `FADE` and the strategy degrades gracefully to locked-baseline behavior.

### 4.6 Side flip on TREND label

The direction switch lives in the touch handler:

```python
# src/simulator_v2.py:199-206
if label == Label.SKIP:
    candidate.triggered = True
    continue
if label == Label.FADE:
    side = candidate.fade_side
else:  # TREND
    side = "buy" if candidate.fade_side == "sell" else "sell"
```

For a cluster **above** the 9:45 close: `fade_side = "sell"`, `limit_price = cluster.low`. `FADE` → enter sell at `cluster.low`; `TREND` → flip to **buy** at `cluster.low`.

For a cluster **below** the 9:45 close: `fade_side = "buy"`, `limit_price = cluster.high`. `FADE` → enter buy at `cluster.high`; `TREND` → flip to **sell** at `cluster.high`.

**The fill price never changes.** Both `FADE` and `TREND` use the same `candidate.limit_price` and the same touch bar — only the position's direction flips. This is the V2 contribution that distinguishes the strategy from the original mean-reversion-only design (`AllFade` in `src/indicators/base.py:48-54` recovers that older behavior exactly and is the byte-equivalence reference for the locked baseline; see `src/simulator_v2.py:13-15`).

### 4.7 Empirical label distribution

From `results/40_40_v2_full/20260514_125349/trades.parquet` (sha256 `1ccf859e…feb`, 908 rows):

| cluster_label | count | share |
|---|---:|---:|
| TREND | 517 | 56.94% |
| FADE  | 391 | 43.06% |
| **Total trades** | **908** | 100% |

Side counts: **buy 401**, **sell 507**.

Cross-tab `cluster_label × side`:

|  | buy | sell | total |
|---|---:|---:|---:|
| FADE  | 174 | 217 | 391 |
| TREND | 227 | 290 | 517 |
| **total** | **401** | **507** | **908** |

The side-flip rule (§4.6) was checked end-to-end against the parquet: for every row, the recorded `side` matches `fade_side` on `FADE` rows and the inverse on `TREND` rows — **0 / 908 violations**.

**SKIP count: 744.** `SKIP` clusters by design produce no row in the trades parquet (consumed, not traded), so the count must come from the classifier-tap research. Cited at `docs/research-log-2026-05-regime-v2-investigation.md:103`: *"The 744 trades where ADX and DI disagreed got SKIPPED, and those skips are where the variance reduction comes from."* Combined with the 908 traded clusters, the unanimous gate handled **1,652 cluster touches** over the 7-year window — roughly **55% traded, 45% skipped** by indicator disagreement.

## 5. Trade management & exits

Once a trade is opened per §4, the management phase is **mechanically trivial**: a fixed 40-pt bracket, no intraday adjustments, no scale-outs, no trailing — the position lives until stop, target, or the 11:30 force-close, whichever comes first. The simplicity is deliberate. The rejected variants in §7 (B, C, E, plus the cancelled D) all tried to add management complexity; all three with real results regressed walk-forward Sharpe-like by 17–30%.

### 5.1 Brackets — 40-pt stop, 40-pt target (1:1 R:R)

Bracket prices are derived at entry from the side and the fill price:

```python
# src/simulator_v2_4040.py:112-127
def check_exit(side: str, entry_price: float, bar: dict) -> Optional[tuple[str, float]]:
    if side == "buy":
        stop = entry_price - STOP_POINTS
        target = entry_price + TARGET_POINTS
        stop_hit = bar["low"] <= stop
        target_hit = bar["high"] >= target
    else:
        stop = entry_price + STOP_POINTS
        target = entry_price - TARGET_POINTS
        stop_hit = bar["high"] >= stop
        target_hit = bar["low"] <= target
    if stop_hit:
        return ("stop", stop)
    if target_hit:
        return ("target", target)
    return None
```

Constants are module-level (`src/simulator_v2_4040.py:29-34`):

```python
LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
STOP_POINTS = 40.0
TARGET_POINTS = 40.0
POINT_VALUE_USD = 2.0
```

`STOP_POINTS = 40.0` and `TARGET_POINTS = 40.0` are the only functional difference from the locked 30/30 baseline in `src/simulator_v2.py:36-37` — same TR/DM chain, same simulator state machine, same trade dataclass. The fork's docstring explicitly notes the trades parquet it emits is **not** byte-equivalent to the locked baseline by design (`src/simulator_v2_4040.py:13-15`).

**Per-trade economics.** 40 MNQ points × `POINT_VALUE_USD = $2/pt` = **$80 win or loss per contract** per resolved trade. The +/-$80 quantum is visible directly in the trades parquet — every `target` row has `pnl_dollars = +$80.00` and every `stop` row has `pnl_dollars = -$80.00` (verified end-to-end: 0/442 target violations, 0/336 stop violations of the 40-pt distance invariant).

**1:1 R:R is symmetric.** No asymmetric configurations (30/50, 25/50, 20/40, etc.) have been tested at the V2 classifier — they are listed in §9 as queued. The closest historical asymmetric tests were the pre-V2 hybrid R-003 (20/40, lost) and R-004 (45/45, lost) — both predate the V2 classifier and are not directly comparable.

### 5.2 Same-bar precedence — stop-first conservative

`check_exit` (quoted above) checks `stop_hit` **before** `target_hit`, so when a single bar's range contains both prices the simulator credits the stop:

```python
if stop_hit:
    return ("stop", stop)    # ← takes precedence
if target_hit:
    return ("target", target)
```

This is the pessimistic-for-the-strategy convention documented in `docs/decisions.md:D-005`: industry standard for bar-based backtests; the rule biases the simulator pessimistically so any error from this rule alone would understate edge. The same code path also defines **Bug A** in the bar-vs-tick reconciliation (`docs/decisions.md:D-005`; `docs/results-log.md:86-101`).

**Bug A exposure at 40/40: zero on stop-outs.** The stop-loss diagnostic at `results/archive/v2_4040_stop_loss_diagnostic_20260516/` flagged **0 of 336 stop-outs** as Bug A candidates. The check requires the exit bar to span ≥80 points symmetric around the entry price; the 40/40 bracket *is* that 80-point window, so a single 1-min MNQ bar would have to traverse the entire bracket end-to-end — outside typical bar range. The same geometric argument applies to target-outs: by construction the 40/40 bracket essentially neutralizes Bug A on this strategy on both exit sides. (At 30/30, the symmetric span is only 60pt, materially easier to hit — hence the ~1% rate cited in D-005.)

**Bug B is independent and DOES occur at 40/40.** The entry-bar chronology bug (`docs/decisions.md:D-014`) is unrelated to bracket width — it concerns whether a stop/target extreme preceded or followed the limit fill within the same minute. The stop-loss diagnostic measured **3.27% (11/336)** Bug B incidence on stop-outs, matching the doc-estimated ~3% rate from the 30/30 tick-verification slice. See §8 for the full bar-vs-tick reconciliation and the sensitivity bounds (~$908 max recoverable P&L under Bug B correction).

### 5.3 C2 — one position at a time

The C2 rule is enforced by a single `if open_pos is None:` gate at the cluster-touch check (`src/simulator_v2_4040.py:180-205`):

```python
# src/simulator_v2_4040.py:180-212
for bar in bar_records:
    if open_pos is None:
        candidate = find_first_fill(setups, bar)
        if candidate is not None:
            label = classifier(candidate.cluster, bar, bars_today)
            ...
            candidate.triggered = True
            open_pos = {...}
            ...
    else:
        exit_result = check_exit(open_pos["side"], open_pos["entry_price"], bar)
        if exit_result is not None:
            ...
            open_pos = None
```

While a position is open, the simulator only evaluates the `else` branch (exit check). **No new cluster touches are considered, no classifier evaluations are performed, no `triggered` flag is set on competing clusters.** The behavior is documented in `docs/decisions.md:D-004` (locked: "Only one position open at any time across all clusters in a session").

**Consequence: higher-quality clusters can be permanently skipped.** `docs/results-log.md:R-010` (the C2 one-position-rule diagnostic on 2024-08-12) shows the case mechanism: a size-4 cluster fired at 09:46 and locked the engine until 10:06; during that lockout, a size-7 cluster and another size-4 were touched and never re-touched after exit. Order of evaluation is temporal-touch order, not quality order. Tiebreaker on same-bar multi-touch is closest-limit-to-bar-open (geometry-driven, not signal-quality-driven; §4.1). No code bug — D-004 is implemented correctly per spec — but the design has a known cost.

**SKIP-on-classifier is different.** A cluster touched while `open_pos is None` and classified as `SKIP` *is* consumed (`triggered = True`; `src/simulator_v2_4040.py:186-187`) and frees the C2 slot immediately (`continue` then next bar). A cluster touched while `open_pos is not None` is **never reached at all** — the `else` branch only checks the open position for an exit and does not call `find_first_fill`. The two skip paths are not equivalent.

### 5.4 Force-close at 11:30

After the trading-window loop exits with `open_pos is not None`, force-close handles the residual position (`src/simulator_v2_4040.py:214-224`):

```python
if open_pos is not None:
    fc_bar = find_force_close_bar(bars_today)
    if fc_bar is not None:
        exit_price = float(fc_bar["open"])
        exit_time = fc_bar["ts_utc"]
    else:
        last = bar_records[-1]
        exit_price = float(last["close"])
        exit_time = last["ts_utc"]
    trades.append(make_trade(session_date, contract, open_pos,
                             exit_time, exit_price, "force_close"))
```

`find_force_close_bar` (`src/simulator_v2_4040.py:154-161`) finds the bar whose `ts_ny` is exactly `(11, 30)`; the exit price is that bar's **open** (the very first tick of the 11:30 minute). The 11:30 bar is **not** in the trading window per §4.2 (the `before_end` predicate uses `m < 30`), so no entry/exit check runs against it — it exists only to liquidate. Fallback (lines 219-222): if the 11:30 bar is absent (partial-session edge case), the position closes at the **close** of the last in-window bar.

**`exit_reason` is set to the literal string `"force_close"`** (line 224), independent of the bar's behavior. The simulator does NOT consult the 11:30 bar's high or low for stop/target hits before liquidating — per `docs/decisions.md:D-010`, this is intentional: closest analogue to a market order placed at 11:30, avoids the "did the stop hit at 11:30:15 or did the position survive to 11:30:45" ambiguity.

**Empirical (`results/40_40_v2_full/20260514_125349/trades.parquet`, 130 force-close trades):**

| stat | value |
|---|---:|
| Count | 130 / 908 (**14.32%**) |
| Total P&L | **+$328.00** |
| Mean / trade | **+$2.52** |
| Median | +$1.00 |
| Std dev | $32.47 |
| Min | −$71.00 |
| Max | +$66.50 |
| Positive | 68 (52.3%) |
| Negative | 62 (47.7%) |
| Exactly zero | 0 |

The force-close bucket is **approximately P&L-neutral with a slight positive lean**. It is not a meaningful contributor to the +$8,808 headline — that comes entirely from the target/stop spread ($35,360 from targets − $26,880 from stops = +$8,480, plus +$328 force-close ≈ +$8,808).

**Distribution-shape note.** The force-close P&L is roughly symmetric (medians and means agree at near-zero) but the per-trade range (−$71 to +$66.50) is comparable to the −$80 / +$80 stop/target quantum — i.e. many force-close trades are unresolved positions that drifted close to one bracket or the other without quite touching. The full force-close *shape* (skew, kurtosis, time-of-day distribution, regime distribution) is not currently characterized; queued in §9.

### 5.5 Position size — 1 contract

Position size is **implicit, not parameterized.** The simulator never reads or multiplies by a size variable. The conversion from points to dollars is:

```python
# src/simulator_v2_4040.py:146
pnl_dollars=pts * POINT_VALUE_USD,
```

with `POINT_VALUE_USD = 2.0` — the **per-contract** MNQ tick value. Every recorded `pnl_dollars` figure is therefore "1 contract worth of P&L." There is no sizing logic in either the simulator or `src/run_4040_v2_full.py` (the runner only loads bars and ORB table, constructs the classifier, and calls `run_backtest`; see `src/run_4040_v2_full.py:184-238`).

**No dynamic sizing.** No Kelly, no volatility scaling, no per-trade risk targeting, no cluster-quality conviction sizing. The backtest is single-contract throughout for reproducibility. Live deployment would consider sizing separately; sizing variants are listed as untested in §9.

### 5.6 What is NOT in the current version

The deployment candidate is **deliberately minimal** on the management side. Features explicitly absent:

| Absent feature | Status |
|---|---|
| Break-even stop moves | Tested as part of Variant B (initial stop −40, runner BE after p1 hits +40) and Variant C (initial stop −25). Both **rejected**, see §7 and `docs/research-log-2026-05-14-modifications.md`. |
| Partial exits / scale-outs | Tested in Variant B and Variant C (2-contract size, p1 target +40, p2 to next cluster). Both **rejected**. |
| Trailing stops | **Never tested.** |
| Runner break-even after partial | Same as the BE-move feature — tested via Variant B/C, **rejected**. |
| Combined BE@+20 + partial + tight stop | Variant D — **cancelled before execution** (spec superseded mid-design; no artifacts). |
| Asymmetric R:R (e.g. 30/50, 25/50) | **Never tested** at V2; queued in §9. |
| Far-border entry (cluster.high → cluster.low and vice versa) | Variant E — **rejected**, see §7 and `src/experimental/simulator_v2_farborder.py`. |
| Cluster-size filter (MIN_CLUSTER_SIZE = 4 or 5) | **Queued** as F1 / F2; interrupted by 2026-05-14 API-529. See §7 and §9. |
| Regime indicators beyond ADX + DI | Tested in R-012: ROC was noise (failed Gate 4), ATR confirmed noise, VWAP confirmed noise. Composite is the ADX∧DI 2-stack only. |
| Volatility-adjusted position sizing | **Never tested.** |
| Time-of-day filtering beyond 9:46–11:30 | **Never tested.** |
| News / event filtering (FOMC, CPI, etc.) | **Never tested.** Listed in §9. |

**The empirical pattern from the rejected variants.** All three modifications with real walk-forward results regressed WF Sharpe-like by 17% (Variant E, 5.32→5.72 vs the V2+40/40 baseline 6.86) to 30% (Variant B, 6.86→4.83) — even when slightly improving headline absolute P&L or max DD. The recurring failure mode is that each modification rearranges P&L without adding edge: same-bar leak from added cluster-targeting (B), tight-stop trap converting winners to many small losses (C), or surrendered edge on the kept trades despite correct filtering (E). V2 + 40/40 appears to sit at or near a **local optimum for the levers tested** (`docs/research-log-2026-05-14-modifications.md` §"Pattern across the four variants").

This does **not** prove V2 + 40/40 is the global optimum. Adjacent moves haven't helped; non-adjacent or qualitatively-different moves (cluster-size filter, asymmetric R:R, time-of-day filter, regime gating at a different timeframe) are untested. See §9 for the prioritized queue.

## 6. Performance details

Empirical results for **V2 + 40/40** on the 7-year window **2019-05-15 → 2026-04-15**. All figures recomputed end-to-end from `results/40_40_v2_full/20260514_125349/trades.parquet` (sha256 `1ccf859e…feb`, 908 rows) and `summary.json`; walk-forward windows are quoted directly from `results/archive/strategy_report_20260512/strategy_4040_test.md`. All numbers are **gross** — no commissions, no slippage (see §8.3 and §9 for cost-adjusted treatment). For methodology see §3–§5; for known caveats see §8.

### 6.1 Headline numbers

| Metric | Value |
|---|---:|
| Trades | **908** |
| Wins / Losses / Flats | 510 / 398 / 0 |
| Win rate | **56.17%** |
| Total P&L | **+$8,808.00** |
| Total P&L (points) | +4,404.0 pts |
| Mean per trade | +$9.70 |
| Avg winner | +$73.13 |
| Avg loser | −$71.58 |
| Gross win | +$37,297.50 |
| Gross loss | −$28,489.50 |
| Profit factor | **1.309** |
| Max drawdown | **−$1,228.00** |
| Max-DD duration (peak → recovery) | **380 calendar days** |
| Max-DD recovered? | **yes** |
| Annualized Sharpe (daily) | **2.504** |
| Annualized Sortino | **3.61** |
| Walk-forward Sharpe-like (median/stdev) | **6.86** |
| 8/8 calendar years positive | ✓ |
| 7/7 walk-forward OOS windows positive | ✓ |

Sources: `summary.json` for trades / WR / P&L / Sharpe / max DD; this section's recompute for avg winner/loser/gross splits (mean and direction verified to 2dp against `summary.json`); `strategy_4040_test.md` headline table for Sortino and WF Sharpe-like.

### 6.2 Walk-forward 7-window OOS breakdown

Windows: 3 years in-sample + 1 year out-of-sample, advancing 6 months per window. Same classifier parameters across all 7 windows. From `strategy_4040_test.md` "Per-window OOS P&L" table:

| Window | OOS P&L |
|---|---:|
| W1 | +$1,304 |
| W2 | +$1,644 |
| W3 | +$1,688 |
| W4 | +$1,538 |
| W5 | +$1,936 |
| W6 | +$2,028 |
| W7 | +$1,820 |
| **Sum** | **+$11,956** |
| Median | $1,688 |
| Min | $1,304 |
| Max | $2,028 |
| Range | $1,304 – $2,028 (tight) |
| Sign stability | **7/7 positive** |

**4-gate qualification audit** (R-012 deployment-strict gates, `docs/research-log-2026-05-regime-v2-investigation.md`):

| Gate | Threshold | V2 + 40/40 observed | Pass? |
|---|---|---:|:---:|
| 1. median(per-window OOS P&L) > 0 | > $0 | +$1,688 | ✓ |
| 2. ≥ 6 of 7 OOS windows positive | ≥ 6/7 | 7/7 | ✓ |
| 3. WF Sharpe-like > null p95 | > 1.06 | 6.86 | ✓ |
| 4. total P&L > 0 over the full 7y | > $0 | +$8,808 | ✓ |

**All four gates pass.** The null-distribution p95 from 50 RandomBinary seeds in R-012 was a WF Sharpe-like of 1.06; V2 + 40/40 exceeds this by **6.5×**. Compare AllFade (no classifier) at the same brackets: WF Sharpe-like = −2.00, sign 0/7, total P&L −$11,253 — fails every gate.

Caveat note from §4.5 / §2.3: the walk-forward windows overlap (1y OOS, 6mo advance), so the same trades contribute to multiple windows' evaluations. This is a softer test than disjoint-OOS walk-forward.

### 6.3 Calendar-year P&L

Recomputed from the trades parquet:

| Year | Trades | Win rate | P&L |
|---:|---:|---:|---:|
| 2019 (May–Dec) | 88 | 59.09% | +$1,123.50 |
| 2020 | 87 | 51.72% | +$503.00 |
| 2021 | 95 | 53.68% | +$653.50 |
| 2022 | 139 | 53.24% | +$793.00 |
| 2023 | 144 | 57.64% | +$1,569.00 |
| 2024 | 105 | 59.05% | +$1,226.00 |
| 2025 | 140 | 60.71% | +$2,347.50 |
| 2026 (Jan–Apr) | 110 | 52.73% | +$592.50 |
| **Total** | **908** | **56.17%** | **+$8,808.00** |

**Every year positive (8/8).** Worst year: 2020 at +$503 (still 51.72% WR despite the COVID-era volatility regime). Best year: 2025 at +$2,347.50 (140 trades, 60.71% WR). 2019 is partial (May–Dec, level pool also warming up) and 2026 is partial (Jan–Apr). On a per-trade basis 2026 is the weakest non-warm-up year (+$5.39/trade vs the 7-year average +$9.70) — see §2.4 for the recent-period concern and the V2-vs-AllFade comparison at 40/40 that softens it.

### 6.4 Exit-type distribution

| Exit reason | Count | Share | Mean P&L | Total P&L |
|---|---:|---:|---:|---:|
| target | 442 | **48.68%** | +$80.00 | +$35,360.00 |
| stop | 336 | **37.00%** | −$80.00 | −$26,880.00 |
| force_close | 130 | **14.32%** | +$2.52 | +$328.00 |
| **all** | **908** | 100% | +$9.70 | **+$8,808.00** |

Force-close shape detailed in §5.4 (median +$1, std $32.47, range −$71 to +$66.50, slightly positive lean).

**Coin-flip baseline check.** At 1:1 R:R with 40/40 brackets and zero force-closes, a random classifier with no edge would yield 50% target / 50% stop / WR = 50% and total P&L = $0. V2 + 40/40 produces **56.17% WR** — 6.17 percentage points above coin-flip. Applied across 908 trades at the ±$80 quantum, the implied edge from the WR gap alone is approximately `908 × 0.0617 × $160 ≈ $8,961` (close enough to the observed +$8,808 that the force-close bucket's near-zero contribution is the explanatory residual). **The strategy's entire edge sits in the WR gap, not in the per-win-vs-per-loss asymmetry** (which is locked to exactly 1:1 by the symmetric bracket).

### 6.5 Classifier label split (FADE vs TREND)

From the trades parquet (`SKIP` clusters by design produce no row — see §4.5):

| cluster_label | trades | share | WR | mean P&L | total P&L |
|---|---:|---:|---:|---:|---:|
| FADE  | 391 | 43.06% | 54.99% | +$7.35  | +$2,873.00 |
| TREND | 517 | 56.94% | 57.06% | +$11.48 | +$5,935.00 |
| **all** | **908** | 100% | 56.17% | +$9.70 | +$8,808.00 |

Cross-tab from §4.7: FADE → (174 buy, 217 sell), TREND → (227 buy, 290 sell). Total: buy 401, sell 507. Side-flip rule (§4.6) was verified end-to-end with **0/908 violations**.

**The TREND label is the V2 contribution's direct payoff.** Without the regime classifier, every cluster touch would be a FADE — the V2 contribution is the 517 trades labeled TREND (with `side` inverted from the locked-baseline fade direction). Those 517 trades net **+$5,935 (67% of the +$8,808 total)** with WR 2.07pp higher than the FADE-labeled subset. The FADE-labeled subset itself (+$2,873 / 391 trades / 54.99% WR) **already outperforms locked-baseline AllFade** at 40/40 (which produced −$11,253 / 1,600 trades — see §6.8) because the classifier filters the unanimous-FADE-only touches.

For the **744 SKIP** clusters from R-012 (30/30 geometry, cited at `docs/research-log-2026-05-regime-v2-investigation.md:103`) — see §2.3 and §4.7. The exact SKIP count for the 40/40 fork is not separately documented in project artifacts and is not derivable from the trades parquet (SKIPped clusters leave no row by design).

### 6.6 Drawdown profile

Computed from the cumulative equity curve of the trades parquet (sorted by `entry_time`):

| Metric | Value |
|---|---|
| Max drawdown | **−$1,228.00** |
| Trough date | 2022-04-07 (trade index 342) |
| Prior-peak date | 2022-01-10 (trade index 287) |
| Recovery date | 2023-01-25 (trade index 425) |
| Peak → trough | 87 calendar days |
| Peak → recovery (time underwater) | **380 calendar days** |
| Recovered? | **yes** — equity exceeded prior peak |
| Distinct DD episodes (any depth) | 87 |
| DD episodes deeper than $500 | **6** |
| 5 worst episode depths | −$1,228, −$779, −$646, −$640, −$640 |
| Trades occurring below a prior peak | 720 / 908 (**79.3%**) |

**Max-DD context.** The single −$1,228 episode is concentrated in early-2022 (a 87-day decline from 2022-01-10 to 2022-04-07), recovering by 2023-01-25 — entirely within the 7-year window. The 380-day recovery is the longest underwater stretch. The 79.3% "trades below a prior peak" figure is the expected behavior of a monotone-rising equity curve with frequent small dips — most trades happen while the strategy is in *some* drawdown, even if small.

The five DD episodes deeper than $500 cluster around volatile years (2022 hosts the worst); see §6.3 for the year-by-year P&L pattern.

### 6.7 Risk-adjusted metrics

| Metric | Value | Interpretation |
|---|---:|---|
| Profit factor | **1.309** | gross-win / gross-loss; >1.3 is the locked-baseline threshold informally referenced in R-012 work |
| WR vs coin-flip baseline | **+6.17pp** | strategy's WR above the 50% no-edge baseline at 1:1 R:R |
| Annualized Sharpe (daily) | **2.504** | within-period, daily-bar P&L mean / stdev × √252 (`summary.json`) |
| Annualized Sortino | **3.61** | downside-deviation analogue (`strategy_4040_test.md`) |
| Per-trade Sharpe | **0.130** | mean / stdev across the 908 trade P&Ls (`summary.json`) |
| **WF Sharpe-like (median/stdev over 7 OOS windows)** | **6.86** | cross-period stability — the deployment-confidence metric |

**Methodological note on the two Sharpes.** The 2.504 daily-annualized Sharpe and the 6.86 WF Sharpe-like measure different things:

- **Daily-annualized Sharpe = 2.504.** Standard finance reporting measure. Computed from the daily aggregate P&L series across the 7-year window: `mean(daily_pnl) / stdev(daily_pnl) × √252`. Answers: "If I trade this strategy for a year, how variable will my daily P&L be relative to its mean?"
- **WF Sharpe-like = 6.86.** R-012's 4-gate qualifier. Computed across 7 walk-forward OOS windows of 1 year each: `median(per-window OOS P&L) / stdev(per-window OOS P&L)`. Answers: "How stable is the strategy's annual P&L across rolling 1-year out-of-sample slices?"

Both numbers are high; they should not be confused. R-012 used WF Sharpe-like as the deployment-strict gate because cross-window stability is the hard generalization test that defeated the original always-fade and the V1 hybrid (see §2.1 / R-006).

### 6.8 Comparison vs alternative configurations

From `strategy_4040_test.md` — 4-strategy side-by-side at the 7-year level:

| Metric | V2 30/30 | **V2 40/40 (this)** | AllFade 30/30 | AllFade 40/40 |
|---|---:|---:|---:|---:|
| Trades | 949 | **908** | 1,693 | 1,600 |
| Win rate | 55.2% | **56.2%** | 48.7% | 45.7% |
| Total P&L | +$5,803 | **+$8,808** | −$3,378 | −$11,253 |
| Mean / trade | +$6.11 | **+$9.70** | −$1.99 | −$7.03 |
| Profit factor | 1.243 | **1.309** | 0.932 | 0.823 |
| Max DD | −$1,103 | **−$1,228** | −$6,156 | −$11,694 |
| Max-DD recovered? | yes | **yes** | no | no |
| Annualized Sharpe (daily) | 1.76 | **2.15** | −0.74 | −1.90 |
| Annualized Sortino | 2.88 | **3.61** | −0.95 | −2.34 |
| WF Sharpe-like | 5.32 | **6.86** | 0.37 | −2.00 |
| WF sign stability | 7/7 | **7/7** | 4/7 | 0/7 |
| 4-gate deploy-qualified | ✓ | **✓** | — | — |

(The Annualized-Sharpe row from `strategy_4040_test.md` shows V2 + 40/40 = 2.15, while `summary.json`'s `sharpe_daily_annualized` for the same run is 2.504. The two numbers come from different aggregation conventions — strategy_4040_test.md's table value is the cross-strategy comparison figure; the summary.json value is the canonical per-run figure. Citing both here for transparency; the discrepancy doesn't change qualitative ranking.)

**Three reads from the 4-way comparison:**

1. **V2 + 40/40 dominates V2 + 30/30 on every metric** except max DD (which is slightly wider at −$1,228 vs −$1,103, but recovers in 380 days vs the 30/30's 596 days — a meaningful improvement in time-underwater).
2. **Both V2 variants pass the 4-gate; both AllFade variants fail.** The classifier is the qualifying lever — bracket geometry alone does not make either AllFade variant deployable.
3. **The bracket-widening effect is positive WITH the classifier and negative WITHOUT it.** V2: 30/30 → 40/40 = +$3,005 (+52%). AllFade: 30/30 → 40/40 = −$7,875 (worse by 233%). This is the strongest single piece of evidence that the classifier-bracket interaction is **causal, not coincidental** — wider brackets only help when an upstream regime gate has already filtered the wrong-regime touches. Without the gate, wider brackets compound losses by holding through unfavorable moves that would have force-closed at the narrower bracket.

## 7. Modifications tested (rejected)

Four post-R-012 modifications were tested against the V2 + 40/40 deployment candidate (the baseline at +$8,808 / WF Sharpe-like 6.86 / sign 7/7 — §6). **Three (B, C, E) were run and rejected; one (D) was cancelled mid-spec when superseded; one (F1/F2) is queued and not yet executed.** None of the executed variants improved on the baseline on the deployment-critical WF Sharpe-like metric. The cross-cutting pattern is the most important finding (§7.6).

All variants preserve the locked geometry from §3 (3-pt clusters, MIN_SIZE=3, lookback=200, 9:46–11:30 NY window, C2 one-position-at-a-time, force-close at 11:30 bar OPEN, stop-first conservative). Experimental simulator code lives under `src/experimental/`; `src/simulator_v2.py` and `src/simulator_v2_4040.py` were NOT modified.

### 7.1 Variant B — partial exit + runner break-even (initial stop −40)

**Spec** (`results/archive/v2_4040_modifications_20260514/report.md`):

- **2 contracts** per entry (p1 + p2)
- **p1:** target = +40, stop = −40 (same as baseline)
- **p2 (runner):** target = nearest level of the *next* cluster in the trade direction (entry cluster excluded by object identity); initial stop = −40
- **Runner-BE rule:** when p1 exits at +40 on bar X, p2's stop moves to entry effective bar X+1 (never on bar X itself — entry-bar BE paradox resolved with "option 1")

**Hypothesis.** Partial exit lets the strategy capture moves that traverse past +40 (the next cluster level); runner-BE protects the runner once p1 has locked profit.

**Result** (vs V2 + 40/40 baseline algebraically scaled to 2c for like-for-like — dollar quantities ×2, ratio metrics unchanged):

| Metric | Baseline (×2c) | **Variant B** | Δ |
|---|---:|---:|---:|
| Entries | 908 | 899 | −9 |
| WR | 56.2% | 56.0% | −0.2pp |
| Total P&L | +$17,616 | +$16,591 | **−$1,025** |
| Mean per entry | +$19.40 | +$18.45 | −$0.95 |
| PF | 1.309 | 1.323 | +0.014 (↑) |
| Max DD | −$2,456 | −$2,080 | +$376 (↑) |
| Ann. Sharpe | 2.15 | 2.42 | +0.27 (↑) |
| Ann. Sortino | 3.61 | 4.20 | +0.59 (↑ +16%) |
| **WF Sharpe-like** | **6.86** | **4.83** | **−2.03 (↓ −30%)** |
| Sign stability | 7/7 | 7/7 | — |
| 4-gate qualified | ✓ | ✓ | — |

**Reject reason — same-bar cluster-target leak.** The runner-BE diagnostic (`results/archive/v2_4040_modifications_20260514/runner_be_diagnostics.md` §2c) found **203 entries where p1 hit +40 *and* p2 hit its cluster target on the same bar X** — the BE flag fired but never effectively activated (p2 was already exiting). Those 203 trades earned **mean $50.63 / total $10,278 on p2**, whereas the same 203 trades under the baseline 2c-scaled scheme (p2 target = +40) would have earned $80 each = **$16,240 → net leak −$5,962**.

**Runner-BE activated strictly** (p1 hit +40 AND p2 still open into bar X+1): **233 entries (26%)**. Of those: 113 stop-out at break-even ($0), 55 hit p2 cluster-target on a later bar (+$8,955.50), 65 force-close (+$10,146.50). The BE rule "saves" the 113 BE-stops from being losses, but the savings don't recover the same-bar leak.

**Calendar-year impact.** 2025 (baseline's best year) regressed by **−$1,108** — the modification's biggest single-year drag, in the strategy's strongest regime.

**Artifacts:** `results/archive/v2_4040_modifications_20260514/` (`report.md`, `runner_be_diagnostics.md`, `trades_variant_b_partial_runnerBE.parquet`). Experimental simulator: `src/experimental/simulator_v2_partial.py`, runner: `src/experimental/run_variants_bc.py`.

### 7.2 Variant C — tight stop −25 + partial exit + runner-BE

**Spec.** Identical to Variant B except **initial stop = −25** for both p1 and p2 (replacing the −40 stop).

**Hypothesis.** A tighter stop reduces the magnitude of losing trades while preserving the partial-exit upside.

**Result** (vs baseline ×2c):

| Metric | Baseline (×2c) | **Variant C** | Δ |
|---|---:|---:|---:|
| Entries | 908 | 917 | +9 |
| WR | 56.2% | **44.6%** | **−11.6pp** |
| Total P&L | +$17,616 | +$8,938 | **−$8,678** |
| Mean per entry | +$19.40 | +$9.75 | −$9.65 |
| PF | 1.309 | 1.197 | −0.112 |
| Max DD | −$2,456 | −$1,680 | +$776 (↑) |
| Ann. Sharpe | 2.15 | 1.45 | −0.70 |
| Ann. Sortino | 3.61 | 2.68 | −0.93 |
| **WF Sharpe-like** | **6.86** | **1.89** | **−4.97 (↓ −72%)** |
| Sign stability | 7/7 | 7/7 | — |
| 4-gate qualified | ✓ | ✓ | — |

**Reject reason — classic tight-stop trap.** The −25 stop converts moderate-magnitude reversal trades into many small losses. p1 stop-outs jumped from 334 (Variant B at −40) to **484 (Variant C at −25)** — a 45% increase in stop-out count for the same setup population. WR collapse from 56% → 44.6% is the cleanest disqualifier; it's not that the stops are smaller (which is true) — it's that the volume of stops outpaces the per-stop savings.

**Artifacts:** same directory as Variant B; trade log at `trades_variant_c_tight_partial_runnerBE.parquet`.

### 7.3 Variant D — combined BE@+20 + partial + tight stop (cancelled before run)

**Status: cancelled before execution. No artifacts produced.**

The source log entry is brief (`docs/research-log-2026-05-14-modifications.md:22-23`):

> "Cancelled before run. Spec superseded mid-design by the runner-BE-at-p1-exit rule. No artifacts."

The original spec combined three rules: a BE@+20 trigger, partial exit, and a tight stop. During spec design the BE@+20 trigger was dropped in favor of the runner-BE-at-p1-exit rule that became part of B and C. With BE@+20 removed, the remaining "combined" variant would have been substantially redundant with Variants B/C (which already exercise partial + runner-BE at both stop widths), so D was formally cancelled rather than run. The precise mechanical equivalence (whether D-minus-BE@+20 was *exactly* identical to C, or merely a near-duplicate) is not documented in the source log.

### 7.4 Variant E — far-border entry

**Spec** (`results/archive/v2_4040_far_border_20260514/report.md`). Single change: limit price moves from the cluster's **near** edge to the **far** edge. Cluster above 9:45 ORB close → limit at `cluster_high` (was `cluster_low`). Cluster below close → limit at `cluster_low` (was `cluster_high`). Applies uniformly to FADE and TREND. Trigger direction unchanged. Classifier is unchanged but evaluated at the *later* bar where price reaches the far edge.

**Hypothesis.** Requiring price to fully traverse the cluster before entry should filter out weak-momentum touches that don't push through.

**Result** (vs V2 + 40/40 baseline, both single-contract):

| Metric | Baseline | **Variant E** | Δ |
|---|---:|---:|---:|
| Entries | 908 | 848 | −60 |
| WR | 56.2% | 55.5% | −0.7pp |
| Total P&L | +$8,808 | +$7,554 | **−$1,254** |
| Mean per entry | +$9.70 | +$8.91 | −$0.79 |
| PF | 1.309 | 1.282 | −0.027 |
| Max DD | −$1,228 | −$910 | +$318 (↑ −26%) |
| DD duration (days) | 380 | 278 | −102 (↑) |
| Ann. Sharpe | 2.15 | 2.18 | +0.03 (↑ +1.4%) |
| Ann. Sortino | 3.61 | 3.79 | +0.18 (↑ +5%) |
| **WF Sharpe-like** | **6.86** | **5.72** | **−1.14 (↓ −17%)** |
| Median per-window OOS | $1,688 | $1,339 | −$349 |
| Sign stability | 7/7 | 7/7 | — |
| 4-gate qualified | ✓ | ✓ | — |

**Filter-effect diagnostic** (the conceptually important part):

- **Baseline clusters fired: 908**; **Far-border clusters fired: 848**
- **Shared (same cluster identity fires in both): 745**
- **Filtered out by far-border requirement: 163** (baseline-only)
- **New in far-border: 103** (re-orderings from C2 timing)

The **163 filtered-out trades** netted just **+$48 / 50.3% WR in the baseline** — exit breakdown 61 target / 64 stop / 38 force-close. **The filter is correctly identifying weak-momentum touches.** It is doing what it was hypothesized to do.

But the **745 shared clusters performed worse at the far border**: mean per trade fell from **$11.76 (baseline subset of 745) → $8.91 (far border)**, a **−$2,123 total degradation on the kept trades**. The wider entry surrendered edge on the trades it kept faster than it shed losses on the trades it filtered. Net: −$1,254.

**Cluster-size signal.** The 163 filtered-out trades had **mean cluster_size = 4.23** vs **3.74 for shared trades** — larger clusters resist full traversal more often. This is the direct motivation for the queued F1/F2 cluster-size filter (§7.5).

**Reject reason.** No net P&L gain, WF Sharpe regression of 17%, and the same trade-shape-improvement-without-edge-addition pattern as B. The filter signal is real; the entry-price drag of moving to the far border washes it out.

**Artifacts:** `results/archive/v2_4040_far_border_20260514/` (`report.md`, `trades_v2_4040_far_border.parquet`). Experimental simulator: `src/experimental/simulator_v2_farborder.py`, runner: `src/experimental/run_farborder.py`.

### 7.5 Variant F1 / F2 — cluster-size filter (queued)

**Status: queued. Implementation prepared; the actual walk-forward run was interrupted by an API 529 overload on 2026-05-14 and has not been re-run.**

**Spec** (`docs/research-log-2026-05-14-modifications.md:45-48`):

- **F1:** V2 + 40/40 with `MIN_CLUSTER_SIZE = 4` (was 3)
- **F2:** V2 + 40/40 with `MIN_CLUSTER_SIZE = 5`
- **Implementation:** module-level constant override on `simulator_v2` (e.g. `sim.MIN_CLUSTER_SIZE = 4`) — the same pattern used by `strategy_4040_test.py`. **No fork required; no `clusters.py` edit needed.** Constant location: `src/simulator_v2.py:35`, consumed inside `find_clusters(...)` at `src/simulator_v2.py:263`.

**Motivation.** The Variant E filter diagnostic (§7.4) showed that **filtered-out trades had mean cluster size 4.23** vs **3.74 for shared trades** — larger clusters correlate with traversal resistance. F1/F2 tests this lever directly without inheriting the entry-price drag that hurt Variant E. The expected mechanism: fewer trades, but each on a structurally stronger zone.

**Expected:** trade count will drop substantially (median cluster size in the baseline is exactly 3 — see §3.3 empirical distribution: 576 of 908 trades are size-3, so MIN_SIZE=4 would eliminate ~63% of trades and MIN_SIZE=5 would eliminate ~82%). Per-window OOS estimates will be noisier on the smaller sample. The decisive number is the **filter-effect diagnostic** mean of filtered-out trades (analogous to the $0.29/trade noise figure in §7.4).

**Why this is the most interesting queued test.** F1/F2 is a **"selection" lever** rather than a "mechanics" lever — it changes which clusters get traded rather than what to do once a setup fires. All four executed variants (B, C, E, plus cancelled D) were mechanics changes. F1/F2 is the first selection-side modification post-R-012 and the most natural follow-up to the §7.4 filter-effect finding.

**Artifacts (placeholder):** `results/archive/v2_4040_cluster_size_filter_20260514/` (currently only `.gitkeep`).

### 7.6 Cross-cutting empirical pattern

The three executed variants split into two failure modes:

| Variant | Headline P&L Δ vs baseline | WF Sharpe Δ | Headline Sharpe / Sortino / Max DD |
|---|---:|---:|---|
| **B** (partial + runner-BE −40) | −$1,025 (2c basis) | **−30%** (6.86 → 4.83) | Sharpe +13%, Sortino +16%, Max DD +15% — **all three improved** |
| **C** (partial + runner-BE −25) | −$8,678 (2c basis) | **−72%** (6.86 → 1.89) | Sharpe −33%, Sortino −26%, Max DD +32% — Sharpe/Sortino regressed |
| **E** (far-border entry)        | −$1,254 (1c basis) | **−17%** (6.86 → 5.72) | Sharpe +1.4%, Sortino +5%, Max DD +26% — **all three improved** |

**Two distinct failure modes:**

- **Subtle-decay mode (B and E).** Both variants *improved* every headline shape metric (Sharpe, Sortino, max DD) while regressing only the deployment-critical WF Sharpe-like by 17–30%. They look better on a one-period summary but generalize worse across the 7 walk-forward windows. The same trade-shape-improvement-without-edge-addition pattern.
- **Catastrophic-mode (C).** WR collapsed by 11.6pp; everything regressed. This is a different class of failure — not subtle stability decay but a direct disqualification through the tight-stop trap.

(Note: the prior §5.6 framing "modifications regressed WF Sharpe-like by 17–30%" referred specifically to the B and E subtle-decay cases; C is the separate −72% catastrophic class.)

**Mechanistic interpretation.** Each modification adds a tunable parameter or rule that doesn't generalize across regimes. The original V2 classifier was selected from this 7-year dataset and survives 4-gate qualification; adding rules on top introduces new fitting-surface area without going through the same gate-defended selection process. Variant B's same-bar leak (203 trades, −$5,962) and Variant E's edge-degradation-on-shared-clusters (745 trades, −$2,123) are concrete mechanisms — but the broader pattern is that *adding management complexity adds parameters that need to be tuned, and tuned parameters don't survive cross-window evaluation as well as the gate-qualified baseline.*

**Pragmatic conclusion.** V2 + 40/40 appears to sit at a **local optimum** for the levers tested. The four adjacent moves attempted haven't helped. This does **not** prove it's the global optimum:

- F1/F2 (queued, §7.5) is the first "selection" lever — fewer trades on structurally stronger clusters. Different mechanism from the mechanics-lever variants tested so far.
- Asymmetric R:R (untested; §9) — the 1:1 R:R has never been challenged at V2.
- Cost-adjusted re-run (queued; §9) — could change relative rankings if commissions/slippage have non-trivial per-trade impact.
- Other regime gates at different timeframes (untested; R-012 tested only 1-min ADX/DI).

Cross-references: §2.3 (V2 contribution), §2.4 (edge sources and limits), §5.6 (what is NOT in current version), §6.8 (4-strategy comparison including the AllFade-vs-V2 bracket-interaction evidence), §9 (open questions including the F1/F2 priority).

## 8. Known caveats

Every headline number in §6 carries qualifications, documented here. Caveats are organized by the empirical claim they qualify. **Where a caveat from an earlier section's TODO has been resolved by subsequent work**, the resolution is noted explicitly (§8.4 force-close character; §8.5 2026 Jan–April; §8.1 Bug A at 40/40). Live open questions are forwarded to §9.

### 8.1 Bar simulator vs tick simulator (Bugs A, B, phantom fills)

V2 + 40/40 is a **bar-based** backtest on 1-min OHLCV bars. Three distinct biases between the bar simulator and tick-truth are documented, with implications for the +$8,808 headline.

**Bug A — same-bar stop+target ambiguity** (`docs/decisions.md:D-005`).
- *Mechanism.* When a single 1-min bar's range contains both the stop and target prices, the simulator credits stop first (the "stop-first conservative" rule from §5.2).
- *Direction of bias.* **Pessimistic** (understates edge — the rule biases the simulator to assume the worse outcome on ambiguous bars).
- *Documented incidence (30/30 brackets).* ~1% of trades; counterfactual P&L impact +$600 across the locked baseline (D-005).
- *Empirical at 40/40 (deployment candidate).* **0 of 336 stop-outs flagged** (today's diagnostic, `results/archive/v2_4040_stop_loss_diagnostic_20260516/summary.json`). The check requires the exit bar to span ≥80 points symmetric around the entry price — the 40/40 bracket *is* that 80-point window, so a single 1-min MNQ bar would need to traverse it end-to-end, which is outside typical bar range. The same geometric argument applies to target exits. **Widening from 30/30 to 40/40 essentially neutralizes Bug A on both exit sides.**

**Bug B — entry-bar chronology** (`docs/decisions.md:D-014`).
- *Mechanism.* On the entry bar, the simulator counts target/stop hits if `bar.high` / `bar.low` crosses the level, regardless of WHEN within the minute the extreme occurred. If the bar's extreme preceded the limit fill, the credited exit is anachronistic — the entry hadn't happened yet when the extreme printed.
- *Direction of bias.* **Net optimistic** overall (target-side phantom wins exceed stop-side phantom losses across documented incidence).
- *Documented incidence (30/30, 32-trade tick overlap).* ~3% of trades.
- *Empirical at 40/40 (deployment candidate).* **11 of 336 stop-outs (3.27%) flagged** (today's diagnostic) — matches the doc-estimated rate almost exactly. **Localization is non-random:** 8 of 11 are TREND-labeled (vs TREND's overall 54% share of stops), and **all 11 fired between 09:46 and 10:55 NY** — with **4 at 09:46 itself** (the first bar of the trading window). Pattern is consistent with fast morning moves in trending conditions, where the entry and adverse extreme can plausibly coexist within a single minute.
- *P&L sensitivity bound.* If every Bug B candidate had not actually stopped (best case): **upper-bound recovery ~$908** = +10.3% of stop-out P&L = +3.3% of the +$8,808 headline. Full bidirectional Bug B effect (target side too) NOT computed; queued in §9.

**Phantom fills** (`docs/decisions.md:D-015`).
- *Mechanism (per D-015).* Databento OHLCV-1m bar `high`/`low` can include non-executed prints — implied levels, RFQ quotes — not just actually-traded prices. NinjaTrader's tick "Last" stream shows only executed trades. So the bar high/low can exceed any price at which a real trade occurred; when the simulator checks "did bar.high reach the limit?", it can return `True` even when no real trade ever touched that price.
- *Direction of bias.* D-015 frames as **optimistic on the entry side** (phantom fills credit limit hits at prices nothing actually traded at; subsequent path may not have been favorable). The same mechanism applied to exit bars (a phantom stop triggered by a non-trade print) would be **pessimistic** (over-counted false stop losses). The net direction at strategy level requires tick verification to quantify.
- *Documented incidence (30/30 entry-side).* ~6% of trades on the 32-trade tick-overlap slice.
- *Empirical at 40/40 (deployment candidate).* **100 of 336 stop-outs (29.76%) flagged phantom-suspect via an 8-pt wick heuristic** (today's diagnostic). The 8-pt threshold is loose and over-flags volatile bars; the true phantom-print rate is bounded above by this ~30% figure but is likely closer to the documented ~6% from the tick-confirmed slice. Phantom-suspect rate tracks bar-range volatility (highest in 2022 and 2026 partial), not necessarily phantom-print prevalence. **Confirmation requires tick data not present on this laptop.**

**Aggregate effect — what's known and what isn't:**

- On the only tick-verified slice (4 weeks of 2026-03-17 → 2026-04-15, R-001 config, 32 trades, 30/30 brackets): **bar simulator +$240 vs tick simulator $0** — bars overstated edge by ~100% on that slice (`docs/results-log.md:86-101`).
- That slice predates the V2 classifier and the 40/40 brackets. **No tick verification of the V2 + 40/40 deployment-candidate run has been done.**
- The 40/40 bracket widening **eliminated Bug A** on stop-outs and (by the same geometric argument) target-outs.
- **Bug B remains present at the doc-expected incidence (~3%)** on V2 + 40/40 stop-outs.
- **Phantom-fill exposure cannot be quantified without tick data.** The 32-trade R-001 tick-overlap result is the only direct evidence; it's a small sample on a different bracket configuration and classifier.

**Bottom line.** The +$8,808 figure is an **upper bound** on the bar simulator's view of V2 + 40/40 edge under the documented biases. The lower bound (real tick-truth edge) is unknown but materially less. Bracket widening eliminated the largest known pessimistic bias (Bug A) while leaving the optimistic biases (Bug B, phantom-entry) intact, so the *net* direction of bias removal is slightly optimistic at 40/40 — that is, the +$8,808 headline may overstate real edge by *more* than the doc-estimated overall biases would suggest.

Cross-references: §5.2 (same-bar precedence and the Bug A self-protection mechanism); the full diagnostic at `results/archive/v2_4040_stop_loss_diagnostic_20260516/report.md`; §9 (queued tick-verification follow-up).

### 8.2 No commissions or slippage applied to headline figures

The +$8,808 / $9.70-per-trade headline is **fully gross** — no commissions, no slippage, no exchange fees.

**Commission (documented).** `docs/decisions.md:OQ-4` records the locked-baseline-era estimate: "~$447 over 526 trades reduces net to ~$1,475 over 2 years" → roughly **$0.85 per round-trip per contract**. Applied to V2 + 40/40's 908 trades: **−$771.80 total commission adjustment**. Net of commission only:

| Metric | Gross (headline) | Net of $0.85/trade commission |
|---|---:|---:|
| Per-trade expectancy | +$9.70 | **+$8.85** |
| Total P&L | +$8,808 | **+$8,036** |

**Slippage (NOT quantified).** `docs/decisions.md:OQ-5` is explicit: *"Limit fills assume zero slippage. Force-close uses bar open. Real fills may be worse, especially for force-close in fast markets."* No project-doc-stated estimate exists for MNQ slippage. Industry-typical estimates (1–2 ticks per side, ~$0.50–$2 per round-trip on MNQ at $0.50/tick) would further reduce expectancy by an unquantified amount.

**Bottom line.** Until cost-adjusted re-run is done (queued in §9), the +$8,808 figure should be read as an **upper bound**, not a deployment expectation. A documented-commission-only adjustment puts the floor at +$8,036; realistic slippage assumptions would shave additional dollars-per-trade.

### 8.3 In-sample classifier selection risk

The V2 classifier parameters (ADX N=15, threshold=30; DI N=15, threshold=8) were **selected via walk-forward parameter sweep on the 2019–2026 dataset itself** — not on a held-out future period.

R-012 acknowledges this explicitly (`docs/research-log-2026-05-regime-v2-investigation.md:225`):

> *"This is **good evidence** of signal, not **proof**. The composite was selected from the data; deployment confidence must come from forward validation."*

**What supports the signal being real (despite selection on the data):**

- The 50-seed RandomBinary null distribution from R-012 had **max WF Sharpe-like of 1.21**, p95 of 1.06. V2 + 40/40's WF Sharpe-like is **6.86 — 5.7× the null max, 6.5× the null p95**.
- None of 50 random seeds achieved 7/7 sign stability (best was 6/7). V2 + 40/40 is 7/7.
- DI discrimination check (R-012): DI's actual scores landed at **100th percentile** of 30 same-bias (73% TREND) random labelings on all three metrics. DI is genuinely selecting clusters, not just imposing a bias.
- Unanimous AND-gate composite has **no decay** across the 7 walk-forward windows (slope +$33/window, r²=0.12, t=+0.83), even though DI solo has significant negative slope (−$230/window, t=−2.59).

**What doesn't fully eliminate selection-risk concern:**

- The 4 R-012 gates (median > 0, sign ≥ 6/7, WF Sharpe > 1.06, total > 0) were applied to a parameter grid that was itself swept on this dataset. The qualifying configuration was the top one out of that grid; the grid's noise floor is the null distribution.
- Walk-forward windows overlap (3y IS + 1y OOS, advancing 6mo) — same trade can contribute to multiple windows' evaluations. This is a softer test than disjoint-OOS walk-forward (see §8.8).
- Cross-window OOS evaluation with same parameters across all 7 windows is informationally weaker than pure walk-forward (per-window parameter selection on disjoint OOS).

Cross-reference: §2.4 (statistical significance of the original locked baseline at ~1.3σ above breakeven, p ≈ 0.09); §6.2 (4-gate qualification audit); §8.8 (walk-forward overlap); §9 (forward paper-test as the deployment-readiness gate).

### 8.4 Force-close P&L distribution (RESOLVED)

**Originally listed as a caveat** because the force-close character was not characterized. **Resolved in §5.4** from the V2 + 40/40 trades parquet:

| Stat | Value |
|---|---:|
| Count | 130 / 908 (14.32%) |
| Total P&L | +$328.00 |
| Mean / trade | +$2.52 |
| Median | +$1.00 |
| Std dev | $32.47 |
| Min | −$71.00 |
| Max | +$66.50 |
| Positive / Negative / Zero | 68 / 62 / 0 |

**Force-close is NOT a hidden drain on the strategy.** The 14.3% rate is high but per-trade P&L is approximately zero with a slight positive lean. Force-close trades neither systematically save the strategy nor erode it.

The full distribution *shape* (skew, kurtosis, time-of-day distribution, regime distribution) is not yet characterized — see §9. The mean / median / range above are sufficient to retire force-close as a top-tier caveat.

### 8.5 2026 January–April underperformance vs AllFade (PARTIALLY RESOLVED)

The headline deployment concern from R-012 was that V2 underperformed the no-classifier AllFade baseline by **−$1,422 over the most recent 4 months at 30/30 brackets** ($199 V2 vs $1,620 AllFade; `docs/research-log-2026-05-regime-v2-investigation.md:172-200`). Three interpretations were possible: (a) small-sample noise, (b) regime drift starting, (c) generalization failure.

**Partial resolution: at 40/40 the sign flips.** Per `results/archive/strategy_report_20260512/strategy_4040_test.md` calendar-year table (cited in full in §6.8 and resolved in §2.4):

| 2026 Jan–Apr | V2 | AllFade | Δ (V2 − AllFade) |
|---|---:|---:|---:|
| 30/30 brackets | +$199 | +$1,620 | **−$1,421** |
| **40/40 brackets (deployment candidate)** | **+$592** | **−$112** | **+$704** |

At the deployment-candidate bracket width, V2 *outperforms* AllFade by $704 on the same period. The widened bracket flips the sign of the recent-period gap — consistent with the §6.8 finding that the **bracket-widening interaction with the classifier is causal**, not coincidental (AllFade alone bleeds from $-3,378 at 30/30 to $-11,253 at 40/40; V2 gains from +$5,803 to +$8,808).

**What's still open.** The 2026 sample is only 4 months and ~110 trades. Cannot distinguish genuine classifier decay from random short-period variation. The 6.86 WF Sharpe-like over the 7 walk-forward windows is the deployment-confidence number, not the 2026 partial. Recent-period monitoring remains a live concern; the forward paper-test in §9 has explicit pass/fail criteria around AllFade-vs-V2 tracking.

### 8.6 Recent-period decay risk on the underlying indicators

The R-012 window-trend regression (`docs/research-log-2026-05-regime-v2-investigation.md:141-156`) shows different decay properties across configs:

| Config | Window-trend slope ($/window) | r² | t-stat | Verdict |
|---|---:|---:|---:|---|
| **B ADX∧DI unanimous (composite)** | **+$33** | 0.12 | +0.83 | **Healthy — no decay** |
| ADX solo | +$100 | 0.54 | +2.44 | **Strengthening** (significant) |
| **DI solo** | **−$230** | 0.57 | **−2.59** | **Significant decay** |
| LOO-ATR | −$48 | 0.10 | −0.75 | Mild decay |
| LOO-DI | −$57 | 0.47 | −2.09 | Borderline decay |
| LOO-ROC | −$99 | 0.68 | **−3.26** | Significant decay |

**The unanimous AND-gate "fixes" DI's significant negative trend.** This is good news for V2's robustness — the composite has the healthiest signal of any qualifying config tested. **But** the fix relies on ADX and DI maintaining *independent* signal. If both lose signal simultaneously in a future regime, the AND-gate degrades (since it requires both to agree).

ATR solo and VWAP solo were both **confirmed as noise** by R-012's Phase 0 null distribution (sharpe-like 0.43 and 0.70 respectively, both below the null p95 of 1.06). They are NOT redundant signal sources — adding them would not provide failure-mode insurance.

ROC qualified the original 3-gate but failed gate 4 (total P&L −$1,430), confirming regime-inversion risk. Its decay is the largest of the LOO variants (t=−3.26).

Cross-reference: §9 for forward paper-test pass/fail criteria including AllFade-vs-V2 monitoring and the "3+ consecutive losing months" invalidating trigger.

### 8.7 Strategy tested only on MNQ futures

All testing — locked baseline, R-006 historical extension, R-012 V2 classifier sweep, V2 + 40/40 candidate, all four rejected variants (B/C/D/E), today's stop-loss diagnostic — has been on **MNQ** (Micro E-mini Nasdaq-100) 1-minute bars only.

**No cross-instrument validation has been done.** ES, NQ, RTY, agricultural futures, currencies, crypto — generalization is unknown and untested.

**Reasons to suspect transfer might work:**
- The ORB premise (9:30–9:45 NY as a watched window) generalizes naturally to other US equity index futures (ES, NQ, RTY).
- The 200-session level pool is statistically driven, not instrument-specific.
- The ADX / ±DI indicators are well-defined on any OHLCV stream.

**Reasons to suspect transfer might fail:**
- The 40-pt bracket is calibrated to **MNQ point value** ($2/pt) and MNQ-specific 1-min bar volatility. Other instruments would need bracket re-calibration to equivalent dollar risk, and the bracket-classifier interaction (§6.8) may not survive the re-calibration.
- The ORB-cluster premise depends on the 9:30–9:45 NY window being a meaningful structural event. True for US equity index futures during cash-market hours; less obvious for 24h instruments (FX, crypto) where there is no "open."
- R-012's classifier parameter selection happened on MNQ; the same (N=15, thr=30 and thr=8) would need separate re-validation on each new instrument.

**The honest framing.** The strategy is a hypothesis about MNQ specifically; everything else is speculation. Cross-instrument testing is on the deferred-research list, not the deployment path.

### 8.8 Walk-forward overlap methodology

The 7-window walk-forward used in R-012 and §6.2 is **3y in-sample + 1y out-of-sample, advancing 6 months per window**. Same classifier parameters applied across all 7 windows.

**The 1-year OOS slices OVERLAP.** With a 6-month advance and a 12-month OOS, consecutive windows share 6 months of OOS data. A single trade can therefore contribute to **two windows' OOS evaluations** (rarely three, given the overlap geometry).

| Property | This study (overlap) | Disjoint-OOS (untested) |
|---|---|---|
| OOS windows on the same dataset | 7 | ~4–5 |
| Same trade contributes to multiple windows | yes | no |
| Per-window evaluation noise | lower (more trades per window) | higher |
| Cross-period stability test rigor | softer | stricter |

R-012 documents this design choice explicitly. The overlap **softens the cross-period stability test** (per-window OOS estimates are not statistically independent) — they're more like rolling-window correlations than disjoint cross-validation folds. The +$11,956 sum across the 7 windows (§6.2) **counts the same dollars multiple times** in different windows; the underlying 7-year total is +$8,808 (§6.1).

**Why this matters.** The 7/7 sign stability is real but it's a softer statistic than 5/5 sign stability on disjoint OOS would be. The WF Sharpe-like of 6.86 should be compared against the null distribution's 1.06 p95 (which was computed under the same overlapping-window protocol — so the comparison is internally valid, even if the absolute number is less stringent than disjoint-OOS would produce).

**Disjoint-OOS reproduction is untested.** Likely results: noisier per-window estimates, narrower margin above the null distribution, possibly weaker sign stability. The qualitative conclusion (V2 + 40/40 has signal, AllFade does not) would likely survive; the exact metric values would change.

Cross-reference: §6.2 (per-window OOS table, 4-gate qualification audit); §8.3 (in-sample selection risk); §9 (disjoint-OOS replication as a follow-up).

## 9. Open questions & next steps

This section is a **prioritized backlog**. Items are grouped by category: **Queued** (work prepared, awaiting execution), **Operational** (required for deployment readiness), **Investigative** (new hypotheses worth testing), **Sensitivity** (parameter sweeps not yet attempted), **Deferred** (research considered but parked). Priorities (BLOCKER / HIGH / MEDIUM / LOW / AFTER MNQ) are this document's interpretation based on §6 / §7 / §8 evidence and are not separately enumerated in `docs/decisions.md`. Mapping to that doc's `OQ-#` entries is given inline where it exists.

§9.6 is a one-page tabular view for quick scan.

### 9.1 Queued — work prepared, awaiting execution

**F1 / F2 — Cluster-size filter (MIN_CLUSTER_SIZE = 4 or 5)** _[maps to `docs/decisions.md:OQ-3`]_

- *Motivation.* §7.4 Variant E found filtered-out trades had **mean cluster size 4.23 vs 3.74 for shared trades** — larger clusters resist full traversal. F1 / F2 test this lever directly without inheriting Variant E's entry-price drag.
- *Implementation.* Module-level constant override on `simulator_v2` (e.g. `sim.MIN_CLUSTER_SIZE = 4`); same pattern as `strategy_4040_test.py`. **No fork required; no `clusters.py` edit.** Constant location `src/simulator_v2.py:35`, consumed at `src/simulator_v2.py:263`.
- *Expected output.* Per-window OOS table and 4-gate qualification for F1 (`MIN_SIZE=4`) and F2 (`MIN_SIZE=5`) vs the baseline `MIN_SIZE=3`. Trade-count drop expected ~63% (F1) or ~82% (F2) based on §3.3's empirical size distribution.
- *Status.* Interrupted by API 529 overload on 2026-05-14. Placeholder dir `results/archive/v2_4040_cluster_size_filter_20260514/` exists with `.gitkeep` only.
- **Priority: HIGH** — first **selection-side** lever, distinct mechanism from the four mechanics-side modifications already rejected (§7.6).

**Target-side Bug B mirror diagnostic**

- *Motivation.* §8.1's Bug B sensitivity bound is one-sided. Today's diagnostic (2026-05-16) flagged 11/336 stop-outs as Bug B candidates (~3.3% upper-bound recovery). The 442 target trades have the mirror exposure — bars where the target extreme might have preceded the limit fill on the entry bar. Without the mirror, the *net* Bug B effect on V2 + 40/40 P&L can't be computed.
- *Expected output.* Bug B candidate count on target trades; P&L sensitivity bound under "target trades that didn't actually win" → net Bug B P&L correction range (both sides).
- *Status.* Prepared (mirror of today's `_run.py`); not run.
- **Priority: MEDIUM** — closes the Bug A/B picture but doesn't change strategy direction.

### 9.2 Operational — required before live deployment

**Cost-adjusted re-run** _[maps to `docs/decisions.md:OQ-4` (commission) + `OQ-5` (slippage)]_

- *Motivation.* §8.2 — the +$8,808 headline is fully gross. Documented commission per `OQ-4` is **~$0.85/trade**; documented commission-only adjustment lowers per-trade expectancy to ~$8.85 and total P&L to ~$8,036. Slippage per `OQ-5` is unquantified.
- *Expected output.* Per-window OOS table with realistic per-trade cost applied; revised 4-gate qualification check; sensitivity over a slippage range (e.g., 0 / 1 tick / 2 ticks per side).
- *Status.* Not run. Cheap implementation — a flat subtraction at the trade-level in the parquet, no re-simulation needed for the commission-only step. Slippage variant needs a model (per-trade or volatility-conditional).
- **Priority: HIGH** — must precede any deployment-readiness sign-off.

**Forward paper-test (≥ 6 months)** _[maps to `docs/decisions.md:OQ-6`]_

- *Motivation.* §8.3 — V2 classifier parameters were selected via walk-forward parameter sweep on the 2019–2026 dataset itself. Deployment confidence requires out-of-data forward validation. R-012 specifies this as the single most important gate.
- *Period (per `docs/research-log-2026-05-regime-v2-investigation.md:235`).* Minimum 6 months paper trading; suggested window 2026-05-13 → 2026-11-13.
- *Expected trade volume.* ~70 trades (based on the 7-year rate of ~135 trades/year for the deployment winner at 30/30; 40/40 at ~130 trades/year is comparable).
- *Pass criteria (all must hold; per `docs/research-log-2026-05-regime-v2-investigation.md:241-245`):*
  - Cumulative P&L over 6 months > $0
  - ≥ 4 of 6 months with positive P&L
  - Max drawdown from peak ≤ $2,000 sustained for > 30 days
  - No 3 consecutive losing months
  - 2026-partial underperformance vs AllFade does **not** continue into Q3–Q4 of the forward period
- *Invalidating triggers (any one; per `docs/research-log-2026-05-regime-v2-investigation.md:247-253`):*
  - Cumulative 6-month P&L < $0
  - Drawdown from peak > $2,000 sustained for > 30 days
  - 3+ consecutive losing months
  - 4+ of 6 forward months negative
  - **AllFade outperforms ADX∧DI by > $1,000 cumulative across the forward period** (the 2026-partial pattern persisting)
- *Status.* Not started. Requires live execution infrastructure or paper-trading setup.
- **Priority: BLOCKER** — single largest remaining unknown.

**Full-period tick verification**

- *Motivation.* §8.1 — only 32 trades of tick overlap verified (R-001 at 30/30, predates V2 and 40/40). The +$240 bar vs $0 tick result is the only direct evidence on real-tick edge. Full 908-trade tick verification on V2 + 40/40 puts a hard lower bound on the +$8,808 headline.
- *Expected output.* Per-trade tick-vs-bar P&L delta for all 908 trades; updated upper/lower bounds on real edge; quantification of Bug B and phantom-fill net effect.
- *Status.* Needs tick data on the Mac mini (not present on this laptop per the prior environment audit).
- **Priority: HIGH** — directly resolves the largest single caveat (§8.1). Logically lower priority than forward paper-test (forward data on real execution covers some of the same ground), but cheaper to run if tick data is already in place.

### 9.3 Investigative — new hypotheses worth testing

**Intraday cluster-touch density as regime indicator**

- *Motivation.* Informal 10-trade audit on 2026-05-15 observed: 2 of 4 losses had **zero** "touched-but-not-traded" clusters (out of pools of 22–28 clusters per session); all 4 winners had **1+ touched-not-traded** counts. Suggests days where price hits *only* the entry cluster are momentum-trend days (strategy bleeds); days with multiple cluster touches are ranging days (strategy works).
- *Hypothesis.* Count cluster touches in some lookback window (e.g., the trading window up to the entry bar, or a rolling 30-minute window) and gate entries on it. If touched-cluster count < threshold, skip; else take normally.
- *Sample.* 10 days is too thin for an actionable claim. The full 908-trade analysis from the trades parquet + bar data would compute touched-cluster counts pre-entry for every trade and cross-tab against outcome (target / stop / force_close).
- *Expected output.* Cross-tab of trade outcome × touched-cluster-count-before-entry. One-pass empirical from existing data; no new simulation required for the first cut.
- *Status.* Idea only. Primary source is the visualization audit at `results/archive/v2_4040_examples_with_clusters_20260515/` — **not present on this laptop** (Mac-mini only per the prior environment audit). Secondary source is chat history 2026-05-15.
- **Priority: MEDIUM** — first real intraday-regime hypothesis post-R-012; cheap to evaluate from existing parquet + bar data.

**Force-close distribution conditional on regime**

- *Motivation.* §5.4 / §8.4 characterized force-close as ~P&L-neutral on average. Breaking it down by classifier label (FADE vs TREND), by year, by NY time-of-day, by cluster size might reveal that one slice systematically force-closes positive while another force-closes negative — a hidden filtering signal.
- *Expected output.* Cross-tabs of force-close P&L × (cluster_label, year, hour, cluster_size) from the trades parquet.
- *Status.* Not started. One-pass empirical, no simulation.
- **Priority: LOW** — current characterization is sufficient for §6/§8; this is refinement.

### 9.4 Sensitivity — parameter sweeps not yet attempted

**Lookback sensitivity (100 vs 200 vs 500 prior sessions)** _[maps to `docs/decisions.md:OQ-2`]_

- *Motivation.* §3.2 — `LOOKBACK = 200` chosen empirically ("roughly 10 months of trading days" per `docs/decisions.md:D-007`). No sensitivity test done. `OQ-2` records this explicitly.
- *Risk.* Results might be sensitive to lookback choice (over-fit to 200) or robust (real signal). Unknown.
- *Status.* Not started. Implementation: module-level constant override on `simulator_v2.LOOKBACK`; no fork needed.
- **Priority: MEDIUM** — confirms 200 isn't a hidden overfit; important for selection-risk story in §8.3.

**MIN_CLUSTER_SIZE sensitivity beyond F1/F2 (MIN = 6, MIN = 7)**

- *Motivation.* §3.3 — long right tail in cluster size (max observed = 11). After F1/F2 results, may want to push further if size-edge looks monotonic.
- *Status.* Not started. Run after F1/F2 informs whether to extend.
- **Priority: LOW** — depends on F1/F2 outcome.

**CLUSTER_GAP sensitivity (gap = 2.0 vs 3.0 vs 5.0)**

- *Motivation.* §3.3 — `CLUSTER_GAP = 3.0` chosen empirically per `docs/decisions.md:D-002`. No sensitivity test. R-002 in `docs/results-log.md` tested gap=2.0 at 30/30 fade-only baseline and found it weaker, but no V2 + 40/40 equivalent.
- *Status.* Not started.
- **Priority: LOW.**

**Asymmetric R:R (e.g. 30/50, 25/40, 50/30)**

- *Motivation.* §5.1 / §6.4 — at the current 1:1 R:R, the strategy's entire edge sits in the WR gap (56.17% vs 50% coin-flip = +6.17pp). Asymmetric R:R might trade WR for per-trade size, potentially lifting expectancy.
- *Risk.* Shifts win/loss balance; needs to maintain 4-gate qualification. Pre-V2 hybrid R-003 (20/40) and R-004 (45/45) both lost, but neither used the V2 classifier so not directly comparable.
- *Status.* Not started.
- **Priority: MEDIUM** — natural axis to explore after F1/F2; the only untested bracket-axis at V2.

**News / event filtering (FOMC, CPI, NFP, etc.)**

- *Motivation.* §8.1 Bug B localization to 09:46–10:55 NY hints at fast morning bars driving Bug B incidence. A news filter (skip days with major scheduled releases) could remove regime-changing days from the trade population.
- *Risk.* Drops sample size; might remove high-edge days as well as bug-prone ones.
- *Status.* Not started. Requires event calendar data (not currently in project).
- **Priority: LOW** — interesting but speculative; F1/F2 should come first.

**Time-of-day filtering within the 9:46–11:30 window**

- *Motivation.* §8.1 Bug B all 11 candidates fired 09:46–10:55; 4 at 09:46 itself. Restricting entries to the mid/late window might remove the bug-heavy slice.
- *Risk.* Drops the first hour, which may contain higher-edge trades along with the higher-bug ones.
- *Status.* Not started.
- **Priority: LOW.**

### 9.5 Deferred — considered but parked

**Cross-instrument validation (ES, NQ, RTY, agricultural, currencies)**

- *Motivation.* §8.7 — no cross-instrument testing done. ORB premise generalizes to US index futures most naturally; less obvious for 24h instruments.
- *Status.* Deferred. Requires per-instrument data, bracket re-calibration, classifier re-validation per instrument.
- **Priority: AFTER MNQ deployment-readiness sign-off.**

**Disjoint-OOS walk-forward replication**

- *Motivation.* §8.8 — current 7-window WF uses 6-month overlap (same trade can contribute to two windows). Disjoint-OOS is the more rigorous test of cross-period stability.
- *Expected output.* Replication of 4-gate qualification on disjoint-OOS slices (~4–5 windows on the same dataset instead of 7); confirmation that the qualitative conclusion (V2 has signal, AllFade does not) survives the stricter protocol.
- *Status.* Not started.
- **Priority: MEDIUM** — confirms cross-period stability isn't an artifact of overlapping windows; promote if forward paper-test surfaces stability concerns.

**Alternative regime indicators (BBWIDTH, KAMA, RSI, MACD, etc.)**

- *Motivation.* R-012 considered and rejected ATR and VWAP as noise; ROC failed gate 4. Other regime indicators not tested.
- *Risk.* Re-opens the in-sample-selection problem (§8.3) — each new indicator added to the search grid lowers the bar for spurious survival.
- *Status.* Deferred.
- **Priority: LOW** — additional regime sources are tempting but risky; F1/F2 + asymmetric R:R should come first.

### 9.6 Priority backlog (one-page view)

| Priority | Category | Item |
|---|---|---|
| **BLOCKER** | Operational | Forward paper-test (≥ 6 months) — OQ-6 |
| **HIGH** | Queued | F1 / F2 cluster-size filter — OQ-3 |
| **HIGH** | Operational | Cost-adjusted re-run — OQ-4 + OQ-5 |
| **HIGH** | Operational | Full-period tick verification |
| MEDIUM | Investigative | Intraday cluster-touch density indicator |
| MEDIUM | Sensitivity | Asymmetric R:R variants |
| MEDIUM | Sensitivity | Lookback sensitivity (100, 500) — OQ-2 |
| MEDIUM | Queued | Target-side Bug B mirror diagnostic |
| MEDIUM | Deferred | Disjoint-OOS walk-forward replication |
| LOW | Investigative | Force-close distribution conditional on regime |
| LOW | Sensitivity | MIN_CLUSTER_SIZE > 5 (after F1/F2) |
| LOW | Sensitivity | CLUSTER_GAP sensitivity |
| LOW | Sensitivity | News / event filtering |
| LOW | Sensitivity | Time-of-day filtering within trading window |
| LOW | Deferred | Alternative regime indicators (BBWIDTH, KAMA, …) |
| AFTER MNQ | Deferred | Cross-instrument validation |

**Counts by bucket:** 1 BLOCKER · 3 HIGH · 5 MEDIUM · 6 LOW · 1 AFTER MNQ = **16 items total**.

**Mapping to `docs/decisions.md` open questions:** OQ-2 → §9.4 lookback; OQ-3 → §9.1 F1/F2; OQ-4 + OQ-5 → §9.2 cost-adjusted; OQ-6 → §9.2 forward paper-test. **OQ-1 (regime detection)** predates the R-012 V2 classifier and is **effectively superseded** — the V2 ADX∧DI composite is the answer to OQ-1, with the queued forward paper-test as the validation gate. Priorities (BLOCKER / HIGH / MEDIUM / LOW / AFTER MNQ) are this document's interpretation; `docs/decisions.md` lists OQs without explicit priorities.

## 10. Code, data, decisions, glossary

Operational reference: file map for navigating the codebase (§10.1), data integrity protocol (§10.2), decision-log and open-questions index (§10.3, §10.4), glossary for the strategy-specific terms used throughout (§10.5), and external dependencies (§10.6). The canonical sources are `docs/decisions.md`, `docs/strategy-spec.md`, and the code; this section is a navigation aid.

### 10.1 Source code map

**Simulators**

| File | Role |
|---|---|
| `src/simulator_v2.py` | **Locked baseline** V2 simulator (30/30 brackets). Owns the C2 rule, per-cluster classifier hook (§4.5), force-close logic (§5.4). Byte-equivalence contract with `AllFade` classifier reproduces the locked extended baseline. |
| `src/simulator_v2_4040.py` | **V2 + 40/40 deployment candidate's simulator.** Two-line fork: `STOP_POINTS = TARGET_POINTS = 40.0`. Deliberately *not* byte-equivalent to the locked baseline (§5.1). |
| `src/simulator_v2_dyntp.py` | Dynamic-target experimental simulator (predates the §7 modifications session). |
| `src/simulator.py` | Pre-V2 original simulator (no classifier hook). Historical reference. |
| `src/simulator_hybrid.py` | V1 hybrid classifier (`expected_normalized_distance` rule). Superseded by V2; reference for R-007 (`docs/results-log.md`). |
| `src/simulator_hybrid_4040.py` | V1 hybrid at 40/40 brackets. Reference for R-008 (rejected, see `docs/results-log.md`). |
| `src/simulator_priors_only.py` | R-009 "today's ORB excluded" variant. |
| `src/simulator_breakout.py` | R-005 breakout variant. |
| `src/tick_simulator.py` | **Tick-truth verification** (the source of truth for §8.1 bar-vs-tick reconciliation). Needs tick data — Mac-mini-only. |
| `src/experimental/simulator_v2_partial.py` | Variants B & C (partial exits + runner-BE). Rejected per §7.1, §7.2. |
| `src/experimental/simulator_v2_farborder.py` | Variant E (far-border entry). Rejected per §7.4. |

**Runners**

| File | Role |
|---|---|
| `src/run_4040_v2_full.py` | **V2 + 40/40 canonical runner.** Loads bars + ORB table; precomputes ADX(15) + DI(15) lookups; composes `UnanimousClassifier`; calls `simulator_v2_4040.run_backtest`; writes trades.parquet + summary.json + summary.md + equity_curve.png + trades.csv to `results/40_40_v2_full/<timestamp>/`. |
| `src/phase6_run.py` | R-012 composite runner (Variant A: 5-corner stack + LOOs; Variant B: ADX∧DI 2-stack). 30/30 geometry only. |
| `src/strategy_4040_test.py` | 4-way comparison runner (V2 30/30 vs V2 40/40 vs AllFade 30/30 vs AllFade 40/40). Produced the comparison cited in §6.8. |
| `src/strategy_report.py` | Reporting / summary script. |
| `src/experimental/run_variants_bc.py` | Variants B & C runner. |
| `src/experimental/run_farborder.py` | Variant E runner. |
| `src/dynamic_tp_test.py`, `src/clusters_2pt_dynamic_tp_test.py` | Dynamic-target experimental runners (pre-modifications-session work). |
| `src/skip_analysis.py` | SKIP-cluster tap (counts SKIP labels by wrapping `UnanimousClassifier` and recording every SKIP event). Source of the 744 SKIP count at 30/30 (§4.7). |

**Indicators** (under `src/indicators/`)

| File | Role |
|---|---|
| `adx.py` | Wilder ADX, configurable N. V2 composite uses `N=15, threshold=30` (§4.3). |
| `di.py` | `\|+DI − −DI\|` absolute spread, configurable N. V2 composite uses `N=15, threshold=8` (§4.4). |
| `base.py` | `Label` enum, `Classifier` protocol, `AllFade`/`AllTrend`/`AllSkip`/`RandomBinary`/`BiasedRandom`/**`UnanimousClassifier`** (the AND-gate; §4.5). |
| `atr.py` | Average True Range classifier. R-012 confirmed noise. |
| `vwap.py` | VWAP-based classifier. R-012 confirmed noise. |
| `roc.py` | Rate-of-change classifier. R-012 failed gate 4 (total P&L < 0). |

**Cluster construction**

| File | Role |
|---|---|
| `src/clusters.py` | `find_clusters()` — single greedy walk over sorted level pool (§3.3). `Cluster` dataclass. `CLUSTER_GAP=3.0`, `MIN_CLUSTER_SIZE=3` consumed from caller via parameters. |

**ORB / data pipeline**

| File | Role |
|---|---|
| `src/orb.py` | Computes `orb_table.parquet` from raw bars (§3.1). Excludes incomplete-window sessions to `orb_excluded.parquet`. |
| `src/data_prep.py` | Raw Databento CSV(s) → `mnq_adjusted_1m.parquet`. Panama back-adjustment per `docs/decisions.md:D-001`. |
| `src/paths.py` | Centralized data paths (`BARS_PARQUET`, `ORB_TABLE_PARQUET`, `RESULTS_DIR`, `ARCHIVE_DIR`). |
| `src/build_tick_cache.py` | Tick-data ingestion (Mac-mini-only pipeline). |

**Walk-forward / methodology**

| File | Role |
|---|---|
| `src/walk_forward.py` | 7-window WF infrastructure (3y IS + 1y OOS, 6mo advance per §6.2). |
| `src/phase0_validate.py` | Phase 0 framework validation (harness sanity checks). |
| `src/phase0_null.py` | 50-seed RandomBinary null distribution generator (§6.2, §8.3). |
| `src/phase7_analysis.py` | R-012 Phase 7 diagnostics (window-trend regression, DI discrimination, 2026-partial comparison). |

**Sweeps** (single-indicator parameter sweeps)

| File | Role |
|---|---|
| `src/sweep_adx.py`, `src/sweep_di.py`, `src/sweep_atr.py`, `src/sweep_vwap.py`, `src/sweep_roc.py` | R-012 Phase 1–5 solo-indicator sweeps. |

**Verification / sanity / visualization**

| File | Role |
|---|---|
| `src/verify_ticks.py` | Bar-vs-tick reconciliation runner (the source of the 32-trade R-001 tick-overlap result cited in §8.1). |
| `src/ambig_check.py` | Same-bar stop+target ambiguity detector (Bug A enumeration; D-005). |
| `src/adx_sanity.py` | ADX implementation sanity test. |
| `src/visualize_trade.py`, `src/visualize_trade_4040.py` | Per-trade chart rendering. |
| `src/robustness.py` | R-001 statistical-significance scripts (§2.4). |

### 10.2 Data sources and integrity protocol

**Source bars (gitignored — Mac-mini regenerable)**

- **Provider:** Databento. 1-minute OHLCV for MNQ continuous, Panama back-adjusted per `docs/decisions.md:D-001`.
- **File:** `data/processed/mnq_adjusted_1m.parquet`
- **Current sha256:** `9c14cfacacbc9a1afb704d4ed9b7dd811ded99229938e54ffedcb048ef38e299`
- **Size:** 60,516,533 bytes (~60 MB)
- **Coverage:** 2019-05-06 → 2026-05-10 (~2.47M rows)
- **Source pipeline:** `src/data_prep.py` ingests raw Databento OHLCV-1m CSVs from `data/raw/glbx-mdp3-*.ohlcv-1m.csv`; the tick stream (`src/build_tick_cache.py`) lives only on the Mac mini.

**Locked baseline trades (committed; sha256-pinned reference)**

- **File:** `data/processed/trades.parquet`
- **Locked sha256:** `d24f128ac88227900ac6d44047f0f51e5a5906011e683643a925c63feb15f4c6`
- **Contents:** V2 + 30/30 locked-baseline trades (the byte-equivalence reference).
- **Verification protocol:** every Claude Code session **must** verify this sha256 unchanged before and after any work. The locked baseline is the project's reproducibility anchor; mutation would invalidate every "verified against locked baseline" claim in `docs/research-log-*.md`.

**V2 + 40/40 deployment-candidate trades**

- **File:** `results/40_40_v2_full/20260514_125349/trades.parquet`
- **sha256:** `1ccf859e3a580d78eb85cbc37a2cfa7159c3af59c3eb4bb58b5443d0aaf54feb`
- **Contents:** 908 trades, 2019-05-15 → 2026-04-15, the V2 + 40/40 candidate's actual run (the canonical source for all §6 numbers).

**Other processed artifacts**

| File | sha256 / Size | Purpose |
|---|---|---|
| `data/processed/orb_table.parquet` | 50,154 B | Per-session ORB high / low / close (§3.1). Reproducible via `src/orb.py`. |
| `data/processed/orb_excluded.parquet` | 4,260 B | Sessions excluded for incomplete ORB window. |
| `data/processed/rolls.parquet` | 4,223 B | Contract-roll log. |
| `data/processed/mnq_adjusted_1m.parquet` | 60 MB / gitignored | See above. |

**Reproducibility checklist**

- Locked baseline sha256 verifiable at session start and end.
- ORB table reproducible from raw bars via `python src/orb.py`.
- Cluster construction reproducible from level pool via `src/clusters.py` (pure function, tested at module-level).
- Classifier composition explicit in `src/run_4040_v2_full.py:199-204` — no implicit state.
- Null-distribution randomness in R-012 Phase 0 is seeded (`src/phase0_null.py`; 50 explicit seeds 1–50).
- Today's stop-loss diagnostic (`results/archive/v2_4040_stop_loss_diagnostic_20260516/_run.py`) is idempotent on inputs.

### 10.3 Decision log (D-### index)

Canonical source: `docs/decisions.md`. **All 15 entries (D-001 through D-015) status: locked / in-force at deployment-candidate time.** This is a navigable index with cross-references to the section that documents the decision's consequence.

| # | Title | Date | Status | Cross-ref |
|---|---|---|---|---|
| D-001 | Panama back-adjustment for continuous price series | 2026-04 | locked | §10.2 data integrity (no explicit §2–§9 reference — data-prep choice, not strategy mechanic) |
| D-002 | Cluster definition Option B (chain rule, not diameter) | 2026-04 | locked | §3.3 (chain-rule explanation + worked example) |
| D-003 | Cluster classification skips clusters spanning the 9:45 close | 2026-04 | locked | §3.4 (three-branch table; "spans" branch) |
| D-004 | One position at a time (C2 rule) | 2026-04 | locked | §5.3 (gate at `simulator_v2.py:181`) |
| D-005 | Stop-first conservative for ambiguous same-bar stop and target (**Bug A**) | 2026-04 | locked (deliberate pessimistic bias) | §5.2, §8.1, today's diagnostic |
| D-006 | First-touch entry on cluster boundary | 2026-04 | locked (alternative last-touch superseded) | §3.5 (near-border placement) |
| D-007 | 200-session lookback for level pool | 2026-04 | locked, sensitivity test pending | §3.2; sensitivity queued at §9.4 (OQ-2) |
| D-008 | 30-point fixed stop and target (1:1 R:R) | 2026-04 | locked (V2 + 40/40 deployment candidate **deliberately widens** to 40/40) | §5.1 (the 40/40 fork rationale and the §6.8 comparison) |
| D-009 | Sticky forward-only rollover | 2026-04 | locked | §10.2 data integrity (no explicit §2–§9 reference — rollover policy is data-prep) |
| D-010 | Force-close at 11:30 bar OPEN, not high or low | 2026-04 | locked | §4.2 (window upper bound), §5.4 (force-close mechanics) |
| D-011 | Trading window 9:46 to 11:30 NY time | 2026-04 | locked | §4.2 (window definition) |
| D-012 | Calendar spread filtering | 2026-04 | locked | §10.2 data integrity (no explicit §2–§9 reference — symbol filtering at data-prep time) |
| D-013 | NY timezone for all session logic | 2026-04 | locked | implicit throughout §3, §4, §5 (every timestamp citation is NY-local via `ts_ny`) |
| D-014 | Entry-bar chronology bug (**Bug B**) — credited even when bar's extreme preceded fill | 2026-04 | known bug, not fixed in baseline | §8.1 (full incidence and sensitivity), today's diagnostic |
| D-015 | Phantom fills — Databento bar high includes non-trade prints | 2026-04 | known data-source artifact, not patched | §8.1 (mechanism), today's diagnostic (phantom-suspect heuristic) |

**D-### entries without explicit §2–§9 cross-references (3 of 15):** D-001 (Panama), D-009 (rollover policy), D-012 (calendar-spread filtering). All three are data-prep / ingestion choices that produce the bar parquet but don't surface as strategy *mechanics*. They are properly documented in `docs/decisions.md` itself and indirectly enable §10.2's reproducibility claims; they don't need their own §2–§9 prose. **Flagged here for completeness rather than as omissions to fix.**

D-013 (NY timezone) is consumed implicitly by every section that references a NY-local time; no single section has an explicit "this is because of D-013" callout.

### 10.4 Open questions log (OQ-### index)

Canonical source: `docs/decisions.md` lines 186–193. All six entries are still open in the source doc; this index adds the §9 backlog cross-references and a brief status update from the work done since each was filed.

| # | Title | §9 backlog item | Status update |
|---|---|---|---|
| OQ-1 | Regime detection (ATR / ADX / ORB-width-relative) | — | **Effectively superseded by R-012.** The V2 ADX∧DI composite is the answer to OQ-1; deployment readiness gated on §9.2 forward paper-test. |
| OQ-2 | Lookback sensitivity (100, 500-session) | §9.4 lookback sensitivity | Open. Priority MEDIUM. |
| OQ-3 | Cluster minimum size (4 or 5) | §9.1 F1 / F2 | Open. Implementation prepared; run interrupted by API 529 on 2026-05-14. Priority HIGH. |
| OQ-4 | Commission impact | §9.2 cost-adjusted re-run | Open. Documented estimate ~$0.85/trade applied → commission-only adjusted P&L ~$8,036. Priority HIGH. |
| OQ-5 | Slippage model | §9.2 cost-adjusted re-run | Open. Not quantified in any project doc. Bundled with commission re-run. Priority HIGH. |
| OQ-6 | Walk-forward / out-of-sample | §9.2 forward paper-test | Open. R-012 specifies pass criteria and invalidating triggers; see §9.2. Priority BLOCKER. |

All 6 OQs have a clear cross-reference home in this document. None are silently omitted.

### 10.5 Glossary

Alphabetical; each entry one line.

- **1:1 R:R** — risk-reward ratio of 1:1; in V2 + 40/40, stop and target are both 40 points (§5.1).
- **4-gate qualification** — R-012's deployment-strict gates: median OOS > 0; sign ≥ 6/7 windows; WF Sharpe-like > 1.06; total P&L > 0 over 7 years (§6.2).
- **200-session lookback** — historical level pool window for cluster construction; counts ORB-complete sessions, not calendar days (§3.2).
- **9:30–9:45** — opening range window (NY local); `orb_high`, `orb_low`, `orb_close` derived from this (§3.1).
- **9:46–11:30** — V2 trading window (NY local); inclusive at start (`m >= 46`), strict at end (`m < 30`); 11:30 reserved for force-close (§4.2, §5.4).
- **ADX** — Average Directional Index (Wilder); V2 composite uses N=15, threshold=30; never emits SKIP (§4.3).
- **AllFade** — strategy variant: every cluster touch is faded; no classifier. Pre-V2 baseline. Loses money OOS over 7 years (§2.1, §6.8).
- **AND-gate** — V2 unanimous classifier: requires ADX and DI to agree on FADE or TREND; disagreement → SKIP (§4.5).
- **Bug A** — same-bar stop+target ambiguity (D-005). Pessimistic. ~1% of trades at 30/30; **0 at 40/40 on stop-outs** (§5.2, §8.1).
- **Bug B** — entry-bar chronology (D-014). Net optimistic. ~3% of trades; **3.27% on V2 + 40/40 stop-outs** (§8.1).
- **C2** — one-position-at-a-time rule (D-004). New cluster touches are never reached while a position is open (§5.3).
- **Cluster** — group of ≥ 3 historical ORB levels where every adjacent pair (after sorting) is within 3 points (§3.3, D-002 chain rule).
- **Cluster_high / cluster_low** — top and bottom edges of a cluster (the highest and lowest levels in the sorted chain).
- **±DI** — Plus / Minus Directional Indicator pair; V2 composite uses the absolute spread `|+DI − −DI|`, N=15, threshold=8; magnitude only, not sign (§4.4).
- **DI discrimination check** — R-012 test: DI's actual scores vs 30 same-bias (73% TREND) random labelings on Sharpe / median / total. DI hit 100th percentile on all three (§2.3, §8.3).
- **FADE** — classifier label; trade in the locked-baseline mean-reversion direction (§4.6).
- **fade_side** — the pre-V2 mean-reversion direction (sell for clusters above ORB close, buy for clusters below). Set at setup time per cluster position (§3.4).
- **Far border** — cluster edge opposite the near border (`cluster.high` for above-close clusters, `cluster.low` for below-close). Tested as Variant E entry, rejected (§7.4).
- **Force-close** — time-based exit at 11:30 NY bar OPEN. 130/908 trades affected, mean +$2.52 (§5.4).
- **Hybrid (V1)** — earlier regime classifier using `expected_normalized_distance` rule; sign-flipped across periods, rejected (R-007).
- **Locked baseline** — V2 + 30/30 byte-equivalent simulation (sha256-pinned at `d24f128a…f4c6`). Project's reproducibility anchor (§10.2).
- **MIN_CLUSTER_SIZE** — minimum levels for a chain to qualify as a cluster (currently 3; F1/F2 tests 4 and 5) (§3.3, §9.1).
- **MNQ** — Micro E-mini Nasdaq-100 futures contract. The only instrument tested (§8.7).
- **Near border** — cluster edge nearest the ORB close (`cluster.low` for above-close clusters, `cluster.high` for below-close). Default V2 entry point (§3.5).
- **Null distribution** — 50-seed RandomBinary baseline from R-012: p95 WF Sharpe-like = 1.06; max = 1.21; 0/50 achieved 7/7 sign (§6.2, §8.3).
- **OOS** — Out-of-sample. Per-window evaluation slice in walk-forward (§6.2).
- **ORB** — Opening Range Box / Bar. The 9:30–9:45 NY 15-minute window. `orb_high` / `orb_low` are extremes; `orb_close` is the close of the 9:44 bar (= price at 9:45:00 NY) (§3.1).
- **Phantom fill** — bar-data artifact (D-015): bar `high`/`low` includes non-trade prints (implied levels, RFQ quotes), so a limit can appear filled at a price nothing actually traded at. ~6% on tick-overlap slice; net optimistic on entries (§8.1).
- **Profit factor** — gross win / gross loss. V2 + 40/40: 1.309 (§6.1).
- **R-### / D-### / OQ-###** — research-log entries / decision-log entries / open-questions in `docs/`. R-001 = locked baseline; R-012 = V2 classifier deployment winner (30/30); D-005 = Bug A; OQ-6 = forward paper-test (§10.3, §10.4).
- **Setup** — candidate trade defined at 9:45 per cluster: limit price, fade side, trigger direction. Fixed for the session (§3, §4.1).
- **SKIP** — classifier label produced by AND-gate disagreement. Cluster is consumed (marked `triggered`) but the C2 slot remains free (§4.5).
- **Sortino** — Sharpe analogue using downside deviation only. V2 + 40/40: 3.61 (§6.1, §6.7).
- **Stop-first conservative** — same-bar precedence rule: if a bar's range contains both stop and target, credit stop. Pessimistic per design (§5.2, D-005).
- **TREND** — classifier label inverting the fade direction; trades with the prior price action (§4.6).
- **trigger_above** — `Setup` flag: True if entry triggers when `bar.high ≥ limit_price` (above-close cluster), False if `bar.low ≤ limit_price` (below-close cluster). Set at setup time (§3.5, §4.1).
- **UnanimousClassifier** — `src/indicators/base.py:111-133` AND-gate over a list of solo classifiers. Used in V2 composite as `UnanimousClassifier([clf_adx, clf_di], …)` (§4.5).
- **V2** — the regime-classifier-gated strategy version (R-012). Distinct from pre-V2 AllFade and from V1 hybrid (§2.3).
- **WF Sharpe-like** — `median(per-window OOS P&L) / stdev(per-window OOS P&L)` across the 7 walk-forward windows. R-012's deployment-confidence metric. V2 + 40/40: 6.86 (§6.7).

### 10.6 External references

- **Anthropic Claude / Claude Code** — development assistant used throughout the project (sessions logged in `docs/research-log-*.md`).
- **Databento** — bar data provider (`glbx-mdp3-*.ohlcv-1m` schema; per-batch manifests in `data/raw/extensions/`).
- **NinjaTrader** — tick "Last" stream is the source of truth for the tick simulator (§8.1, `src/tick_simulator.py`); Mac-mini-only.
- **Python ecosystem:** `pandas` (parquet I/O, EWM smoothing for Wilder ADX/DI), `numpy` (vectorized indicator math), `matplotlib` (equity curves, per-trade visualizations).
- **pytest / `pandas.testing.assert_frame_equal(check_exact=True)`** — byte-equivalence test for the locked baseline (§10.2 reproducibility checklist).

---

_Cross-references:_
- CLAUDE.md — session primer
- docs/strategy-spec.md — formal specification
- docs/decisions.md — chronological decision rationale
- docs/results-log.md — R-001 through R-012 entries
- docs/research-log-2026-05-*.md — per-test detailed logs
- results/archive/strategy_report_20260512/ — V2 + 40/40 baseline report (uncommitted)
- results/archive/v2_4040_modifications_20260514/ — Variants B, C
- results/archive/v2_4040_far_border_20260514/ — Variant E
- results/archive/v2_4040_examples_20260515/ — 10 trade visualizations
- results/archive/v2_4040_examples_with_clusters_20260515/ — 10 trades with cluster landscape
