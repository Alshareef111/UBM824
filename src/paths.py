"""Central path resolver for the MNQ strategy project.

All scripts must import from here instead of using Path(__file__).parent.
This keeps file locations in one place — change a path here, every script updates.
"""
from pathlib import Path

# Project root = parent of src/
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Top-level directories
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DOCS_DIR = PROJECT_ROOT / "docs"
RESULTS_DIR = PROJECT_ROOT / "results"
CHARTS_DIR = RESULTS_DIR / "charts"
ARCHIVE_DIR = RESULTS_DIR / "archive"

# Raw data files
# Sorted list of Databento OHLCV-1m batches. Each forward-test extension lands
# here as glbx-mdp3-<start>-<end>.ohlcv-1m.csv; data_prep concatenates them in
# filename order (which equals chronological order given the naming scheme).
RAW_CSV_FILES = sorted(RAW_DIR.glob("glbx-mdp3-*.ohlcv-1m.csv"))
# Deprecated alias for back-compat. Prefer RAW_CSV_FILES. Resolves to the
# earliest batch when present, else the original baseline filename.
RAW_CSV = RAW_CSV_FILES[0] if RAW_CSV_FILES else RAW_DIR / "glbx-mdp3-20240401-20260501.ohlcv-1m.csv"
TICK_FILE = RAW_DIR / "MNQ 06-26.LastT.txt"
MANIFEST_JSON = RAW_DIR / "manifest.json"
METADATA_JSON = RAW_DIR / "metadata.json"
CONDITION_JSON = RAW_DIR / "condition.json"

# Processed data files
BARS_PARQUET = PROCESSED_DIR / "mnq_unadjusted_1m.parquet"
ROLLS_PARQUET = PROCESSED_DIR / "rolls.parquet"
ORB_TABLE_PARQUET = PROCESSED_DIR / "orb_table.parquet"
ORB_EXCLUDED_PARQUET = PROCESSED_DIR / "orb_excluded.parquet"
TRADES_PARQUET = PROCESSED_DIR / "trades.parquet"
TICKS_OVERLAP_PARQUET = PROCESSED_DIR / "ticks_overlap.parquet"
VERIFICATION_PARQUET = PROCESSED_DIR / "verification_results.parquet"

# Helper to ensure all dirs exist (call from any script if needed)
def ensure_dirs() -> None:
    """Create the standard data/results directory tree if missing.

    Idempotent: silently no-ops when directories already exist.
    """
    for d in [RAW_DIR, PROCESSED_DIR, CHARTS_DIR, ARCHIVE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
