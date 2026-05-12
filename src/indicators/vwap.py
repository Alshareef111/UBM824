"""VWAP-distance classifier — per-cluster FADE/TREND via |close - VWAP| at touch bar T-1.

Indicator magnitude: |close_{T-1} - VWAP_{T-1}| in raw points, where VWAP is
session-anchored cumulative typical-price-weighted average from the anchor.

Two anchor options (per framework #2):
  - 'session' (18:00 prior-day NY): VWAP accumulates from the start of each
    session_date. The data_prep groups overnight bars to the next session_date,
    so cumulative-from-session-start ≈ 18:00 prior-day anchor.
  - '9:30_ny' (today's NY session open): VWAP accumulates from 9:30 NY only.
    Before 9:30 NY each day, VWAP is undefined (NaN). At touch bars 9:46-11:29,
    has 16-119 minutes of data.

Typical price: (high + low + close) / 3 (standard VWAP convention).

Threshold rule: distance at T-1 >= threshold -> TREND, else FADE.

NaN (warm-up before anchor) defaults to FADE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from clusters import Cluster
from indicators.base import Label


def compute_vwap_series(bars: pd.DataFrame, anchor: str) -> pd.Series:
    """Session-anchored cumulative VWAP. NaN before the anchor each session.

    anchor: 'session' (= start of session_date, ~18:00 prior NY day)
            '9:30_ny' (= 9:30 America/New_York)
    """
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    pv = typical * bars["volume"]
    v = bars["volume"]

    if anchor == "session":
        pv_use = pv
        v_use = v
        mask_after_anchor = pd.Series(True, index=bars.index)
    elif anchor == "9:30_ny":
        h = bars["ts_ny"].dt.hour
        m = bars["ts_ny"].dt.minute
        mask_after_anchor = (h > 9) | ((h == 9) & (m >= 30))
        # Zero out contributions before 9:30 so cumsum-by-session starts at 9:30
        pv_use = pv.where(mask_after_anchor, 0)
        v_use = v.where(mask_after_anchor, 0)
    else:
        raise ValueError(f"unknown anchor: {anchor!r}")

    pv_cum = pv_use.groupby(bars["session_date"].to_numpy(), sort=False).cumsum()
    v_cum = v_use.groupby(bars["session_date"].to_numpy(), sort=False).cumsum()

    vwap = pv_cum / v_cum.replace(0, np.nan)
    vwap = vwap.where(mask_after_anchor.to_numpy(), np.nan)
    vwap.index = bars.index
    return vwap


def precompute_lookup(bars: pd.DataFrame, anchor: str) -> dict:
    """{ts_utc: |close - VWAP|(anchor) at bar T-1} in points."""
    vwap = compute_vwap_series(bars, anchor)
    distance = (bars["close"] - vwap).abs()
    shifted = distance.shift(1)
    return dict(zip(bars["ts_utc"].to_numpy(), shifted.to_numpy()))


class VwapClassifier:
    """|close - VWAP|(anchor) >= threshold -> TREND, else FADE. Lookup at T-1."""

    def __init__(self, lookup: dict, anchor: str, threshold: float):
        self.lookup = lookup
        self.anchor = anchor
        self.threshold = float(threshold)
        self.name = f"VWAP({anchor},thr={threshold})"

    def __call__(self, cluster: Cluster, touch_bar: dict, bars_today: pd.DataFrame) -> Label:
        val = self.lookup.get(touch_bar["ts_utc"], np.nan)
        if pd.isna(val):
            return Label.FADE
        return Label.TREND if val >= self.threshold else Label.FADE
