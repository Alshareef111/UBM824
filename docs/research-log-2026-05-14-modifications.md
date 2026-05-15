# Session Log — 2026-05-14: V2 + 40/40 Modifications Testing

## Status entering session
- Deployment candidate per CLAUDE.md: V2 + 30/30 (R-012, +$5,803, Sharpe 5.32)
- Disk evidence of stronger candidate: V2 + 40/40 at results/archive/strategy_report_20260512/strategy_4040_test.md (uncommitted, undocumented in research-log series until now)
- V2 + 40/40 headline: 908 trades, 56.2% WR, +$8,808, max DD −$1,228 (recovered 380d), ann. Sharpe 2.15, WF Sharpe-like 6.86, sign 7/7, 8/8 calendar years positive
- Locked baseline sha256: d24f128a…f4c6 (unchanged throughout session)

## Modifications tested — ALL REJECTED

### Variant B — partial exit + runner break-even (initial stop −40)
2 contracts; p1 target +40; p2 target = nearest level of next cluster in trade direction; p2 stop moves to entry after p1 hits +40 (enforced from bar X+1).
Result: 899 entries, 56.0% WR, +$16,591 (vs scaled baseline $17,616 = −$1,025), WF Sharpe-like 4.83 (−30%), Sortino 4.20.
Reject reason: same-bar cluster-target leak (−$5,962 on 203 trades where p2's cluster sits close to +40) cancels the runner-BE protection benefit (+$0 on 113 BE-stops). 2025 underperforms baseline by −$1,108 (worst year impact in the baseline's best year). WF Sharpe regression alone is disqualifying.
Artifacts: results/archive/v2_4040_modifications_20260514/

### Variant C — tight stop −25 + partial + runner-BE
Same as B except initial stop −25.
Result: 917 entries, 44.6% WR (−11.6pp vs baseline), +$8,938, WF Sharpe-like 1.89.
Reject reason: tight stop converts moderate-magnitude reversal winners into many small losses. Classic tight-stop trap. Win-rate collapse is the cleanest disqualification.

### Variant D — BE@+20 combined with partial and tight stop
Cancelled before run. Spec superseded mid-design by the runner-BE-at-p1-exit rule. No artifacts.

### Variant E — far-border entry (symmetric, both FADE and TREND)
Entry rule swap: cluster.high → cluster.low and cluster.low → cluster.high in classify_setups; trigger logic preserved.
Result: 848 entries, 55.5% WR, +$7,554 (−$1,254 vs baseline), max DD −$910 (−26% smaller), WF Sharpe-like 5.72 (−17%), sign 7/7.
Filter diagnostic: 163 baseline trades filtered out were net +$48 / 50.3% WR (pure noise — filter is correctly identifying weak-momentum touches). But 745 shared clusters performed worse at far border ($11.76 → $8.91 mean per trade, −$2,123 total). Filter works but the wider entry surrenders edge on the kept trades.
Reject reason: no net P&L gain, WF Sharpe regression, same risk-vs-return trade-off pattern as Variants B/C.
Artifacts: results/archive/v2_4040_far_border_20260514/

## Pattern across the four variants
All three tests with real results regressed on WF Sharpe-like (the deployment-critical metric) while modestly improving headline Sharpe or max DD. Pattern is consistent: each modification rearranges P&L without adding edge. Suggests V2 + 40/40 baseline is at or near its local optimum for these levers.

## Methodological decisions made this session
- Entry-bar BE paradox resolved with "option 1" — break-even rule enforced from bar X+1 onward, never on same bar as the trigger event. Applied uniformly across BE-style variants.
- Same-bar precedence: stop-first conservative (existing project convention preserved).
- All experimental simulator code lives in src/experimental/ (created this session). src/simulator_v2.py was NOT modified.
- All experimental result dirs in results/archive/v2_4040_*_20260514/ format.
- Per-variant filter-effect diagnostic added to report format: comparing variant trades to baseline trades by (session_date + cluster_low + cluster_high) tuple to compute "what did we filter out and was it good or bad."

## Pending — interrupted by API 529 overload
Cluster-size filter test was specified, prep'd, and started — locked baseline verified, output dir created at results/archive/v2_4040_cluster_size_filter_20260514/ — but the actual walk-forward run did not execute. To resume:

- F1: V2 + 40/40 with MIN_CLUSTER_SIZE = 4 (currently 3)
- F2: V2 + 40/40 with MIN_CLUSTER_SIZE = 5
- Implementation: module-level constant override on simulator_v2 (sim.MIN_CLUSTER_SIZE = 4) — same pattern as strategy_4040_test.py. No fork needed, no clusters.py edit.
- MIN_CLUSTER_SIZE found at simulator_v2.py:35, used at simulator_v2.py:263 inside find_clusters call.
- Rationale: far-border diagnostic showed filtered-out trades had mean cluster size 4.23 vs 3.74 for shared trades, suggesting cluster size correlates with traversal resistance. This test isolates the size-filter insight without the entry-price drag of Variant E.

## Next-session resumption checklist
1. git pull (or git status on Mac mini)
2. Verify data/processed/trades.parquet sha256 = d24f128ac88227900ac6d44047f0f51e5a5906011e683643a925c63feb15f4c6
3. Verify data/processed/mnq_adjusted_1m.parquet is present (gitignored — must already be on this machine; if not, copy from Mac mini or re-fetch from Databento)
4. Read this log + docs/research-log-2026-05-regime-v2-investigation.md (R-012)
5. Read CLAUDE.md (deployment candidate status)
6. Resume cluster-size filter test using the spec above
