"""ATR ratio classifier — per-cluster FADE/TREND via ATR(N_short)/ATR(N_long) at T-1.

Indicator magnitude: ratio of short-window ATR to long-window ATR.
  ratio = ATR(N_short) / ATR(N_long)  at bar T-1

ratio > 1 → recent volatility expanding vs long-run baseline → TREND candidate
ratio < 1 → recent volatility contracting → FADE candidate

By framework spec: N_long = 4 × N_short.

Threshold rule: ratio at T-1 >= threshold -> TREND, else FADE.

Wilder smoothing via pandas EWM with alpha=1/N, adjust=False.
NaN values during warm-up default to FADE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from clusters import Cluster
from indicators.base import Label


def compute_atr_series(bars: pd.DataFrame, n: int) -> pd.Series:
    """Wilder ATR(N) at every bar."""
    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()
    close = bars["close"].to_numpy()

    prev_close = np.concatenate([[np.nan], close[:-1]])
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])

    alpha = 1.0 / n
    atr = pd.Series(tr).ewm(alpha=alpha, adjust=False).mean()
    atr.index = bars.index
    return atr


def precompute_ratio_lookup(bars: pd.DataFrame, n_short: int, n_long: int) -> dict:
    """{ts_utc: ATR(N_short)/ATR(N_long) at bar T-1} for every bar."""
    atr_s = compute_atr_series(bars, n_short)
    atr_l = compute_atr_series(bars, n_long)
    ratio = (atr_s / atr_l.replace(0, np.nan)).shift(1)
    return dict(zip(bars["ts_utc"].to_numpy(), ratio.to_numpy()))


class AtrRatioClassifier:
    """ATR(N_short)/ATR(N_long) >= threshold -> TREND, else FADE. Lookup at touch_bar's T-1."""

    def __init__(self, lookup: dict, n_short: int, n_long: int, threshold: float):
        self.lookup = lookup
        self.n_short = n_short
        self.n_long = n_long
        self.threshold = float(threshold)
        self.name = f"ATR(Ns={n_short},Nl={n_long},thr={threshold})"

    def __call__(self, cluster: Cluster, touch_bar: dict, bars_today: pd.DataFrame) -> Label:
        val = self.lookup.get(touch_bar["ts_utc"], np.nan)
        if pd.isna(val):
            return Label.FADE
        return Label.TREND if val >= self.threshold else Label.FADE
