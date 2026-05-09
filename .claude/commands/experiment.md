You are about to help the user run a new strategy experiment.

Before doing anything:
1. Read docs/strategy-spec.md, docs/decisions.md, docs/results-log.md if you haven't already.
2. Ask the user for these details if not provided:
   - What parameter(s) are changing from baseline?
   - What is the hypothesis (what do they expect to happen and why)?
   - What is a short descriptor for filenames? (e.g. "tighter_gap", "wider_stop")

Then propose a plan:
1. Copy src/simulator.py to a new variant (e.g. src/simulator_<descriptor>.py) — do not modify the original.
2. Apply only the requested parameter changes. Everything else stays identical.
3. Save the new trades file to results/archive/trades_<descriptor>.parquet — NEVER overwrite data/processed/trades.parquet.
4. Run the new simulator.
5. Run robustness analysis on the new trades file (you may need to copy robustness.py too, or pass the path as an argument).
6. Append a new R-XXX entry to docs/results-log.md using the template at the bottom of that file. Include: trades, win rate, P&L, expectancy, exits breakdown, yearly split, max drawdown, hypothesis result, and the output file path.

Show the plan to the user. Wait for explicit approval before executing.

After execution, summarize the result vs the locked baseline (526 / 52.9% / +$1,975) so the user can see the delta clearly.
