# IMPORTANT — read these files NOW before responding to anything

Before answering ANY user request in this project, read these files in order:
1. docs/strategy-spec.md (the locked rules)
2. docs/decisions.md (why each rule exists)
3. docs/results-log.md (what has already been tested)

After reading, internalize:
- The locked baseline is 526 trades, 52.9% win rate, +$1,975. Do NOT overwrite data/processed/trades.parquet.
- All paths come from src/paths.py. Never use Path(__file__).parent.
- New experiments save to results/archive/ with descriptive names.
- After any experiment, append an R-XXX entry to docs/results-log.md.

Only after reading those three files should you respond to the user's actual request. Do not skip this step even if the request seems simple.

---

# MNQ ORB-Cluster Mean-Reversion Strategy Backtest

## What this project is

A backtest of a futures trading strategy on MNQ (Micro E-mini Nasdaq-100). The strategy enters limit orders at clusters of historical Opening Range Breakout (ORB) levels, expecting mean reversion. Built on 7 years of 1-minute bars from Databento (May 2019 to May 2026), with optional tick-level verification on a 7-week overlap (March to May 2026). The original 2-year in-sample window (Apr 2024 – May 2026) is what produced the locked baseline; the 5 historical years (May 2019 – Mar 2024) and 5 forward sessions (May 2026) provide out-of-sample evaluation.

## Strategy in one paragraph

Each NY trading session, compute the Opening Range from 9:30 to 9:45 AM (high and low). Maintain a rolling pool of the last 200 sessions' ORB highs and lows, plus today's (402 levels total). Find clusters where 3 or more levels have every adjacent pair within 3 points (Option B, chain rule, not diameter). Classify each cluster vs the 9:45 close: above price equals sell setup, below price equals buy setup, spanning price equals skip. During 9:46 to 11:30 NY, place resting limit orders at the cluster boundary closest to the price. First-touch entry. 30-point fixed stop, 30-point fixed target (1:1 R:R). One position at a time. Force close any open position at the 11:30 bar open.

## Current results (baseline, locked)

- 526 trades over 540 sessions (Apr 2024 to May 2026)
- 52.9% win rate (278 W / 247 L / 1 flat)
- +987.5 points = +$1,975 gross (no commissions)
- Exits: 271 target / 237 stop / 18 force-close
- Yearly: 2024 +$436 / 2025 -$81.50 / 2026 +$1,620.50
- Max drawdown: -$1,349.50 over 369 days
- Worst month: 2025-05 (-$695)
- Edge is statistically weak (~1.3 sigma above breakeven, p approx 0.09)

## Repository layout

MNQ-Strategy/
- CLAUDE.md (this file)
- README.md (human-facing intro)
- docs/strategy-spec.md (full strategy rules and all decisions)
- docs/decisions.md (why we chose each option)
- docs/results-log.md (all configs tested and outcomes)
- data/raw/ (Databento CSV, JSONs, tick file symlink)
- data/processed/ (parquet outputs, regenerable)
- src/paths.py (all file paths centralized, import from here)
- src/clusters.py (pure module, find_clusters)
- src/data_prep.py (raw CSV to BARS_PARQUET and ROLLS_PARQUET)
- src/orb.py (BARS_PARQUET to ORB_TABLE_PARQUET)
- src/simulator.py (bar-based backtest to TRADES_PARQUET)
- src/visualize_trade.py (session charts to results/charts/)
- src/ambig_check.py (flags same-bar stop and target)
- src/robustness.py (yearly, monthly, drawdown stats)
- src/build_tick_cache.py (tick text to TICKS_OVERLAP_PARQUET)
- src/tick_simulator.py (tick-based backtest verification)
- src/verify_ticks.py (bar vs tick discrepancy report)
- results/charts/ (all PNGs)
- results/archive/ (orphaned, historical outputs)

## How to run

All commands from project root (~/Desktop/MNQ-Strategy/):

- python3 src/data_prep.py (raw CSV to adjusted bars)
- python3 src/orb.py (compute ORB table)
- python3 src/simulator.py (run backtest, writes trades.parquet)
- python3 src/robustness.py (yearly, monthly stats)
- python3 src/ambig_check.py (ambiguous-bar audit)
- python3 src/visualize_trade.py (generate session charts)

Tick verification pipeline (requires Google Drive synced for the tick file symlink):

- python3 src/build_tick_cache.py
- python3 src/verify_ticks.py
- python3 src/tick_simulator.py

## Working conventions

- All file paths come from src/paths.py. NEVER use Path(__file__).parent in new scripts.
- All timestamps in NY timezone after data_prep, America/New_York, DST-aware.
- All prices are Panama back-adjusted continuous series. They will NOT match raw market quotes (e.g. TradingView) exactly. Point distances and dollar P&L are correct; absolute prices are not.
- 2 dollars per point per MNQ contract.
- Calendar spreads filtered out via regex matching outright contracts only in data_prep.
- Sticky forward-only rollover based on volume.
- One position at a time (C2 rule).
- Stop-first conservative for ambiguous same-bar stop and target.
- Force-close at the 11:30 bar's OPEN price (the 11:30 bar's high and low are NOT consulted).
- Trading window inclusive: 9:46 through 11:29 bars; force-close on 11:30 open.

