"""Data preparation for MNQ backtest.

Reads the raw CSV (all MNQ contract bars), drops calendar spreads, picks the
front-month per session date with sticky forward-only rollover, and applies
Panama back-adjustment to produce a continuous price series. Writes parquet.

Run once:
    python data_prep.py
"""

import re
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from paths import RAW_CSV, BARS_PARQUET, ROLLS_PARQUET, ensure_dirs

OUTRIGHT_REGEX = re.compile(r"^MNQ[HMUZ]\d+$")
MONTH_IDX = {"H": 0, "M": 1, "U": 2, "Z": 3}
NY_TZ = ZoneInfo("America/New_York")
# CME futures halt at 17:00 NY and reopen at 18:00 NY. Bars at/after 18:00 NY
# belong to the next session. Adding 6h to NY-local time pushes the boundary
# to midnight so .dt.date yields the correct session date in one step.
SESSION_OFFSET_HOURS = 6


def contract_rank(symbol: str) -> int:
    # Single-digit year is fine for 2024-2029. Past 2029 the 9->0 wrap would
    # invert ordering and this needs to handle the decade boundary.
    return int(symbol[4:]) * 4 + MONTH_IDX[symbol[3]]


def load_and_filter_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        usecols=["ts_event", "open", "high", "low", "close", "volume", "symbol"],
        dtype={
            "symbol": "string",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "int64",
        },
    )
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df = df[df["symbol"].str.match(OUTRIGHT_REGEX, na=False)].copy()
    df = df.sort_values("ts_event").reset_index(drop=True)
    return df


def add_session_date(df: pd.DataFrame) -> pd.DataFrame:
    ny_time = df["ts_event"].dt.tz_convert(NY_TZ)
    df["ts_ny"] = ny_time
    df["session_date"] = (ny_time + pd.Timedelta(hours=SESSION_OFFSET_HOURS)).dt.date
    return df


def assign_front_months(df: pd.DataFrame) -> pd.DataFrame:
    daily_vol = (
        df.groupby(["session_date", "symbol"])["volume"]
        .sum()
        .unstack(fill_value=0)
    )

    rows = []
    current = None
    for date in sorted(daily_vol.index):
        day = daily_vol.loc[date]
        if current is None or current not in day.index or day[current] == 0:
            current = day.idxmax()
        else:
            current_r = contract_rank(current)
            forward = day[[s for s in day.index if contract_rank(s) > current_r]]
            if not forward.empty:
                best = forward.idxmax()
                if forward[best] > day[current]:
                    current = best
        rows.append({"session_date": date, "front_month": current})
    return pd.DataFrame(rows)


def detect_transitions(fronts: pd.DataFrame) -> list[tuple]:
    transitions = []
    prev = None
    for _, r in fronts.iterrows():
        if prev is not None and r["front_month"] != prev:
            transitions.append((r["session_date"], prev, r["front_month"]))
        prev = r["front_month"]
    return transitions


def compute_roll_gaps(raw: pd.DataFrame, transitions: list) -> pd.DataFrame:
    by_symbol = {s: g for s, g in raw.groupby("symbol", sort=False)}
    records = []
    for roll_date, old, new in transitions:
        old_pre = by_symbol[old][by_symbol[old]["session_date"] < roll_date]
        new_pre = by_symbol[new][by_symbol[new]["session_date"] < roll_date]
        merged = old_pre[["ts_event", "close"]].merge(
            new_pre[["ts_event", "close"]],
            on="ts_event",
            suffixes=("_old", "_new"),
        )
        if not merged.empty:
            ref = merged.iloc[-1]
            gap = float(ref["close_new"] - ref["close_old"])
            ref_ts = ref["ts_event"]
        else:
            # No simultaneous bar before the roll: fall back to last old close
            # and first new close. Less accurate but rare.
            old_last = old_pre["close"].iloc[-1] if not old_pre.empty else np.nan
            new_post = by_symbol[new][by_symbol[new]["session_date"] >= roll_date]
            new_first = new_post["close"].iloc[0] if not new_post.empty else np.nan
            gap = float(new_first - old_last)
            ref_ts = pd.NaT
        records.append({
            "roll_date": roll_date,
            "old_contract": old,
            "new_contract": new,
            "gap": gap,
            "ref_ts": ref_ts,
        })
    return pd.DataFrame(records)


