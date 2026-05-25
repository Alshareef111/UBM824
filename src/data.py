"""
src/data.py — MNQ data loader and continuous-series builder.

Loads raw Databento 1-min CSVs (symlinked into data/raw/), filters to outright
contracts, identifies front-month per session via volume crossover, and builds
an unadjusted continuous series saved as data/processed/mnq_unadjusted_1m.parquet.

Run from project root:
    python -m src.data compare    # Side-by-side: volume vs existing rolls
    python -m src.data process    # Build the canonical parquet (default)
    python -m src.data info       # Show stats about the processed parquet
"""

import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
PROCESSED_PARQUET = DATA_PROCESSED / "mnq_unadjusted_1m.parquet"

# Outright MNQ contracts: MNQH4, MNQM24, MNQU5, MNQZ26, etc.
# Quarterly letters: H=Mar, M=Jun, U=Sep, Z=Dec
OUTRIGHT_PATTERN = re.compile(r"^MNQ[HMUZ]\d+$")


# ─── Loading ──────────────────────────────────────────────────────────────

def list_raw_csvs() -> list[Path]:
    """List the Databento 1-min OHLCV CSVs in ``data/raw/``, sorted.

    Returns:
        List of Paths matching ``glbx-mdp3-*.ohlcv-1m.csv``.
    """
    return sorted(DATA_RAW.glob("glbx-mdp3-*.ohlcv-1m.csv"))


def load_raw_bars(verbose: bool = True) -> pd.DataFrame:
    """Load all raw 1-min bars, drop calendar spreads, keep only outrights.

    Args:
        verbose: Print per-file progress and a summary.

    Returns:
        Concatenated DataFrame of outright MNQ bars sorted by
        (ts_event, symbol). ``ts_event`` is tz-aware UTC.
    """
    csvs = list_raw_csvs()
    if not csvs:
        raise FileNotFoundError(f"No glbx-mdp3-*.ohlcv-1m.csv in {DATA_RAW}")

    frames = []
    for path in csvs:
        if verbose:
            print(f"Loading {path.name} ...", flush=True)
        df = pd.read_csv(
            path,
            usecols=["ts_event", "symbol", "open", "high", "low", "close", "volume"],
            parse_dates=["ts_event"],
        )
        before = len(df)
        df = df[df["symbol"].astype(str).str.match(OUTRIGHT_PATTERN)].copy()
        if verbose:
            print(f"  {before:,} rows -> {len(df):,} outright "
                  f"({before - len(df):,} dropped)")
        frames.append(df)

    bars = pd.concat(frames, ignore_index=True)
    if bars["ts_event"].dt.tz is None:
        bars["ts_event"] = bars["ts_event"].dt.tz_localize("UTC")
    bars = bars.sort_values(["ts_event", "symbol"]).reset_index(drop=True)

    if verbose:
        print(f"\nTotal: {len(bars):,} outright bars")
        print(f"Range: {bars['ts_event'].min()} -> {bars['ts_event'].max()}")
        print(f"Contracts: {bars['symbol'].nunique()} unique")
    return bars


# ─── Roll detection ───────────────────────────────────────────────────────

def build_front_map(bars: pd.DataFrame) -> pd.Series:
    """Map every NY session_date to its front-month contract by volume.

    For each session, the contract with the highest aggregate 1-min volume
    is the front-month.

    Args:
        bars: Raw bars with ``ts_event`` (UTC), ``symbol``, ``volume``.

    Returns:
        Series of contract symbols indexed by ``session_date``.
    """
    df = bars[["ts_event", "symbol", "volume"]].copy()
    df["session_date"] = df["ts_event"].dt.tz_convert("America/New_York").dt.date
    daily = df.groupby(["session_date", "symbol"], as_index=False)["volume"].sum()
    daily = daily.sort_values(["session_date", "volume"], ascending=[True, False])
    front = daily.drop_duplicates(subset=["session_date"], keep="first")
    return front.set_index("session_date")["symbol"]


def compute_rolls_from_volume(bars: pd.DataFrame) -> pd.DataFrame:
    """Roll dates from volume crossover (kept for ``compare_rolls``).

    Args:
        bars: Raw bars (see ``build_front_map``).

    Returns:
        DataFrame with ``roll_date``, ``old_front``, ``new_front`` for each
        session where the front-month contract changed.
    """
    front_map = build_front_map(bars)
    s = front_map.sort_index()
    prev = s.shift(1)
    rolls = pd.DataFrame({
        "roll_date": s.index,
        "old_front": prev.values,
        "new_front": s.values,
    })
    rolls = rolls[
        (rolls["old_front"] != rolls["new_front"]) & rolls["old_front"].notna()
    ].reset_index(drop=True)
    return rolls


def load_existing_rolls() -> pd.DataFrame:
    """Load the externally-supplied roll table from ``data/raw``.

    Returns:
        DataFrame as stored in ``rolls_existing.parquet``.
    """
    p = DATA_RAW / "rolls_existing.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found — symlink missing?")
    return pd.read_parquet(p)


# ─── Continuous series ────────────────────────────────────────────────────

