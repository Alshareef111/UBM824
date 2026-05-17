"""V2 + 40/40 tick replayer — Window variant (full-population in tick coverage).

Fork of tick_replay_v2.py. Identical per-trade algorithm; differs only in
input filtering and reporting:

  - Processes ALL trades whose entry_time falls in the tick coverage window,
    not just the Phase 1 sample.
  - Phase 1 sample membership is tracked as a per-trade flag and as a summary
    metric (cross-reference for audit-trail consistency), not used as a filter.
  - Stop-out Bug B summary (sub-section) is broken out separately, since
    Bug B is a stop-side concept and stops are the audit-relevant subset.
  - Reports the 09:46-10:55 NY Bug B concentration band incidence on stops.

The original `tick_replay_v2.py` stays as the Phase 1-only canonical verifier
for audit-trail consistency. Both can be run independently; the Window variant
is the workhorse for quantifying Bug B incidence on the deployment-relevant
subset (e.g., the 2026-01-01..2026-05-01 Tight window after Databento data
acquisition).

Design: results/tick_verification/_phase2_replayer_design.md
Cache:  defaults to data/processed/ticks_databento_2026-01-01_to_2026-05-01.parquet
        (built from the Databento dbn.zst download via a future cache-builder;
        falls back to ticks_overlap.parquet if the Databento cache is missing).

Inputs:
  - results/40_40_v2_full/20260514_125349/trades.parquet  (sha256-pinned)
  - data/processed/<tick parquet, see TICKS_PATH below>
  - results/tick_verification/phase1_sample_20260516.csv  (sha256-pinned;
    used only for cross-reference annotation, never as a filter)

Output (one new dir per run):
  results/tick_verification/phase2_window_<YYYYMMDD_HHMMSS>/
    - reconciliation.parquet
    - summary.json
    - report.md
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------- Config ----------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TRADES_PATH = REPO_ROOT / "results/40_40_v2_full/20260514_125349/trades.parquet"
SAMPLE_CSV = REPO_ROOT / "results/tick_verification/phase1_sample_20260516.csv"
OUTPUT_BASE = REPO_ROOT / "results/tick_verification"

# Preferred tick cache: Databento Jan-May 2026 (Tight window).
# Fallback: NinjaTrader overlap cache (Mar 17 - Apr 15 2026).
TICKS_DATABENTO_PARQUET = REPO_ROOT / "data/processed/ticks_databento_2026-01-01_to_2026-05-01.parquet"
TICKS_OVERLAP_PARQUET = REPO_ROOT / "data/processed/ticks_overlap.parquet"

EXPECTED_TRADES_SHA = "1ccf859e3a580d78eb85cbc37a2cfa7159c3af59c3eb4bb58b5443d0aaf54feb"
EXPECTED_SAMPLE_SHA = "2ebd7512ef115d0a68e1c3a0cd4b9a05841f0c0b1ae97a12514833369f791484"

STOP_POINTS = 40.0
TARGET_POINTS = 40.0
POINT_VALUE_USD = 2.0
ENTRY_MINUTE_SEC = 60
FORCE_CLOSE_UTC_HM = (15, 30)

MECH_MATCH = "MATCH"
MECH_BUG_B_SAME_BAR = "BUG_B_SAME_BAR"
MECH_BUG_B_NEXT_BAR = "BUG_B_NEXT_BAR"
MECH_PHANTOM_ENTRY = "PHANTOM_ENTRY"
MECH_OUT_OF_COVERAGE = "OUT_OF_COVERAGE"
MECH_OTHER = "OTHER"


def sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def verify_inputs() -> tuple[str, str]:
    trades_sha = sha256(TRADES_PATH)
    sample_sha = sha256(SAMPLE_CSV)
    if trades_sha != EXPECTED_TRADES_SHA:
        sys.exit(
            f"FAIL: trades sha256 mismatch\n"
            f"  got:    {trades_sha}\n"
            f"  expect: {EXPECTED_TRADES_SHA}"
        )
    if sample_sha != EXPECTED_SAMPLE_SHA:
        sys.exit(
            f"FAIL: sample CSV sha256 mismatch\n"
            f"  got:    {sample_sha}\n"
            f"  expect: {EXPECTED_SAMPLE_SHA}"
        )
    return trades_sha, sample_sha


def resolve_ticks_path() -> Path:
    """Prefer the Databento cache; fall back to the NinjaTrader overlap cache."""
    if TICKS_DATABENTO_PARQUET.exists():
        return TICKS_DATABENTO_PARQUET
    if TICKS_OVERLAP_PARQUET.exists():
        print(
            f"WARNING: {TICKS_DATABENTO_PARQUET.name} not found.\n"
            f"         Falling back to {TICKS_OVERLAP_PARQUET.name} (Mar 17 - Apr 15 2026 only).\n"
            f"         Build the Databento cache to verify the full Tight window.",
            file=sys.stderr,
        )
        return TICKS_OVERLAP_PARQUET
    sys.exit(
        f"FAIL: no tick cache found.\n"
        f"  tried: {TICKS_DATABENTO_PARQUET}\n"
        f"  tried: {TICKS_OVERLAP_PARQUET}"
    )


# ---------------- Per-trade replay (identical algorithm to tick_replay_v2.py) ----------------

def replay_trade(trade: dict, ticks_df: pd.DataFrame,
                 tick_min: pd.Timestamp, tick_max: pd.Timestamp) -> dict:
    side = trade["side"]
    entry_price = float(trade["entry_price"])
    entry_time = trade["entry_time"]

    if side == "buy":
        stop_price = entry_price - STOP_POINTS
        target_price = entry_price + TARGET_POINTS
    else:
        stop_price = entry_price + STOP_POINTS
        target_price = entry_price - TARGET_POINTS

    if entry_time < tick_min or entry_time > tick_max:
        return {
            "tick_outcome": "OUT_OF_COVERAGE",
            "fill_ts": pd.NaT, "fill_price": np.nan,
            "tick_exit_ts": pd.NaT, "tick_exit_price": np.nan,
            "tick_pnl_dollars": np.nan,
            "stop_price": stop_price, "target_price": target_price,
            "bug_b_pre_fill_stop": False, "bug_b_pre_fill_target": False,
            "bug_b_exit_bar_gap_stop": False, "bug_b_exit_bar_gap_target": False,
            "phantom_suspect": False, "out_of_coverage": True,
            "mechanism": MECH_OUT_OF_COVERAGE,
        }

    entry_window_end = entry_time + pd.Timedelta(seconds=ENTRY_MINUTE_SEC)
    em = ticks_df[
        (ticks_df["ts_utc"] >= entry_time) & (ticks_df["ts_utc"] < entry_window_end)
    ]
    last_arr = em["last"].to_numpy()
    ts_arr = em["ts_utc"].to_numpy()

    if side == "buy":
        fill_pos = np.where(last_arr <= entry_price)[0]
    else:
        fill_pos = np.where(last_arr >= entry_price)[0]

    if len(fill_pos) == 0:
        return {
            "tick_outcome": "NO_FILL",
            "fill_ts": pd.NaT, "fill_price": np.nan,
            "tick_exit_ts": pd.NaT, "tick_exit_price": np.nan,
            "tick_pnl_dollars": 0.0,
            "stop_price": stop_price, "target_price": target_price,
            "bug_b_pre_fill_stop": False, "bug_b_pre_fill_target": False,
            "bug_b_exit_bar_gap_stop": False, "bug_b_exit_bar_gap_target": False,
            "phantom_suspect": True, "out_of_coverage": False,
            "mechanism": MECH_PHANTOM_ENTRY,
        }

    fill_idx = int(fill_pos[0])
    fill_ts = pd.Timestamp(ts_arr[fill_idx])
    fill_price = float(last_arr[fill_idx])

    pre_last = last_arr[:fill_idx]
    if side == "buy":
        bug_b_stop = bool(pre_last.size and (pre_last <= stop_price).any())
        bug_b_target = bool(pre_last.size and (pre_last >= target_price).any())
    else:
        bug_b_stop = bool(pre_last.size and (pre_last >= stop_price).any())
        bug_b_target = bool(pre_last.size and (pre_last <= target_price).any())

    session_date = pd.Timestamp(trade["session_date"]).date()
    fc_utc = pd.Timestamp(
        f"{session_date} {FORCE_CLOSE_UTC_HM[0]:02d}:{FORCE_CLOSE_UTC_HM[1]:02d}:00",
        tz="UTC",
    )

    after = ticks_df[
        (ticks_df["ts_utc"] > fill_ts) & (ticks_df["ts_utc"] < fc_utc)
    ]
    a_last = after["last"].to_numpy()
    a_ts = after["ts_utc"].to_numpy()

    if side == "buy":
        stop_hits = np.where(a_last <= stop_price)[0]
        target_hits = np.where(a_last >= target_price)[0]
    else:
        stop_hits = np.where(a_last >= stop_price)[0]
        target_hits = np.where(a_last <= target_price)[0]

    first_stop = int(stop_hits[0]) if len(stop_hits) else None
    first_target = int(target_hits[0]) if len(target_hits) else None

    if first_stop is None and first_target is None:
        fc_after = ticks_df[ticks_df["ts_utc"] >= fc_utc]
        if len(fc_after):
            fc_tick = fc_after.iloc[0]
            outcome = "force_close"
            exit_ts = pd.Timestamp(fc_tick["ts_utc"])
            exit_price = float(fc_tick["last"])
        else:
            outcome = "force_close"
            exit_ts = pd.NaT
            exit_price = fill_price
        pnl_pts = (exit_price - entry_price) if side == "buy" else (entry_price - exit_price)
    elif first_stop is None or (first_target is not None and first_target < first_stop):
        outcome = "target"
        exit_ts = pd.Timestamp(a_ts[first_target])
        exit_price = target_price
        pnl_pts = TARGET_POINTS
    else:
        outcome = "stop"
        exit_ts = pd.Timestamp(a_ts[first_stop])
        exit_price = stop_price
        pnl_pts = -STOP_POINTS

    # Exit-bar chronology gap-through (audit p4b "chronology generalization"):
    # multi-bar trades with a stop/target exit where the bar sim's exit-bar
    # OPEN (= first tick of that minute) is strictly past the credited level.
    # Independent of the tick exit walk above; can fire even when the chrono
    # outcome agrees with sim (because exit_price uses the credited level by
    # bar-sim convention, masking gap-through in the P&L comparison).
    bug_b_exit_gap_stop = False
    bug_b_exit_gap_target = False
    sim_entry_ts = pd.Timestamp(trade["entry_time"])
    sim_exit_ts = pd.Timestamp(trade["exit_time"])
    if sim_exit_ts > sim_entry_ts:
        bar_start = sim_exit_ts.floor("min")
        bar_end = bar_start + pd.Timedelta(seconds=60)
        bar_ticks = ticks_df[
            (ticks_df["ts_utc"] >= bar_start) & (ticks_df["ts_utc"] < bar_end)
        ]
        if len(bar_ticks) > 0:
            first_tick_price = float(bar_ticks.iloc[0]["last"])
            if side == "buy":
                bug_b_exit_gap_stop = first_tick_price < stop_price
                bug_b_exit_gap_target = first_tick_price > target_price
            else:
                bug_b_exit_gap_stop = first_tick_price > stop_price
                bug_b_exit_gap_target = first_tick_price < target_price

    return {
        "tick_outcome": outcome,
        "fill_ts": fill_ts, "fill_price": fill_price,
        "tick_exit_ts": exit_ts, "tick_exit_price": exit_price,
        "tick_pnl_dollars": float(pnl_pts * POINT_VALUE_USD),
        "stop_price": stop_price, "target_price": target_price,
        "bug_b_pre_fill_stop": bug_b_stop, "bug_b_pre_fill_target": bug_b_target,
        "bug_b_exit_bar_gap_stop": bug_b_exit_gap_stop,
        "bug_b_exit_bar_gap_target": bug_b_exit_gap_target,
        "phantom_suspect": False, "out_of_coverage": False,
        "mechanism": None,
    }


def attribute_mechanism(trade: dict, replay: dict) -> str:
    if replay["mechanism"] in (MECH_OUT_OF_COVERAGE, MECH_PHANTOM_ENTRY):
        return replay["mechanism"]

    sim_outcome = trade["exit_reason"]
    tick_outcome = replay["tick_outcome"]
    sim_pnl = float(trade["pnl_dollars"])
    tick_pnl = float(replay["tick_pnl_dollars"]) if replay["tick_pnl_dollars"] is not None else 0.0
    same_bar = pd.Timestamp(trade["entry_time"]) == pd.Timestamp(trade["exit_time"])

    # Bug B positive-evidence checks come BEFORE MATCH. Because replay_trade
    # uses the credited stop/target level as exit_price (bar-sim convention),
    # the gap-through case for next-bar Bug B would otherwise produce a P&L
    # MATCH and never surface the chronology issue. Same-bar Bug B + outcome
    # MATCH is rare to nonexistent per the audit, but the ordering is
    # symmetric for consistency.
    if same_bar:
        if sim_outcome == "stop" and replay["bug_b_pre_fill_stop"]:
            return MECH_BUG_B_SAME_BAR
        if sim_outcome == "target" and replay["bug_b_pre_fill_target"]:
            return MECH_BUG_B_SAME_BAR
    else:
        if sim_outcome == "stop" and replay["bug_b_exit_bar_gap_stop"]:
            return MECH_BUG_B_NEXT_BAR
        if sim_outcome == "target" and replay["bug_b_exit_bar_gap_target"]:
            return MECH_BUG_B_NEXT_BAR

    if sim_outcome == tick_outcome and abs(sim_pnl - tick_pnl) < 0.01:
        return MECH_MATCH

    return MECH_OTHER


# ---------------- Report rendering ----------------

def build_report(summary: dict, recon: pd.DataFrame, sample_dates: set,
                 tmin: pd.Timestamp, tmax: pd.Timestamp) -> str:
    lines: list[str] = []
    lines.append(f"# V2 + 40/40 tick replayer (Window variant) — run {summary['run_timestamp']}")
    lines.append("")
    lines.append(
        "Per-trade reconciliation of V2 + 40/40 bar-sim trades against tick truth, "
        "over the FULL trade population whose entry_time falls in the tick coverage "
        "window. Phase 1 sample membership is reported as a metric, not used as a "
        "filter. Bug B (D-014) and phantom-fill (D-015) attribution per the design "
        "doc: `results/tick_verification/_phase2_replayer_design.md`."
    )
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(f"- Trades parquet sha256: `{summary['trades_sha256']}`")
    lines.append(f"- Phase 1 sample CSV sha256: `{summary['sample_sha256']}`  (cross-reference only)")
    lines.append(f"- Tick parquet: `{summary['ticks_path']}`")
    lines.append(
        f"- Tick coverage: {tmin} → {tmax}  "
        f"({summary['tick_coverage']['n_ticks']:,} ticks)"
    )
    lines.append(
        f"- Bracket: {summary['bracket']['stop_points']:.0f} / "
        f"{summary['bracket']['target_points']:.0f}"
    )
    lines.append("")
    lines.append("## Counts (all trades in window)")
    lines.append("")
    c = summary["counts"]
    lines.append("| Mechanism | Count |")
    lines.append("|---|---:|")
    lines.append(f"| MATCH | {c['match']} |")
    lines.append(f"| BUG_B_SAME_BAR | {c['bug_b_same_bar']} |")
    lines.append(f"| BUG_B_NEXT_BAR | {c['bug_b_next_bar']} |")
    lines.append(f"| PHANTOM_ENTRY | {c['phantom_entry']} |")
    lines.append(f"| OTHER | {c['other']} |")
    lines.append(f"| **Verified subtotal** | **{c['verified']}** |")
    lines.append(f"| OUT_OF_COVERAGE | {c['out_of_coverage']} |")
    lines.append("")

    s = summary["stop_outs"]
    lines.append("## Stop-out subset (audit-relevant — Bug B is a stop-side concept)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Verified stop-outs | {s['n']} |")
    lines.append(f"| Stop-outs in 09:46–10:55 NY band | {s['n_in_bug_b_band']} |")
    lines.append(f"| Stop-outs with BUG_B_SAME_BAR | {s['bug_b_same_bar']} |")
    lines.append(f"| Stop-outs with BUG_B_NEXT_BAR | {s['bug_b_next_bar']} |")
    lines.append(f"| Stop-outs flagged bug_b_pre_fill_stop | {s['flagged_pre_fill_stop']} |")
    lines.append(f"| Stop-outs FADE / TREND | {s['fade']} / {s['trend']} |")
    lines.append("")

    pp = summary["phase1_overlap"]
    lines.append("## Phase 1 sample cross-reference")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Phase 1 dates in window | {pp['p1_dates_in_window']} / {pp['p1_dates_total']} |")
    lines.append(f"| Verified trades on Phase 1 dates | {pp['verified_on_p1']} |")
    lines.append(f"| Verified stops on Phase 1 dates | {pp['verified_stops_on_p1']} |")
    lines.append("")

    p = summary["pnl"]
    lines.append("## P&L reconciliation (verified trades only)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Sim P&L  | ${p['sim_pnl_verified']:+,.2f} |")
    lines.append(f"| Tick P&L | ${p['tick_pnl_verified']:+,.2f} |")
    lines.append(f"| Δ (tick − sim) | ${p['pnl_delta']:+,.2f} |")
    if p["delta_pct_of_sim"] is not None:
        lines.append(f"| Δ % of sim | {p['delta_pct_of_sim']:+.1f}% |")
    lines.append("")

    verified = recon[recon["mechanism"] != MECH_OUT_OF_COVERAGE]
    if len(verified):
        lines.append("## Per-trade table (verified, sorted by entry_time)")
        lines.append("")
        lines.append(
            "| session_date | side | label | entry | sim | tick | sim $ | tick $ | mech | P1 |"
        )
        lines.append("|---|---|---|---:|---|---|---:|---:|---|:-:|")
        for _, r in verified.sort_values("entry_time").iterrows():
            tick_pnl_s = (
                f"${r['tick_pnl_dollars']:+,.2f}" if pd.notna(r["tick_pnl_dollars"]) else "n/a"
            )
            on_p1 = "✓" if bool(r["on_phase1_date"]) else ""
            lines.append(
                f"| {pd.Timestamp(r['session_date']).date()} | {r['side']} | "
                f"{r['cluster_label']} | {r['entry_price']:.2f} | {r['exit_reason']} | "
                f"{r['tick_outcome']} | ${r['pnl_dollars']:+,.2f} | {tick_pnl_s} | "
                f"{r['mechanism']} | {on_p1} |"
            )
        lines.append("")

    oof = recon[recon["mechanism"] == MECH_OUT_OF_COVERAGE]
    if len(oof):
        lines.append("## Out-of-coverage (trades on dates outside the tick window)")
        lines.append("")
        by_date = (
            oof.assign(date=oof["session_date"].dt.date)
            .groupby("date")
            .size()
            .reset_index(name="n_trades")
        )
        lines.append(f"Total OOF trades: {len(oof)} across {len(by_date)} dates.")
        lines.append("")

    lines.append("## Coverage caveat")
    lines.append("")
    lines.append(
        f"Tick coverage: {tmin.date()} → {tmax.date()}. The trade population "
        f"verified here is **all V2+40/40 trades** whose entry_time falls in this "
        f"window — not restricted to the Phase 1 sample. The original "
        f"`tick_replay_v2.py` is the canonical Phase 1-only verifier; this "
        f"variant trades the stratified-sample audit-trail for full in-window "
        f"coverage."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------- Main ----------------

def main() -> None:
    print("=" * 76)
    print("V2 + 40/40 tick replayer — Window variant")
    print("=" * 76)

    trades_sha, sample_sha = verify_inputs()
    ticks_path = resolve_ticks_path()
    print(f"trades sha256:  {trades_sha}")
    print(f"sample sha256:  {sample_sha}  (cross-reference only)")
    print(f"ticks path:     {ticks_path}")

    trades = pd.read_parquet(TRADES_PATH).copy()
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades["session_date"] = pd.to_datetime(trades["session_date"])

    ticks = pd.read_parquet(ticks_path)
    ticks["ts_utc"] = pd.to_datetime(ticks["ts_utc"], utc=True)
    ticks = ticks.sort_values("ts_utc").reset_index(drop=True)
    tick_min = ticks["ts_utc"].min()
    tick_max = ticks["ts_utc"].max()

    sample = pd.read_csv(SAMPLE_CSV)
    sample_dates = set(pd.to_datetime(sample["date"]).dt.date)

    print(f"Loaded:        {len(trades)} trades, {len(ticks):,} ticks, "
          f"{len(sample_dates)} P1 sample dates")
    print(f"Tick coverage: {tick_min}  ->  {tick_max}")

    # Filter: in coverage only (no Phase 1 filter — that's the whole point of this fork)
    in_coverage = (trades["entry_time"] >= tick_min) & (trades["entry_time"] <= tick_max)
    target = trades[in_coverage].reset_index(drop=True)

    # Annotate each verified trade with Phase 1 membership for cross-reference.
    target["on_phase1_date"] = target["session_date"].dt.date.isin(sample_dates)

    # OOF: trades NOT in tick coverage (full population, not just sample)
    oof = trades[~in_coverage].reset_index(drop=True)
    oof["on_phase1_date"] = oof["session_date"].dt.date.isin(sample_dates)

    print(f"In tick coverage:     {len(target)} trades  "
          f"(of which {int(target['on_phase1_date'].sum())} on Phase 1 dates)")
    print(f"Out of tick coverage: {len(oof)} trades  "
          f"(of which {int(oof['on_phase1_date'].sum())} on Phase 1 dates)")

    if len(target) == 0:
        sys.exit("No trades in tick coverage; aborting.")

    rows: list[dict] = []
    for _, t in target.iterrows():
        td = t.to_dict()
        replay = replay_trade(td, ticks, tick_min, tick_max)
        replay["mechanism"] = attribute_mechanism(td, replay)
        rows.append({**td, **replay})

    for _, t in oof.iterrows():
        td = t.to_dict()
        replay = replay_trade(td, ticks, tick_min, tick_max)
        rows.append({**td, **replay})

    recon = pd.DataFrame(rows)
    recon["match"] = recon["mechanism"] == MECH_MATCH
    recon["pnl_delta"] = recon["tick_pnl_dollars"] - recon["pnl_dollars"]

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_BASE / f"phase2_window_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    recon.to_parquet(out_dir / "reconciliation.parquet", index=False)

    verified = recon[recon["mechanism"] != MECH_OUT_OF_COVERAGE]
    n_verified = int(len(verified))

    # Stop-out subset (audit-relevant)
    stops_v = verified[verified["exit_reason"] == "stop"].copy()
    if len(stops_v):
        ny = stops_v["entry_time"].dt.tz_convert("America/New_York")
        h = ny.dt.hour
        m = ny.dt.minute
        in_band = ((h == 9) & (m >= 46)) | ((h == 10) & (m <= 55))
        stop_summary = {
            "n": int(len(stops_v)),
            "n_in_bug_b_band": int(in_band.sum()),
            "bug_b_same_bar": int((stops_v["mechanism"] == MECH_BUG_B_SAME_BAR).sum()),
            "bug_b_next_bar": int((stops_v["mechanism"] == MECH_BUG_B_NEXT_BAR).sum()),
            "flagged_pre_fill_stop": int(stops_v["bug_b_pre_fill_stop"].sum()),
            "fade": int((stops_v["cluster_label"] == "FADE").sum()),
            "trend": int((stops_v["cluster_label"] == "TREND").sum()),
        }
    else:
        stop_summary = {"n": 0, "n_in_bug_b_band": 0, "bug_b_same_bar": 0,
                        "bug_b_next_bar": 0, "flagged_pre_fill_stop": 0,
                        "fade": 0, "trend": 0}

    # Phase 1 cross-reference (counts, not a filter)
    p1_dates_in_window = sum(
        1 for d in sample_dates
        if tick_min <= pd.Timestamp(d).tz_localize("UTC") <= tick_max
    )
    phase1_overlap = {
        "p1_dates_total": len(sample_dates),
        "p1_dates_in_window": p1_dates_in_window,
        "verified_on_p1": int(verified["on_phase1_date"].sum()) if len(verified) else 0,
        "verified_stops_on_p1": int(stops_v["on_phase1_date"].sum()) if len(stops_v) else 0,
    }

    counts = {
        "verified": n_verified,
        "match": int((verified["mechanism"] == MECH_MATCH).sum()),
        "bug_b_same_bar": int((verified["mechanism"] == MECH_BUG_B_SAME_BAR).sum()),
        "bug_b_next_bar": int((verified["mechanism"] == MECH_BUG_B_NEXT_BAR).sum()),
        "phantom_entry": int((verified["mechanism"] == MECH_PHANTOM_ENTRY).sum()),
        "other": int((verified["mechanism"] == MECH_OTHER).sum()),
        "out_of_coverage": int((recon["mechanism"] == MECH_OUT_OF_COVERAGE).sum()),
    }
    sim_pnl_v = float(verified["pnl_dollars"].sum())
    tick_pnl_v = float(verified["tick_pnl_dollars"].fillna(0).sum())
    delta = tick_pnl_v - sim_pnl_v
    delta_pct = (delta / sim_pnl_v * 100) if sim_pnl_v != 0 else None

    summary = {
        "run_timestamp": run_ts,
        "variant": "window",
        "trades_sha256": trades_sha,
        "sample_sha256": sample_sha,
        "ticks_path": str(ticks_path.relative_to(REPO_ROOT)),
        "tick_coverage": {
            "start": str(tick_min), "end": str(tick_max), "n_ticks": int(len(ticks)),
        },
        "counts": counts,
        "stop_outs": stop_summary,
        "phase1_overlap": phase1_overlap,
        "pnl": {
            "sim_pnl_verified": sim_pnl_v,
            "tick_pnl_verified": tick_pnl_v,
            "pnl_delta": delta,
            "delta_pct_of_sim": delta_pct,
        },
        "bracket": {"stop_points": STOP_POINTS, "target_points": TARGET_POINTS},
    }

    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    report = build_report(summary, recon, sample_dates, tick_min, tick_max)
    with open(out_dir / "report.md", "w") as f:
        f.write(report)

    print()
    print(f"Output dir: {out_dir}")
    print(f"  reconciliation.parquet  ({len(recon)} rows)")
    print(f"  summary.json")
    print(f"  report.md")
    print()
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
