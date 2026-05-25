"""Visualize one trading session: candlesticks, ORB window, cluster zones,
historical levels, trade entries/exits with stop/target lines.

Usage:
    python3 visualize_trade.py 2026-04-02
    python3 visualize_trade.py 2026-04-02 2026-04-08 ...

Or import plot_session(date_str) directly.
"""

import sys
from collections import deque
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from clusters import find_clusters
from paths import BARS_PARQUET, CHARTS_DIR, ORB_TABLE_PARQUET, TRADES_PARQUET, ensure_dirs

LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
STOP_POINTS = 30.0
TARGET_POINTS = 30.0

ORB_HM = (9, 30, 9, 45)  # ORB window 9:30-9:45 NY
TRADE_WIN_HM = (9, 46, 11, 30)  # Trading window 9:46-11:30 NY
PLOT_WIN_HM = (9, 0, 12, 0)  # Chart context 9:00-12:00 NY


def _build_clusters_for_day(orb_table: pd.DataFrame, session_date) -> tuple:
    """Replay the running level pool to recover today's clusters and ref price."""
    orb_table = orb_table.sort_values("session_date").reset_index(drop=True)
    level_pool: deque = deque(maxlen=LOOKBACK)
    today_row = None
    for orb_row in orb_table.itertuples():
        sd = pd.Timestamp(orb_row.session_date).date()
        if sd == session_date:
            today_row = orb_row
            break
        level_pool.append((float(orb_row.orb_high), float(orb_row.orb_low)))

    if today_row is None:
        return None, [], [], None

    levels = []
    for h, l in level_pool:
        levels.append(h)
        levels.append(l)
    levels.append(today_row.orb_high)
    levels.append(today_row.orb_low)
    clusters = find_clusters(levels, max_gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE)

    ref = float(today_row.orb_close)
    classified = []
    for c in clusters:
        if c.low > ref:
            side = "sell"
        elif c.high < ref:
            side = "buy"
        else:
            side = "skip"
        classified.append((c, side))
    return today_row, clusters, classified, ref


def _ny_time(date_obj, hh: int, mm: int) -> pd.Timestamp:
    return pd.Timestamp(f"{date_obj} {hh:02d}:{mm:02d}:00").tz_localize("America/New_York")


def _draw_candles(ax, day_bars: pd.DataFrame) -> None:
    times = day_bars["ts_ny"].dt.tz_localize(None)  # naive NY local for matplotlib
    times_num = mdates.date2num(times)
    bar_w = 1.0 / (24 * 60) * 0.8  # 80% of one minute
    up_color = "#26a69a"
    dn_color = "#ef5350"
    for i in range(len(day_bars)):
        b = day_bars.iloc[i]
        t = times_num[i]
        op = float(b["open"])
        cl = float(b["close"])
        hi = float(b["high"])
        lo = float(b["low"])
        col = up_color if cl >= op else dn_color
        ax.plot([t, t], [lo, hi], color=col, linewidth=0.6, alpha=0.7, solid_capstyle="butt")
        body_lo = min(op, cl)
        body_hi = max(op, cl)
        height = max(body_hi - body_lo, 0.05)
        rect = mpatches.Rectangle(
            (t - bar_w / 2, body_lo),
            bar_w,
            height,
            facecolor=col,
            edgecolor=col,
            linewidth=0.4,
            zorder=2,
        )
        ax.add_patch(rect)


