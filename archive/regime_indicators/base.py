"""Indicator infrastructure: Label enum, Classifier protocol, synthetic classifiers.

A Classifier is a callable that maps (cluster, touch_bar, bars_today) -> Label
per cluster touch. simulator_v2 calls the classifier at the bar where the
limit would first fill, and uses the returned label to gate trade direction:

  FADE  -> trade in the locked-baseline direction (against price action)
  TREND -> invert direction (with price action, same fill price)
  SKIP  -> consume this cluster without entering a trade

Lookback contract (locked in framework #1): the indicator may only consult
bars strictly before the touch bar T. Bars indexed [T-N, T-1] with N >= 1.
The simulator passes the touch bar dict and the full bars_today; the
classifier is responsible for honoring no-look-ahead.

Synthetic classifiers below are for Phase 0 validation and harness sanity
testing only. Real indicator classifiers live in adx.py / di.py / roc.py /
atr.py / vwap.py.
"""
from __future__ import annotations

import hashlib
from enum import Enum
from typing import Protocol

import pandas as pd

from clusters import Cluster


class Label(Enum):
    FADE = "FADE"
    TREND = "TREND"
    SKIP = "SKIP"


class Classifier(Protocol):
    """Callable returning a Label for a cluster touch at bar T (touch_bar)."""

    def __call__(
        self,
        cluster: Cluster,
        touch_bar: dict,
        bars_today: pd.DataFrame,
    ) -> Label: ...


class AllFade:
    """Every cluster -> FADE. Recovers locked-baseline behavior."""

    name = "AllFade"

    def __call__(self, cluster, touch_bar, bars_today) -> Label:
        return Label.FADE


class AllTrend:
    """Every cluster -> TREND. Inverts every locked-baseline trade direction."""

    name = "AllTrend"

    def __call__(self, cluster, touch_bar, bars_today) -> Label:
        return Label.TREND


class AllSkip:
    """Every cluster -> SKIP. Produces zero trades. Tests the SKIP path."""

    name = "AllSkip"

    def __call__(self, cluster, touch_bar, bars_today) -> Label:
        return Label.SKIP


class RandomBinary:
    """Deterministic 50/50 FADE/TREND classifier. Keyed by (session_date, cluster)."""

    def __init__(self, seed: int = 0):
        self.seed = seed
        self.name = f"RandomBinary(seed={seed})"

    def __call__(self, cluster, touch_bar, bars_today) -> Label:
        sd = touch_bar["session_date"]
        key = f"{self.seed}|{sd}|{cluster.low}|{cluster.high}|{cluster.size}".encode()
        h = int(hashlib.md5(key).hexdigest()[:8], 16)
        return Label.FADE if (h & 1) == 0 else Label.TREND


class BiasedRandom:
    """Random FADE/TREND with bias. Deterministic via seed + cluster identity.

    Used in Phase 7 discrimination check: tests whether a real indicator's P&L
    exceeds what a SAME-BIAS random labeling would produce. Distinguishes
    "indicator selects high-conviction clusters" from "indicator imposes a
    directional bias that happens to fit history."
    """

    def __init__(self, seed: int, trend_prob: float):
        self.seed = seed
        self.trend_prob = float(trend_prob)
        self.name = f"BiasedRandom(seed={seed},trend={self.trend_prob:.2f})"

    def __call__(self, cluster, touch_bar, bars_today) -> Label:
        sd = touch_bar["session_date"]
        key = f"{self.seed}|{sd}|{cluster.low}|{cluster.high}|{cluster.size}".encode()
        h = int(hashlib.md5(key).hexdigest()[:8], 16)
        u = h / (16 ** 8)
        return Label.TREND if u < self.trend_prob else Label.FADE


class UnanimousClassifier:
    """Unanimous AND-gate composite: all wrapped classifiers must agree.

    Returns FADE if all wrapped classifiers say FADE.
    Returns TREND if all wrapped classifiers say TREND.
    Returns SKIP on any disagreement (or if any wrapped classifier emits SKIP).

    Used for Phase 6 composite tests:
      - Variant A (5 corners): full-stack unanimous + 5 LOOs (4-of-5)
      - Variant B (2 corners): ADX ∧ DI unanimous
    """

    def __init__(self, classifiers: list, name: str | None = None):
        self.classifiers = list(classifiers)
        self.name = name or "Unanimous(" + " ∧ ".join(c.name for c in classifiers) + ")"

    def __call__(self, cluster, touch_bar, bars_today) -> Label:
        labels = [c(cluster, touch_bar, bars_today) for c in self.classifiers]
        if all(l == Label.FADE for l in labels):
            return Label.FADE
        if all(l == Label.TREND for l in labels):
            return Label.TREND
        return Label.SKIP
