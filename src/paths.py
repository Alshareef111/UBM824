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
RAW_CSV = RAW_DIR / "glbx-mdp3-20240401-20260501.ohlcv-1m.csv"
TICK_FILE = RAW_DIR / "MNQ 06-26.LastT.txt"
MANIFEST_JSON = RAW_DIR / "manifest.json"
METADATA_JSON = RAW_DIR / "metadata.json"
CONDITION_JSON = RAW_DIR / "condition.json"

# Processed data files
BARS_PARQUET = PROCESSED_DIR / "mnq_adjusted_1m.parquet"
ROLLS_PARQUET = PROCESSED_DIR / "rolls.parquet"
ORB_TABLE_PARQUET = PROCESSED_DIR / "orb_table.parquet"
ORB_EXCLUDED_PARQUET = PROCESSED_DIR / "orb_excluded.parquet"
TRADES_PARQUET = PROCESSED_DIR / "trades.parquet"
TICKS_OVERLAP_PARQUET = PROCESSED_DIR / "ticks_overlap.parquet"
VERIFICATION_PARQUET = PROCESSED_DIR / "verification_results.parquet"

# Helper to ensure all dirs exist (call from any script if needed)
def ensure_dirs():
    for d in [RAW_DIR, PROCESSED_DIR, CHARTS_DIR, ARCHIVE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
