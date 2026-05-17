"""V2 + 40/40 tick replayer — Phase 2 v1.

Per-trade reconciliation of V2 + 40/40 bar-sim outcomes against tick truth,
with Bug B (D-014) and phantom-fill (D-015) attribution. Verifies only those
trades that fall inside both the canonical Phase 1 sample (sha256-pinned)
AND the locally available tick coverage window.

Design: results/tick_verification/_phase2_replayer_design.md

Inputs (all sha256-pinned where applicable):
  - results/40_40_v2_full/20260514_125349/trades.parquet  (908 V2+40/40 trades)
  - data/processed/ticks_overlap.parquet                  (5.67M ticks, 2026-03-17..04-15)
  - results/tick_verification/phase1_sample_20260516.csv  (40 stratified dates)

Output (one new dir per run):
  results/tick_verification/phase2_<YYYYMMDD_HHMMSS>/
    - reconciliation.parquet   per-trade replay + mechanism attribution
    - summary.json             machine-readable headline
    - report.md                human-readable summary

Mechanism categories:
  MATCH               sim outcome and tick outcome and P&L all agree
  BUG_B_SAME_BAR      bar sim's same-bar exit; tick truth shows the credited
                      extreme occurred BEFORE the fill within the entry minute
  BUG_B_NEXT_BAR      bar sim's exit_time > entry_time and outcomes disagree
                      (covers next-bar chronology + phantom-exit candidates;
                      sub-classification deferred to v2)
  PHANTOM_ENTRY       no tick crossed the limit price during the entry minute
                      (D-015 entry-side phantom fill)
  OUT_OF_COVERAGE     trade entry_time falls outside the local tick window;
                      unverifiable here, awaiting wider tick acquisition
  OTHER               residual mismatch not attributed to a known mechanism
"""
from __future__ import annotations

import hashlib
import json
import sys
import zoneinfo
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------- Config ----------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TRADES_PATH = REPO_ROOT / "results/40_40_v2_full/20260514_125349/trades.parquet"
TICKS_PATH = REPO_ROOT / "data/processed/ticks_overlap.parquet"
SAMPLE_CSV = REPO_ROOT / "results/tick_verification/phase1_sample_20260516.csv"
OUTPUT_BASE = REPO_ROOT / "results/tick_verification"

EXPECTED_TRADES_SHA = "1ccf859e3a580d78eb85cbc37a2cfa7159c3af59c3eb4bb58b5443d0aaf54feb"
EXPECTED_SAMPLE_SHA = "2ebd7512ef115d0a68e1c3a0cd4b9a05841f0c0b1ae97a12514833369f791484"

STOP_POINTS = 40.0
TARGET_POINTS = 40.0
POINT_VALUE_USD = 2.0
ENTRY_MINUTE_SEC = 60
# Force-close is 11:30 NY-LOCAL, not a fixed UTC offset. The NY ↔ UTC offset
# changes with DST (EST = UTC-5, EDT = UTC-4), so fc_utc must be computed
# per-trade from the session_date via zoneinfo. The same constant is
# duplicated in tick_replay_v2_window.py — both verifiers are self-contained
# experimental scripts and don't currently warrant a shared module.
NY_TZ = zoneinfo.ZoneInfo("America/New_York")
FORCE_CLOSE_NY_HM = (11, 30)

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


# ---------------- Per-trade replay ----------------

