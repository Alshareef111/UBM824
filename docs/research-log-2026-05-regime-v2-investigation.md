# V2 Regime Classifier — Investigation Report

**Date:** 2026-05-12
**Status:** Investigation complete. Deployment recommendation pending forward test.
**Dataset:** 2,467,393 1-min bars / 1,805 ORB sessions / 2019-05-06 → 2026-05-10.
**Locked baseline preserved:** `data/processed/trades.parquet` sha256 `d24f128a…f4c6` unchanged.

---

## Executive summary

The v2 regime classifier investigation tested five indicators (ADX, ±DI, ROC, ATR, VWAP) as per-cluster FADE/TREND classifiers gating the locked-baseline geometry. **Two indicators produce robust signal; three are noise.** The deployment-recommended configuration is:

> **ADX(N=15, thr=30) ∧ DI(N=15, thr=8) unanimous** — per-cluster AND-gate. Evaluated at the touch bar T using ADX and ±DI computed on bars `[T−15, T−1]`. FADE/TREND label fires only when BOTH agree; otherwise SKIP the cluster.

**Headline numbers (7-year backtest, 2019-05 to 2026-04):**

| Metric | Value |
|---|---:|
| Trades | 949 |
| Win rate | 55.2% (524 W / 425 L) |
| Total P&L | +$5,803 |
| OOS sharpe-like across 7 walk-forward windows | **5.32** |
| Sign stability (OOS windows positive) | 7/7 |
| Median per-window OOS P&L | $1,082 |
| Yearly P&L positive | 8/8 calendar years |
| Worst year | 2020 (+$198) |

For context: locked fade-only baseline on the same 7-year dataset = 1,693 trades / 48.7% WR / **−$3,378** (R-006). The composite filter cuts trades by 44% but converts a losing strategy into a consistent winner across all 7 walk-forward OOS windows and all 8 calendar years.

**Material deployment concern flagged:** in the most recent 4 months (Jan-Apr 2026), the locked AllFade baseline outperforms the deployment winner by $1,422. Could be small-sample noise (4 months, 113 trades) or evidence that the unanimous filter is removing trades that the current favorable-fade regime is profitable on. **Forward test required before live deployment.**

---

## Methodology

### Framework (locked 2026-05-12)

**Unit of decision: per cluster touch.** For each cluster touch at bar T, the classifier reads bars `[T−N, T−1]` (lookback ≥ 1) and emits `{FADE, TREND, SKIP}`. Locked-baseline geometry (3-pt clusters, 30-pt bracket, first-touch, C2 one-position-at-a-time, 9:46-11:30 window, force-close at 11:30 open) is untouched — only the per-cluster trade direction is gated.

- FADE → locked-baseline direction (against price action at the cluster)
- TREND → invert direction (with price action, same fill price)
- SKIP → consume the cluster without entering a trade

**Walk-forward evaluation:** 7 windows of (3y IS + 1y OOS, advance 6mo) starting 2019-05-06. Same parameters across all windows. Each config's OOS score is `sharpe_like = median(per-window OOS P&L) / stdev(per-window OOS P&L)`.

**Qualification gates (4-gate, deployment-strict):**
1. median(per-window OOS P&L) > 0
2. ≥ 6 of 7 OOS windows positive
3. sharpe_like > 1.06 (null p95 from 50-seed RandomBinary distribution)
4. total_pnl > 0 over the full 7-year dataset

### Null distribution baseline (Phase 0 supplement)

Before testing real indicators, 50 RandomBinary classifiers (seeds 1-50, per-cluster 50/50 FADE/TREND) established the noise floor:

| Stat | min | p25 | median | p75 | **p95** | max |
|---|---:|---:|---:|---:|---:|---:|
| sharpe_like | −1.31 | −0.49 | −0.07 | +0.26 | **+1.06** | +1.21 |
| sign_count | 1/7 | 2/7 | 3/7 | 4/7 | **5/7** | 6/7 |
| median_oos | −$738 | −$393 | −$31 | +$225 | **+$646** | +$1,193 |

Qualification rate under null: **2/50 = 4.0%**. None of the 50 random seeds hit 7/7 sign stability.

This is the control comparison every indicator result is judged against.

---

## Phase-by-phase results

### Solo sweeps (Phases 1-5)

Each indicator swept across a parameter grid, scored on the 7 walk-forward OOS windows.

| Phase | Indicator | Configs | Qualifying (deploy 4-gate) | Best config | Best sharpe | Verdict |
|---|---|---:|---:|---|---:|---|
| 1 | ADX | 49 | 5 | (N=15, thr=30) | **4.02** | Strong signal |
| 2 | ±DI | 49 | 10 | (N=15, thr=8) | 2.30 | Strong signal |
| 3 | ROC | 49 | 0 | (N=60, thr=80) | 1.43 | Noise (fails 4-gate) |
| 4 | ATR | 16 | 0 | (Ns=30, thr=1.3) | 0.43 | Confirmed noise |
| 5 | VWAP | 14 | 0 | (9:30 NY, thr=50) | 0.70 | Confirmed noise |

