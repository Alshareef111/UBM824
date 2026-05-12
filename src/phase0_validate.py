"""Phase 0 validation: byte-equivalence + walk-forward harness sanity.

Non-negotiable per user spec. Both must pass before Phase 1 can start.

Validation 1 — Byte-equivalence:
  simulator_v2 with AllFade classifier must produce trades identical
  (across BASELINE_COLS) to results/archive/trades_baseline_extended_20260511.parquet
  via pandas.testing.assert_frame_equal(check_exact=True). If it fails:
  STOP. Do not start Phase 1. Report failure details.

Validation 2 — Walk-forward harness sanity:
  Run simulator_v2 with AllFade, AllTrend, AllSkip, RandomBinary(seed=0).
  Verify:
    - 7 walk-forward windows have expected date ranges
    - AllSkip produces 0 trades (SKIP path works)
    - AllFade and AllTrend produce identical trade counts (same fills)
    - AllFade and AllTrend produce matched (session_date, entry_time,
      entry_price) tuples with INVERTED sides (mechanical inversion correct)
    - RandomBinary produces a mix of FADE and TREND labels
    - Per-window P&L bucketing is internally consistent: sum across
      all OOS windows equals sum of trades that fall in any OOS window
    - sharpe_like / sign_stability / qualifies return finite values

Writes report.md and the AllFade/AllTrend trade parquets to
results/archive/phase0_YYYYMMDD/ for inspection.
"""
from __future__ import annotations

import sys
from datetime import date

import pandas as pd
import pandas.testing as pdt

from indicators.base import AllFade, AllSkip, AllTrend, RandomBinary
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET, ensure_dirs
from simulator_v2 import (
    BASELINE_COLS,
    POINT_VALUE_USD,
    run_backtest,
    trades_to_dataframe,
)
import walk_forward as wf

BASELINE_PARQUET = ARCHIVE_DIR / "trades_baseline_extended_20260511.parquet"
TODAY = date.today().strftime("%Y%m%d")
PHASE0_DIR = ARCHIVE_DIR / f"phase0_{TODAY}"


def load_data():
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    return bars, orb_table


def run_classifier(bars, orb_table, classifier, label):
    print(f"  Running {label}...", flush=True)
    trades = run_backtest(bars, orb_table, classifier)
    df = trades_to_dataframe(trades)
    print(f"    {len(df)} trades  P&L ${df['pnl_dollars'].sum() if len(df) else 0:,.2f}", flush=True)
    return df


def validate_byte_equivalence(allfade_df: pd.DataFrame) -> tuple[bool, str]:
    """Compare simulator_v2(AllFade) against the locked extended baseline."""
    if not BASELINE_PARQUET.exists():
        return False, f"Baseline parquet not found: {BASELINE_PARQUET}"
    baseline = pd.read_parquet(BASELINE_PARQUET)
    v2_check = allfade_df[BASELINE_COLS].reset_index(drop=True)
    base_check = baseline[BASELINE_COLS].reset_index(drop=True)

    details: list[str] = []
    details.append(f"baseline rows: {len(base_check):,}  sum_pnl: ${base_check['pnl_dollars'].sum():,.2f}")
    details.append(f"v2 AllFade rows: {len(v2_check):,}  sum_pnl: ${v2_check['pnl_dollars'].sum():,.2f}")
    if len(v2_check) != len(base_check):
        return False, "\n".join(details + [f"ROW COUNT MISMATCH: {len(v2_check)} vs {len(base_check)}"])

    try:
        pdt.assert_frame_equal(v2_check, base_check, check_exact=True)
    except AssertionError as e:
        return False, "\n".join(details + ["assert_frame_equal FAILED:", str(e)[:2000]])
    return True, "\n".join(details + ["assert_frame_equal(check_exact=True) PASSED"])


def validate_skip_path(allskip_df: pd.DataFrame) -> tuple[bool, str]:
    n = len(allskip_df)
    if n == 0:
        return True, "AllSkip produced 0 trades — SKIP path works"
    return False, f"AllSkip produced {n} trades (expected 0)"


