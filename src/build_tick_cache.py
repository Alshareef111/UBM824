"""Single-pass tick-cache builder.

Streams MNQ 06-26.LastT.txt once and keeps only ticks that fall inside any
trade's [entry_time - 1min, exit_time + 1min] window for trades whose
session_date is in the 2026-03-17..2026-05-01 overlap with the tick file.

Outputs ticks_overlap.parquet locally so per-trade verification reads from
disk instead of re-streaming Google Drive.
"""

import time
from datetime import datetime, timezone

import pandas as pd

from paths import TICK_FILE, TICKS_OVERLAP_PARQUET, TRADES_PARQUET, ensure_dirs

OVERLAP_START_DATE = pd.Timestamp("2026-03-17")
OVERLAP_END_DATE = pd.Timestamp("2026-05-01")
BUFFER = pd.Timedelta(minutes=1)

UTC = timezone.utc


def minute_prefix(dt: datetime) -> str:
    """13-char prefix 'YYYYMMDD HHMM' — comparable lexicographically because the
    format is fixed-width."""
    return dt.strftime("%Y%m%d %H%M")


def main() -> None:
    ensure_dirs()
    trades = pd.read_parquet(TRADES_PARQUET)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades["session_date"] = pd.to_datetime(trades["session_date"])

    overlap = trades[
        (trades["session_date"] >= OVERLAP_START_DATE)
        & (trades["session_date"] <= OVERLAP_END_DATE)
    ].copy()

    print(
        f"Trades in overlap window (session_date 2026-03-17..2026-05-01): "
        f"{len(overlap)} / {len(trades)} total"
    )

    # Session-wide windows: for each session_date that has any overlap trade,
    # cache 13:45 UTC -> 15:31 UTC (covers the 9:46-11:30 NY trading window
    # plus a 1-minute buffer on each side). This guarantees gap-free coverage
    # so verification can stream chronologically without crossing trade boundaries.
    sessions = sorted(overlap["session_date"].dt.date.unique())
    raw = []
    for sd in sessions:
        s = pd.Timestamp(f"{sd} 13:45:00", tz="UTC").to_pydatetime()
        e = pd.Timestamp(f"{sd} 15:31:00", tz="UTC").to_pydatetime()
        raw.append((s, e))
    raw.sort()

    merged: list[tuple[datetime, datetime]] = []
    for s, e in raw:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    print(f"Merged windows: {len(merged)}")
    print(f"Stream from {merged[0][0]} -> {merged[-1][1]}")

    # Pre-compute minute prefixes for all interval boundaries
    iv_prefix_s = [minute_prefix(s) for s, _ in merged]
    iv_prefix_e = [minute_prefix(e) for _, e in merged]
    overall_start_p = iv_prefix_s[0]
    overall_end_p = iv_prefix_e[-1]

    iv_idx = 0
    cur_s_p = iv_prefix_s[iv_idx]
    cur_e_p = iv_prefix_e[iv_idx]

    rec_ts: list[datetime] = []
    rec_last: list[float] = []
    rec_bid: list[float] = []
    rec_ask: list[float] = []
    rec_vol: list[int] = []

    total_lines = 0
    kept = 0

    t0 = time.time()
    with open(TICK_FILE, buffering=4 * 1024 * 1024) as f:
        for line in f:
            total_lines += 1
            mp = line[:13]  # 'YYYYMMDD HHMM'
            if mp < overall_start_p:
                continue
            if mp > overall_end_p:
                break
            # Advance current interval if past the end
            while mp > cur_e_p:
                iv_idx += 1
                if iv_idx >= len(merged):
                    cur_s_p = cur_e_p = None
                    break
                cur_s_p = iv_prefix_s[iv_idx]
                cur_e_p = iv_prefix_e[iv_idx]
            if cur_s_p is None:
                break
            if mp < cur_s_p:
                continue
            # In a window — full parse
            try:
                y = int(line[0:4])
                mo = int(line[4:6])
                d = int(line[6:8])
                h = int(line[9:11])
                mi = int(line[11:13])
                sec = int(line[13:15])
                us = int(line[16:23]) // 10  # 7-digit 100-ns -> microseconds
                if us > 999999:
                    us = 999999
                ts = datetime(y, mo, d, h, mi, sec, us, tzinfo=UTC)
                rest = line[24:].rstrip("\n")
                p_last, p_bid, p_ask, p_vol = rest.split(";")
                rec_ts.append(ts)
                rec_last.append(float(p_last))
                rec_bid.append(float(p_bid))
                rec_ask.append(float(p_ask))
                rec_vol.append(int(p_vol))
                kept += 1
            except (ValueError, IndexError):
                continue

    elapsed = time.time() - t0

    df = pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(rec_ts, utc=True),
            "last": rec_last,
            "bid": rec_bid,
            "ask": rec_ask,
            "volume": rec_vol,
        }
    )
    df = df.sort_values("ts_utc").reset_index(drop=True)
    df.to_parquet(TICKS_OVERLAP_PARQUET, index=False)

    print()
    print(f"Lines scanned:   {total_lines:>15,}")
    print(f"Ticks cached:    {kept:>15,}")
    print(
        f"Cache file:      {TICKS_OVERLAP_PARQUET.name} ({TICKS_OVERLAP_PARQUET.stat().st_size / 1024 / 1024:.2f} MB)"
    )
    print(f"Elapsed:         {elapsed:.1f} s")
    print(f"Avg lines/sec:   {total_lines / elapsed:,.0f}")
    if kept:
        print(f"Cached ticks span: {df['ts_utc'].min()} -> {df['ts_utc'].max()}")


if __name__ == "__main__":
    main()