**Only directional-momentum indicators produced robust signal.** Volatility magnitude (ATR), price-vs-VWAP, and absolute price displacement (ROC) all failed to exceed the null p95. The "trending session" concept on this strategy maps to directional pressure, not to volatility expansion or distance-from-mean.

ROC qualified the original 3-gate (median+ / sign≥6) but failed gate 4 (total P&L −$1,430), confirming the regime-inversion pattern: its OOS slice covered 2022+ where ROC happened to work, but the 3-year pre-2022 stretch is heavily negative. Same regime-dependence failure mode as the original hybrid v1 classifier.

### Composite (Phase 6)

Two variants tested:
- **Variant A (framework-faithful):** all 5 indicators at solo-best params. 5 solos + 5 LOOs + 1 full-5 unanimous = 11 configs.
- **Variant B (deployment-relevant):** only the 2 solo-qualifying indicators (ADX + DI). 1 unanimous = 1 unique additional config.

**Three required comparisons:**

**1. ADX solo vs DI solo vs ADX∧DI unanimous** (Variant B central question):

| Config | trades | median OOS | sharpe | sign | total |
|---|---:|---:|---:|:---:|---:|
| ADX solo | 1,693 | $1,174 | 4.02 | 7/7 | $4,058 |
| DI solo | 1,693 | $1,510 | 2.30 | 7/7 | $7,426 |
| **ADX∧DI unanimous** | **949** | **$1,082** | **5.32** | **7/7** | **$5,803** |

**Outcome 3: unanimous wins.** Higher Sharpe than either solo. The 744 trades where ADX and DI disagreed got SKIPPED, and those skips are where the variance reduction comes from.

**2. Variant A LOOs ranked by improvement (Δsharpe vs Full5=0.87):**

| Removed indicator | LOO sharpe | Δ vs Full5 | Interpretation |
|---|---:|---:|---|
| **ATR** | 2.00 | **+1.13** | Biggest drag — pure noise |
| **DI** | 1.37 | +0.50 | Drag in 5-stack (73% TREND bias clashes with FADE-leaning ATR/VWAP) |
| **ROC** | 1.15 | +0.28 | Modest drag |
| VWAP | 0.78 | −0.09 | Roughly neutral |
| **ADX** | 0.48 | **−0.39** | Structural carry — removing hurts most |

ADX is the structural carry. ATR and ROC are confirmed drags. DI is paradoxical — drag in the 5-stack but the BEST partner for ADX in the 2-stack.

**3. Variant B vs best Variant A LOO:**

| Config | sharpe | median | sign | trades |
|---|---:|---:|:---:|---:|
| **B ADX∧DI** | **5.32** | $1,082 | 7/7 | 949 |
| A LOO-ATR (best A LOO) | 2.00 | $658 | 7/7 | 538 |

Variant B wins by 2.66 sharpe. The deployment-relevant tight 2-corner stack dominates the framework-faithful pruned stack.

**Deployment-qualifying configs (ranked by sharpe):**

| Rank | Config | sharpe | median | sign | total |
|---:|---|---:|---:|:---:|---:|
| 1 | **B ADX∧DI unanimous** | **5.32** | $1,082 | 7/7 | $5,803 |
| 2 | A solo ADX | 4.02 | $1,174 | 7/7 | $4,058 |
| 3 | A solo DI | 2.30 | $1,510 | 7/7 | $7,426 |
| 4 | A LOO-ATR | 2.00 | $658 | 7/7 | $2,790 |
| 5 | A LOO-DI | 1.37 | $247 | 6/7 | $940 |
| 6 | A LOO-ROC | 1.15 | $300 | 6/7 | $2,116 |

---

## Phase 7 diagnostics

### 1. Window-trend regression

Linear regression of OOS P&L vs window index W1..W7 for each deploy-qualifying config. Tests whether the signal is decaying or strengthening across time. (df=5 for OLS; |t| > 2.57 ≈ p<0.05 two-tailed.)

| Config | sharpe | slope $/window | r² | t-stat | W1 → W7 drift | Verdict |
|---|---:|---:|---:|---:|---:|---|
| **B ADX∧DI** | 5.32 | **+$33** | 0.12 | +0.83 | $+304 | **Healthy — no decay** |
| ADX solo | 4.02 | **+$100** | 0.54 | +2.44 | $+902 | **Strengthening** (significant) |
| DI solo | 2.30 | −$230 | 0.57 | **−2.59** | $−1,186 | **Significant decay** |
| LOO-ATR | 2.00 | −$48 | 0.10 | −0.75 | $−409 | Mild decay |
| LOO-DI | 1.37 | −$57 | 0.47 | −2.09 | $−362 | Borderline decay |
| LOO-ROC | 1.15 | −$99 | 0.68 | **−3.26** | $−503 | Significant decay |

