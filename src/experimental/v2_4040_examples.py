"""Generate 10 day-by-day candle visualizations of V2 + 40/40 trades.

Output: results/archive/v2_4040_examples_20260515/
  trade_NN_YYYYMMDD_<outcome>.png   (10 individual figures)
  contact_sheet.png                 (5x2 grid)
  manifest.md                       (tabular summary)

No modifications to protected files. Pure read-only against trades parquet
and bars parquet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from paths import ARCHIVE_DIR, BARS_PARQUET

TRADES_PARQUET = ARCHIVE_DIR / "strategy_report_20260512" / "trades_v2_4040.parquet"
OUT_DIR = ARCHIVE_DIR / "v2_4040_examples_20260515"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STOP_POINTS = 40.0
TARGET_POINTS = 40.0


def select_trades(trades: pd.DataFrame) -> list[dict]:
    """Return 10 selected trades with outcome category label."""
    trades = trades.copy()
    trades["session_date"] = pd.to_datetime(trades["session_date"])
    trades["year"] = trades["session_date"].dt.year
    trades = trades.sort_values("session_date").reset_index(drop=True)

    recent = trades[trades["year"] >= 2024]
    rng = np.random.default_rng(20260515)

    def pick(df, n=2):
        if len(df) == 0:
            return []
        idx = rng.choice(len(df), size=min(n, len(df)), replace=False)
        return df.iloc[sorted(idx)].to_dict("records")

    fade_wins = recent[(recent["cluster_label"] == "FADE") & (recent["exit_reason"] == "target")]
    trend_wins = recent[(recent["cluster_label"] == "TREND") & (recent["exit_reason"] == "target")]
    fade_losses = recent[(recent["cluster_label"] == "FADE") & (recent["exit_reason"] == "stop")]
    trend_losses = recent[(recent["cluster_label"] == "TREND") & (recent["exit_reason"] == "stop")]
    fc_pos = recent[(recent["exit_reason"] == "force_close") & (recent["pnl_dollars"] > 0)]
    fc_neg = recent[(recent["exit_reason"] == "force_close") & (recent["pnl_dollars"] < 0)]

    out = []
    for cat, df, n in [
        ("FADE win", fade_wins, 2),
        ("TREND win", trend_wins, 2),
        ("FADE loss", fade_losses, 2),
        ("TREND loss", trend_losses, 2),
    ]:
        picks = pick(df, n)
        for p in picks:
            p["_category"] = cat
            out.append(p)
        if len(picks) < n:
            print(
                f"  warning: only {len(picks)} found for {cat} in 2024-2026; "
                f"would substitute but bucket still has slots"
            )

    # Force-closes: one positive, one negative
    for cat, df, n in [("force-close win", fc_pos, 1), ("force-close loss", fc_neg, 1)]:
        picks = pick(df, n)
        for p in picks:
            p["_category"] = cat
            out.append(p)
        if len(picks) < n:
            print(f"  warning: only {len(picks)} found for {cat} in 2024-2026")

    # Fill any gaps from earlier years if needed
    while len(out) < 10:
        leftover = trades[~trades["entry_time"].isin([t["entry_time"] for t in out])]
        p = leftover.iloc[rng.integers(len(leftover))].to_dict()
        p["_category"] = "substitute"
        out.append(p)

    return out[:10]


def session_bars(bars: pd.DataFrame, session_date) -> pd.DataFrame:
    sd = pd.Timestamp(session_date)
    day = bars[bars["session_date"].astype("datetime64[ns]") == sd]
    return day.copy()


def draw_candles(ax, day_bars: pd.DataFrame):
    """Draw OHLC candles. x = matplotlib date numbers from ts_ny."""
    from matplotlib.dates import date2num

    ts_naive = day_bars["ts_ny"].dt.tz_localize(None)
    xs = date2num(ts_naive)

    width_minutes = 0.6 / (24 * 60)  # 60% of a minute in matplotlib date units

    for i, (x, row) in enumerate(zip(xs, day_bars.itertuples())):
        o = float(row.open)
        c = float(row.close)
        h = float(row.high)
        l = float(row.low)
        up = c >= o
        body_color = "#2a9d8f" if up else "#e76f51"
        edge_color = body_color
        # Wick
        ax.plot([x, x], [l, h], color=edge_color, linewidth=0.6, zorder=2)
        # Body
        body_low = min(o, c)
        body_height = max(abs(c - o), 1e-9)
        ax.add_patch(
            Rectangle(
                (x - width_minutes / 2, body_low),
                width_minutes,
                body_height,
                facecolor=body_color,
                edgecolor=edge_color,
                linewidth=0.4,
                zorder=3,
            )
        )


def format_text_panel(trade: dict) -> tuple[str, str]:
    """Return (body_text, result_color)."""
    side = str(trade["side"]).upper()
    direction = "BUY (long)" if side == "BUY" else "SELL (short)"
    label = trade["cluster_label"]
    cluster_low = float(trade["cluster_low"])
    cluster_high = float(trade["cluster_high"])
    cluster_width = cluster_high - cluster_low
    cluster_size = int(trade["cluster_size"])

    entry_price = float(trade["entry_price"])
    if side == "BUY":
        stop_price = entry_price - STOP_POINTS
        target_price = entry_price + TARGET_POINTS
        stop_dlt = "-40"
        target_dlt = "+40"
    else:
        stop_price = entry_price + STOP_POINTS
        target_price = entry_price - TARGET_POINTS
        stop_dlt = "+40"
        target_dlt = "-40"

    entry_time = pd.Timestamp(trade["entry_time"]).tz_convert("America/New_York")
    exit_time = pd.Timestamp(trade["exit_time"]).tz_convert("America/New_York")

    reason_map = {
        "target": "target hit",
        "stop": "stop hit",
        "force_close": "force close (11:30)",
    }
    reason = reason_map.get(trade["exit_reason"], trade["exit_reason"])

    pnl_pts = float(trade["pnl_points"])
    pnl_usd = float(trade["pnl_dollars"])
    sign = "+" if pnl_pts >= 0 else ""
    result_color = "#2a9d8f" if pnl_usd > 0 else ("#e76f51" if pnl_usd < 0 else "#888888")

    sd = pd.Timestamp(trade["session_date"]).strftime("%Y-%m-%d")

    txt = (
        f"Date:         {sd}\n"
        f"Direction:    {direction}\n"
        f"Classifier:   {label}\n"
        f"\n"
        f"Cluster\n"
        f"  low:        {cluster_low:.2f}\n"
        f"  high:       {cluster_high:.2f}\n"
        f"  width:      {cluster_width:.2f} pts\n"
        f"  size:       {cluster_size} levels\n"
        f"\n"
        f"Entry:        {entry_price:.2f}  @ {entry_time.strftime('%H:%M')}\n"
        f"Target:       {target_price:.2f}  ({target_dlt})\n"
        f"Stop:         {stop_price:.2f}  ({stop_dlt})\n"
        f"\n"
        f"Exit:         {float(trade['exit_price']):.2f}  @ {exit_time.strftime('%H:%M')}\n"
        f"Reason:       {reason}\n"
    )
    result_block = f"\nResult:       {sign}{pnl_pts:.0f} pts\n              {sign}${pnl_usd:.0f}"

    return txt, result_block, result_color


def draw_one_trade(ax_chart, ax_text, trade: dict, day_bars: pd.DataFrame, compact: bool = False):
    """Draw left=candle, right=text. If compact, reduce font/marker sizes."""
    from matplotlib.dates import DateFormatter, date2num

    sd = pd.Timestamp(trade["session_date"]).date()
    win_start = pd.Timestamp.combine(sd, pd.Timestamp("09:00").time()).tz_localize(
        "America/New_York"
    )
    win_end = pd.Timestamp.combine(sd, pd.Timestamp("11:45").time()).tz_localize("America/New_York")

    mask = (day_bars["ts_ny"] >= win_start) & (day_bars["ts_ny"] <= win_end)
    win = day_bars[mask].sort_values("ts_ny").reset_index(drop=True)
    if win.empty:
        ax_chart.text(0.5, 0.5, "no bars in window", ha="center", va="center")
        return

    draw_candles(ax_chart, win)

    cluster_low = float(trade["cluster_low"])
    cluster_high = float(trade["cluster_high"])
    entry_price = float(trade["entry_price"])
    side = str(trade["side"]).lower()
    if side == "buy":
        stop_price = entry_price - STOP_POINTS
        target_price = entry_price + TARGET_POINTS
    else:
        stop_price = entry_price + STOP_POINTS
        target_price = entry_price - TARGET_POINTS

    # x range based on win
    x_min = date2num(win["ts_ny"].dt.tz_localize(None).iloc[0])
    x_max = date2num(win["ts_ny"].dt.tz_localize(None).iloc[-1])

    # Cluster band
    ax_chart.axhspan(cluster_low, cluster_high, facecolor="#6a4c93", alpha=0.15, zorder=1)

    # Entry/stop/target horizontal lines
    ax_chart.axhline(entry_price, color="#222222", linewidth=1.4, zorder=4)
    ax_chart.axhline(target_price, color="#2a9d8f", linewidth=1.0, linestyle="--", zorder=4)
    ax_chart.axhline(stop_price, color="#e63946", linewidth=1.0, linestyle="--", zorder=4)

    # 9:45 and 11:30 vertical dotted lines
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

    # y-range — include all bar extremes + entry/stop/target with padding
    lo = min(float(win["low"].min()), stop_price, target_price, cluster_low) - 4
    hi = max(float(win["high"].max()), stop_price, target_price, cluster_high) + 4
    ax_chart.set_ylim(lo, hi)

    ax_chart.xaxis_date()
    ax_chart.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    ax_chart.set_xlabel("NY time" if not compact else "", fontsize=9 if not compact else 7)
    ax_chart.set_ylabel("Price" if not compact else "", fontsize=9 if not compact else 7)
    ax_chart.grid(True, alpha=0.25, linewidth=0.4)
    ax_chart.tick_params(labelsize=8 if not compact else 6)

    # Text panel
    txt, result_block, result_color = format_text_panel(trade)
    fontsize = 10 if not compact else 7
    ax_text.set_axis_off()
    main_obj = ax_text.text(
        0.02,
        0.98,
        txt,
        family="monospace",
        fontsize=fontsize,
        va="top",
        ha="left",
        transform=ax_text.transAxes,
    )
    # Use canvas to measure bounding box, then place result text just below
    fig = ax_text.figure
    fig.canvas.draw()
    bbox = main_obj.get_window_extent()
    inv = ax_text.transAxes.inverted()
    y_bottom_axes = inv.transform((bbox.x0, bbox.y0))[1]
    ax_text.text(
        0.02,
        max(0.0, y_bottom_axes - 0.02),
        result_block.lstrip("\n"),
        family="monospace",
        fontsize=fontsize,
        va="top",
        ha="left",
        color=result_color,
        transform=ax_text.transAxes,
        fontweight="bold",
    )


def make_individual(trade: dict, idx: int, day_bars: pd.DataFrame) -> Path:
    fig = plt.figure(figsize=(12, 5), dpi=120)
    gs = fig.add_gridspec(1, 2, width_ratios=[0.65, 0.35], wspace=0.05)
    ax_chart = fig.add_subplot(gs[0])
    ax_text = fig.add_subplot(gs[1])

    cat = trade["_category"]
    sd_str = pd.Timestamp(trade["session_date"]).strftime("%Y%m%d")
    fig.suptitle(f"Trade {idx} of 10 — {cat}", fontsize=13, y=0.98)

    draw_one_trade(ax_chart, ax_text, trade, day_bars, compact=False)

    safe_cat = cat.replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
    fname = OUT_DIR / f"trade_{idx:02d}_{sd_str}_{safe_cat}.png"
    fig.savefig(fname, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return fname


def make_contact_sheet(selected: list[dict], bars: pd.DataFrame) -> Path:
    fig = plt.figure(figsize=(20, 40), dpi=110)
    outer = fig.add_gridspec(5, 2, hspace=0.5, wspace=0.15)

    for i, trade in enumerate(selected):
        row = i // 2
        col = i % 2
        inner = outer[row, col].subgridspec(1, 2, width_ratios=[0.65, 0.35], wspace=0.05)
        ax_chart = fig.add_subplot(inner[0])
        ax_text = fig.add_subplot(inner[1])

        ax_chart.set_title(f"#{i + 1} — {trade['_category']}", fontsize=10)

        day_bars = session_bars(bars, trade["session_date"])
        draw_one_trade(ax_chart, ax_text, trade, day_bars, compact=True)

    fname = OUT_DIR / "contact_sheet.png"
    fig.savefig(fname, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return fname


def trade_note(trade: dict, day_bars: pd.DataFrame) -> str:
    """One-line distinctive description."""
    entry_t = pd.Timestamp(trade["entry_time"]).tz_convert("America/New_York")
    exit_t = pd.Timestamp(trade["exit_time"]).tz_convert("America/New_York")
    minutes = (exit_t - entry_t).total_seconds() / 60.0
    reason = trade["exit_reason"]
    side = trade["side"]
    pnl = float(trade["pnl_dollars"])

    if reason == "target":
        if minutes <= 5:
            return f"fast target hit ({minutes:.0f} min after entry)"
        elif minutes <= 20:
            return f"target hit in {minutes:.0f} minutes"
        else:
            return f"target hit after {minutes:.0f} minutes of consolidation"
    if reason == "stop":
        if minutes <= 5:
            return f"stopped within {minutes:.0f} minutes of entry"
        elif minutes <= 20:
            return f"reversed against entry, stopped after {minutes:.0f} min"
        else:
            return f"slow-grind stop after {minutes:.0f} minutes"
    if reason == "force_close":
        if pnl > 0:
            return (
                f"held through 11:30 force-close, small winner ({pnl:+.0f}$ over {minutes:.0f} min)"
            )
        elif pnl < 0:
            return f"ranged sideways until force-close, loser ({pnl:+.0f}$ over {minutes:.0f} min)"
        else:
            return f"force-close at break-even after {minutes:.0f} min"
    return f"{reason} after {minutes:.0f} min"


def write_manifest(selected: list[dict], filenames: list[Path], bars: pd.DataFrame):
    lines = []
    lines.append("# V2 + 40/40 example trades — manifest")
    lines.append("")
    lines.append("Date generated: 2026-05-15")
    lines.append(
        "Source: `results/archive/strategy_report_20260512/trades_v2_4040.parquet` (908 trades)"
    )
    lines.append(
        "Selection: 2 each of FADE win / TREND win / FADE loss / TREND loss, plus 2 force-close (one +, one −). Preferred 2024-2026."
    )
    lines.append("")
    lines.append("| # | Date | Side | Label | Outcome | P&L | File |")
    lines.append("|---:|---|---|---|---|---:|---|")
    for i, (trade, fn) in enumerate(zip(selected, filenames), start=1):
        sd = pd.Timestamp(trade["session_date"]).strftime("%Y-%m-%d")
        side = str(trade["side"]).upper()
        label = trade["cluster_label"]
        cat = trade["_category"]
        pnl = float(trade["pnl_dollars"])
        lines.append(f"| {i} | {sd} | {side} | {label} | {cat} | ${pnl:+,.0f} | `{fn.name}` |")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for i, trade in enumerate(selected, start=1):
        day_bars = session_bars(bars, trade["session_date"])
        note = trade_note(trade, day_bars)
        sd = pd.Timestamp(trade["session_date"]).strftime("%Y-%m-%d")
        lines.append(f"{i}. **{sd} ({trade['_category']})** — {note}")
    (OUT_DIR / "manifest.md").write_text("\n".join(lines))


def main():
    trades = pd.read_parquet(TRADES_PARQUET)
    bars = pd.read_parquet(BARS_PARQUET)

    print(f"Loaded {len(trades)} V2+40/40 trades, {len(bars):,} bars")
    selected = select_trades(trades)

    print(f"\nSelected {len(selected)} trades:")
    print(
        f"  {'#':>2}  {'date':<10}  {'side':<5}  {'lbl':<6}  {'entry':>10}  {'exit':>10}  {'reason':<12}  {'P&L':>8}"
    )
    for i, t in enumerate(selected, start=1):
        sd = pd.Timestamp(t["session_date"]).strftime("%Y-%m-%d")
        print(
            f"  {i:>2}  {sd:<10}  {t['side']:<5}  {t['cluster_label']:<6}  "
            f"{float(t['entry_price']):>10.2f}  {float(t['exit_price']):>10.2f}  "
            f"{t['exit_reason']:<12}  {float(t['pnl_dollars']):>+8.0f}  [{t['_category']}]"
        )

    filenames = []
    for i, trade in enumerate(selected, start=1):
        day_bars = session_bars(bars, trade["session_date"])
        fn = make_individual(trade, i, day_bars)
        filenames.append(fn)
        print(f"  wrote {fn.name}")

    print("\nBuilding contact sheet (5x2 grid, 20x40 inches)...")
    cs = make_contact_sheet(selected, bars)
    print(f"  wrote {cs.name}")

    write_manifest(selected, filenames, bars)
    print("  wrote manifest.md")

    print("\n--- manifest.md ---")
    print((OUT_DIR / "manifest.md").read_text())

    print("\n--- PNG files ---")
    for f in sorted(OUT_DIR.glob("*.png")):
        print(f"  {f.name}")


if __name__ == "__main__":
    sys.exit(main() or 0)