def replay_trade(trade: dict, ticks_df: pd.DataFrame,
                 tick_min: pd.Timestamp, tick_max: pd.Timestamp) -> dict:
    """Replay a single trade against tick data.

    Reuses verify_ticks.py's threshold-cross logic for entry fill and
    chronological exit walk. Adds Bug B pre-fill check and phantom-fill
    flag. Returns the new reconciliation columns (not the trade columns).
    """
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
            "fill_ts": pd.NaT,
            "fill_price": np.nan,
            "tick_exit_ts": pd.NaT,
            "tick_exit_price": np.nan,
            "tick_pnl_dollars": np.nan,
            "stop_price": stop_price,
            "target_price": target_price,
            "bug_b_pre_fill_stop": False,
            "bug_b_pre_fill_target": False,
            "phantom_suspect": False,
            "out_of_coverage": True,
            "mechanism": MECH_OUT_OF_COVERAGE,
        }

    # Entry-minute slice
    entry_window_end = entry_time + pd.Timedelta(seconds=ENTRY_MINUTE_SEC)
    em = ticks_df[
        (ticks_df["ts_utc"] >= entry_time) & (ticks_df["ts_utc"] < entry_window_end)
    ]
    last_arr = em["last"].to_numpy()
    ts_arr = em["ts_utc"].to_numpy()

    # Threshold-cross fill detection (reuse verify_ticks.py logic, no epsilon)
    if side == "buy":
        fill_pos = np.where(last_arr <= entry_price)[0]
    else:
        fill_pos = np.where(last_arr >= entry_price)[0]

    if len(fill_pos) == 0:
        return {
            "tick_outcome": "NO_FILL",
            "fill_ts": pd.NaT,
            "fill_price": np.nan,
            "tick_exit_ts": pd.NaT,
            "tick_exit_price": np.nan,
            "tick_pnl_dollars": 0.0,
            "stop_price": stop_price,
            "target_price": target_price,
            "bug_b_pre_fill_stop": False,
            "bug_b_pre_fill_target": False,
            "phantom_suspect": True,
            "out_of_coverage": False,
            "mechanism": MECH_PHANTOM_ENTRY,
        }

    fill_idx = int(fill_pos[0])
    fill_ts = pd.Timestamp(ts_arr[fill_idx])
    fill_price = float(last_arr[fill_idx])

    # Bug B pre-fill check: ticks STRICTLY before fill in the entry minute
    pre_last = last_arr[:fill_idx]
    if side == "buy":
        bug_b_stop = bool(pre_last.size and (pre_last <= stop_price).any())
        bug_b_target = bool(pre_last.size and (pre_last >= target_price).any())
    else:
        bug_b_stop = bool(pre_last.size and (pre_last >= stop_price).any())
        bug_b_target = bool(pre_last.size and (pre_last <= target_price).any())

    # Chronological exit walk from fill onward. fc_utc is derived from the
    # NY-local force-close clock time (11:30) converted to UTC via the
    # session_date's zoneinfo, so it picks up EST/EDT correctly.
    session_date = pd.Timestamp(trade["session_date"]).date()
    fc_ny = pd.Timestamp(
        f"{session_date} {FORCE_CLOSE_NY_HM[0]:02d}:{FORCE_CLOSE_NY_HM[1]:02d}:00",
        tz=NY_TZ,
    )
    fc_utc = fc_ny.tz_convert("UTC")

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
        # Neither hit before force-close. Use first tick at/after fc_utc.
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

    return {
        "tick_outcome": outcome,
        "fill_ts": fill_ts,
        "fill_price": fill_price,
        "tick_exit_ts": exit_ts,
        "tick_exit_price": exit_price,
        "tick_pnl_dollars": float(pnl_pts * POINT_VALUE_USD),
        "stop_price": stop_price,
        "target_price": target_price,
        "bug_b_pre_fill_stop": bug_b_stop,
        "bug_b_pre_fill_target": bug_b_target,
        "phantom_suspect": False,
        "out_of_coverage": False,
        "mechanism": None,
    }


def attribute_mechanism(trade: dict, replay: dict) -> str:
    """Final mechanism categorization combining sim/tick comparison."""
    if replay["mechanism"] in (MECH_OUT_OF_COVERAGE, MECH_PHANTOM_ENTRY):
        return replay["mechanism"]

    sim_outcome = trade["exit_reason"]
    tick_outcome = replay["tick_outcome"]
    sim_pnl = float(trade["pnl_dollars"])
    tick_pnl = float(replay["tick_pnl_dollars"]) if replay["tick_pnl_dollars"] is not None else 0.0

    if sim_outcome == tick_outcome and abs(sim_pnl - tick_pnl) < 0.01:
        return MECH_MATCH

    same_bar = pd.Timestamp(trade["entry_time"]) == pd.Timestamp(trade["exit_time"])
    if same_bar:
        if sim_outcome == "stop" and replay["bug_b_pre_fill_stop"]:
            return MECH_BUG_B_SAME_BAR
        if sim_outcome == "target" and replay["bug_b_pre_fill_target"]:
            return MECH_BUG_B_SAME_BAR
        return MECH_OTHER

    return MECH_BUG_B_NEXT_BAR


# ---------------- Report rendering ----------------

