"""
src/indicators.py — Wilder-EWM ADX(N) and ±DI(N) on the 1-min continuous series.

Verbatim port of /Users/hashim/Desktop/MNQ-Strategy/src/indicators/{adx,di}.py.
Approximates Wilder smoothing as pandas EWM with alpha=1/N, adjust=False.
NO per-session reset — the EWM runs across overnight bars, matching QC.

The classifier consumer (src/vbt_backtest.py) is responsible for shifting by 1
to enforce no-look-ahead (indicator at T-1 gates the entry at T).

Run sanity check:
    .venv/bin/python -m src.indicators
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd


def _wilder_components(bars: pd.DataFrame, n: int):
    """Shared Wilder TR / +DM / -DM smoothing. Returns (tr_s, plus_dm_s, minus_dm_s)."""
    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()
    close = bars["close"].to_numpy()

    prev_high = np.concatenate([[np.nan], high[:-1]])
    prev_low = np.concatenate([[np.nan], low[:-1]])
    prev_close = np.concatenate([[np.nan], close[:-1]])

    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])

    up_move = high - prev_high
    down_move = prev_low - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    alpha = 1.0 / n
    tr_s = pd.Series(tr).ewm(alpha=alpha, adjust=False).mean()
    plus_dm_s = pd.Series(plus_dm).ewm(alpha=alpha, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm).ewm(alpha=alpha, adjust=False).mean()
    return tr_s, plus_dm_s, minus_dm_s


def compute_adx_series(bars: pd.DataFrame, n: int = 15) -> pd.Series:
    """Wilder ADX(N) at every bar. Returns Series aligned with bars.index."""
    tr_s, plus_dm_s, minus_dm_s = _wilder_components(bars, n)
    plus_di = 100.0 * plus_dm_s / tr_s.replace(0, np.nan)
    minus_di = 100.0 * minus_dm_s / tr_s.replace(0, np.nan)
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1.0 / n, adjust=False).mean()
    adx.index = bars.index
    return adx


def compute_plus_minus_di(bars: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Wilder +DI(N) and -DI(N) at every bar. Returns DataFrame aligned with bars.index
    with columns plus_di, minus_di. |+DI − -DI| gives the magnitude (spread)."""
    tr_s, plus_dm_s, minus_dm_s = _wilder_components(bars, n)
    plus_di = 100.0 * plus_dm_s / tr_s.replace(0, np.nan)
    minus_di = 100.0 * minus_dm_s / tr_s.replace(0, np.nan)
    out = pd.DataFrame({"plus_di": plus_di.to_numpy(),
                        "minus_di": minus_di.to_numpy()},
                       index=bars.index)
    return out


def sanity_check():
    """Print sample ADX/+DI/-DI values and assert basic invariants."""
    from src.data import load_processed_bars
    print("Loading bars...", flush=True)
    bars = load_processed_bars()
    print(f"  {len(bars):,} bars from {bars.index[0]} to {bars.index[-1]}", flush=True)

    print("Computing ADX(15) on full continuous series...", flush=True)
    adx = compute_adx_series(bars, n=15)
    print("Computing +DI(15)/-DI(15) on full continuous series...", flush=True)
    di = compute_plus_minus_di(bars, n=15)
    spread = (di["plus_di"] - di["minus_di"]).abs()

    n_warm = 30
    print(f"\nFirst {n_warm} ADX values (warm-up; NaN expected initially):", flush=True)
    print(adx.iloc[:n_warm].to_string(), flush=True)

    print(f"\nSample mid-series values (around 2022-06-15 14:30 NY):", flush=True)
    ref_ts = pd.Timestamp("2022-06-15 14:30:00", tz="America/New_York")
    if ref_ts in adx.index:
        nearby = adx.index.get_indexer([ref_ts])[0]
        sample = pd.DataFrame({
            "adx":      adx.iloc[nearby - 2: nearby + 3].to_numpy(),
            "plus_di":  di["plus_di"].iloc[nearby - 2: nearby + 3].to_numpy(),
            "minus_di": di["minus_di"].iloc[nearby - 2: nearby + 3].to_numpy(),
            "|spread|": spread.iloc[nearby - 2: nearby + 3].to_numpy(),
        }, index=adx.index[nearby - 2: nearby + 3])
        print(sample.round(3).to_string(), flush=True)

    valid_adx = adx.dropna()
    valid_pdi = di["plus_di"].dropna()
    valid_mdi = di["minus_di"].dropna()
    print(f"\nInvariant checks (non-NaN range):", flush=True)
    print(f"  ADX:      min={valid_adx.min():.3f}  max={valid_adx.max():.3f}   "
          f"(must be in [0,100])", flush=True)
    print(f"  +DI:      min={valid_pdi.min():.3f}  max={valid_pdi.max():.3f}   "
          f"(must be in [0,100])", flush=True)
    print(f"  -DI:      min={valid_mdi.min():.3f}  max={valid_mdi.max():.3f}   "
          f"(must be in [0,100])", flush=True)
    assert valid_adx.min() >= 0 and valid_adx.max() <= 100, "ADX out of [0,100]"
    assert valid_pdi.min() >= 0 and valid_pdi.max() <= 100, "+DI out of [0,100]"
    assert valid_mdi.min() >= 0 and valid_mdi.max() <= 100, "-DI out of [0,100]"

    print(f"\nDistribution of ADX (across {len(valid_adx):,} non-NaN bars):", flush=True)
    print(valid_adx.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).to_string(), flush=True)
    print(f"\nDistribution of |+DI − -DI| spread:", flush=True)
    print(spread.dropna().describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).to_string(), flush=True)

    pct_above_30 = float((valid_adx >= 30).mean()) * 100
    pct_above_8 = float((spread.dropna() >= 8).mean()) * 100
    print(f"\nGating preview (default thresholds ADX≥30, |DI|≥8):", flush=True)
    print(f"  bars with ADX ≥ 30:    {pct_above_30:.1f}%", flush=True)
    print(f"  bars with |DI| ≥ 8:    {pct_above_8:.1f}%", flush=True)
    both = ((valid_adx >= 30) & (spread.reindex(valid_adx.index) >= 8))
    print(f"  bars with BOTH:        {float(both.mean())*100:.1f}%", flush=True)


if __name__ == "__main__":
    sanity_check()
