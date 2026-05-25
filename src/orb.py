"""ORB (Opening Range) calculation.

Reads the front-month adjusted parquet, computes the 9:30-9:45 NY ORB high,
low, and close for each session, and writes a clean per-session table.
Sessions with incomplete ORB windows (holidays, half-days, gaps) are excluded
and logged separately.

Run after data_prep.py:
    python orb.py
"""

from pathlib import Path

import pandas as pd

from paths import BARS_PARQUET, ORB_TABLE_PARQUET, ORB_EXCLUDED_PARQUET, ensure_dirs

# 1-minute bar timestamped HH:MM represents the interval [HH:MM, HH:MM+1).
# 9:30-9:45 NY = 15 bars timestamped 9:30 ... 9:44 (last bar's close = 9:45:00).
ORB_START_HM = (9, 30)
ORB_END_HM = (9, 45)
EXPECTED_BARS = 15
MIN_BARS_REQUIRED = 14  # allow up to one minute of missing data


def in_orb_window(ts_ny: pd.Series) -> pd.Series:
    """Boolean mask of timestamps inside the [09:30, 09:45) NY window.

    Args:
        ts_ny: Datetime Series in NY time.

    Returns:
        Boolean Series aligned with ``ts_ny``.
    """
    h = ts_ny.dt.hour
    m = ts_ny.dt.minute
    after_start = (h > ORB_START_HM[0]) | ((h == ORB_START_HM[0]) & (m >= ORB_START_HM[1]))
    before_end = (h < ORB_END_HM[0]) | ((h == ORB_END_HM[0]) & (m < ORB_END_HM[1]))
    return after_start & before_end


def compute_orb(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute per-session ORB high/low/close and partition by completeness.

    Args:
        bars: DataFrame with ``ts_ny``, ``session_date``, ``high``, ``low``,
              ``close``.

    Returns:
        Pair of DataFrames ``(complete, excluded)``. ``complete`` carries
        ``session_date``, ``orb_high``, ``orb_low``, ``orb_close``,
        ``num_bars`` for sessions with >= MIN_BARS_REQUIRED bars in window.
        ``excluded`` has the remaining sessions plus a ``reason`` column
        (``no_bars_in_window`` or ``partial_window``).
    """
    in_window = bars[in_orb_window(bars["ts_ny"])]

    # Bars are sorted by ts_utc globally, so within each session group the last
    # row is the bar timestamped 9:44 — its close is the price at 9:45:00.
    agg = in_window.groupby("session_date", as_index=False).agg(
        orb_high=("high", "max"),
        orb_low=("low", "min"),
        orb_close=("close", "last"),
        num_bars=("ts_ny", "count"),
    )

    all_sessions = pd.DataFrame({"session_date": sorted(bars["session_date"].unique())})
    full = all_sessions.merge(agg, on="session_date", how="left")
    full["num_bars"] = full["num_bars"].fillna(0).astype(int)

    complete = full[full["num_bars"] >= MIN_BARS_REQUIRED].reset_index(drop=True)
    excluded = full[full["num_bars"] < MIN_BARS_REQUIRED].reset_index(drop=True)
    excluded["reason"] = excluded["num_bars"].apply(
        lambda n: "no_bars_in_window" if n == 0 else "partial_window"
    )
    return complete, excluded


def main() -> None:
    ensure_dirs()
    print(f"Loading {BARS_PARQUET.name}...")
    bars = pd.read_parquet(BARS_PARQUET)
    print(f"  {len(bars):,} bars across {bars['session_date'].nunique()} sessions")

    print("Computing ORB...")
    complete, excluded = compute_orb(bars)

    if not excluded.empty:
        print(f"Excluding {len(excluded)} sessions with < {MIN_BARS_REQUIRED} bars in ORB window:")
        for _, row in excluded.iterrows():
            print(f"  {row['session_date'].date()}: {row['num_bars']} bars ({row['reason']})")

    print(f"Writing {ORB_TABLE_PARQUET.name}...")
    complete.to_parquet(ORB_TABLE_PARQUET, index=False)

    if not excluded.empty:
        print(f"Writing {ORB_EXCLUDED_PARQUET.name}...")
        excluded.to_parquet(ORB_EXCLUDED_PARQUET, index=False)

    range_pts = complete["orb_high"] - complete["orb_low"]
    print(f"Done. {len(complete)} complete ORB sessions.")
    print(f"  Avg ORB range:    {range_pts.mean():.2f} pts")
    print(f"  Median ORB range: {range_pts.median():.2f} pts")
    print(f"  Max ORB range:    {range_pts.max():.2f} pts")
    print(f"  Min ORB range:    {range_pts.min():.2f} pts")


if __name__ == "__main__":
    main()
