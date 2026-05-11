# V2 Regime Classifier — Design Spec

**Date:** 2026-05-11
**Status:** SPEC ONLY. **No code written yet.** Resume here tomorrow.

---

## Motivation

The current hybrid regime classifier in `simulator_hybrid.py` uses a single metric:
```
expected_normalized_distance = (limit_price - 9:46_NY_open) / lagged_ATR_10
```
with `|d| <= 0.09` → "flat" → reverse to breakout, else "directional" → fade.

Today's 7-year extension showed this classifier **sign-flips between periods** — the directional cell loses $3,884 historically vs +$2,406 in-sample, and the flat cell does the opposite. Same indicator, opposite payoff. **The classifier doesn't measure trend strength — it measures the relative proximity of a single cluster boundary to the session-open price, which is a property of the cluster geometry rather than the market regime.**

To distinguish trend regimes from chop regimes we need proper trend-strength indicators evaluated **at the daily timeframe** (not intraday), computed from data **available before the session starts** (no look-ahead).

---

## Proposed indicator set

All computed daily, using prior-session-close data (no look-ahead). Lag by 1 session.

| Indicator | Definition | Use |
|---|---|---|
| **ADX(14)** | Average Directional Index over 14 daily bars | Trend strength magnitude |
| **+DI(14) / −DI(14)** | Directional indicators (positive/negative) over 14 daily bars | Trend direction |
| **ROC(10)** | Rate-of-change of close over 10 days, `(close_T-1 - close_T-11) / close_T-11` | Trend confirmation (signed) |
| **ATR(14)** | True range avg over 14 days | Volatility baseline |
| **ATR(50)** | True range avg over 50 days | Volatility baseline (longer) |
| **ATR(14) / ATR(50)** ratio | Recent vs long-run volatility | Expanding (>1) vs contracting (<1) volatility |
| **Session VWAP, anchored 9:30 NY** | Volume-weighted average price from session open | Intraday trend reference (computed in real time at 9:46) |

Some sub-options to consider (intraday vs daily; see Open Decisions below).

---

## Proposed regime taxonomy

Evaluated each session at 9:46 NY using yesterday's-close daily indicators + today's 9:30–9:46 session-VWAP if applicable:

| Regime | Conditions | Action |
|---|---|---|
| **TRENDING_UP** | `ADX >= 25` AND `+DI > -DI` AND `price >= VWAP` | Trade only **LONG**-side clusters (BUY setups where `cluster.high < 9:45_close`); skip SELL setups |
| **TRENDING_DOWN** | `ADX >= 25` AND `-DI > +DI` AND `price <= VWAP` | Trade only **SHORT**-side clusters (SELL setups where `cluster.low > 9:45_close`); skip BUY setups |
| **SIDEWAYS** | `ADX < 20` | Fade both directions (current locked-baseline behavior) |
| **MIXED / NEUTRAL** | Anything else: 20 ≤ ADX < 25, or trending indicators conflict (ADX strong but DI/VWAP disagree) | **Skip the session entirely** |

Rationale: in a strong uptrend, fading sell-clusters (limits above price waiting for a top) is fighting the trend; in chop, the original fade strategy is the right one; in unclear regimes, do nothing.

---

## Six open design decisions to resolve tomorrow

### Decision 1 — Timeframe for trend indicators

Daily vs intraday (e.g. 5-minute ADX from prior session). **Default proposal: daily.** Justification: daily indicators are slower-moving, less noisy, and align with the session-level regime classification. Intraday ADX would add another variable to fit.

### Decision 2 — VWAP anchor point

Options: (a) 9:30 NY (session open), (b) 18:00 prior-day NY (overnight session anchor), (c) skip VWAP entirely. **Default proposal: 9:30 NY.** Justification: matches the strategy's session-level decision-making (we don't trade overnight). At 9:46 we have 16 minutes of post-9:30 data for the VWAP — usable. Caveat: VWAP at 9:46 with only 16 bars is noisy; consider downgrading to "price ≥ ORB_close" as a simpler intraday-direction proxy.

### Decision 3 — Aggressiveness of regime filtering

How strict to be:
- **Strict (proposed default):** with-trend only in strong trends (ADX ≥ 25 AND DI agrees AND VWAP agrees)
- **Moderate:** with-trend in strong trends (ADX ≥ 25 AND DI agrees); ignore VWAP
- **Loose:** with-trend in any clear trend (ADX ≥ 20 AND DI agrees)

The stricter, the fewer trades we take. Strict cuts the most weak-edge entries but also kills sample size. Probably worth testing all three.

### Decision 4 — Sideways regime behavior

When ADX < 20:
- **Default proposal: fade clusters (current locked behavior).** Justification: this is where mean reversion theoretically works. Inherits the locked baseline's behavior — but on a filtered subset that should be more favorable.
- Alternative: also fade, but only when prior-session range was contained (low-volatility regime continuation).

### Decision 5 — Mixed/neutral handling

When indicators conflict or ADX is in 20–25 limbo:
- **Default proposal: skip the session entirely.**
- Alternative: trade only the higher-quality clusters (`size >= 5` or some threshold). Hybridizes with the C2 diagnostic finding about cluster quality.

### Decision 6 — Code structure

Proposed module layout:
- `src/regime_v2.py` — pure module computing regime label per session_date (returns dict `{TRENDING_UP, TRENDING_DOWN, SIDEWAYS, MIXED}`). Like `clusters.py`, no I/O, no simulator state.
- `src/simulator_regime_v2.py` — sibling of `simulator.py` that imports `regime_v2.classify_session(...)` and gates trade direction by the regime label.

**Default proposal: above structure.** Justification: separates the regime classifier (testable independently against historical regimes) from the entry/exit mechanics (already trusted). Easy to A/B test against the locked simulator.

---

## Important caveat

Even with a perfect regime classifier, **the strategy still has the same geometry**: ORB-cluster entries at fixed levels, 30-point bracket, 9:46–11:30 window, C2 one-position-at-a-time, fixed stop-target distances. Today's investigations identified at least three properties that are independent of regime detection:

1. **Forward lockout (2026-05):** the 200-session level pool is structurally below current price in a strong rally; no clusters form near current price, no trades fire. Regime detection wouldn't help — there are no signals to filter.
2. **Cluster-size quality:** the C2 rule permanently skips larger clusters when smaller ones fire first (2024-08-12 case). Regime detection doesn't address this.
3. **Stop/target asymmetry:** 30 points reflects MNQ's natural mean-reversion magnitude at this timeframe; widening hurts (see 40/40 variant). Regime detection doesn't change this.

**If the strategy's bottleneck is the geometry rather than regime detection, a v2 classifier alone won't make the strategy profitable.** Worth running the v2 variant and seeing what the historical OOS looks like, but the expected result might be "smaller loss, still not winner."

---

## Resume checklist for tomorrow

1. Read this document and `docs/research-log-2026-05-historical-extension.md` to refresh context
2. Walk through the **six open decisions** with the user and lock in defaults or revisions
3. Implement `src/regime_v2.py` (pure classifier) — unit-tested against a few hand-computed sessions
4. Implement `src/simulator_regime_v2.py` — wraps the entry logic with regime gating
5. Run on 7-year extended dataset; output to `results/archive/trades_regime_v2_YYYYMMDD.parquet`
6. Compare to extended fade-only baseline and hybrid 30/30 on the same three slices (historical OOS / in-sample / forward)
7. Honest report: does v2 survive historical OOS, or does it just shrink the loss?

---

## Status: SPEC ONLY

No code committed for v2. No simulator runs. The framework above is a design proposal awaiting decisions 1–6 to be resolved tomorrow.