def build_adjustments(rolls: pd.DataFrame) -> dict:
    if rolls.empty:
        return {}
    adj = {}
    cumulative = 0.0
    for _, r in rolls.iloc[::-1].iterrows():
        adj[r["old_contract"]] = cumulative + r["gap"]
        cumulative += r["gap"]
    adj[rolls.iloc[-1]["new_contract"]] = 0.0
    return adj


def filter_to_front_month(raw: pd.DataFrame, fronts: pd.DataFrame) -> pd.DataFrame:
    merged = raw.merge(fronts, on="session_date", how="inner")
    return merged[merged["symbol"] == merged["front_month"]].copy()


def apply_panama_adjustment(front_bars: pd.DataFrame, rolls: pd.DataFrame) -> pd.DataFrame:
    adj = build_adjustments(rolls)
    if not adj:
        return front_bars
    adj_series = front_bars["symbol"].map(adj).fillna(0.0)
    for col in ("open", "high", "low", "close"):
        front_bars[col] = front_bars[col] + adj_series
    return front_bars


def sanity_checks(out: pd.DataFrame) -> None:
    dupes = out["ts_utc"].duplicated().sum()
    assert dupes == 0, f"Duplicate timestamps in output: {dupes}"

    neg_vol = (out["volume"] < 0).sum()
    assert neg_vol == 0, f"Negative volumes: {neg_vol} bars"

    hi_violations = (out["high"] < out[["open", "close"]].max(axis=1)).sum()
    assert hi_violations == 0, f"OHLC integrity (high): {hi_violations} bars where high < max(open, close)"

    lo_violations = (out["low"] > out[["open", "close"]].min(axis=1)).sum()
    assert lo_violations == 0, f"OHLC integrity (low): {lo_violations} bars where low > min(open, close)"

    weekday = out["session_date"].dt.weekday
    bad_days = out.loc[weekday >= 5, "session_date"].unique()
    assert len(bad_days) == 0, f"Non-weekday session dates: {bad_days[:5]}"


def main() -> None:
    ensure_dirs()
    print(f"Loading {RAW_CSV.name}...")
    raw = load_and_filter_csv(RAW_CSV)
    print(f"  {len(raw):,} outright bars across {raw['symbol'].nunique()} contracts")

    raw = add_session_date(raw)

    print("Assigning front-month per session...")
    fronts = assign_front_months(raw)
    contracts_used = sorted(fronts["front_month"].unique(), key=contract_rank)
    print(f"  {len(fronts)} session days, contracts used: {contracts_used}")

    transitions = detect_transitions(fronts)
    print(f"  {len(transitions)} rollover(s)")

    print("Computing roll gaps...")
    rolls = compute_roll_gaps(raw, transitions)
    if not rolls.empty:
        print(rolls[["roll_date", "old_contract", "new_contract", "gap"]].to_string(index=False))

    print("Filtering to front-month bars...")
    front_bars = filter_to_front_month(raw, fronts)
    print(f"  {len(front_bars):,} bars retained")

    print("Applying Panama back-adjustment...")
    adjusted = apply_panama_adjustment(front_bars, rolls)

    out = (
        adjusted[["ts_event", "ts_ny", "session_date", "symbol",
                  "open", "high", "low", "close", "volume"]]
        .rename(columns={"ts_event": "ts_utc", "symbol": "contract"})
        .sort_values("ts_utc")
        .reset_index(drop=True)
    )
    # Parquet handles datetime64 cleanly; Python date objects sometimes don't.
    out["session_date"] = pd.to_datetime(out["session_date"])

    print("Running sanity checks...")
    sanity_checks(out)
    print("  all checks passed")

    print(f"Writing {BARS_PARQUET.name}...")
    out.to_parquet(BARS_PARQUET, index=False)

    print(f"Writing {ROLLS_PARQUET.name}...")
    rolls.to_parquet(ROLLS_PARQUET, index=False)

    n_sessions = out["session_date"].nunique()
    total_vol = int(out["volume"].sum())
    avg_bars = len(out) / n_sessions
    print(
        f"Done. {len(out):,} bars, "
        f"{out['session_date'].min().date()} to {out['session_date'].max().date()}, "
        f"{out['contract'].nunique()} contracts."
    )
    print(f"  Unique session days: {n_sessions}")
    print(f"  Avg bars per day:    {avg_bars:.1f}")
    print(f"  Total volume:        {total_vol:,}")


if __name__ == "__main__":
    main()
