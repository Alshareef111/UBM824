# Session Handoff

## CURRENT STATUS (end of session 2026-05-23)

### Final locked config
```
gate            within_200       (cluster center within 200 pts of 09:45 / OR-close price)
lookback        200 sessions
gap             7.0 pts
min_size        2 levels
entry_location  center
entry_buffer    1.0 pt
stop            30 pts
target          20 pts
forced_exit     11:30 ET (entry window 09:45-11:29)
ADX/DI filter   NONE (dropped — see reversal #1 below)
costs (model)   $2/RT commission, 0.5pt/side slippage Model A (target=limit)
```

### Headline metrics, full period 2019-2026 (Model A, $2/RT, 0.5pt slip)
```
1394 trades · WR 77.3% · net $19,690 · PF 1.990 · Sharpe 5.35 · max_dd $-455
Train PF 1.896 → Test PF 2.097 → Holdout PF 1.986
89.3% positive months · worst rolling 3-month -$69 · worst losing streak 5 trades / -$272
```

### Reversals vs prior handoff (2026-05-21)
This session overturned three locked decisions from the previous handoff:

1. **ADX/DI filter DROPPED.** Old config used (30, 8) SKIP-only filter, which lifted PF on
   inside_OR. On within_200 it cuts 70% of trades for negligible PF gain on full period and
   *degrades* holdout PF (1.504 → 1.390). The filter's edge was specific to inside_OR's
   sparsity; under within_200 it is dead weight, possibly a regime artifact.
   → `results/within200_adx_grid.csv`

2. **Gate: inside_OR → within_200.** Old rule "cluster center must be inside today's OR"
   discards positive-EV setups; relaxing to "cluster center within 200 pts of 09:45 price"
   dominates inside_OR on PF, net, and Sharpe across every walk-forward split. No-gate
   (all clusters) marginally improves net but degrades PF/max_dd — within_200 is the
   sweet spot, not the corner.
   → `results/vbt_gate_proximity_sweep.csv`, `results/within200_validation.csv`

3. **Target: 40 → 20.** Full 5×5 TP/SL surface shows the entire `target=20` column above
   PF 1.95 regardless of stop. Not an argmax artifact — it's a broad region. 30/20 was
   chosen over 40/20 by marginal Sharpe/PF; 40/20 is the safe alternative.
   → `results/within200_tp_sl_grid.csv`

### 4 validation gates passed (no walk-forward until all four)
1. **Fill realism** — engine is already pessimistic (stop-first); <1.6% of trades hit
   ambiguous bars even at 20-pt target; pessimistic-vs-optimistic ΔPF tiny.
   → `results/within200_fill_realism.csv`
2. **Slippage stress** — Model A breakeven slippage 4.05 pts/side (16.2 ticks); realistic
   0.5pt/side leaves the tight-cell PF advantage intact.
   → `results/within200_slippage.csv`
3. **Walk-forward** — train PF 1.896 → test 2.097 → holdout 1.986. Edge is every-year
   (2020 smallest Δ vs 40/40 at +0.25; 2022 largest at +0.89), not regime-concentrated.
   → `results/within200_tight_walkforward.csv`
4. **Move-stop-to-BE falsification** — BE at B∈{5,10,15} all destructive on 20-pt target
   (winners spend time at +5/+10 en route, getting pulled prematurely). No BE in locked
   config.
   → `results/within200_breakeven_stop.csv`

### Risk audit
- Max DD $-455 (0.91% of $50k starting equity) — single episode 2020-06-12 → 2020-09-21
  (101 calendar days; depth and duration coincide)
- 89.3% of 75 months positive · best $851 · worst $-179 · worst rolling 3M -$69
- Trade-P&L skew -1.31, excess kurtosis -0.26 (sub-Gaussian, no fat-tail risk visible)
- Worst single loss $-64 · worst losing-trade streak 5 ($-272) · worst losing-day streak 5
- Dark streaks (no-candidate sessions under within_200): median 2, p90 8, max 14;
  CURRENT trailing 7-session streak still active (2026-04-30 → 2026-05-08)
→ `results/within200_3020_risk_audit.csv`

### What's pending / next step
Deployment prep. See `docs/DEPLOYMENT_PLAN.md`.

## KEY FILES

### Source (used by locked config)
- `src/data.py` · `src/signals.py` · `src/vbt_backtest.py` · `src/indicators.py`
- `data/processed/mnq_unadjusted_1m.parquet` (canonical bars)

### Result CSVs powering the lock decision
| file | what it shows |
|---|---|
| `vbt_pairwise_sweep.csv` | 120-cell lb×gap×ms sweep — original C config baseline |
| `vbt_gate_proximity_sweep.csv` | 54-cell gate sweep — where within_200 was discovered |
| `within200_validation.csv` | walk-forward for all gates; per-year breakdown |
| `within200_adx_grid.csv` | ADX filter falsification on within_200 |
| `within200_robustness.csv` | buffer / forced_exit / earliest_entry sensitivity |
| `within200_entry_geometry.csv` | offset + reference-point sensitivity |
| `within200_tp_sl_grid.csv` | 5×5 TP/SL surface |
| `within200_fill_realism.csv` | ambiguous-bar audit + pess/opt spread |
| `within200_slippage.csv` | slippage decay + breakeven cost |
| `within200_tight_walkforward.csv` | 30/20 + 40/20 + 20/20 walk-forward |
| `within200_breakeven_stop.csv` | BE-stop falsification |
| `within200_3020_risk_audit.csv` | full risk audit for locked config |

### Dashboard
- `results/dashboard.html` — rebuild with `python -m src.dashboard`.
  Panels read directly from the CSVs above; auto-skips any missing source.

## OPEN HYPOTHESES (research leads, not blockers)
1. **09:50 entry anomaly** — pushing earliest entry from 09:45 → 09:50 lifts PF from 1.468
   to 1.585 (raw within_200, no other changes). Possibly real (avoids first-bar fake
   breakouts) or possibly in-sample. Not validated walk-forward.
   → tested in `results/within200_robustness.csv`
2. **Cluster ≠ S/R levels.** The fact that within_200 (proximity to price) dominates
   inside_OR (proximity to OR band) suggests clusters are functioning as a *session
   selector* — "is today's price near historical OR action" — rather than as
   support/resistance levels. The 7-pt clustering gap is then a smoothing radius, not
   a tightness threshold for level density.

## REVERSED HYPOTHESES (closed this session)
- (Old #1) "Clusters may act as session selector, not S/R" → CONFIRMED. Drove gate change.
- (Old #2) "ADX filter is an exposure modulator, not a regime detector" → CONFIRMED, and
  on within_200 it turns out the modulation is net-negative.

## REPRODUCTION
- `.venv/bin/python` for everything
- Reproduce the locked-config metrics: the analysis lives in ad-hoc heredoc scripts in
  the session log; the canonical pipeline is `src/vbt_backtest.py` for legacy 40/40 +
  the within_200 logic inlined in the heredocs (gate, custom slippage model). A
  `src.run_locked` CLI module would be a worthwhile cleanup but is not yet written.