def plot_session(session_date_input, save_dir: Path | None = None) -> Path | None:
    if isinstance(session_date_input, str):
        session_date = pd.Timestamp(session_date_input).date()
    else:
        session_date = pd.Timestamp(session_date_input).date()

    bars = pd.read_parquet(BARS_PARQUET)
    bars["ts_ny"] = pd.to_datetime(bars["ts_ny"], utc=False)
    bars["session_date"] = pd.to_datetime(bars["session_date"]).dt.date
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    orb_table["session_date"] = pd.to_datetime(orb_table["session_date"])
    trades = pd.read_parquet(TRADES_PARQUET)
    trades["session_date"] = pd.to_datetime(trades["session_date"]).dt.date
    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    trades["exit_time"] = pd.to_datetime(trades["exit_time"], utc=True)

    plot_start = _ny_time(session_date, PLOT_WIN_HM[0], PLOT_WIN_HM[1])
    plot_end = _ny_time(session_date, PLOT_WIN_HM[2], PLOT_WIN_HM[3])
    day_bars = (
        bars[
            (bars["session_date"] == session_date)
            & (bars["ts_ny"] >= plot_start)
            & (bars["ts_ny"] < plot_end)
        ]
        .sort_values("ts_ny")
        .reset_index(drop=True)
    )
    if day_bars.empty:
        print(f"  No bars for {session_date} — skipping")
        return None

    today_row, _all_clusters, classified, ref_close = _build_clusters_for_day(
        orb_table, session_date
    )
    if today_row is None:
        print(f"  No ORB row for {session_date} — skipping")
        return None

    day_trades = trades[trades["session_date"] == session_date].sort_values("entry_time")

    fig, ax = plt.subplots(figsize=(17, 10))
    _draw_candles(ax, day_bars)

    pmin = float(day_bars["low"].min())
    pmax = float(day_bars["high"].max())

    orb_start = _ny_time(session_date, ORB_HM[0], ORB_HM[1])
    orb_end = _ny_time(session_date, ORB_HM[2], ORB_HM[3])
    win_start = _ny_time(session_date, TRADE_WIN_HM[0], TRADE_WIN_HM[1])
    win_end = _ny_time(session_date, TRADE_WIN_HM[2], TRADE_WIN_HM[3])
    ax.axvspan(
        mdates.date2num(orb_start.tz_localize(None)),
        mdates.date2num(orb_end.tz_localize(None)),
        color="#fff176",
        alpha=0.30,
        zorder=0,
    )
    ax.axvspan(
        mdates.date2num(win_start.tz_localize(None)),
        mdates.date2num(win_end.tz_localize(None)),
        color="#bdbdbd",
        alpha=0.10,
        zorder=0,
    )

    orb_high = float(today_row.orb_high)
    orb_low = float(today_row.orb_low)
    ax.axhline(
        orb_high,
        color="#1565c0",
        linestyle="--",
        linewidth=1.4,
        alpha=0.85,
        zorder=3,
        label=f"ORB high {orb_high:.2f}",
    )
    ax.axhline(
        orb_low,
        color="#1565c0",
        linestyle="--",
        linewidth=1.4,
        alpha=0.85,
        zorder=3,
        label=f"ORB low  {orb_low:.2f}",
    )
    ax.axhline(
        ref_close,
        color="#6a1b9a",
        linestyle=":",
        linewidth=1.0,
        alpha=0.85,
        zorder=3,
        label=f"ORB close (ref) {ref_close:.2f}",
    )

    plot_pad = (pmax - pmin) * 0.05 if pmax > pmin else 5.0
    visible_pmin = pmin - plot_pad
    visible_pmax = pmax + plot_pad

    side_styles = {
        "buy": {"line": "#2e7d32", "face": (0.27, 0.63, 0.28, 0.18)},
        "sell": {"line": "#c62828", "face": (0.78, 0.16, 0.16, 0.18)},
        "skip": {"line": "#616161", "face": (0.62, 0.62, 0.62, 0.15)},
    }

    annot_x = mdates.date2num(plot_end.tz_localize(None))
    plotted_levels = set()
    for c, side in classified:
        if c.high < visible_pmin or c.low > visible_pmax:
            continue
        st = side_styles[side]
        ax.axhspan(c.low, c.high, color=st["face"], zorder=1)
        for lvl in c.levels:
            if lvl in plotted_levels:
                continue
            plotted_levels.add(lvl)
            ax.axhline(lvl, color=st["line"], linewidth=0.5, alpha=0.45, zorder=2)
        mid = (c.low + c.high) / 2
        ax.annotate(
            f"{side.upper()} cluster\n{c.low:.2f}–{c.high:.2f}\nsize={c.size}",
            xy=(annot_x, mid),
            xycoords="data",
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=7,
            ha="left",
            va="center",
            color=st["line"],
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=st["line"], alpha=0.85),
            zorder=6,
        )

    if not day_trades.empty:
        for _, t in day_trades.iterrows():
            side = t["side"]
            ep = float(t["entry_price"])
            et = pd.Timestamp(t["entry_time"]).tz_convert("America/New_York").tz_localize(None)
            xt = pd.Timestamp(t["exit_time"]).tz_convert("America/New_York").tz_localize(None)
            et_n = mdates.date2num(et)
            xt_n = mdates.date2num(xt)
            xp = float(t["exit_price"])

            if side == "buy":
                stop = ep - STOP_POINTS
                target = ep + TARGET_POINTS
                arrow_marker = "^"
                arrow_color = "#1b5e20"
                lbl_dy = 30
            else:
                stop = ep + STOP_POINTS
                target = ep - TARGET_POINTS
                arrow_marker = "v"
                arrow_color = "#b71c1c"
                lbl_dy = -45

            ax.scatter(
                [et_n],
                [ep],
                marker=arrow_marker,
                s=220,
                color=arrow_color,
                edgecolor="black",
                linewidth=1.0,
                zorder=7,
            )

            er = t["exit_reason"]
            exit_color = {"target": "#2e7d32", "stop": "#c62828", "force_close": "#f9a825"}.get(
                er, "#424242"
            )
            ax.scatter(
                [xt_n],
                [xp],
                marker="X",
                s=200,
                color=exit_color,
                edgecolor="black",
                linewidth=1.0,
                zorder=7,
            )

            ax.plot(
                [et_n, xt_n],
                [stop, stop],
                color="#c62828",
                linewidth=1.4,
                linestyle="-",
                alpha=0.7,
                zorder=4,
            )
            ax.plot(
                [et_n, xt_n],
                [target, target],
                color="#2e7d32",
                linewidth=1.4,
                linestyle="-",
                alpha=0.7,
                zorder=4,
            )
            ax.plot(
                [et_n, xt_n],
                [ep, xp],
                color="black",
                linewidth=0.7,
                linestyle=":",
                alpha=0.5,
                zorder=4,
            )

            label = (
                f"{side.upper()} @ {ep:.2f}\n"
                f"S {stop:.2f}  T {target:.2f}\n"
                f"{er}: {t['pnl_points']:+.1f}pt (${t['pnl_dollars']:+.0f})"
            )
            ax.annotate(
                label,
                xy=(et_n, ep),
                xytext=(0, lbl_dy),
                textcoords="offset points",
                fontsize=7,
                ha="center",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=arrow_color, alpha=0.92),
                zorder=8,
            )

    ax.set_ylim(visible_pmin, visible_pmax)
    ax.set_xlim(
        mdates.date2num(plot_start.tz_localize(None)),
        mdates.date2num(plot_end.tz_localize(None)),
    )
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 15, 30, 45]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_xlabel("Time (NY local)")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.25)

    n_trades = len(day_trades)
    if n_trades:
        pnl_pts = float(day_trades["pnl_points"].sum())
        pnl_usd = float(day_trades["pnl_dollars"].sum())
        title = (
            f"{session_date}  |  {n_trades} trade(s)  |  "
            f"{pnl_pts:+.2f} pts  (${pnl_usd:+,.2f})  |  "
            f"contract: {day_bars['contract'].iloc[0]}"
        )
    else:
        title = f"{session_date}  |  no trades  |  contract: {day_bars['contract'].iloc[0]}"
    ax.set_title(title, fontsize=13, fontweight="bold")

    legend_handles = [
        mpatches.Patch(color="#fff176", alpha=0.6, label="ORB window (9:30–9:45)"),
        mpatches.Patch(color="#bdbdbd", alpha=0.5, label="Trading window (9:46–11:30)"),
        plt.Line2D([0], [0], color="#1565c0", linestyle="--", label="ORB high/low"),
        plt.Line2D([0], [0], color="#6a1b9a", linestyle=":", label="ORB close (ref)"),
        mpatches.Patch(color=side_styles["buy"]["line"], alpha=0.4, label="BUY cluster zone"),
        mpatches.Patch(color=side_styles["sell"]["line"], alpha=0.4, label="SELL cluster zone"),
        mpatches.Patch(color=side_styles["skip"]["line"], alpha=0.4, label="Skipped (spans ref)"),
        plt.Line2D([0], [0], color="#2e7d32", linewidth=1.4, label="Target line"),
        plt.Line2D([0], [0], color="#c62828", linewidth=1.4, label="Stop line"),
        plt.Line2D(
            [0],
            [0],
            marker="^",
            color="w",
            markerfacecolor="#1b5e20",
            markeredgecolor="black",
            label="Buy entry",
            linestyle="None",
            markersize=10,
        ),
        plt.Line2D(
            [0],
            [0],
            marker="v",
            color="w",
            markerfacecolor="#b71c1c",
            markeredgecolor="black",
            label="Sell entry",
            linestyle="None",
            markersize=10,
        ),
        plt.Line2D(
            [0],
            [0],
            marker="X",
            color="w",
            markerfacecolor="#424242",
            markeredgecolor="black",
            label="Exit",
            linestyle="None",
            markersize=10,
        ),
    ]
    ax.legend(handles=legend_handles, loc="upper left", fontsize=8, framealpha=0.92, ncol=2)

    plt.tight_layout()
    save_dir = save_dir or CHARTS_DIR
    save_path = save_dir / f"trade_chart_{session_date}.png"
    plt.savefig(save_path, dpi=120)
    plt.close(fig)
    return save_path


