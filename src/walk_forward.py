"""Walk-forward harness: 7 windows of (3y IS + 1y OOS), advance 6mo.

Window start dates: 2019-05-06, 2019-11-06, 2020-05-06, 2020-11-06,
2021-05-06, 2021-11-06, 2022-05-06. Each window:
  - IS:  is_start to is_start + 3y
  - OOS: is_end  to is_end  + 1y

Per-config OOS evaluation (locked framework #4b, #5, #6a, #6b):
  - per-window-pnl: total pnl_dollars of trades whose session_date falls in OOS slice
  - sharpe_like = median(per_window_pnl) / stdev(per_window_pnl)
  - sign_stable = (count of windows with pnl > 0) >= 6 of 7
  - median_ok   = median(per_window_pnl) > 0
  - qualified   = sign_stable AND median_ok
  - deployment rank: highest sharpe_like among qualifying configs

Window membership uses session_date (calendar date) — tz-free and matches
the rest of the project's session-date semantics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DATA_START = pd.Timestamp("2019-05-06")
DATA_END = pd.Timestamp("2026-05-10")

IS_YEARS = 3
OOS_YEARS = 1
ADVANCE_MONTHS = 6
N_WINDOWS = 7

SIGN_STABILITY_MIN = 6  # of N_WINDOWS
NULL_P95_SHARPE_LIKE = 1.06  # 95th percentile from phase0_null_20260512 (50 RandomBinary seeds)


@dataclass
class Window:
    name: str
    is_start: pd.Timestamp
    is_end: pd.Timestamp  # exclusive; also = oos_start
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp  # exclusive


def make_windows() -> list[Window]:
    """7 walk-forward windows: 3y IS + 1y OOS, advance 6mo, starting 2019-05-06."""
    windows = []
    for i in range(N_WINDOWS):
        is_start = DATA_START + pd.DateOffset(months=i * ADVANCE_MONTHS)
        is_end = is_start + pd.DateOffset(years=IS_YEARS)
        oos_start = is_end
        oos_end = oos_start + pd.DateOffset(years=OOS_YEARS)
        windows.append(
            Window(
                name=f"W{i + 1}",
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
            )
        )
    return windows


def filter_trades_to_window(
    trades_df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Return trades whose session_date falls in [start, end)."""
    s = pd.to_datetime(trades_df["session_date"])
    mask = (s >= start) & (s < end)
    return trades_df[mask]


def per_window_pnl(
    trades_df: pd.DataFrame, windows: list[Window], slice_: str = "oos"
) -> dict[str, float]:
    """Dict of window_name -> total pnl_dollars in that window's IS or OOS slice."""
    out: dict[str, float] = {}
    for w in windows:
        if slice_ == "oos":
            sub = filter_trades_to_window(trades_df, w.oos_start, w.oos_end)
        elif slice_ == "is":
            sub = filter_trades_to_window(trades_df, w.is_start, w.is_end)
        else:
            raise ValueError(f"slice_ must be 'oos' or 'is', got {slice_!r}")
        out[w.name] = float(sub["pnl_dollars"].sum()) if len(sub) else 0.0
    return out


def sharpe_like_score(per_window: dict[str, float]) -> float:
    """median(values) / stdev(values, ddof=1). Robust to outlier windows."""
    vals = np.array(list(per_window.values()), dtype=float)
    if len(vals) < 2:
        return float("nan")
    med = float(np.median(vals))
    sd = float(np.std(vals, ddof=1))
    if sd == 0:
        return float("nan") if med == 0 else float("inf") * (1.0 if med > 0 else -1.0)
    return med / sd


def sign_stability_count(per_window: dict[str, float]) -> int:
    """Number of windows with strictly positive P&L."""
    return int(sum(1 for v in per_window.values() if v > 0))


def median_pnl(per_window: dict[str, float]) -> float:
    vals = np.array(list(per_window.values()), dtype=float)
    return float(np.median(vals)) if len(vals) else float("nan")


def qualifies(
    per_window: dict[str, float],
    total_pnl: float | None = None,
    sharpe_threshold: float | None = None,
) -> bool:
    """Corner-qualification gates.

    3-gate (Phases 1-3, default): sign >= 6/7 AND median(OOS) > 0.
    4-gate (Phase 4+, total_pnl gate): also total_pnl > 0.
    Deployment 4-gate (Phase 6+, sharpe gate): also sharpe_like > sharpe_threshold
    (e.g. NULL_P95_SHARPE_LIKE = 1.06 from phase0_null).

    Phase 1-5 reports used the simpler form. Phase 6 deployment evaluation
    passes both total_pnl AND sharpe_threshold for full 4-gate qualification.
    """
    sign_ok = sign_stability_count(per_window) >= SIGN_STABILITY_MIN
    median_ok = median_pnl(per_window) > 0
    total_ok = True if total_pnl is None else total_pnl > 0
    if sharpe_threshold is None:
        sharpe_ok = True
    else:
        s = sharpe_like_score(per_window)
        sharpe_ok = (not np.isnan(s)) and s > sharpe_threshold
    return sign_ok and median_ok and total_ok and sharpe_ok


def summarize(per_window: dict[str, float], label: str = "", total_pnl: float | None = None) -> str:
    """One-line summary string."""
    score = sharpe_like_score(per_window)
    med = median_pnl(per_window)
    sign = sign_stability_count(per_window)
    qual = "QUALIFIED" if qualifies(per_window, total_pnl=total_pnl) else "REJECTED "
    return (
        f"{label:24s} median=${med:>9.0f}  sharpe_like={score:>7.3f}  "
        f"sign={sign}/{N_WINDOWS}  {qual}"
    )
