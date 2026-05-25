"""Unit tests for src.vbt_backtest.generate_signals.

Tiny hand-built fixtures, no data dependency. One session per scenario,
asserting exact entry timestamps, sides, and fill prices for the rules
that matter to the locked pipeline:

    * entry direction (long only / short only)
    * fill = max(trigger, open) for long; min(trigger, open) for short
    * break-on-first-hit (only the first triggering bar fires)
    * tiebreak (both hit) → long iff close >= open, else short
    * force_exits at the first bar with time >= 11:30, once per session

Run:
    .venv/bin/python -m tests.test_vbt_backtest
"""

import datetime as dt
import sys

import pandas as pd

from src.vbt_backtest import generate_signals

NY = "America/New_York"


def _bars(rows):
    """rows: list of (date_str, time_str, open, high, low, close).
    Returns DataFrame indexed by tz-aware NY timestamps with a session_date
    column — matches load_processed_bars()'s contract."""
    idx, recs = [], []
    for date_str, time_str, o, h, l, c in rows:
        ts = pd.Timestamp(f"{date_str} {time_str}", tz=NY)
        idx.append(ts)
        recs.append(
            {
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "session_date": dt.date.fromisoformat(date_str),
            }
        )
    return pd.DataFrame(recs, index=pd.DatetimeIndex(idx))


def _cands(rows):
    """rows: list of (date_str, high, low). Sets cluster_id=0 per session
    and supplies center=median=midpoint, low/high direct. Default
    entry_location='high_low' uses high/low as anchors."""
    recs = []
    for i, (date_str, hi, lo) in enumerate(rows):
        recs.append(
            {
                "session_date": dt.date.fromisoformat(date_str),
                "cluster_id": i,
                "center": (hi + lo) / 2.0,
                "median": (hi + lo) / 2.0,
                "n_levels": 3,
                "low": float(lo),
                "high": float(hi),
            }
        )
    return pd.DataFrame(recs)


def _entry_at(long_e, short_e, entry_p, ts):
    """Return (side or None, fill) for the entry at ts (if any)."""
    side = None
    if bool(long_e.at[ts]):
        side = "long"
    elif bool(short_e.at[ts]):
        side = "short"
    fill = float(entry_p.at[ts]) if not pd.isna(entry_p.at[ts]) else None
    return side, fill


def _session_entries(long_e, short_e, entry_p, session_date):
    """All bars on session_date that fired an entry. Returns list of
    (ts, side, fill)."""
    in_session = pd.Series(
        long_e.index.tz_convert(NY).date == session_date,
        index=long_e.index,
    )
    fired = (long_e | short_e) & in_session
    out = []
    for ts in long_e.index[fired]:
        side, fill = _entry_at(long_e, short_e, entry_p, ts)
        out.append((ts, side, fill))
    return out


# A common candidate shape used by most scenarios:
#   high=100, low=95, entry_buffer=1.0 →
#     long_trigger = 101.0,  short_trigger = 94.0
def _ts(date_str, time_str):
    return pd.Timestamp(f"{date_str} {time_str}", tz=NY)