def build_report(summary: dict, recon: pd.DataFrame, sample_dates: set,
                 tmin: pd.Timestamp, tmax: pd.Timestamp) -> str:
    lines: list[str] = []
    lines.append(f"# V2 + 40/40 tick replayer — Phase 2 run {summary['run_timestamp']}")
    lines.append("")
    lines.append(
        "Per-trade reconciliation of V2 + 40/40 bar-sim trades against tick truth, "
        "with Bug B (D-014) and phantom-fill (D-015) attribution. Design: "
        "`results/tick_verification/_phase2_replayer_design.md`."
    )
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(f"- Trades parquet sha256: `{summary['trades_sha256']}`")
    lines.append(f"- Phase 1 sample CSV sha256: `{summary['sample_sha256']}`")
    lines.append(
        f"- Tick coverage: {tmin} → {tmax}  "
        f"({summary['tick_coverage']['n_ticks']:,} ticks)"
    )
    lines.append(
        f"- Bracket: {summary['bracket']['stop_points']:.0f} / "
        f"{summary['bracket']['target_points']:.0f}"
    )
    lines.append("")
    lines.append("## Counts")
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
        lines.append("## Per-trade table (verified)")
        lines.append("")
        lines.append(
            "| session_date | side | entry | sim outcome | tick outcome | sim $ | tick $ | mechanism |"
        )
        lines.append("|---|---|---:|---|---|---:|---:|---|")
        for _, r in verified.sort_values("entry_time").iterrows():
            tick_pnl_s = (
                f"${r['tick_pnl_dollars']:+,.2f}" if pd.notna(r["tick_pnl_dollars"]) else "n/a"
            )
            lines.append(
                f"| {pd.Timestamp(r['session_date']).date()} | {r['side']} | "
                f"{r['entry_price']:.2f} | {r['exit_reason']} | {r['tick_outcome']} | "
                f"${r['pnl_dollars']:+,.2f} | {tick_pnl_s} | {r['mechanism']} |"
            )
        lines.append("")

    oof = recon[recon["mechanism"] == MECH_OUT_OF_COVERAGE]
    if len(oof):
        lines.append("## Out-of-coverage (sample but no local tick data)")
        lines.append("")
        by_date = (
            oof.assign(date=oof["session_date"].dt.date)
            .groupby("date")
            .size()
            .reset_index(name="n_trades")
        )
        lines.append(f"Total OOF trades: {len(oof)} across {len(by_date)} dates.")
        lines.append("")
        for _, row in by_date.sort_values("date").iterrows():
            lines.append(f"- {row['date']}: {row['n_trades']} trades")
        lines.append("")

    lines.append("## Coverage caveat")
    lines.append("")
    lines.append(
        f"Local tick data covers {tmin.date()} → {tmax.date()} (a ~6-week window). "
        f"The canonical Phase 1 sample spans 7 years. Of {len(sample_dates)} sample dates, "
        f"only those within the tick window are verifiable here; the rest are reported as "
        f"OUT_OF_COVERAGE pending wider tick acquisition (see "
        f"`results/tick_verification/_databento_acquisition_brief.md`)."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------- Main ----------------

def main() -> None:
    print("=" * 76)
    print("V2 + 40/40 tick replayer — Phase 2 v1")
    print("=" * 76)

    trades_sha, sample_sha = verify_inputs()
    print(f"trades sha256:  {trades_sha}")
    print(f"sample sha256:  {sample_sha}")

    trades = pd.read_parquet(TRADES_PATH).copy()
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)
    trades["session_date"] = pd.to_datetime(trades["session_date"])

    ticks = pd.read_parquet(TICKS_PATH)
    ticks["ts_utc"] = pd.to_datetime(ticks["ts_utc"], utc=True)
    ticks = ticks.sort_values("ts_utc").reset_index(drop=True)
    tick_min = ticks["ts_utc"].min()
    tick_max = ticks["ts_utc"].max()

    sample = pd.read_csv(SAMPLE_CSV)
    sample_dates = set(pd.to_datetime(sample["date"]).dt.date)

    print(f"Loaded:        {len(trades)} trades, {len(ticks):,} ticks, "
          f"{len(sample_dates)} sample dates")
    print(f"Tick coverage: {tick_min}  ->  {tick_max}")

    sd_only = trades["session_date"].dt.date
    in_sample = sd_only.isin(sample_dates)
    in_coverage = (trades["entry_time"] >= tick_min) & (trades["entry_time"] <= tick_max)

    target = trades[in_sample & in_coverage].reset_index(drop=True)
    oof = trades[in_sample & ~in_coverage].reset_index(drop=True)
    print(f"In sample AND in tick coverage: {len(target)} trades")
    print(f"In sample but OUT of coverage:  {len(oof)} trades")

    if len(target) + len(oof) == 0:
        sys.exit("No sample trades to process; aborting.")

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
    recon["pnl_delta"] = recon["tick_pnl_dollars"].fillna(0) - recon["pnl_dollars"]

    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_BASE / f"phase2_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    recon.to_parquet(out_dir / "reconciliation.parquet", index=False)

    verified = recon[recon["mechanism"] != MECH_OUT_OF_COVERAGE]
    n_verified = int(len(verified))
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
        "trades_sha256": trades_sha,
        "sample_sha256": sample_sha,
        "tick_coverage": {
            "start": str(tick_min),
            "end": str(tick_max),
            "n_ticks": int(len(ticks)),
        },
        "counts": counts,
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
