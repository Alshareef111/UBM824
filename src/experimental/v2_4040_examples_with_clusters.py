"""Regenerate the 10 V2+40/40 example charts, now showing ALL clusters from
each session's 9:45 pool, colored by fate (TRADED / TOUCHED_NOT_TRADED /
UNTOUCHED / SPANS_CLOSE).

Output: results/archive/v2_4040_examples_with_clusters_20260515/
  trade_NN_YYYYMMDD_<outcome>_with_clusters.png  (10 individual figures)
  contact_sheet_with_clusters.png                (5x2 grid)
  cluster_pool_<date>.csv                        (10 cluster catalogs)
  manifest.md                                    (per-trade landscape summary)

No edits to protected files. Pure read-only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, date2num
from matplotlib.patches import Rectangle

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from clusters import find_clusters

# Re-use deterministic selection from prior script to ensure same 10 trades
from experimental.v2_4040_examples import format_text_panel, select_trades
from paths import ARCHIVE_DIR, BARS_PARQUET, ORB_TABLE_PARQUET

TRADES_PARQUET = ARCHIVE_DIR / "strategy_report_20260512" / "trades_v2_4040.parquet"
OUT_DIR = ARCHIVE_DIR / "v2_4040_examples_with_clusters_20260515"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
STOP_POINTS = 40.0
TARGET_POINTS = 40.0
Y_HALF_RANGE = 60.0  # zoom y to entry +/- this

CAT_COLORS = {
    "TRADED": dict(color="#6a4c93", alpha=0.45, edge_alpha=0.85, edge_lw=1.0),
    "TOUCHED_NOT_TRADED": dict(color="#7d7d7d", alpha=0.25, edge_alpha=0.55, edge_lw=0.6),
    "UNTOUCHED": dict(color="#7d7d7d", alpha=0.10, edge_alpha=0.0, edge_lw=0.0),
    "SPANS_CLOSE": dict(color="#e9c46a", alpha=0.18, edge_alpha=0.0, edge_lw=0.0),
}


def reconstruct_cluster_pool(
    session_date, orb_table: pd.DataFrame
) -> tuple[list, float, float, float]:
    """Return (clusters, orb_close, orb_high, orb_low) for the given session.

    Mirrors simulator_v2.run_backtest's level-pool construction: 200 prior
    sessions' ORB highs/lows + today's ORB high/low, then find_clusters with
    locked params.
    """
    orb_table = orb_table.sort_values("session_date").reset_index(drop=True)
    sd_ts = pd.Timestamp(session_date).normalize()
    # Find today's row in ORB table
    matches = orb_table[orb_table["session_date"].astype("datetime64[ns]") == sd_ts]
    if matches.empty:
        raise ValueError(f"session_date {session_date} not in ORB table")
    today_idx = matches.index[0]
    today_row = orb_table.iloc[today_idx]

    # Past 200 sessions strictly before today
    prior = orb_table.iloc[max(0, today_idx - LOOKBACK) : today_idx]

    levels = []
    for _, row in prior.iterrows():
        levels.append(float(row["orb_high"]))
        levels.append(float(row["orb_low"]))
    levels.append(float(today_row["orb_high"]))
    levels.append(float(today_row["orb_low"]))

    clusters = find_clusters(levels, max_gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE)
    return (
        clusters,
        float(today_row["orb_close"]),
        float(today_row["orb_high"]),
        float(today_row["orb_low"]),
    )


def categorize_clusters(
    clusters: list, orb_close: float, traded_low: float, traded_high: float, win_bars: pd.DataFrame
) -> list[dict]:
    """For each cluster, compute position vs ORB close and fate during 9:46–11:30.

    Position: ABOVE / BELOW / SPANS (with respect to orb_close)
    Fate:
      TRADED:             matches (traded_low, traded_high)
      SPANS_CLOSE:        spans the ORB close (overrides fate logic)
      TOUCHED_NOT_TRADED: near-border crossed by some bar's range in 9:46–11:30
      UNTOUCHED:          near-border never crossed
    """
    out = []
    win_high = win_bars["high"].to_numpy() if len(win_bars) else np.array([])
    win_low = win_bars["low"].to_numpy() if len(win_bars) else np.array([])

    for c in clusters:
        low = float(c.low)
        high = float(c.high)
        size = int(c.size)
        traded = (abs(low - traded_low) < 1e-9) and (abs(high - traded_high) < 1e-9)

        if low > orb_close:
            position = "ABOVE"
            near_border = low
            touched = bool(np.any(win_high >= near_border)) if len(win_high) else False
        elif high < orb_close:
            position = "BELOW"
            near_border = high
            touched = bool(np.any(win_low <= near_border)) if len(win_low) else False
        else:
            position = "SPANS"
            near_border = float("nan")
            touched = False  # n/a for spanning clusters

        if position == "SPANS":
            fate = "SPANS_CLOSE"
        elif traded:
            fate = "TRADED"
        elif touched:
            fate = "TOUCHED_NOT_TRADED"
        else:
            fate = "UNTOUCHED"

        out.append(
            {
                "cluster_low": low,
                "cluster_high": high,
                "cluster_size": size,
                "position": position,
                "near_border": near_border,
                "fate": fate,
            }
        )
    return out


def session_window_bars(bars: pd.DataFrame, session_date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (chart_window_bars, trading_window_bars)."""
    sd = pd.Timestamp(session_date)
    day = bars[bars["session_date"].astype("datetime64[ns]") == sd].sort_values("ts_ny")
    sd_date = sd.date()
    chart_start = pd.Timestamp.combine(sd_date, pd.Timestamp("09:00").time()).tz_localize(
        "America/New_York"
    )
    chart_end = pd.Timestamp.combine(sd_date, pd.Timestamp("11:45").time()).tz_localize(
        "America/New_York"
    )
    chart = day[(day["ts_ny"] >= chart_start) & (day["ts_ny"] <= chart_end)].reset_index(drop=True)

    trade_start = pd.Timestamp.combine(sd_date, pd.Timestamp("09:46").time()).tz_localize(
        "America/New_York"
    )
    trade_end = pd.Timestamp.combine(sd_date, pd.Timestamp("11:30").time()).tz_localize(
        "America/New_York"
    )
    trade = day[(day["ts_ny"] >= trade_start) & (day["ts_ny"] < trade_end)].reset_index(drop=True)
    return chart, trade


