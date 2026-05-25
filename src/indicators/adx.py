"""ADX classifier — per-cluster FADE/TREND decision via ADX(N) at touch bar T-1.

Indicator magnitude: standard Wilder ADX over N consecutive 1-min bars.
Threshold rule: ADX(N) at bar T-1 >= threshold -> TREND, else FADE.

The classifier never looks at bar T (the touch bar) — only at bars strictly
before T, honoring the locked lookback contract from framework #7.

Wilder smoothing is approximated via pandas EWM with alpha=1/N, adjust=False —
matches TradingView/most platforms after the warm-up period (first ~N bars).
NaN values during warm-up default to FADE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from clusters import Cluster
from indicators.base import Label


def compute_adx_series(bars: pd.DataFrame, n: int) -> pd.Series:
    """Compute Wilder ADX(N) at every bar. Returns a Series aligned with bars.index."""
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

    plus_di = 100.0 * plus_dm_s / tr_s.replace(0, np.nan)
    minus_di = 100.0 * minus_dm_s / tr_s.replace(0, np.nan)

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum

    adx = dx.ewm(alpha=alpha, adjust=False).mean()
    adx.index = bars.index
    return adx


def precompute_lookup(bars: pd.DataFrame, n: int) -> dict:
    """Pre-compute {ts_utc: ADX(N) at bar T-1} for every bar.

    Shifting by 1 row gives "ADX as of the bar immediately before T", which
    is exactly what the classifier needs at touch bar T (no look-ahead).
    """
    adx_series = compute_adx_series(bars, n)
    adx_shifted = adx_series.shift(1)
    return dict(zip(bars["ts_utc"].to_numpy(), adx_shifted.to_numpy()))


class AdxClassifier:
    """ADX(N) >= threshold -> TREND, else FADE. Lookup at touch_bar's T-1."""

    def __init__(self, lookup: dict, n: int, threshold: float):
        self.lookup = lookup
        self.n = n
        self.threshold = float(threshold)
        self.name = f"ADX(N={n},thr={threshold})"

    def __call__(self, cluster: Cluster, touch_bar: dict, bars_today: pd.DataFrame) -> Label:
        val = self.lookup.get(touch_bar["ts_utc"], np.nan)
        if pd.isna(val):
            return Label.FADE  # warm-up default
        return Label.TREND if val >= self.threshold else Label.FADE