**Critical finding: the unanimous filter fixes DI's solo decay.** DI alone shows significant negative drift (−$230/window, t=−2.59). When AND-gated with ADX, the composite's slope is +$33/window with no statistical decay signal. The deployment winner has the healthiest signal of any qualifying config.

ADX solo is the only config with significant POSITIVE drift — its signal is strengthening over time.

### 2. DI(15,8) discrimination check

DI labels 73% TREND / 27% FADE. The question: is DI selecting high-conviction clusters, or just imposing a directional bias that happened to fit history? Compared against 30 `BiasedRandom(seed, trend_prob=0.73)` seeds — same TREND bias, otherwise random.

| Metric | DI(15,8) actual | Random p50 | Random p95 | Random max | DI percentile |
|---|---:|---:|---:|---:|---:|
| Sharpe-like | **2.30** | −0.11 | 0.66 | 0.90 | **100%** |
| Median OOS | **$1,510** | −$216 | $708 | $889 | **100%** |
| Total P&L | **$7,426** | $778 | $3,844 | $4,256 | **100%** |

**Strongest possible discrimination result.** DI's actual scores exceed every single one of 30 same-bias random labelings on all three metrics. DI is genuinely SELECTING good clusters, not merely imposing a directional bias.

For comparison, DI sharpe (2.30) is 2.5× the maximum random sharpe (0.90), DI median ($1,510) is 1.7× the max random median ($889), and DI total ($7,426) is 1.7× the max random total ($4,256). The selection effect alone (separating signal from the directional bias) is worth ~$3,500 in total P&L.

### 3. AllFade vs ADX∧DI on 2026 Jan-Apr (4-month partial)

The most recent unverified data:

| | trades | total P&L | win rate |
|---|---:|---:|---:|
| AllFade (locked baseline) | 189 | **+$1,620** | 57.7% |
| ADX∧DI unanimous (deployment) | 113 | +$199 | 51.3% |

**Monthly breakdown:**

| Month | AllFade P&L (n) | ADX∧DI P&L (n) | Δ |
|---|---:|---:|---:|
| 2026-01 | +$480 (67) | +$139 (38) | −$341 |
| 2026-02 | +$541 (56) | −$60 (41) | −$601 |
| 2026-03 | +$360 (40) | −$120 (24) | −$480 |
| 2026-04 | +$240 (26) | +$240 (10) | $0 |
| **Total** | **+$1,620** | **+$199** | **−$1,422** |

**Material concern.** In 3 of 4 recent months, ADX∧DI underperformed AllFade. The unanimous filter removed 76 trades that AllFade took; those 76 trades net-contributed to AllFade's outperformance.

The 7-year sharpe of 5.32 doesn't show this — it averages across 7 OOS windows where the composite was strong (median per-window $1,082). The 4 recent months are a small sample but represent the regime most relevant to deployment.

Possible interpretations:
- **(a) Small-sample noise on 4 months / 113 trades.** Reasonable null hypothesis; can only be tested with more forward data.
- **(b) Regime drift starting.** The 2024-2026 favorable-fade regime is asserting itself enough that the unanimous filter's TREND inversions are net-negative in this period.
- **(c) Generalization failure.** The composite's edge is specific to the historical periods that dominated the walk-forward windows, not to current conditions.

Distinguishing (a) from (b)/(c) requires forward data.

---

## Honest framing

**This was cross-window OOS evaluation, not pure walk-forward.** Same parameters across all 7 walk-forward windows. Parameter combinations were judged by their cross-window OOS Sharpe-like, and we picked the combo that maximized this score. IS data implicitly informed our parameter choices.

The 7 OOS windows OVERLAP (1y OOS, 6mo advance) — the same trades contribute to multiple windows' evaluations. This is a softer test than pure walk-forward (per-window parameter selection on disjoint OOS).

**What supports the result being real signal, not artifact:**
- Sign stability 7/7 across overlapping windows. **None of 50 random seeds in the null distribution hit 7/7** — best was 6/7. Joint probability under any independent null is extremely small.
- Surface coherence in Phases 1-2: top ADX and DI configs cluster in stable regions of the parameter space, not isolated points.
- Mechanism is interpretable: ADX measures trend strength via directional movement; ±DI measures directional pressure spread.
- DI discrimination check: DI's edge beats 100% of same-bias random labelings on all three metrics. The selection IS doing work, not just the directional bias.
- ADX solo has POSITIVE window-trend slope (+$100/window, significant) — signal strengthens, doesn't decay.
- Unanimous filter has NO decay (slope +$33, insignificant) — the filter fixes the only decay signal we found (DI solo at −$230/window).