## When making changes

1. READ docs/strategy-spec.md and docs/decisions.md BEFORE proposing any change to logic.
2. NEVER modify the strategy rules without explicit user approval, this baseline is locked.
3. For experiments, branch the config (don't overwrite trades.parquet). Save new outputs with descriptive names in results/archive/.
4. Always back up any parquet before regenerating.
5. After any code change, run the full pipeline and verify the headline results match (526 / 52.9% / +$1,975) unless an intentional change is being made.

## Current status (as of 2026-05-12)

### Dataset
- **Span:** 2019-05-06 → 2026-05-10 (7 years), 2,467,393 1-min bars, 1,805 ORB-eligible sessions, 28 rolls
- **Front-month series:** Panama back-adjusted, 29 contracts (MNQM9 through MNQM6)
- Multi-CSV concat infrastructure in `src/paths.py` (`RAW_CSV_FILES = sorted(...)`) and `src/data_prep.py`. Future extensions = drop a new `glbx-mdp3-*.ohlcv-1m.csv` into `data/raw/` and rerun `python3 src/data_prep.py`.

### Locked baseline
- `data/processed/trades.parquet` (526 trades / 52.9% / +$1,975) **preserved as historical reference**, sha256 `d24f128ac88227900ac6d44047f0f51e5a5906011e683643a925c63feb15f4c6`. Do NOT overwrite.
- This file corresponds to the 2024-04-01 → 2026-05-01 in-sample window only. The extended-data equivalent lives at `results/archive/trades_baseline_extended_20260511.parquet`.

### Today's headline finding: strategy does not generalize OOS

7-year extended simulator runs:
- **Hybrid 30/30 (extended):** 1,693 trades / 49.9% / **+$62.50 combined**. By period: −$2,232 historical OOS (5 years) / +$2,295 in-sample / $0 forward.
- **Fade-only locked baseline (extended):** 1,693 trades / 48.7% / **−$3,378 combined**. By period: −$5,535 historical OOS / +$2,157 in-sample / $0 forward.
- Hybrid regime classifier **sign-flips between periods** — directional cell loses $3,884 historically vs +$2,406 in-sample (same indicator, opposite payoff).
- Forward week (2026-05-04 to 2026-05-08) produced **0 trades** in both simulators: MNQ rallied above the entire 200-session level pool; no clusters near current price.

### Tonight's variant tests (all kept; outputs in results/archive/)

| Variant | File | Result | Verdict |
|---|---|---|---|
| Hybrid 30/30 (re-run on 7y) | `trades_hybrid.parquet` | +$62/1693 | Near-zero edge |
| Fade-only (re-run on 7y) | `trades_baseline_extended_20260511.parquet` | −$3,378/1693 | Loses across history |
| Hybrid 40/40 | `trades_hybrid_4040_20260511.parquet` | −$3,216/1600 | Worse than 30/30 |
| Priors-only fade (today's ORB excluded from clustering) | `trades_priors_only_20260511.parquet` | −$2,373/1491 | Modest improvement, still negative |

### V2 regime classifier — COMPLETE (2026-05-12)

Investigation finished. **Deployment winner: ADX(N=15, thr=30) ∧ DI(N=15, thr=8) unanimous AND-gate per cluster touch.**

- Headline: 949 trades / 55.2% WR / **+$5,803** over 7 years (R-012)
- Walk-forward 7×(3y IS + 1y OOS, advance 6mo): sharpe-like **5.32**, sign **7/7**, median per-window OOS **$1,082**
- 8 of 8 calendar years positive (worst 2020 +$199, best 2025 +$1,408)
- Trades parquet: `results/archive/trades_regime_v2_20260512.parquet`
- Framework abandoned the original "daily timeframe + 6 design decisions" approach; replaced with per-indicator-as-hypothesis investigation on 1-min bars. ADX and ±DI work; ROC, ATR, VWAP confirmed noise.
- Phase 7 diagnostics: window-trend slope +$33/window (no decay); DI discrimination 100th percentile vs 30 same-bias random labelings; **2026 Jan-Apr underperforms AllFade by -$1,422 — deployment concern**.
- **Forward test required before live deployment.** 6 months minimum, specific pass/fail criteria in `docs/research-log-2026-05-regime-v2-investigation.md`.

New source: `src/indicators/{base,adx,di,roc,atr,vwap}.py`, `src/simulator_v2.py`, `src/walk_forward.py`, `src/phase6_run.py`, `src/phase7_analysis.py`. Locked simulator/baseline untouched.

Full report: `docs/research-log-2026-05-regime-v2-investigation.md`. Entry: R-012 in `docs/results-log.md`.

### Standing tick-verification caveat (unchanged)

Tick-verification on the 2026-03-17 to 2026-04-15 overlap (32 trades) showed bar-sim overstated P&L by ~100% on that slice — phantom fills from non-trade prints (~6%) and entry-bar chronology errors (~3%) partially offset by stop-first conservative rule (~1%). Net: optimistic bias. See `docs/decisions.md` D-005, D-014, D-015.
