# MNQ ORB-Cluster Backtest

Backtest of an Opening Range Breakout cluster mean-reversion strategy on MNQ futures, built with Claude Code.

## Quick start

From the project root:

    python3 src/data_prep.py      # raw CSV to adjusted bars
    python3 src/orb.py            # compute ORB table
    python3 src/simulator.py      # run backtest, writes trades.parquet
    python3 src/robustness.py     # yearly, monthly, drawdown stats

Expected baseline output: 526 trades, 52.9% win rate, +$1,975 over 2024-04 to 2026-05.

## What's where

- CLAUDE.md — read this first if you are Claude Code or another assistant.
- docs/strategy-spec.md — exact strategy rules.
- docs/decisions.md — why each design choice was made.
- docs/results-log.md — every parameter sweep tested and its outcome.
- src/ — all Python scripts. Always import paths from src/paths.py.
- data/raw/ — Databento CSV plus tick file symlink (do not edit).
- data/processed/ — generated parquet files (regenerable from src/).
- results/charts/ — visualization PNGs.
- results/archive/ — historical or experimental outputs.

## Requirements

- Python 3.11+
- pandas, numpy, matplotlib, pyarrow
- Mac or Linux (paths use POSIX conventions)

## Running experiments

Do not overwrite the locked baseline (data/processed/trades.parquet). Save experiment outputs to results/archive/ with a descriptive name and add an entry to docs/results-log.md.

## Origin

Project built collaboratively in Claude Code, May 2026. See docs/decisions.md for the design history.