def build_continuous_unadjusted(
    bars: pd.DataFrame,
    front_map: pd.Series,
) -> pd.DataFrame:
    """Keep only bars whose contract == front-month for that session_date.

    Args:
        bars:      Raw bars (see ``load_raw_bars``).
        front_map: Series of front-month symbols indexed by session_date
                   (see ``build_front_map``).

    Returns:
        DataFrame with columns ``ts_utc``, ``ts_ny``, ``session_date``,
        ``contract``, ``open``, ``high``, ``low``, ``close``, ``volume``,
        sorted by ``ts_utc``.
    """
    df = bars.copy()
    df["session_date"] = df["ts_event"].dt.tz_convert("America/New_York").dt.date
    df["front"] = df["session_date"].map(front_map)

    df = df[df["symbol"] == df["front"]].copy()

    df["ts_utc"] = df["ts_event"]
    df["ts_ny"] = df["ts_event"].dt.tz_convert("America/New_York")
    df = df.rename(columns={"symbol": "contract"})
    cols = ["ts_utc", "ts_ny", "session_date", "contract",
            "open", "high", "low", "close", "volume"]
    return df[cols].sort_values("ts_utc").reset_index(drop=True)


def save_processed(df: pd.DataFrame, path: Path = PROCESSED_PARQUET) -> None:
    """Write ``df`` to a snappy-compressed parquet at ``path``.

    Args:
        df:   DataFrame to persist (typically the continuous-unadjusted
              bars from ``build_continuous_unadjusted``).
        path: Destination parquet path. Parent directory is created if
              missing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", compression="snappy")
    size_mb = path.stat().st_size / (1024 ** 2)
    print(f"\nSaved {len(df):,} rows to {path}")
    print(f"File size: {size_mb:.1f} MB")


def load_processed_bars(path: Path = PROCESSED_PARQUET) -> pd.DataFrame:
    """Load the canonical continuous bars, indexed by ts_ny (tz-aware ET).

    The NY-time index makes session-based logic ergonomic — between_time(),
    daily groupby on session_date, etc. The ts_utc column is preserved.

    Args:
        path: Source parquet (defaults to ``PROCESSED_PARQUET``).

    Returns:
        DataFrame indexed by ``ts_ny`` (tz-aware ET) with columns
        ``ts_utc``, ``session_date``, ``contract``, ``open``, ``high``,
        ``low``, ``close``, ``volume``.
    """
    df = pd.read_parquet(path)
    df = df.set_index("ts_ny").sort_index()
    return df


# ─── CLI commands ─────────────────────────────────────────────────────────

def compare_rolls():
    print("=" * 72)
    print("LOAD RAW BARS")
    print("=" * 72)
    bars = load_raw_bars()

    print("\n" + "=" * 72)
    print("EXISTING rolls.parquet")
    print("=" * 72)
    existing = load_existing_rolls()
    print(f"Shape: {existing.shape}")
    print("\nFirst 5:")
    print(existing.head().to_string())
    print("\nLast 5:")
    print(existing.tail().to_string())

    print("\n" + "=" * 72)
    print("COMPUTED rolls (volume crossover)")
    print("=" * 72)
    computed = compute_rolls_from_volume(bars)
    print(f"Shape: {computed.shape}")
    print("\nFirst 5:")
    print(computed.head().to_string())
    print("\nLast 5:")
    print(computed.tail().to_string())


def process():
    print("=" * 72)
    print("BUILDING CONTINUOUS UNADJUSTED SERIES (volume-based rolls)")
    print("=" * 72)
    bars = load_raw_bars()
    front_map = build_front_map(bars)
    print(f"\nFront-month assigned for {len(front_map):,} session dates")

    df = build_continuous_unadjusted(bars, front_map)
    print(f"\nContinuous series: {len(df):,} bars")
    print(f"Range: {df['ts_utc'].min()} -> {df['ts_utc'].max()}")
    print(f"Sessions: {df['session_date'].nunique():,}")
    print(f"Contracts used: {df['contract'].nunique()}")

    save_processed(df)


def info():
    if not PROCESSED_PARQUET.exists():
        print(f"No processed parquet at {PROCESSED_PARQUET}")
        print("Run: python -m src.data process")
        return
    df = pd.read_parquet(PROCESSED_PARQUET)
    print(f"File: {PROCESSED_PARQUET}")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {list(df.columns)}")
    print(f"\nDate range:")
    print(f"  UTC: {df['ts_utc'].min()} -> {df['ts_utc'].max()}")
    print(f"  NY:  {df['ts_ny'].min()} -> {df['ts_ny'].max()}")
    print(f"Sessions: {df['session_date'].nunique():,}")
    print(f"Contracts: {sorted(df['contract'].unique())}")
    print(f"\nSample (first 3):")
    print(df.head(3).to_string())
    print(f"\nSample (last 3):")
    print(df.tail(3).to_string())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "process"
    {"compare": compare_rolls, "process": process, "info": info}.get(
        cmd, lambda: print(f"Unknown: {cmd}\nUsage: compare | process | info")
    )()