def draw_candles(ax, day_bars: pd.DataFrame):
    ts_naive = day_bars["ts_ny"].dt.tz_localize(None)
    xs = date2num(ts_naive)
    width_minutes = 0.6 / (24 * 60)
    for x, row in zip(xs, day_bars.itertuples()):
        o = float(row.open)
        c = float(row.close)
        h = float(row.high)
        l = float(row.low)
        up = c >= o
        color = "#2a9d8f" if up else "#e76f51"
        ax.plot([x, x], [l, h], color=color, linewidth=0.6, zorder=2)
        body_low = min(o, c)
        body_height = max(abs(c - o), 1e-9)
        ax.add_patch(
            Rectangle(
                (x - width_minutes / 2, body_low),
                width_minutes,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
                zorder=3,
            )
        )


def draw_cluster_bands(ax, cluster_records: list[dict]):
    # Stack in this order so TRADED is drawn last (on top).
    order = ["UNTOUCHED", "SPANS_CLOSE", "TOUCHED_NOT_TRADED", "TRADED"]
    by_fate = {k: [c for c in cluster_records if c["fate"] == k] for k in order}
    for fate in order:
        sty = CAT_COLORS[fate]
        for c in by_fate[fate]:
            ax.axhspan(
                c["cluster_low"],
                c["cluster_high"],
                facecolor=sty["color"],
                alpha=sty["alpha"],
                zorder=1,
            )
            if sty["edge_lw"] > 0:
                ax.axhline(
                    c["cluster_low"],
                    color=sty["color"],
                    alpha=sty["edge_alpha"],
                    linewidth=sty["edge_lw"],
                    linestyle="-",
                    zorder=1.5,
                )
                ax.axhline(
                    c["cluster_high"],
                    color=sty["color"],
                    alpha=sty["edge_alpha"],
                    linewidth=sty["edge_lw"],
                    linestyle="-",
                    zorder=1.5,
                )


def landscape_summary(cluster_records: list[dict]) -> dict:
    total = len(cluster_records)
    above = sum(1 for c in cluster_records if c["position"] == "ABOVE")
    below = sum(1 for c in cluster_records if c["position"] == "BELOW")
    spans = sum(1 for c in cluster_records if c["position"] == "SPANS")
    traded = sum(1 for c in cluster_records if c["fate"] == "TRADED")
    touched = sum(1 for c in cluster_records if c["fate"] == "TOUCHED_NOT_TRADED")
    untouched = sum(1 for c in cluster_records if c["fate"] == "UNTOUCHED")
    return {
        "total": total,
        "above": above,
        "below": below,
        "spans": spans,
        "traded": traded,
        "touched": touched,
        "untouched": untouched,
    }


