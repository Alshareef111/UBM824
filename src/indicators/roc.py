"""ROC classifier — per-cluster FADE/TREND via |ROC(N)| in points at touch bar T-1.

Indicator magnitude: absolute rate of change in raw points:
  |ROC_pts(N) at T-1| = |close_{T-1} - close_{T-1-N}|

Threshold rule: |ROC_pts(N)| at T-1 >= threshold -> TREND, else FADE.

Note on price scale: Panama back-adjusted prices range from ~6,000 (2019) to
~25,000 (2026). A fixed point threshold means the relative threshold (as a
fraction of price) decreases ~4× across the dataset. This is by user spec
(per Phase 7 framework #7 — thresholds in points, not percent). If results
look regime-biased, that scale effect is a candidate explanation.

NaN values during warm-up default to FADE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from clusters import Cluster
from indicators.base import Label


def compute_roc_series_pts(bars: pd.DataFrame, n: int) -> pd.Series:
    """|close_t - close_{t-n}| at every bar t, in raw points."""
    close = bars["close"]
    roc = (close - close.shift(n)).abs()
    roc.index = bars.index
    return roc


def precompute_lookup(bars: pd.DataFrame, n: int) -> dict:
    """{ts_utc: |ROC(N)| at bar T-1} for every bar."""
    roc_series = compute_roc_series_pts(bars, n)
    shifted = roc_series.shift(1)
    return dict(zip(bars["ts_utc"].to_numpy(), shifted.to_numpy()))


class RocClassifier:
    """|ROC(N)| >= threshold -> TREND, else FADE. Lookup at touch_bar's T-1."""

    def __init__(self, lookup: dict, n: int, threshold: float):
        self.lookup = lookup
        self.n = n
        self.threshold = float(threshold)
        self.name = f"ROC(N={n},thr={threshold})"

    def __call__(self, cluster: Cluster, touch_bar: dict, bars_today: pd.DataFrame) -> Label:
        val = self.lookup.get(touch_bar["ts_utc"], np.nan)
        if pd.isna(val):
            return Label.FADE
        return Label.TREND if val >= self.threshold else Label.FADE
