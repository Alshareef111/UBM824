"""Databento DBN -> ticks parquet cache builder.

Ingests a Databento trades-schema dbn.zst download into the same parquet
schema as `ticks_overlap.parquet` so the existing tick consumers
(`tick_replay_v2*.py`, `verify_ticks.py`) work unchanged.

Schema produced (matches `ticks_overlap.parquet`):
    ts_utc  : pd.Timestamp (UTC)
    last    : float64 (trade print price)
    bid     : float64 (NaN — not in trades schema)
    ask     : float64 (NaN — not in trades schema)
    volume  : int64 (trade size in contracts)

Defaults are wired for the Tight-window Databento purchase:
    input:  data/raw/mnq_trades_2026-01-01_to_2026-05-01.dbn.zst
    output: data/processed/ticks_databento_2026-01-01_to_2026-05-01.parquet

For other date ranges, run with --input / --output overrides (or edit
the constants below).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data/raw/mnq_trades_2026-01-01_to_2026-05-01.dbn.zst"
DEFAULT_OUTPUT = REPO_ROOT / "data/processed/ticks_databento_2026-01-01_to_2026-05-01.parquet"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="Databento dbn.zst file (default: Tight window)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Output parquet path (default: matches input)")
    args = parser.parse_args()

    in_path: Path = args.input
    out_path: Path = args.output

    if not in_path.exists():
        sys.exit(f"FAIL: input not found: {in_path}")
    if out_path.exists():
        sys.exit(f"FAIL: refusing to overwrite existing output: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import databento as db
    except ImportError:
        sys.exit("FAIL: databento SDK not installed. Run: pip3 install databento")

    raw_size = in_path.stat().st_size
    print(f"Input:  {in_path}")
    print(f"        {raw_size:,} bytes ({raw_size / 1024**3:.3f} GiB on disk)")
    print(f"Output: {out_path}")
    print()

    t0 = time.time()
    print("Loading DBN store...")
    store = db.DBNStore.from_file(in_path)

    print("Converting to DataFrame (pretty_ts=True, price_type=float)...")
    # to_df returns a DataFrame with ts_recv as index and ts_event + price + size
    # + side + symbol etc. as columns. price_type='float' auto-scales the int64
    # price field by 1e-9.
    try:
        df = store.to_df(pretty_ts=True, price_type="float")
    except TypeError:
        # Older databento SDK: parameters may differ slightly.
        df = store.to_df()

    raw_rows = len(df)
    print(f"  raw DBN rows: {raw_rows:,}")
    print(f"  columns: {list(df.columns)}")
    print(f"  index name: {df.index.name}")

    # ts_event is the actual trade timestamp (when the event occurred on the
    # exchange). ts_recv is when Databento received the message. We want
    # ts_event to match the convention in ticks_overlap.parquet (NinjaTrader
    # Last timestamps are execution times).
    if "ts_event" in df.columns:
        ts_series = df["ts_event"]
    elif df.index.name == "ts_event":
        ts_series = df.index.to_series()
    elif df.index.name == "ts_recv" and "ts_event" not in df.columns:
        print("  WARNING: no ts_event column; falling back to ts_recv (the index)")
        ts_series = df.index.to_series()
    else:
        sys.exit(f"FAIL: cannot identify trade-time column. Columns: {list(df.columns)}, "
                 f"index: {df.index.name}")

    # Normalize ts_series to UTC Timestamp
    ts_utc = pd.to_datetime(ts_series, utc=True) if not pd.api.types.is_datetime64_any_dtype(ts_series) else ts_series
    if ts_utc.dt.tz is None:
        ts_utc = ts_utc.dt.tz_localize("UTC")

    # price column — should be float after pretty_ts conversion; coerce if int
    if "price" not in df.columns:
        sys.exit(f"FAIL: no price column. Columns: {list(df.columns)}")
    price = pd.to_numeric(df["price"], errors="coerce")
    if pd.api.types.is_integer_dtype(price):
        # Unconverted DBN integer price — divide by 1e9 to get actual price
        print("  scaling integer price field by 1e-9")
        price = price.astype("float64") / 1e9

    # size -> volume
    if "size" not in df.columns:
        sys.exit(f"FAIL: no size column. Columns: {list(df.columns)}")
    volume = pd.to_numeric(df["size"], errors="coerce").astype("Int64")

    coerced_price = int(price.isna().sum())
    coerced_volume = int(volume.isna().sum())

    out = pd.DataFrame({
        "ts_utc": ts_utc.reset_index(drop=True),
        "last": price.reset_index(drop=True),
        "bid": pd.Series([np.nan] * raw_rows, dtype="float64"),
        "ask": pd.Series([np.nan] * raw_rows, dtype="float64"),
        "volume": volume.reset_index(drop=True),
    })

    # Drop any row with missing ts or price (cannot be used by verifier)
    before_drop = len(out)
    valid = out["ts_utc"].notna() & out["last"].notna()
    out = out[valid].reset_index(drop=True)
    after_drop = len(out)
    dropped = before_drop - after_drop

    # Sort by timestamp (DBN is usually already sorted but verify)
    out = out.sort_values("ts_utc").reset_index(drop=True)

    print()
    print("Writing parquet...")
    out.to_parquet(out_path, index=False)
    elapsed = time.time() - t0

    cache_size = out_path.stat().st_size
    print()
    print("=" * 72)
    print("Cache built")
    print("=" * 72)
    print(f"Rows in:                  {raw_rows:,}")
    print(f"Rows dropped (no ts/price): {dropped:,}")
    print(f"Rows coerced (price NaN): {coerced_price:,}")
    print(f"Rows coerced (volume NaN):{coerced_volume:,}")
    print(f"Rows out:                 {len(out):,}")
    print(f"ts_utc min:               {out['ts_utc'].min()}")
    print(f"ts_utc max:               {out['ts_utc'].max()}")
    print(f"Output file:              {out_path}")
    print(f"Output size:              {cache_size:,} bytes ({cache_size / 1024**2:.1f} MiB)")
    print(f"Compression ratio:        {raw_size / cache_size:.2f}x vs input dbn.zst")
    print(f"Elapsed:                  {elapsed:.1f} s")


if __name__ == "__main__":
    main()
