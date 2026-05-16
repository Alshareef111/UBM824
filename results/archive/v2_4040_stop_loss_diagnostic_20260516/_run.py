"""V2+40/40 stop-loss diagnostic: flag Bug A / Bug B / phantom-suspect per trade,
compute P&L sensitivity bounds, write flagged parquet + summary.json.

Read-only on inputs. Output: stop_outs_flagged.parquet + summary.json in this dir.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path("results/archive/v2_4040_stop_loss_diagnostic_20260516")
TRADES = Path("results/40_40_v2_full/20260514_125349/trades.parquet")
BARS = Path("data/processed/mnq_adjusted_1m.parquet")

df = pd.read_parquet(TRADES)
bars = pd.read_parquet(BARS)
bars_idx = bars.set_index("ts_utc")

all_target_mean = df[df["exit_reason"] == "target"]["pnl_dollars"].mean()
all_fc_mean = df[df["exit_reason"] == "force_close"]["pnl_dollars"].mean()
print(f"sanity: target mean=${all_target_mean:.2f} | force_close mean=${all_fc_mean:.2f}")

stops = df[df["exit_reason"] == "stop"].copy().reset_index(drop=True)
assert len(stops) == 336, f"expected 336 stops, got {len(stops)}"

stops["stop_price"] = np.where(
    stops["side"] == "buy", stops["entry_price"] - 40.0, stops["entry_price"] + 40.0
)
stops["target_price"] = np.where(
    stops["side"] == "buy", stops["entry_price"] + 40.0, stops["entry_price"] - 40.0
)


def lookup_bar(ts):
    try:
        row = bars_idx.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return row["open"], row["high"], row["low"], row["close"]
    except KeyError:
        return (np.nan,) * 4


ohlc = stops["exit_time"].apply(
    lambda ts: pd.Series(lookup_bar(ts), index=["bar_open", "bar_high", "bar_low", "bar_close"])
)
stops = pd.concat([stops, ohlc], axis=1)
missing = int(stops["bar_open"].isna().sum())
print(f"missing exit-bar lookups: {missing} / 336")

# Bug A: exit bar range spans both stop and target (symmetric 80pt window around entry)
stops["bug_a"] = (stops["bar_low"] <= stops["entry_price"] - 40.0) & (
    stops["bar_high"] >= stops["entry_price"] + 40.0
)

# Bug B: entry and exit on the same minute bar
stops["bug_b"] = stops["entry_time"] == stops["exit_time"]

# Phantom-fill heuristic: wick distance from body edge to stop-triggering extreme
def phantom_row(row):
    if row["side"] == "buy":
        body_low = min(row["bar_open"], row["bar_close"])
        wick = body_low - row["bar_low"]
        return body_low, wick
    body_high = max(row["bar_open"], row["bar_close"])
    wick = row["bar_high"] - body_high
    return body_high, wick


bd = stops.apply(phantom_row, axis=1, result_type="expand")
bd.columns = ["body_edge", "wick_distance"]
stops = pd.concat([stops, bd], axis=1)
stops["phantom_suspect"] = stops["wick_distance"] >= 8.0

n = len(stops)
n_a = int(stops["bug_a"].sum())
n_b = int(stops["bug_b"].sum())
n_both = int((stops["bug_a"] & stops["bug_b"]).sum())
n_neither = int((~stops["bug_a"] & ~stops["bug_b"]).sum())
n_phantom = int(stops["phantom_suspect"].sum())

print()
print("=== Counts ===")
print(f"Total stop-outs:           {n}")
print(f"Bug A candidates:          {n_a} ({n_a/n*100:.2f}%)")
print(f"Bug B candidates:          {n_b} ({n_b/n*100:.2f}%)")
print(f"Both A and B:              {n_both} ({n_both/n*100:.2f}%)")
print(f"Neither A nor B:           {n_neither} ({n_neither/n*100:.2f}%)")
print(f"Phantom-suspect (heur):    {n_phantom} ({n_phantom/n*100:.2f}%)")

print()
print("=== Doc-estimate comparison (32-trade slice at 30/30) ===")
print(f"Bug A doc ~1% across all trades; here on stops at 40/40: {n_a/n*100:.2f}% ({n_a}/{n})")
print(f"Bug B doc ~3% across all trades; here on stops at 40/40: {n_b/n*100:.2f}% ({n_b}/{n})")

stop_pnl = float(stops["pnl_dollars"].sum())
baseline_total = 8808.0
delta_a = 160.0 * n_a
delta_b_flat = 80.0 * n_b
delta_b_fc = (all_fc_mean - (-80.0)) * n_b
delta_both_flat = delta_a + delta_b_flat
delta_both_fc = delta_a + delta_b_fc

print()
print("=== P&L sensitivity ===")
print(f"Current stop-out P&L:      ${stop_pnl:,.2f}")
print()
print("| Scenario | Stop-out P&L | Total P&L |")
print("|----------|-----------:|----------:|")
print(f"| Current (no correction)               | ${stop_pnl:>10,.2f} | ${baseline_total:>9,.2f} |")
print(f"| Bug A flipped to targets              | ${stop_pnl+delta_a:>10,.2f} | ${baseline_total+delta_a:>9,.2f} |")
print(f"| Bug B trades -> flat ($0)             | ${stop_pnl+delta_b_flat:>10,.2f} | ${baseline_total+delta_b_flat:>9,.2f} |")
print(f"| Bug B trades -> force-close (avg ${all_fc_mean:.2f}) | ${stop_pnl+delta_b_fc:>10,.2f} | ${baseline_total+delta_b_fc:>9,.2f} |")
print(f"| BOTH (A->target + B->flat)            | ${stop_pnl+delta_both_flat:>10,.2f} | ${baseline_total+delta_both_flat:>9,.2f} |")
print(f"| BOTH (A->target + B->force-close)     | ${stop_pnl+delta_both_fc:>10,.2f} | ${baseline_total+delta_both_fc:>9,.2f} |")

print()
print("=== Distribution: wick distance on stop-outs ===")
bins = [0, 2, 4, 8, 12, 20, 50, 9999]
labels = ["0-2", "2-4", "4-8", "8-12", "12-20", "20-50", "50+"]
wick_hist = (
    pd.cut(stops["wick_distance"], bins=bins, labels=labels, include_lowest=True, right=False)
    .value_counts()
    .sort_index()
)
for label in labels:
    cnt = int(wick_hist.get(label, 0))
    pct = cnt / n * 100
    print(f"  {label:6}: {cnt:4} ({pct:5.1f}%)")

print()
print("=== Per-year breakdown ===")
stops["year"] = pd.to_datetime(stops["session_date"]).dt.year
year_tab = stops.groupby("year").agg(
    n_stops=("side", "count"),
    n_bug_a=("bug_a", "sum"),
    n_bug_b=("bug_b", "sum"),
    n_phantom=("phantom_suspect", "sum"),
    stop_pnl=("pnl_dollars", "sum"),
)
print(year_tab.to_string())

print()
print("=== Bug B time-of-day (NY) ===")
if n_b > 0:
    bb = stops[stops["bug_b"]].copy()
    bb["hour_ny"] = bb["exit_time"].dt.tz_convert("America/New_York").dt.hour
    bb["minute_ny"] = bb["exit_time"].dt.tz_convert("America/New_York").dt.minute
    print(bb.groupby("hour_ny").size().to_string())
    print()
    print("Bug B minute-of-hour (NY):")
    print(bb.groupby(["hour_ny", "minute_ny"]).size().to_string())

print()
print("=== cluster_label x bug ===")
print("Bug A cross-tab:")
print(pd.crosstab(stops["cluster_label"], stops["bug_a"], margins=True).to_string())
print()
print("Bug B cross-tab:")
print(pd.crosstab(stops["cluster_label"], stops["bug_b"], margins=True).to_string())
print()
print("Phantom-suspect cross-tab:")
print(pd.crosstab(stops["cluster_label"], stops["phantom_suspect"], margins=True).to_string())

out_cols = [
    "session_date", "side", "entry_time", "entry_price", "stop_price", "target_price",
    "exit_time", "exit_price", "pnl_points", "pnl_dollars",
    "cluster_low", "cluster_high", "cluster_size", "cluster_label",
    "bar_open", "bar_high", "bar_low", "bar_close",
    "bug_a", "bug_b", "phantom_suspect", "body_edge", "wick_distance", "year",
]
out = stops[out_cols].copy()
out_path = OUT_DIR / "stop_outs_flagged.parquet"
out.to_parquet(out_path, index=False)
print()
print(f"Wrote: {out_path} ({len(out)} rows)")

summary = {
    "total_stops": n,
    "bug_a_count": n_a,
    "bug_a_pct": n_a / n * 100,
    "bug_b_count": n_b,
    "bug_b_pct": n_b / n * 100,
    "both_a_b_count": n_both,
    "neither_count": n_neither,
    "phantom_suspect_count": n_phantom,
    "phantom_suspect_pct": n_phantom / n * 100,
    "stop_pnl": stop_pnl,
    "baseline_total": baseline_total,
    "force_close_mean": float(all_fc_mean),
    "target_mean": float(all_target_mean),
    "delta_a": float(delta_a),
    "delta_b_flat": float(delta_b_flat),
    "delta_b_fc": float(delta_b_fc),
    "delta_both_flat": float(delta_both_flat),
    "delta_both_fc": float(delta_both_fc),
    "year_tab": {
        int(k): {kk: float(vv) for kk, vv in v.items()}
        for k, v in year_tab.to_dict("index").items()
    },
}
(OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
print(f"Wrote: {OUT_DIR / 'summary.json'}")