def validate_trend_inversion(fade_df: pd.DataFrame, trend_df: pd.DataFrame) -> tuple[bool, str]:
    """AllFade and AllTrend should produce same fills, opposite sides."""
    details: list[str] = []
    if len(fade_df) != len(trend_df):
        return False, f"trade count mismatch: AllFade={len(fade_df)}  AllTrend={len(trend_df)}"
    details.append(f"trade count match: {len(fade_df)}")

    # Same fills: identical (session_date, entry_time, entry_price) sequence
    fade_keys = list(zip(fade_df["session_date"], fade_df["entry_time"], fade_df["entry_price"]))
    trend_keys = list(zip(trend_df["session_date"], trend_df["entry_time"], trend_df["entry_price"]))
    if fade_keys != trend_keys:
        n_diff = sum(1 for a, b in zip(fade_keys, trend_keys) if a != b)
        return False, "\n".join(details + [f"fill-key sequence differs: {n_diff} of {len(fade_keys)} rows"])
    details.append("fill keys (session_date, entry_time, entry_price) match in order")

    # Sides should be opposite
    fade_sides = fade_df["side"].tolist()
    trend_sides = trend_df["side"].tolist()
    expected_trend_sides = ["buy" if s == "sell" else "sell" for s in fade_sides]
    if trend_sides != expected_trend_sides:
        n_diff = sum(1 for a, b in zip(trend_sides, expected_trend_sides) if a != b)
        return False, "\n".join(details + [f"side inversion broken: {n_diff} of {len(trend_sides)} rows"])
    details.append(f"sides inverted at every row ({fade_sides.count('buy')} buy<->sell pairs flipped)")

    # cluster_label values: AllFade should be 100% FADE, AllTrend 100% TREND
    fade_labels = fade_df["cluster_label"].value_counts().to_dict()
    trend_labels = trend_df["cluster_label"].value_counts().to_dict()
    details.append(f"AllFade labels: {fade_labels}")
    details.append(f"AllTrend labels: {trend_labels}")
    if list(fade_labels.keys()) != ["FADE"]:
        return False, "\n".join(details + ["AllFade produced non-FADE labels"])
    if list(trend_labels.keys()) != ["TREND"]:
        return False, "\n".join(details + ["AllTrend produced non-TREND labels"])
    return True, "\n".join(details)


def validate_random_mix(rand_df: pd.DataFrame) -> tuple[bool, str]:
    labels = rand_df["cluster_label"].value_counts().to_dict()
    fade_n = labels.get("FADE", 0)
    trend_n = labels.get("TREND", 0)
    total = fade_n + trend_n
    if total == 0:
        return False, "RandomBinary produced 0 labeled trades"
    fade_frac = fade_n / total
    msg = f"RandomBinary labels: FADE={fade_n} ({fade_frac:.1%})  TREND={trend_n} ({1-fade_frac:.1%})"
    if 0.40 <= fade_frac <= 0.60:
        return True, msg + "  (within 40-60% — OK)"
    return False, msg + "  (outside 40-60% — RNG suspect)"


def validate_windows() -> tuple[bool, str]:
    windows = wf.make_windows()
    if len(windows) != wf.N_WINDOWS:
        return False, f"expected {wf.N_WINDOWS} windows, got {len(windows)}"
    lines = [f"  {w.name}: IS [{w.is_start.date()}, {w.is_end.date()})  OOS [{w.oos_start.date()}, {w.oos_end.date()})"
             for w in windows]
    return True, "\n".join(lines)


def validate_pnl_bucketing(df: pd.DataFrame, label: str) -> tuple[bool, str]:
    """Each per_window_pnl entry must match a direct date-filter sum on that window.

    Walk-forward OOS windows OVERLAP (1y OOS, 6mo advance), so the same trade
    can legitimately contribute to multiple windows' P&L. The harness is
    correct as long as each individual window's entry matches a direct
    session_date-filter sum on that specific window.
    """
    windows = wf.make_windows()
    per_win = wf.per_window_pnl(df, windows, slice_="oos")
    sd = pd.to_datetime(df["session_date"])
    lines: list[str] = []
    for w in windows:
        mask = (sd >= w.oos_start) & (sd < w.oos_end)
        direct = float(df.loc[mask, "pnl_dollars"].sum()) if len(df) else 0.0
        win_pnl = per_win[w.name]
        if abs(win_pnl - direct) > 0.01:
            return False, f"{label}: {w.name} window=${win_pnl:,.2f} != direct=${direct:,.2f}"
        lines.append(f"{w.name}: ${win_pnl:,.0f}")
    return True, f"{label}: all 7 windows match direct-sum  [{', '.join(lines)}]"


def validate_scoring(per_window: dict[str, float]) -> tuple[bool, str]:
    import math

    score = wf.sharpe_like_score(per_window)
    med = wf.median_pnl(per_window)
    sign = wf.sign_stability_count(per_window)
    qual = wf.qualifies(per_window)
    finite_ok = math.isfinite(score) and math.isfinite(med)
    sign_ok = 0 <= sign <= wf.N_WINDOWS
    if finite_ok and sign_ok and isinstance(qual, bool):
        return True, f"sharpe_like={score:.3f}  median=${med:,.2f}  sign={sign}/{wf.N_WINDOWS}  qualified={qual}"
    return False, f"scoring returned non-finite or out-of-range: score={score}  median={med}  sign={sign}"