def plot_session_clean(session_date_input, save_path: Path | None = None) -> Path | None:
    """Stripped-down chart: candles + ORB context + clusters only.

    No trade markers, no trade annotations, no stop/target lines, no in-plot legend.
    """
    if isinstance(session_date_input, str):
        session_date = pd.Timestamp(session_date_input).date()
    else:
        session_date = pd.Timestamp(session_date_input).date()

    bars = pd.read_parquet(BARS_PARQUET)
    bars["ts_ny"] = pd.to_datetime(bars["ts_ny"], utc=False)
    bars["session_date"] = pd.to_datetime(bars["session_date"]).dt.date
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    orb_table["session_date"] = pd.to_datetime(orb_table["session_date"])

    plot_start = _ny_time(session_date, PLOT_WIN_HM[0], PLOT_WIN_HM[1])
    plot_end = _ny_time(session_date, PLOT_WIN_HM[2], PLOT_WIN_HM[3])
    day_bars = (
        bars[
            (bars["session_date"] == session_date)
            & (bars["ts_ny"] >= plot_start)
            & (bars["ts_ny"] < plot_end)
        ]
        .sort_values("ts_ny")
        .reset_index(drop=True)
    )
    if day_bars.empty:
        print(f"  No bars for {session_date} — skipping")
        return None

    today_row, _all_clusters, classified, ref_close = _build_clusters_for_day(
        orb_table, session_date
    )
    if today_row is None:
        print(f"  No ORB row for {session_date} — skipping")
        return None

    fig, ax = plt.subplots(figsize=(17, 10))
    _draw_candles(ax, day_bars)

    pmin = float(day_bars["low"].min())
    pmax = float(day_bars["high"].max())

    orb_start = _ny_time(session_date, ORB_HM[0], ORB_HM[1])
    orb_end = _ny_time(session_date, ORB_HM[2], ORB_HM[3])
    win_start = _ny_time(session_date, TRADE_WIN_HM[0], TRADE_WIN_HM[1])
    win_end = _ny_time(session_date, TRADE_WIN_HM[2], TRADE_WIN_HM[3])
    ax.axvspan(
        mdates.date2num(orb_start.tz_localize(None)),
        mdates.date2num(orb_end.tz_localize(None)),
        color="#fff176",
        alpha=0.30,
        zorder=0,
    )
    ax.axvspan(
        mdates.date2num(win_start.tz_localize(None)),
        mdates.date2num(win_end.tz_localize(None)),
        color="#bdbdbd",
        alpha=0.10,
        zorder=0,
    )

    orb_high = float(today_row.orb_high)
    orb_low = float(today_row.orb_low)
    ax.axhline(orb_high, color="#1565c0", linestyle="--", linewidth=1.4, alpha=0.85, zorder=3)
    ax.axhline(orb_low, color="#1565c0", linestyle="--", linewidth=1.4, alpha=0.85, zorder=3)
    ax.axhline(ref_close, color="#6a1b9a", linestyle=":", linewidth=1.0, alpha=0.85, zorder=3)

    plot_pad = (pmax - pmin) * 0.05 if pmax > pmin else 5.0
    visible_pmin = pmin - plot_pad
    visible_pmax = pmax + plot_pad

    side_styles = {
        "buy": {"line": "#2e7d32", "face": (0.27, 0.63, 0.28, 0.18)},
        "sell": {"line": "#c62828", "face": (0.78, 0.16, 0.16, 0.18)},
        "skip": {"line": "#616161", "face": (0.62, 0.62, 0.62, 0.15)},
    }

    annot_x = mdates.date2num(plot_end.tz_localize(None))
    for c, side in classified:
        if c.high < visible_pmin or c.low > visible_pmax:
            continue
        st = side_styles[side]
        ax.axhspan(c.low, c.high, color=st["face"], zorder=1)
        mid = (c.low + c.high) / 2
        ax.annotate(
            f"{c.low:.2f}–{c.high:.2f}\nsize={c.size}",
            xy=(annot_x, mid),
            xycoords="data",
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=8,
            ha="left",
            va="center",
            color=st["line"],
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=st["line"], alpha=0.85),
            zorder=6,
        )

    ax.set_ylim(visible_pmin, visible_pmax)
    ax.set_xlim(
        mdates.date2num(plot_start.tz_localize(None)),
        mdates.date2num(plot_end.tz_localize(None)),
    )
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 15, 30, 45]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_xlabel("Time (NY local)")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.25)

    title = f"{session_date}  —  {day_bars['contract'].iloc[0]}"
    ax.set_title(title, fontsize=13, fontweight="bold")

    plt.tight_layout()
    if save_path is None:
        save_path = CHARTS_DIR / f"clean_chart_{session_date}.png"
    plt.savefig(save_path, dpi=120)
    plt.close(fig)
    return save_path


def main(argv: list[str]) -> None:
    ensure_dirs()
    if len(argv) < 2:
        print("usage: visualize_trade.py YYYY-MM-DD [YYYY-MM-DD ...]")
        sys.exit(1)
    for date_arg in argv[1:]:
        path = plot_session(date_arg)
        if path:
            print(f"Saved: {path}")


if __name__ == "__main__":
    main(sys.argv)
