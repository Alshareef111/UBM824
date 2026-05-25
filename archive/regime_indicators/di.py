"""±DI spread classifier — per-cluster FADE/TREND via |+DI − -DI| at touch bar T-1.

Indicator magnitude: directional spread |+DI(N) − -DI(N)| over N consecutive
1-min bars, computed via Wilder smoothing (same DM/TR calculations as ADX,
without the final DX/ADX smoothing step). Larger spread = stronger directional
trend regardless of sign.

Threshold rule: |+DI - -DI|(N) at bar T-1 >= threshold -> TREND, else FADE.

NaN values during warm-up default to FADE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from clusters import Cluster
from regime_indicators.base import Label


def compute_di_spread_series(bars: pd.DataFrame, n: int) -> pd.Series:
    """Compute |+DI(N) - -DI(N)| at every bar. Returns Series aligned with bars.index."""
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

    spread = (plus_di - minus_di).abs()
    spread.index = bars.index
    return spread


def precompute_lookup(bars: pd.DataFrame, n: int) -> dict:
    """Pre-compute {ts_utc: |+DI - -DI|(N) at bar T-1} for every bar."""
    spread_series = compute_di_spread_series(bars, n)
    shifted = spread_series.shift(1)
    return dict(zip(bars["ts_utc"].to_numpy(), shifted.to_numpy()))


class DiClassifier:
    """|+DI(N) - -DI(N)| >= threshold -> TREND, else FADE. Lookup at touch_bar's T-1."""

    def __init__(self, lookup: dict, n: int, threshold: float):
        self.lookup = lookup
        self.n = n
        self.threshold = float(threshold)
        self.name = f"DI(N={n},thr={threshold})"

    def __call__(self, cluster: Cluster, touch_bar: dict, bars_today: pd.DataFrame) -> Label:
        val = self.lookup.get(touch_bar["ts_utc"], np.nan)
        if pd.isna(val):
            return Label.FADE
        return Label.TREND if val >= self.threshold else Label.FADE