def main() -> int:
    ensure_dirs()
    PHASE0_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading bars + ORB table...")
    bars, orb_table = load_data()
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions")
    print()

    print("Running synthetic classifiers:")
    fade_df = run_classifier(bars, orb_table, AllFade(), "AllFade")
    trend_df = run_classifier(bars, orb_table, AllTrend(), "AllTrend")
    skip_df = run_classifier(bars, orb_table, AllSkip(), "AllSkip")
    rand_df = run_classifier(bars, orb_table, RandomBinary(seed=0), "RandomBinary(0)")
    print()

    # Persist outputs for inspection
    fade_df.to_parquet(PHASE0_DIR / "trades_v2_allfade.parquet", index=False)
    trend_df.to_parquet(PHASE0_DIR / "trades_v2_alltrend.parquet", index=False)
    rand_df.to_parquet(PHASE0_DIR / "trades_v2_randombinary.parquet", index=False)

    results: list[tuple[str, bool, str]] = []

    # Validation 1 — byte-equivalence (non-negotiable #1)
    print("Validation 1: byte-equivalence vs locked extended baseline")
    ok, detail = validate_byte_equivalence(fade_df)
    results.append(("V1 byte-equivalence", ok, detail))
    print("  PASS" if ok else "  FAIL")
    print("  " + detail.replace("\n", "\n  "))
    print()

    # Validation 2 — walk-forward harness sanity (non-negotiable #2)
    print("Validation 2: walk-forward harness sanity")

    print("  2a windows definition...")
    ok2a, d2a = validate_windows()
    results.append(("V2a windows", ok2a, d2a))
    print("  PASS" if ok2a else "  FAIL")
    print(d2a)

    print("  2b AllSkip -> 0 trades...")
    ok2b, d2b = validate_skip_path(skip_df)
    results.append(("V2b SKIP path", ok2b, d2b))
    print("    " + ("PASS  " if ok2b else "FAIL  ") + d2b)

    print("  2c AllFade <-> AllTrend mechanical inversion...")
    ok2c, d2c = validate_trend_inversion(fade_df, trend_df)
    results.append(("V2c TREND inversion", ok2c, d2c))
    print("    " + ("PASS" if ok2c else "FAIL"))
    print("    " + d2c.replace("\n", "\n    "))

    print("  2d RandomBinary label mix near 50/50...")
    ok2d, d2d = validate_random_mix(rand_df)
    results.append(("V2d RandomBinary mix", ok2d, d2d))
    print("    " + ("PASS  " if ok2d else "FAIL  ") + d2d)

    print("  2e per-window P&L bucketing consistent (AllFade)...")
    ok2e, d2e = validate_pnl_bucketing(fade_df, "AllFade")
    results.append(("V2e bucketing AllFade", ok2e, d2e))
    print("    " + ("PASS  " if ok2e else "FAIL  ") + d2e)

    print("  2f per-window P&L bucketing consistent (AllTrend)...")
    ok2f, d2f = validate_pnl_bucketing(trend_df, "AllTrend")
    results.append(("V2f bucketing AllTrend", ok2f, d2f))
    print("    " + ("PASS  " if ok2f else "FAIL  ") + d2f)

    print("  2g scoring functions return finite values...")
    windows = wf.make_windows()
    pw_fade = wf.per_window_pnl(fade_df, windows, slice_="oos")
    pw_trend = wf.per_window_pnl(trend_df, windows, slice_="oos")
    pw_rand = wf.per_window_pnl(rand_df, windows, slice_="oos")
    ok_g_fade, d_g_fade = validate_scoring(pw_fade)
    ok_g_trend, d_g_trend = validate_scoring(pw_trend)
    ok_g_rand, d_g_rand = validate_scoring(pw_rand)
    ok2g = ok_g_fade and ok_g_trend and ok_g_rand
    d2g = "\n".join([
        f"AllFade   {d_g_fade}",
        f"AllTrend  {d_g_trend}",
        f"RandomBin {d_g_rand}",
    ])
    results.append(("V2g scoring finite", ok2g, d2g))
    print("    " + ("PASS" if ok2g else "FAIL"))
    print("    " + d2g.replace("\n", "\n    "))
    print()

    # Write report.md
    all_pass = all(ok for _, ok, _ in results)
    write_report(results, fade_df, trend_df, rand_df, all_pass, pw_fade, pw_trend, pw_rand)

    print("=" * 60)
    if all_pass:
        print("PHASE 0 VALIDATIONS: ALL PASS")
        print(f"Artifacts: {PHASE0_DIR}")
        return 0
    print("PHASE 0 VALIDATIONS: FAILED")
    print("Do not start Phase 1. Review the failures above.")
    return 1


