# Deployment Plan — within_200 / 30 / 20

Locked config (see `docs/SESSION_HANDOFF.md` for the full decision trail):

```
gate=within_200 · gap=7 · ms=2 · lookback=200 · entry=center · buffer=1.0
stop=30 · target=20 · forced_exit=11:30 ET · no ADX · no BE
```

Backtest 2019-2026, $2/RT, 0.5pt/side Model A slippage:
**1394 trades · WR 77.3% · net $19,690 · PF 1.990 · Sharpe 5.35 · max_dd $-455**

---

## 1. Sizing — "size into the Sharpe"

The historical edge per 1 contract over 7 years (Model A, all costs included):

| metric per 1 contract | value |
|---|---|
| trades/yr | ~199 |
| net/yr | ~$2,810 |
| max DD | $-455 (0.91% of $50k starting equity) |
| worst rolling 3-mo | $-69 |
| Sharpe | 5.35 |

The strategy's DD is tiny relative to its income; that's the Sharpe paying out. Sizing
should scale the same way: pick a size such that the *historical* max DD is comfortable
on the live account, knowing live DD can easily be 2-3× backtest. **Do NOT pick size
based on expected $/yr — pick it based on tolerable DD, then accept the resulting $/yr.**

### Suggested ramp
Live max-DD tolerance is the binding constraint. For an account of size `A`:

| ramp stage | contracts | expected $/yr | historical max DD | sized DD as % of A=$25k |
|---|---|---|---|---|
| **paper** | intended-live size (e.g. 2) | $5,620 | $-910 | 3.6% |
| **stage 1 (live, weeks 1-4)** | 1 | $2,810 | $-455 | 1.8% |
| **stage 2 (weeks 5-12)** | 2 | $5,620 | $-910 | 3.6% |
| **stage 3 (month 4+)** | 3 | $8,430 | $-1,365 | 5.5% |

Numbers are *historical* — apply a 2× buffer mentally for the live DD you should be
prepared to sit through. With size = 3 the historical max DD was 5.5% of a $25k account;
under a 2× live multiplier that's ~11% — about the boundary of "uncomfortable but not
account-threatening" for most retail tolerance.

**Rule:** never start at max size. The ramp is not about edge decay — it's about you
becoming comfortable taking the signal at full size before the inevitable cold streak
arrives. Paper-trading at the *intended* size (not 1 contract) does the first half;
stage 1-2 live does the second.

---

## 2. Paper-trade — at the intended live size, not 1 contract

The point of paper-trading is to test fill quality, not to verify the math. Single-
contract MNQ has different fill characteristics than 2-3 contracts (slightly worse
slippage, more partials on the entry-bar limit fills at the 09:45 trigger).

- **Duration:** 1-2 calendar months (live market hours)
- **Size:** same as intended stage 1-2 live (not 1)
- **Broker:** the broker you intend to deploy on. Paper fills at most retail brokers
  approximate live for liquid futures like MNQ; the differences appear at the partial /
  multi-tick-slippage level.
- **Log every fill** — entry trigger vs entry fill, target limit vs fill, stop vs fill.

If paper shows realized slippage > 0.5 pt/side average on entries, that's the canary —
the Model A baseline starts to bend. Re-run the cost stress test with the observed
slippage before going live.

---

## 3. Tripwires — review (not stop) if these fire

| tripwire | historical worst | live cutoff |
|---|---|---|
| max DD per contract | $-455 | **$-1,000** (≈ 2×) |
| consecutive losing trades | 5 ($-272) | **10 trades** (≈ 2×) |
| consecutive losing days | 5 | **10 days** |
| dark streak (no signal) | 14 sessions | **20 sessions** |
| worst rolling 3-month per contract | $-69 | **$-300** (≈ 4×, since baseline is near-zero) |

"Review" = pause new entries, compare against the live-vs-backtest tracking
dashboard (§4), decide whether to resume / size down / kill. "Stop" should be a
human decision, not automatic — but the tripwire forces the conversation.

---

## 4. Live-vs-backtest tracking — decay shows up here first

Track these per week. Significant deviation from backtest baseline is the early
warning of edge decay, regime change, or execution issues:

| metric | backtest baseline | acceptable live range | action if outside |
|---|---|---|---|
| **win rate** | 77.3% | 70-82% | <70% sustained → review |
| **realized slippage per side** | 0.5pt assumed | ≤0.75pt | >0.75pt → re-cost the strategy |
| **% target-limit fills (target exits)** | 76.6% | ≥70% | <70% → execution diagnosis |
| **avg hold (min)** | 5-9 (target hits ~7) | 5-15 | sharp drop → slippage/spike; sharp rise → trend regime |
| **trades/wk** | ~3.8 (after dark-streak smoothing) | 1-7 | <1 sustained → gate is mis-firing; >7 → check candidate density |
| **PF (rolling 60 trades)** | 1.99 full-period; 25th pct >1.2 (estimate from history) | >1.0 | <1.0 for two windows → review |

Reuse `src/dashboard.py` as the live tracking surface — add a `results/live_trades.csv`
ingestion and a panel comparing rolling live numbers vs the locked backtest baseline.

---

## 5. What to expect during live — normalize the cold patches

Most strategies fail not because the edge died but because the operator bailed during
a normal cold patch. Pre-load the user with what's historically normal:

- **~55% of calendar days are spent underwater from peak.** The strategy makes most of
  its money on a small fraction of "good runs" punctuating long flat stretches. This is
  *expected*, not a malfunction.
- **Dark streaks** (no signal for N consecutive sessions): median 2, p90 8, p95 10,
  observed max 14. **A 7-session streak is active as of 2026-05-08** — that is *within
  the normal distribution*, but new operators tend to assume "something's broken" after
  3 silent days.
- **1-2 losing days in a row are normal.** A 5-day streak has happened once (2020-12-24
  → 2020-12-31). Anything past 5 days starts to be unusual.
- **Negative skew on individual trades.** Stop = 30 pts, target = 20 pts → individual
  losers are bigger than individual winners (by design); the 77% win rate is what makes
  the math work. The first few stops you see live will *feel* like losing 1.5× a normal
  win — that's correct.

---

## 6. Event risk — the unmodeled tail

The backtest matches actual MNQ bars 2019-2026. It does NOT model:

1. **09:45 entries hold through 10:00 data releases and surprise news.** ISM
   manufacturing (10:00 ET on the 1st business day of each month), GDP, FOMC
   minutes (Wednesdays at 2:00 — outside our exit window so safe), Powell unscheduled
   remarks, etc. A trade entered at 09:45 will still be open at 10:00 ≥95% of the
   time (median hold is 10 min). On a 10:00 release with a 50-pt spike, our 30-pt
   stop becomes a 50-100-pt slippage event.

2. **Spike-through fills on stops.** The 30-pt stop assumes a stop *order* is fillable
   at stop_p ± 0.5pt slip. On a vertical 5-second spike, the actual fill can be 3-10
   pts beyond the stop. This is the tail risk that NEVER shows up in 1-min OHLCV data
   because the bar's `low` value is the trough, not the fill price.

3. **Holiday early-closes.** The forced-exit logic assumes 11:30 ET is a valid bar.
   On early-close days the next bar with time ≥ 11:30 may be in the evening session,
   producing the occasional 8-hour-hold outlier. Observed: 1 trade out of 1394 (0.07%).
   Material rather than catastrophic, but flag-worthy.

### Recommended near-term enhancements (not blockers)
- **Econ-calendar skip.** Skip new entries on days with a ≥10:00 ET high-impact release
  (FOMC, NFP, CPI, ISM, GDP). A simple `data/econ_calendar.csv` + a per-day skip flag
  in the signal pipeline. Expected effect: trades drop slightly, tail risk drops a lot.
- **Hard time-stop at 09:55 or 10:00.** Forcing exit ~5 minutes before the most common
  release time bounds the event-risk exposure. Costs some target hits; quantify against
  the current 5.7% time-exit rate before committing.
- **Live stop-fill audit** during paper-trade: when a stop fires, log (stop_p, actual
  fill, slippage_pts). If avg stop slippage > 1pt/side, re-cost the strategy with
  asymmetric slippage (stops slipped more than entries).

---

## Sign-off checklist before going live

- [ ] 1-2 month paper-trade at intended-live size complete
- [ ] Realized slippage ≤ 0.75pt/side average
- [ ] % target-limit fills ≥ 70%
- [ ] Live WR within 70-82% range
- [ ] No tripwire fired during paper-trade (or if any fired, root-caused)
- [ ] Account size such that 2× historical max DD per contract is < 5% of equity
- [ ] Operator has internalized §5 (cold patches are normal)