def format_landscape_block(ls: dict) -> str:
    return (
        f"\nCluster landscape (at 9:45)\n"
        f"  Total in pool:        {ls['total']}\n"
        f"  Above ORB close:      {ls['above']}  (fade SELL setups)\n"
        f"  Below ORB close:      {ls['below']}  (fade BUY setups)\n"
        f"  Spans close:          {ls['spans']}  (skip)\n"
        f"\nFate during 09:46-11:30\n"
        f"  Traded:               {ls['traded']}\n"
        f"  Touched, not traded:  {ls['touched']}\n"
        f"  Untouched:            {ls['untouched']}\n"
        f"\nY-axis zoomed to entry +/- {Y_HALF_RANGE:.0f} pts"
    )


def draw_one_trade(
    ax_chart,
    ax_text,
    trade: dict,
    chart_bars: pd.DataFrame,
    cluster_records: list[dict],
    compact: bool = False,
):
    if chart_bars.empty:
        ax_chart.text(0.5, 0.5, "no bars in window", ha="center", va="center")
        return

    # Draw cluster bands FIRST (background)
    draw_cluster_bands(ax_chart, cluster_records)

    # Candles on top
    draw_candles(ax_chart, chart_bars)

    sd = pd.Timestamp(trade["session_date"]).date()
    entry_price = float(trade["entry_price"])
    side = str(trade["side"]).lower()
    if side == "buy":
        stop_price = entry_price - STOP_POINTS
        target_price = entry_price + TARGET_POINTS
    else:
        stop_price = entry_price + STOP_POINTS
        target_price = entry_price - TARGET_POINTS

    x_min = date2num(chart_bars["ts_ny"].dt.tz_localize(None).iloc[0])
    x_max = date2num(chart_bars["ts_ny"].dt.tz_localize(None).iloc[-1])

    # Entry/stop/target lines
    ax_chart.axhline(entry_price, color="#222222", linewidth=1.4, zorder=4)
    ax_chart.axhline(target_price, color="#2a9d8f", linewidth=1.0, linestyle="--", zorder=4)
    ax_chart.axhline(stop_price, color="#e63946", linewidth=1.0, linestyle="--", zorder=4)

    # 9:45 and 11:30 vertical guides
    orb_close_t = pd.Timestamp.combine(sd, pd.Timestamp("09:45").time()).tz_localize(
        "America/New_York"
    )
    force_close_t = pd.Timestamp.combine(sd, pd.Timestamp("11:30").time()).tz_localize(
        "America/New_York"
    )
    ax_chart.axvline(
        date2num(orb_close_t.tz_localize(None)),
        color="gray",
        linestyle=":",
        linewidth=0.8,
        zorder=2,
    )
    ax_chart.axvline(
        date2num(force_close_t.tz_localize(None)),
        color="gray",
        linestyle=":",
        linewidth=0.8,
        zorder=2,
    )

    # Entry / exit markers
    entry_t = pd.Timestamp(trade["entry_time"]).tz_convert("America/New_York")
    exit_t = pd.Timestamp(trade["exit_time"]).tz_convert("America/New_York")
    marker = "^" if side == "buy" else "v"
    marker_size = 90 if not compact else 50
    ax_chart.scatter(
        date2num(entry_t.tz_localize(None)),
        entry_price,
        marker=marker,
        s=marker_size,
        color="#1d3557",
        edgecolors="white",
        linewidths=0.8,
        zorder=6,
    )
    pnl_d = float(trade["pnl_dollars"])
    exit_color = "#2a9d8f" if pnl_d > 0 else ("#e76f51" if pnl_d < 0 else "#777777")
    ax_chart.scatter(
        date2num(exit_t.tz_localize(None)),
        float(trade["exit_price"]),
        marker="o",
        s=marker_size,
        color=exit_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=6,
    )

    ax_chart.set_xlim(x_min, x_max)

    # Y-axis zoomed to entry ± 60
    ax_chart.set_ylim(entry_price - Y_HALF_RANGE, entry_price + Y_HALF_RANGE)

    ax_chart.xaxis_date()
    ax_chart.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    ax_chart.set_xlabel("NY time" if not compact else "", fontsize=9 if not compact else 7)
    ax_chart.set_ylabel("Price" if not compact else "", fontsize=9 if not compact else 7)
    ax_chart.grid(True, alpha=0.25, linewidth=0.4)
    ax_chart.tick_params(labelsize=8 if not compact else 6)

    # Text panel: main info, result, then landscape
    txt, result_block, result_color = format_text_panel(trade)
    fontsize = 9 if not compact else 6
    ax_text.set_axis_off()

    main_obj = ax_text.text(
        0.02,
        0.99,
        txt,
        family="monospace",
        fontsize=fontsize,
        va="top",
        ha="left",
        transform=ax_text.transAxes,
    )
    fig = ax_text.figure
    fig.canvas.draw()
    bbox = main_obj.get_window_extent()
    inv = ax_text.transAxes.inverted()
    y_after_main = inv.transform((bbox.x0, bbox.y0))[1]

    result_obj = ax_text.text(
        0.02,
        max(0.0, y_after_main - 0.015),
        result_block.lstrip("\n"),
        family="monospace",
        fontsize=fontsize,
        va="top",
        ha="left",
        color=result_color,
        transform=ax_text.transAxes,
        fontweight="bold",
    )
    fig.canvas.draw()
    bbox2 = result_obj.get_window_extent()
    y_after_result = inv.transform((bbox2.x0, bbox2.y0))[1]

    ls = landscape_summary(cluster_records)
    ax_text.text(
        0.02,
        max(0.0, y_after_result - 0.015),
        format_landscape_block(ls).lstrip("\n"),
        family="monospace",
        fontsize=fontsize,
        va="top",
        ha="left",
        transform=ax_text.transAxes,
    )