def write_report(results, fade_df, trend_df, rand_df, all_pass, pw_fade, pw_trend, pw_rand):
    windows = wf.make_windows()
    lines: list[str] = []
    lines.append(f"# Phase 0 Validation Report")
    lines.append(f"")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Status:** {'PASS' if all_pass else 'FAIL'}")
    lines.append(f"")
    lines.append(f"Two non-negotiable validations per user spec:")
    lines.append(f"1. simulator_v2 with AllFade classifier byte-identical to locked extended baseline")
    lines.append(f"2. Walk-forward harness sanity with synthetic classifiers")
    lines.append(f"")
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"| Test | Result | Detail |")
    lines.append(f"|---|---|---|")
    for name, ok, detail in results:
        first_line = detail.split("\n")[0]
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {first_line[:90]} |")
    lines.append(f"")

    lines.append(f"## Validation 1 — Byte-equivalence")
    lines.append(f"")
    for name, ok, detail in results:
        if name == "V1 byte-equivalence":
            lines.append(f"**Status:** {'PASS' if ok else 'FAIL'}")
            lines.append(f"")
            lines.append("```")
            lines.append(detail)
            lines.append("```")
            break
    lines.append(f"")

    lines.append(f"## Validation 2 — Walk-forward harness sanity")
    lines.append(f"")
    lines.append(f"### Window definitions")
    lines.append(f"")
    lines.append(f"| Window | IS start | IS end | OOS start | OOS end |")
    lines.append(f"|---|---|---|---|---|")
    for w in windows:
        lines.append(f"| {w.name} | {w.is_start.date()} | {w.is_end.date()} | {w.oos_start.date()} | {w.oos_end.date()} |")
    lines.append(f"")

    lines.append(f"### Classifier outputs")
    lines.append(f"")
    lines.append(f"| Classifier | Trades | Total P&L | Win/Loss/Force |")
    lines.append(f"|---|---:|---:|---|")
    for label, df in [("AllFade", fade_df), ("AllTrend", trend_df), ("RandomBinary(0)", rand_df)]:
        if len(df) == 0:
            lines.append(f"| {label} | 0 | $0 | — |")
            continue
        tot = df["pnl_dollars"].sum()
        exits = df["exit_reason"].value_counts().to_dict()
        ex_str = f"target={exits.get('target',0)} / stop={exits.get('stop',0)} / fc={exits.get('force_close',0)}"
        lines.append(f"| {label} | {len(df):,} | ${tot:,.2f} | {ex_str} |")
    lines.append(f"")

    lines.append(f"### Per-window OOS P&L")
    lines.append(f"")
    lines.append(f"| Window | AllFade | AllTrend | RandomBinary(0) |")
    lines.append(f"|---|---:|---:|---:|")
    for w in windows:
        lines.append(f"| {w.name} | ${pw_fade[w.name]:,.0f} | ${pw_trend[w.name]:,.0f} | ${pw_rand[w.name]:,.0f} |")
    lines.append(f"")
    lines.append(f"Scoring per classifier:")
    lines.append(f"")
    lines.append(f"```")
    lines.append(wf.summarize(pw_fade,  label="AllFade"))
    lines.append(wf.summarize(pw_trend, label="AllTrend"))
    lines.append(wf.summarize(pw_rand,  label="RandomBinary(0)"))
    lines.append(f"```")
    lines.append(f"")

    lines.append(f"### Detailed sanity check results")
    lines.append(f"")
    for name, ok, detail in results:
        if name.startswith("V1"):
            continue
        lines.append(f"**{name}** — {'PASS' if ok else 'FAIL'}")
        lines.append(f"")
        lines.append("```")
        lines.append(detail)
        lines.append("```")
        lines.append(f"")

    lines.append(f"## Artifacts")
    lines.append(f"")
    lines.append(f"- `trades_v2_allfade.parquet` — for inspection; should byte-match baseline")
    lines.append(f"- `trades_v2_alltrend.parquet` — TREND-inverted variant")
    lines.append(f"- `trades_v2_randombinary.parquet` — 50/50 mix")

    report_path = PHASE0_DIR / "report.md"
    report_path.write_text("\n".join(lines))
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    sys.exit(main())