**What doesn't fully eliminate concern:**
- 2026-partial underperformance vs AllFade (−$1,422 over 4 months).
- DI solo's significant negative window-trend slope. The composite "fixes" this, but the fix may not extend to future regimes if both ADX and DI lose signal simultaneously.
- Cross-window OOS is informationally weaker than pure walk-forward.
- The 7-year dataset includes only ~135 trades/year on the deployment winner. With 7 OOS windows of ~135 trades each, statistical power is moderate.
- The Panama back-adjusted price scale changes ~4× over the dataset (6,000 in 2019 → 25,000 in 2026). This affects fixed-point indicators (ROC tested in points) more than ratio-based indicators (ADX, ±DI, ATR ratio). The deployment winner uses ratio-based indicators so this concern is minimal but worth noting.

**Honest threshold:** This is *good evidence* of signal, not *proof*. The composite was selected from the data; deployment confidence must come from forward validation.

---

## Forward-test recommendation

**Do not deploy live based on historical Sharpe-like alone.** The 2026-partial result is too inconsistent with the 7-year average to deploy without forward validation.

### Required forward test

- **Period:** Minimum 6 months paper trading. Suggested window: 2026-05-13 through 2026-11-13.
- **Expected trade volume:** ~70 trades (based on the 7-year rate of ~135 trades/year for the deployment winner).
- **Tracking:** Daily P&L, monthly cumulative, max drawdown, sign per month, FADE/TREND split, comparison-vs-AllFade on the same period.

### Pass criteria (all must hold)

- **Cumulative P&L over 6 months > $0.**
- **≥ 4 of 6 months with positive P&L** (matches walk-forward sign stability of ≥6/7).
- **Maximum drawdown from peak ≤ $2,000 sustained for > 30 days.** (~50% of the 7-year max DD observed at locked baseline of $1,350.)
- **No 3 consecutive losing months.**
- **2026-partial underperformance vs AllFade does NOT continue into Q3-Q4.** If forward shows ADX∧DI persistently below AllFade, abandon regardless of absolute P&L.

### Invalidating triggers (any one)

- Cumulative 6-month P&L < $0.
- Drawdown from peak > $2,000 sustained for > 30 days.
- 3+ consecutive losing months.
- 4+ of 6 forward months negative (mirror sign-stability failure).
- AllFade outperforms ADX∧DI by > $1,000 cumulative across the forward period (the 2026-partial pattern persisting).

### If forward test passes

Deploy with 1-contract sizing. Continue monitoring monthly. Re-evaluate after 12 months of live trading or any single 3-month losing stretch.

### If forward test fails any trigger

Abandon v2 deployment. Return to evaluating whether the strategy has any deployable form at all, given the locked baseline fails OOS historically (R-006) and the v2 composite shows recent underperformance.

---

## Artifacts

- `results/archive/trades_regime_v2_20260512.parquet` — deployment-winner trades (949 trades, +$5,803)
- `results/archive/composite_20260512/` — Phase 6 full output (12 configs)
- `results/archive/sweep_{adx,di,roc,atr,vwap}_20260512/` — per-indicator sweeps
- `results/archive/phase0_20260512/` — infrastructure validation
- `results/archive/phase0_null_20260512/` — 50-seed null distribution
- `results/archive/phase7_20260512/` — window-trend, discrimination, 2026 comparison

Source modules:
- `src/indicators/{base,adx,di,roc,atr,vwap}.py` — classifiers
- `src/simulator_v2.py` — locked geometry + per-cluster classifier hook
- `src/walk_forward.py` — 7-window harness + scoring + qualification gates
- `src/phase6_run.py` — composite runner
- `src/phase7_analysis.py` — diagnostic analyses

---

## Conclusion

The v2 regime classifier investigation produced a clean signal-vs-noise separation: ADX and ±DI work as per-cluster regime classifiers; ROC, ATR, and VWAP do not. The unanimous AND-gate over the two working indicators (ADX(15,30) ∧ DI(15,8)) produces the strongest single config tested — sharpe-like 5.32 across 7 walk-forward OOS windows, every window positive, every calendar year positive over 8 years, and per-window distribution remarkably tight ($763-$1,340).

The discrimination check confirms DI is genuinely selecting clusters (100th percentile vs 30 same-bias random labelings). The window-trend regression shows the composite has no decay despite DI solo having significant negative decay — the unanimous filter does real work.

The deployment recommendation is conditional on a 6-month forward test, with specific pass/fail criteria. The 2026-partial underperformance vs AllFade (−$1,422 over 4 months) is the single most material concern and must be tracked closely in any forward period.

This investigation took a strategy that loses $3,378 historically over 7 years and identified a derived configuration that wins $5,803 with consistent sign across all windows. That's a real result on the historical data. Whether it generalizes forward is the next question.