def test_long_fill_at_trigger():
    # Bar's open is below trigger → fill at trigger price.
    date = "2024-01-02"
    bars = _bars(
        [
            (date, "09:45", 99.0, 102.0, 99.0, 101.0),
            (date, "11:30", 100.0, 100.0, 100.0, 100.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    long_e, short_e, entry_p, force_e = generate_signals(bars, cands)

    side, fill = _entry_at(long_e, short_e, entry_p, _ts(date, "09:45"))
    assert side == "long", f"expected long, got {side}"
    assert fill == 101.0, f"expected fill 101.0 (trigger), got {fill}"
    print("  OK  long fill at trigger (open < trigger)")


def test_long_fill_gap_at_open():
    # Bar gaps up past trigger → fill at the bar's open (worse).
    date = "2024-01-03"
    bars = _bars(
        [
            (date, "09:45", 103.0, 104.0, 102.0, 104.0),
            (date, "11:30", 104.0, 104.0, 104.0, 104.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    long_e, short_e, entry_p, _ = generate_signals(bars, cands)

    side, fill = _entry_at(long_e, short_e, entry_p, _ts(date, "09:45"))
    assert side == "long"
    assert fill == 103.0, f"expected fill 103.0 (max(101, 103) — gap), got {fill}"
    print("  OK  long fill = max(trigger, open) on gap-up")


def test_short_fill_at_trigger():
    # Bar's open is above trigger → fill at trigger price.
    date = "2024-01-04"
    bars = _bars(
        [
            (date, "09:45", 95.0, 95.0, 93.0, 94.0),
            (date, "11:30", 94.0, 94.0, 94.0, 94.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    long_e, short_e, entry_p, _ = generate_signals(bars, cands)

    side, fill = _entry_at(long_e, short_e, entry_p, _ts(date, "09:45"))
    assert side == "short"
    assert fill == 94.0, f"expected fill 94.0 (trigger), got {fill}"
    print("  OK  short fill at trigger (open > trigger)")


def test_short_fill_gap_at_open():
    # Bar gaps down past trigger → fill at the bar's open (worse).
    date = "2024-01-05"
    bars = _bars(
        [
            (date, "09:45", 90.0, 94.0, 89.0, 92.0),
            (date, "11:30", 92.0, 92.0, 92.0, 92.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    long_e, short_e, entry_p, _ = generate_signals(bars, cands)

    side, fill = _entry_at(long_e, short_e, entry_p, _ts(date, "09:45"))
    assert side == "short"
    assert fill == 90.0, f"expected fill 90.0 (min(94, 90) — gap), got {fill}"
    print("  OK  short fill = min(trigger, open) on gap-down")


def test_tiebreak_long_when_close_ge_open():
    # Both sides hit. close (96) >= open (95) → long.
    date = "2024-01-08"
    bars = _bars(
        [
            (date, "09:45", 95.0, 105.0, 90.0, 96.0),
            (date, "11:30", 96.0, 96.0, 96.0, 96.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    long_e, short_e, entry_p, _ = generate_signals(bars, cands)

    side, fill = _entry_at(long_e, short_e, entry_p, _ts(date, "09:45"))
    assert side == "long", f"tiebreak should resolve long, got {side}"
    assert fill == 101.0, f"expected long fill 101.0, got {fill}"
    print("  OK  tiebreak → long when close >= open")


def test_tiebreak_short_when_close_lt_open():
    # Both sides hit. close (94) < open (95) → short.
    date = "2024-01-09"
    bars = _bars(
        [
            (date, "09:45", 95.0, 105.0, 90.0, 94.0),
            (date, "11:30", 94.0, 94.0, 94.0, 94.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    long_e, short_e, entry_p, _ = generate_signals(bars, cands)

    side, fill = _entry_at(long_e, short_e, entry_p, _ts(date, "09:45"))
    assert side == "short", f"tiebreak should resolve short, got {side}"
    assert fill == 94.0, f"expected short fill 94.0, got {fill}"
    print("  OK  tiebreak → short when close < open")


def test_break_on_first_hit_skips_no_trigger_bar():
    # 09:45 doesn't trigger (high=100 < 101). 09:46 triggers long.
    # Only the 09:46 bar should fire, and only once.
    date = "2024-01-10"
    bars = _bars(
        [
            (date, "09:45", 100.0, 100.0, 99.5, 99.7),
            (date, "09:46", 99.0, 102.0, 99.0, 101.0),
            (date, "09:47", 101.0, 103.0, 100.5, 102.5),  # would also trigger
            (date, "11:30", 102.0, 102.0, 102.0, 102.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    long_e, short_e, entry_p, _ = generate_signals(bars, cands)

    fired = _session_entries(long_e, short_e, entry_p, dt.date(2024, 1, 10))
    assert len(fired) == 1, (
        f"break-on-first-hit: expected exactly 1 entry, got {len(fired)} → {fired}"
    )
    ts, side, fill = fired[0]
    assert ts == _ts(date, "09:46")
    assert side == "long" and fill == 101.0
    # And confirm 09:45 and 09:47 did NOT fire.
    assert not bool(long_e.at[_ts(date, "09:45")])
    assert not bool(long_e.at[_ts(date, "09:47")])
    print("  OK  break-on-first-hit (one entry per session, first triggering bar)")


def test_force_exits_first_bar_at_or_after_1130_only():
    # Per session, force_exits True at the first bar with time >= 11:30,
    # False everywhere else.
    date = "2024-01-11"
    bars = _bars(
        [
            (date, "09:45", 99.0, 100.5, 99.0, 100.0),
            (date, "11:29", 100.0, 100.0, 100.0, 100.0),
            (date, "11:30", 100.0, 100.0, 100.0, 100.0),
            (date, "11:31", 100.0, 100.0, 100.0, 100.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    _, _, _, force_e = generate_signals(bars, cands)

    assert bool(force_e.at[_ts(date, "11:30")]) is True, (
        "force_exits should be True at 11:30 (first ≥-11:30 bar)"
    )
    assert bool(force_e.at[_ts(date, "11:31")]) is False, (
        "force_exits should be False at 11:31 (cumulative > 1)"
    )
    assert bool(force_e.at[_ts(date, "09:45")]) is False
    assert bool(force_e.at[_ts(date, "11:29")]) is False
    print("  OK  force_exits fires once at first ≥-11:30 bar per session")


def test_no_trigger_no_entry():
    # Tight range that never crosses either trigger.
    date = "2024-01-12"
    bars = _bars(
        [
            (date, "09:45", 97.0, 98.0, 96.0, 97.5),
            (date, "11:30", 97.0, 97.0, 97.0, 97.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0)])
    long_e, short_e, entry_p, _ = generate_signals(bars, cands)
    fired = _session_entries(long_e, short_e, entry_p, dt.date(2024, 1, 12))
    assert fired == [], f"no triggers → no entries, got {fired}"
    # entry_prices should be all NaN.
    assert entry_p.isna().all()
    print("  OK  no trigger → no entry, entry_prices all NaN")


def test_multiple_candidates_long_uses_min_triggered():
    # Two candidates: c0 high=100 (long_trigger=101), c1 high=105 (=106).
    # Bar high=110 hits both → trigger = min(101, 106) = 101.
    # Open=100 below trigger → fill = 101.
    date = "2024-01-15"
    bars = _bars(
        [
            (date, "09:45", 100.0, 110.0, 100.0, 109.0),
            (date, "11:30", 109.0, 109.0, 109.0, 109.0),
        ]
    )
    cands = _cands([(date, 100.0, 95.0), (date, 105.0, 90.0)])
    long_e, short_e, entry_p, _ = generate_signals(bars, cands)

    side, fill = _entry_at(long_e, short_e, entry_p, _ts(date, "09:45"))
    assert side == "long"
    assert fill == 101.0, f"multi-cand long: expected min trigger 101.0, got {fill}"
    print("  OK  multi-candidate long uses min of triggered long_triggers")


def main():
    print("Running tests.test_vbt_backtest ...\n")
    test_long_fill_at_trigger()
    test_long_fill_gap_at_open()
    test_short_fill_at_trigger()
    test_short_fill_gap_at_open()
    test_tiebreak_long_when_close_ge_open()
    test_tiebreak_short_when_close_lt_open()
    test_break_on_first_hit_skips_no_trigger_bar()
    test_force_exits_first_bar_at_or_after_1130_only()
    test_no_trigger_no_entry()
    test_multiple_candidates_long_uses_min_triggered()
    print("\nPASS — all generate_signals tests green")


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except AssertionError as e:
        print(f"\nFAIL — {e}", file=sys.stderr)
        sys.exit(1)
