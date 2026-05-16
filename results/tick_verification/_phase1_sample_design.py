"""Phase 1 stratified sample design for V2 + 40/40 tick verification.

Picks ~40 trading session_dates with a deterministic seed for downstream
Databento tick download (Phase 2, separate).

Read-only on all inputs. Writes only to results/tick_verification/.

Documented methodological choices (all defensible defaults; flag if any
would bias the sample):
  - Date key: session_date (NY-trading-session, with +6h offset already
    applied at data_prep time per src/data_prep.py)
  - Random seed: numpy.random.seed(20260516); applied once before all draws
  - "High-vol day": session trading-window bar range (9:46-11:30 NY)
    > mean + 2 std across all 576 covered sessions
  - "Gap day": |first_bar_open(today) - last_bar_close(prior_session)|
    / prior_close > 0.25%; bars at session-edge (no time filtering)
  - "Tight stop touch": abs(entry_bar.{low if buy else high} - stop_price)
    <= 0.25  (1 MNQ tick)
  - S3 sub-stratum target allocation: 3a + 3b + 2c + 2d; backfill within S3
    from earlier sub-strata if any falls short; final fallback per spec.
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path("results/tick_verification")
OUT_PATH = OUT_DIR / "phase1_sample_20260516.csv"
TRADES = Path("results/40_40_v2_full/20260514_125349/trades.parquet")
BARS = Path("data/processed/mnq_adjusted_1m.parquet")

SEED = 20260516
TICK = 0.25  # MNQ tick size in points
STOP_POINTS = 40.0
GAP_PCT_THR = 0.0025  # 0.25%

S1_N = 15
S2_N = 15
S3_TARGET = {"same_bar_exit": 3, "tight_stop_touch": 3, "high_vol_day": 2, "gap_day": 2}


def sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    print(f"Inputs:")
    print(f"  trades:  {TRADES}")
    print(f"  trades sha256: {sha256(TRADES)}")
    print(f"  bars:    {BARS}")
    print(f"  seed:    {SEED}")
    print()

    df = pd.read_parquet(TRADES).copy()
    assert len(df) == 908
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.normalize()

    # Per-date aggregates
    agg = (
        df.groupby("session_date")
        .agg(
            n_trades=("side", "count"),
            total_pnl_gross=("pnl_dollars", "sum"),
            fade_count=("cluster_label", lambda s: (s == "FADE").sum()),
            trend_count=("cluster_label", lambda s: (s == "TREND").sum()),
        )
        .reset_index()
    )
    agg["abs_pnl"] = agg["total_pnl_gross"].abs()
    all_dates = agg["session_date"].sort_values().reset_index(drop=True)
    print(f"Population: {len(all_dates)} unique session_dates, {df.shape[0]} trades")
    print(f"  population FADE/TREND: {(df['cluster_label']=='FADE').sum()}/{(df['cluster_label']=='TREND').sum()}"
          f" = {(df['cluster_label']=='FADE').mean()*100:.1f}%/{(df['cluster_label']=='TREND').mean()*100:.1f}%")
    print()

    selected = []  # list of (date, stratum, sub_stratum, rationale)
    picked = set()

    # ----------- Stratum 1 — Random uniform (n=15) -----------
    rng = np.random.default_rng(SEED)
    pool = all_dates.to_numpy()
    s1_idx = rng.choice(len(pool), size=S1_N, replace=False)
    s1_dates = sorted(pool[s1_idx])
    for d in s1_dates:
        selected.append((d, "S1_uniform", "", "uniform random draw"))
        picked.add(d)
    print(f"S1 picked: {len(s1_dates)} dates")

    # ----------- Stratum 2 — Top |daily P&L| (n=15) -----------
    ranked = agg.sort_values("abs_pnl", ascending=False)["session_date"].tolist()
    s2_dates = []
    for d in ranked:
        if d in picked:
            continue
        s2_dates.append(d)
        if len(s2_dates) == S2_N:
            break
    for d in s2_dates:
        pnl = agg.loc[agg["session_date"] == d, "total_pnl_gross"].iloc[0]
        selected.append((d, "S2_high_stakes", "", f"daily |pnl| = ${abs(pnl):.0f} (top-{S2_N + 1} excluding S1)"))
        picked.add(d)
    print(f"S2 picked: {len(s2_dates)} dates  (top-|pnl| excluding S1 overlaps)")

    # ----------- Stratum 3 — Bug B suspects (n=10) -----------
    s3_picks = []  # list of (date, sub_stratum, rationale)

    # --- Sub a: same_bar_exit ---
    sb_mask = df["entry_time"] == df["exit_time"]
    sb_dates_pool = df.loc[sb_mask, "session_date"].drop_duplicates().sort_values().tolist()
    # filter out picked
    a_avail = [d for d in sb_dates_pool if d not in picked]
    # deterministic shuffle then take up to target
    rng_a = np.random.default_rng(SEED + 1)
    a_avail_arr = np.array(a_avail)
    rng_a.shuffle(a_avail_arr)
    a_picks = a_avail_arr[: S3_TARGET["same_bar_exit"]].tolist()
    for d in a_picks:
        n_sb = int(sb_mask[df["session_date"] == d].sum())
        s3_picks.append((d, "same_bar_exit", f"{n_sb} same-bar exit(s) on this date"))
        picked.add(d)
    print(f"S3a same_bar_exit: picked {len(a_picks)} / {len(a_avail)} available (after excluding S1+S2)")

    # --- Sub b: tight_stop_touch ---
    # Build entry-bar lookup: trades.entry_time -> bar.high, bar.low
    print(f"  loading bars for entry-bar lookup (this takes a moment)...")
    bars = pd.read_parquet(BARS, columns=["ts_utc", "ts_ny", "session_date", "open", "high", "low", "close"])
    bars_idx = bars.set_index("ts_utc")

    def entry_bar_extreme_distance_to_stop(row):
        try:
            r = bars_idx.loc[row["entry_time"]]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
        except KeyError:
            return np.nan
        entry = row["entry_price"]
        if row["side"] == "buy":
            stop = entry - STOP_POINTS
            adverse_extreme = r["low"]
        else:
            stop = entry + STOP_POINTS
            adverse_extreme = r["high"]
        return abs(adverse_extreme - stop)

    df["entry_bar_stop_dist"] = df.apply(entry_bar_extreme_distance_to_stop, axis=1)
    tight_mask = df["entry_bar_stop_dist"] <= TICK + 1e-9
    print(f"  tight-stop entry-bar trades (<= 1 tick): {int(tight_mask.sum())} / 908")

    tight_dates_pool = (
        df.loc[tight_mask]
        .groupby("session_date")
        .size()
        .reset_index(name="n_tight")
        .sort_values("n_tight", ascending=False)
    )
    b_avail = [d for d in tight_dates_pool["session_date"] if d not in picked]
    rng_b = np.random.default_rng(SEED + 2)
    # deterministic order within available: rank by n_tight desc, ties by date asc
    b_picks = b_avail[: S3_TARGET["tight_stop_touch"]]
    for d in b_picks:
        nt = int(tight_dates_pool.loc[tight_dates_pool["session_date"] == d, "n_tight"].iloc[0])
        s3_picks.append((d, "tight_stop_touch", f"{nt} trade(s) with entry bar adverse extreme within 1 tick of stop"))
        picked.add(d)
    print(f"S3b tight_stop_touch: picked {len(b_picks)} / {len(b_avail)} available")

    # --- Sub c: high_vol_day ---
    # Trading-window bars only (9:46-11:30 NY)
    h = bars["ts_ny"].dt.hour
    m = bars["ts_ny"].dt.minute
    tw_mask = ((h > 9) | ((h == 9) & (m >= 46))) & ((h < 11) | ((h == 11) & (m < 30)))
    tw_bars = bars[tw_mask]
    daily_range = (
        tw_bars.groupby("session_date")
        .agg(d_high=("high", "max"), d_low=("low", "min"))
        .assign(d_range=lambda x: x["d_high"] - x["d_low"])
    )
    # restrict to dates with at least one trade
    daily_range = daily_range.loc[daily_range.index.isin(all_dates)]
    mu, sd = daily_range["d_range"].mean(), daily_range["d_range"].std(ddof=1)
    thr = mu + 2 * sd
    high_vol = daily_range[daily_range["d_range"] > thr].sort_values("d_range", ascending=False)
    print(f"  trading-window daily range: mu={mu:.2f}, sd={sd:.2f}, threshold (mu+2sd)={thr:.2f}; high-vol dates: {len(high_vol)}")
    c_avail = [d for d in high_vol.index if d not in picked]
    c_picks = c_avail[: S3_TARGET["high_vol_day"]]
    for d in c_picks:
        rng_pts = float(daily_range.loc[d, "d_range"])
        s3_picks.append((d, "high_vol_day", f"trading-window range {rng_pts:.2f}pt > mu+2sd ({thr:.2f})"))
        picked.add(d)
    print(f"S3c high_vol_day: picked {len(c_picks)} / {len(c_avail)} available")

    # --- Sub d: gap_day ---
    # Per-session first bar open vs prior-session last bar close
    daily = (
        bars.sort_values("ts_utc")
        .groupby("session_date")
        .agg(first_open=("open", "first"), last_close=("close", "last"))
    )
    daily["prior_close"] = daily["last_close"].shift(1)
    daily["gap_pct"] = (daily["first_open"] - daily["prior_close"]).abs() / daily["prior_close"]
    daily = daily.loc[daily.index.isin(all_dates)]
    gap_days = daily[daily["gap_pct"] > GAP_PCT_THR].sort_values("gap_pct", ascending=False)
    print(f"  gap-day threshold: |open - prior_close|/prior_close > {GAP_PCT_THR*100:.2f}%; gap-day count: {len(gap_days)}")
    d_avail = [d for d in gap_days.index if d not in picked]
    d_picks = d_avail[: S3_TARGET["gap_day"]]
    for d in d_picks:
        gp = float(gap_days.loc[d, "gap_pct"])
        s3_picks.append((d, "gap_day", f"open-to-prior-close gap {gp*100:.2f}%"))
        picked.add(d)
    print(f"S3d gap_day: picked {len(d_picks)} / {len(d_avail)} available")

    # Backfill S3 if any sub-stratum fell short
    s3_target_total = sum(S3_TARGET.values())
    short = s3_target_total - len(s3_picks)
    fallback_note = ""
    if short > 0:
        print(f"\nS3 short by {short}; backfilling from same_bar_exit pool (then random uniform if needed)")
        # Try same_bar_exit overflow first
        a_overflow = [d for d in a_avail if d not in picked]
        a_extra = a_overflow[:short]
        for d in a_extra:
            n_sb = int(sb_mask[df["session_date"] == d].sum())
            s3_picks.append((d, "same_bar_exit", f"backfill: {n_sb} same-bar exit(s)"))
            picked.add(d)
        short -= len(a_extra)
        if short > 0:
            # Final fallback: random uniform from remaining population
            remaining = [d for d in pool if d not in picked]
            rng_bf = np.random.default_rng(SEED + 99)
            bf = rng_bf.choice(remaining, size=short, replace=False)
            for d in sorted(bf):
                s3_picks.append((d, "uniform_backfill", "backfill: random uniform"))
                picked.add(d)
            fallback_note = f"S3 used {len(bf)} random-uniform backfill picks (insufficient candidates in sub-strata)"

    for d, sub, rat in s3_picks:
        selected.append((d, "S3_bug_b_suspect", sub, rat))
    print(f"\nS3 picked: {len(s3_picks)} dates total (target {s3_target_total})")

    # ----------- Build output frame -----------
    sel = pd.DataFrame(selected, columns=["session_date", "stratum", "sub_stratum", "rationale"])
    sel = sel.merge(agg[["session_date", "n_trades", "total_pnl_gross", "fade_count", "trend_count"]], on="session_date", how="left")
    sel = sel.rename(columns={"session_date": "date"})
    sel["date"] = pd.to_datetime(sel["date"]).dt.strftime("%Y-%m-%d")
    sel = sel.sort_values("date").reset_index(drop=True)
    sel = sel[["date", "n_trades", "stratum", "sub_stratum", "total_pnl_gross", "fade_count", "trend_count", "rationale"]]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sel.to_csv(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}  ({len(sel)} rows)")

    # ----------- Reports to terminal -----------
    print(f"\n{'='*72}")
    print("Stratum-level summary")
    print(f"{'='*72}")
    by_stratum = (
        sel.groupby("stratum")
        .agg(n_days=("date", "count"), total_trades=("n_trades", "sum"),
             fade_count=("fade_count", "sum"), trend_count=("trend_count", "sum"),
             total_pnl_gross=("total_pnl_gross", "sum"))
        .reset_index()
    )
    print(by_stratum.to_string(index=False))

    print(f"\n{'='*72}")
    print("All 40 dates grouped by stratum (sorted within group)")
    print(f"{'='*72}")
    for stratum in ["S1_uniform", "S2_high_stakes", "S3_bug_b_suspect"]:
        sub = sel[sel["stratum"] == stratum].sort_values("date")
        print(f"\n--- {stratum} (n={len(sub)}) ---")
        for _, r in sub.iterrows():
            sub_lbl = f" [{r['sub_stratum']}]" if r["sub_stratum"] else ""
            print(f"  {r['date']}  trades={r['n_trades']:<2}  pnl=${r['total_pnl_gross']:>+8,.0f}"
                  f"  F/T={r['fade_count']}/{r['trend_count']}{sub_lbl}  - {r['rationale']}")

    print(f"\n{'='*72}")
    print("Coverage and label balance")
    print(f"{'='*72}")
    total_sample_trades = sel["n_trades"].sum()
    total_sample_fade = sel["fade_count"].sum()
    total_sample_trend = sel["trend_count"].sum()
    pop_fade = int((df["cluster_label"] == "FADE").sum())
    pop_trend = int((df["cluster_label"] == "TREND").sum())
    print(f"Trades in sample:   {total_sample_trades} / 908  ({total_sample_trades/908*100:.2f}% of population)")
    print(f"Unique dates:       {len(sel)} / 576  ({len(sel)/576*100:.2f}% of dates)")
    print(f"FADE in sample:     {total_sample_fade}  ({total_sample_fade/total_sample_trades*100:.2f}%)")
    print(f"TREND in sample:    {total_sample_trend}  ({total_sample_trend/total_sample_trades*100:.2f}%)")
    print(f"FADE in population: {pop_fade}  ({pop_fade/(pop_fade+pop_trend)*100:.2f}%)")
    print(f"TREND in population:{pop_trend}  ({pop_trend/(pop_fade+pop_trend)*100:.2f}%)")
    fade_skew = (total_sample_fade/total_sample_trades) - (pop_fade/(pop_fade+pop_trend))
    print(f"FADE skew (sample - pop): {fade_skew*100:+.2f}pp")

    if fallback_note:
        print(f"\nNOTE: {fallback_note}")
    else:
        print(f"\nNo fallbacks invoked; all 4 sub-strata populated to target.")

    print(f"\nFinal trades sha256: {sha256(TRADES)}  (expect 1ccf859e3a580d78eb85cbc37a2cfa7159c3af59c3eb4bb58b5443d0aaf54feb)")


if __name__ == "__main__":
    main()