def make_individual(
    trade: dict, idx: int, chart_bars: pd.DataFrame, cluster_records: list[dict]
) -> Path:
    fig = plt.figure(figsize=(12, 5), dpi=120)
    gs = fig.add_gridspec(1, 2, width_ratios=[0.65, 0.35], wspace=0.05)
    ax_chart = fig.add_subplot(gs[0])
    ax_text = fig.add_subplot(gs[1])

    cat = trade["_category"]
    sd_str = pd.Timestamp(trade["session_date"]).strftime("%Y%m%d")
    fig.suptitle(f"Trade {idx} of 10 — {cat}  (with full 9:45 cluster pool)", fontsize=12, y=0.98)

    draw_one_trade(ax_chart, ax_text, trade, chart_bars, cluster_records, compact=False)

    safe_cat = cat.replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
    fname = OUT_DIR / f"trade_{idx:02d}_{sd_str}_{safe_cat}_with_clusters.png"
    fig.savefig(fname, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return fname


def make_contact_sheet(selected_with_data: list[tuple]) -> Path:
    fig = plt.figure(figsize=(20, 40), dpi=110)
    outer = fig.add_gridspec(5, 2, hspace=0.5, wspace=0.15)
    for i, (trade, chart_bars, cluster_records) in enumerate(selected_with_data):
        row = i // 2
        col = i % 2
        inner = outer[row, col].subgridspec(1, 2, width_ratios=[0.65, 0.35], wspace=0.05)
        ax_chart = fig.add_subplot(inner[0])
        ax_text = fig.add_subplot(inner[1])
        ax_chart.set_title(f"#{i + 1} — {trade['_category']}", fontsize=10)
        draw_one_trade(ax_chart, ax_text, trade, chart_bars, cluster_records, compact=True)
    fname = OUT_DIR / "contact_sheet_with_clusters.png"
    fig.savefig(fname, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return fname


def write_manifest(rows: list[dict]):
    lines = []
    lines.append("# V2 + 40/40 example trades (with 9:45 cluster pool) — manifest")
    lines.append("")
    lines.append("Date generated: 2026-05-15")
    lines.append(
        "Same 10 trades as `v2_4040_examples_20260515/`, now annotated with the full 9:45 cluster pool."
    )
    lines.append("")
    lines.append("**Cluster fate categories (legend in the figures):**")
    lines.append("- TRADED: purple, the cluster the simulator actually traded")
    lines.append(
        "- TOUCHED_NOT_TRADED: medium gray, near-border crossed by a bar's range during 09:46-11:30 but blocked by C2 or by classifier SKIP"
    )
    lines.append("- UNTOUCHED: faint gray, near-border never crossed during 09:46-11:30")
    lines.append("- SPANS_CLOSE: light amber, cluster spans the 9:45 ORB close — SKIP per D-003")
    lines.append("")
    lines.append(
        "Y-axis on every figure is zoomed to entry ± 60 points, so the cluster density near the trade is visible. Clusters outside that band exist but are not visualized."
    )
    lines.append("")
    lines.append(
        "| # | Date | Side | Label | Outcome | P&L | Total clusters | Above | Below | Spans | Touched-not-traded | Untouched | File |"
    )
    lines.append("|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        lines.append(
            f"| {r['idx']} | {r['date']} | {r['side']} | {r['label']} | {r['cat']} | "
            f"${r['pnl']:+,.0f} | {r['ls']['total']} | {r['ls']['above']} | {r['ls']['below']} | "
            f"{r['ls']['spans']} | {r['ls']['touched']} | {r['ls']['untouched']} | `{r['file']}` |"
        )
    lines.append("")
    lines.append("## Per-trade landscape notes")
    lines.append("")
    for r in rows:
        ls = r["ls"]
        lines.append(
            f"{r['idx']}. **{r['date']} ({r['cat']})** — "
            f"pool of {ls['total']} clusters at 9:45 "
            f"({ls['above']} above ORB close, {ls['below']} below, {ls['spans']} spanning). "
            f"During 09:46-11:30: 1 traded, {ls['touched']} touched-not-traded, {ls['untouched']} untouched."
        )
    (OUT_DIR / "manifest.md").write_text("\n".join(lines))


def save_cluster_csv(session_date, cluster_records: list[dict]):
    sd_str = pd.Timestamp(session_date).strftime("%Y%m%d")
    out = pd.DataFrame(cluster_records)
    out.to_csv(OUT_DIR / f"cluster_pool_{sd_str}.csv", index=False)


def main():
    trades = pd.read_parquet(TRADES_PARQUET)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)

    print(
        f"Loaded {len(trades)} V2+40/40 trades, {len(bars):,} bars, {len(orb_table)} ORB sessions"
    )
    selected = select_trades(trades)
    print(f"Re-selected {len(selected)} trades (same deterministic seed as prior script)")

    rows = []
    selected_with_data = []
    for idx, trade in enumerate(selected, start=1):
        sd = pd.Timestamp(trade["session_date"])
        chart_bars, trade_window_bars = session_window_bars(bars, sd)

        clusters, orb_close, orb_high, orb_low = reconstruct_cluster_pool(sd, orb_table)
        cluster_records = categorize_clusters(
            clusters,
            orb_close,
            traded_low=float(trade["cluster_low"]),
            traded_high=float(trade["cluster_high"]),
            win_bars=trade_window_bars,
        )
        save_cluster_csv(sd, cluster_records)

        # Sanity: there must be exactly 1 TRADED cluster
        traded_count = sum(1 for c in cluster_records if c["fate"] == "TRADED")
        if traded_count != 1:
            print(
                f"  warning: session {sd.date()} has {traded_count} TRADED clusters "
                f"(expected 1) — traded_low={trade['cluster_low']} traded_high={trade['cluster_high']}"
            )

        fname = make_individual(trade, idx, chart_bars, cluster_records)
        ls = landscape_summary(cluster_records)
        rows.append(
            {
                "idx": idx,
                "date": sd.strftime("%Y-%m-%d"),
                "side": str(trade["side"]).upper(),
                "label": trade["cluster_label"],
                "cat": trade["_category"],
                "pnl": float(trade["pnl_dollars"]),
                "ls": ls,
                "file": fname.name,
            }
        )
        selected_with_data.append((trade, chart_bars, cluster_records))
        print(
            f"  wrote {fname.name}  (clusters: total {ls['total']}, above {ls['above']}, "
            f"below {ls['below']}, spans {ls['spans']}, touched-NT {ls['touched']}, untouched {ls['untouched']})"
        )

    print("\nBuilding contact sheet...")
    cs = make_contact_sheet(selected_with_data)
    print(f"  wrote {cs.name}")

    write_manifest(rows)
    print("  wrote manifest.md")

    print("\n" + "=" * 100)
    print(
        f"{'#':>3} {'date':<11} {'cat':<18} {'total':>6} {'above':>6} {'below':>6} {'spans':>6} {'touched-NT':>11} {'untouched':>10}"
    )
    print("-" * 100)
    for r in rows:
        ls = r["ls"]
        print(
            f"{r['idx']:>3} {r['date']:<11} {r['cat']:<18} {ls['total']:>6} {ls['above']:>6} "
            f"{ls['below']:>6} {ls['spans']:>6} {ls['touched']:>11} {ls['untouched']:>10}"
        )

    print("\nOutput files:")
    for f in sorted(OUT_DIR.glob("*.png")):
        print(f"  {f.name}")
    for f in sorted(OUT_DIR.glob("*.csv")):
        print(f"  {f.name}")
    print("  manifest.md")


if __name__ == "__main__":
    sys.exit(main() or 0)
