"""Single-trade visualizer for the 40/40 hybrid variant (results/archive/trades_hybrid_4040_20260511.parquet).

Reads a JSON list of selected trades (each with session_date, entry_time_utc, entry_price,
exit_time_utc, exit_price, exit_reason, side, regime, pnl_dollars, cluster_low/high/size)
and writes one PNG per trade with:
  - 1-min candlesticks 8:00–12:30 NY
  - ORB 9:30–9:45 window and trading 9:46–11:30 window background
  - ORB high/low + ORB close (reference) horizontal lines
  - All session's cluster levels as dim dashed lines; the triggering cluster emphasized
  - 40-pt stop and 40-pt target horizontal lines
  - Entry/exit markers
  - Footer: Panama-adjusted-prices note

Sibling of src/visualize_trade.py; original is untouched.
"""

from collections import deque
import json
from pathlib import Path
import sys

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

from clusters import find_clusters
from paths import BARS_PARQUET, ORB_TABLE_PARQUET, PROJECT_ROOT, ensure_dirs

LOOKBACK = 200
CLUSTER_GAP = 3.0
MIN_CLUSTER_SIZE = 3
STOP_POINTS = 40.0
TARGET_POINTS = 40.0

ORB_HM = (9, 30, 9, 45)
TRADE_WIN_HM = (9, 46, 11, 30)
PLOT_WIN_HM = (8, 0, 12, 30)


def _ny_time(date_obj, hh: int, mm: int) -> pd.Timestamp:
    return pd.Timestamp(f"{date_obj} {hh:02d}:{mm:02d}:00").tz_localize("America/New_York")


def _build_clusters_for_day(orb_table: pd.DataFrame, session_date):
    orb_table = orb_table.sort_values("session_date").reset_index(drop=True)
    pool: deque = deque(maxlen=LOOKBACK)
    today_row = None
    for r in orb_table.itertuples():
        sd = pd.Timestamp(r.session_date).date()
        if sd == session_date:
            today_row = r
            break
        pool.append((float(r.orb_high), float(r.orb_low)))
    if today_row is None:
        return None, [], None
    levels = []
    for h, l in pool:
        levels.append(h); levels.append(l)
    levels.append(today_row.orb_high); levels.append(today_row.orb_low)
    clusters = find_clusters(levels, max_gap=CLUSTER_GAP, min_size=MIN_CLUSTER_SIZE)
    ref = float(today_row.orb_close)
    classified = []
    for c in clusters:
        if c.low > ref: side = "sell"
        elif c.high < ref: side = "buy"
        else: side = "skip"
        classified.append((c, side))
    return today_row, classified, ref


def _draw_candles(ax, day_bars: pd.DataFrame) -> None:
    times = day_bars["ts_ny"].dt.tz_localize(None)
    times_num = mdates.date2num(times)
    bar_w = 1.0 / (24 * 60) * 0.8
    up_color = "#26a69a"; dn_color = "#ef5350"
    for i in range(len(day_bars)):
        b = day_bars.iloc[i]
        t = times_num[i]
        op = float(b["open"]); cl = float(b["close"])
        hi = float(b["high"]); lo = float(b["low"])
        col = up_color if cl >= op else dn_color
        ax.plot([t, t], [lo, hi], color=col, linewidth=0.6, alpha=0.7, solid_capstyle="butt")
        body_lo = min(op, cl); body_hi = max(op, cl)
        height = max(body_hi - body_lo, 0.05)
        rect = mpatches.Rectangle(
            (t - bar_w / 2, body_lo), bar_w, height,
            facecolor=col, edgecolor=col, linewidth=0.4, zorder=2,
        )
        ax.add_patch(rect)


def plot_trade(trade: dict, bars: pd.DataFrame, orb_table: pd.DataFrame, save_path: Path) -> Path | None:
    session_date = pd.Timestamp(trade["session_date"]).date()

    plot_start = _ny_time(session_date, PLOT_WIN_HM[0], PLOT_WIN_HM[1])
    plot_end   = _ny_time(session_date, PLOT_WIN_HM[2], PLOT_WIN_HM[3])
    day_bars = bars[
        (bars["session_date"] == session_date)
        & (bars["ts_ny"] >= plot_start)
        & (bars["ts_ny"] < plot_end)
    ].sort_values("ts_ny").reset_index(drop=True)
    if day_bars.empty:
        print(f"  No bars for {session_date} — skipping")
        return None

    today_row, classified, ref_close = _build_clusters_for_day(orb_table, session_date)
    if today_row is None:
        print(f"  No ORB row for {session_date} — skipping")
        return None

    fig, ax = plt.subplots(figsize=(17, 10))
    _draw_candles(ax, day_bars)

    pmin = float(day_bars["low"].min())
    pmax = float(day_bars["high"].max())

    # window backgrounds
    orb_start = _ny_time(session_date, ORB_HM[0], ORB_HM[1])
    orb_end   = _ny_time(session_date, ORB_HM[2], ORB_HM[3])
    win_start = _ny_time(session_date, TRADE_WIN_HM[0], TRADE_WIN_HM[1])
    win_end   = _ny_time(session_date, TRADE_WIN_HM[2], TRADE_WIN_HM[3])
    ax.axvspan(mdates.date2num(orb_start.tz_localize(None)),
               mdates.date2num(orb_end.tz_localize(None)),
               color="#fff176", alpha=0.30, zorder=0)
    ax.axvspan(mdates.date2num(win_start.tz_localize(None)),
               mdates.date2num(win_end.tz_localize(None)),
               color="#bdbdbd", alpha=0.10, zorder=0)

    orb_high = float(today_row.orb_high); orb_low = float(today_row.orb_low)
    ax.axhline(orb_high, color="#1565c0", linestyle="--", linewidth=1.4, alpha=0.85, zorder=3,
               label=f"ORB high {orb_high:.2f}")
    ax.axhline(orb_low,  color="#1565c0", linestyle="--", linewidth=1.4, alpha=0.85, zorder=3,
               label=f"ORB low  {orb_low:.2f}")
    ax.axhline(ref_close, color="#6a1b9a", linestyle=":", linewidth=1.0, alpha=0.85, zorder=3,
               label=f"ORB close (ref) {ref_close:.2f}")

    plot_pad = max((pmax - pmin) * 0.05, 5.0)
    visible_pmin = pmin - plot_pad
    visible_pmax = pmax + plot_pad

    # identify the triggering cluster: matches stored cluster_low/high exactly
    trig_low = float(trade["cluster_low"])
    trig_high = float(trade["cluster_high"])

    side_styles = {
        "buy":  {"line": "#2e7d32", "face": (0.27, 0.63, 0.28, 0.10)},
        "sell": {"line": "#c62828", "face": (0.78, 0.16, 0.16, 0.10)},
        "skip": {"line": "#616161", "face": (0.62, 0.62, 0.62, 0.08)},
    }
    annot_x = mdates.date2num(plot_end.tz_localize(None))

    # draw clusters: dim everything; emphasize the triggering one
    for c, side in classified:
        if c.high < visible_pmin or c.low > visible_pmax:
            continue
        is_trigger = abs(c.low - trig_low) < 0.01 and abs(c.high - trig_high) < 0.01
        st = side_styles[side]
        if is_trigger:
            ax.axhspan(c.low, c.high, color=st["face"][:3] + (0.32,), zorder=1)
            for lvl in c.levels:
                ax.axhline(lvl, color=st["line"], linewidth=1.6, alpha=0.85,
                           linestyle="--", zorder=3)
            mid = (c.low + c.high) / 2
            ax.annotate(
                f"★ TRIGGER\n{side.upper()} cluster\n{c.low:.2f}–{c.high:.2f}\nsize={c.size}",
                xy=(annot_x, mid), xycoords="data",
                xytext=(6, 0), textcoords="offset points",
                fontsize=8, ha="left", va="center", fontweight="bold",
                color=st["line"],
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=st["line"], lw=1.5, alpha=0.95),
                zorder=6,
            )
        else:
            ax.axhspan(c.low, c.high, color=st["face"], zorder=1)
            for lvl in c.levels:
                ax.axhline(lvl, color=st["line"], linewidth=0.4, alpha=0.25,
                           linestyle="--", zorder=2)

    # plot the trade itself
    side = trade["side"]; ep = float(trade["entry_price"])
    et = pd.Timestamp(trade["entry_time_utc"]).tz_convert("America/New_York").tz_localize(None)
    xt = pd.Timestamp(trade["exit_time_utc"]).tz_convert("America/New_York").tz_localize(None)
    et_n = mdates.date2num(et); xt_n = mdates.date2num(xt)
    xp = float(trade["exit_price"])

    if side == "buy":
        stop = ep - STOP_POINTS; target = ep + TARGET_POINTS
        arrow_marker = "^"; arrow_color = "#1b5e20"; lbl_dy = 38
    else:
        stop = ep + STOP_POINTS; target = ep - TARGET_POINTS
        arrow_marker = "v"; arrow_color = "#b71c1c"; lbl_dy = -55

    ax.scatter([et_n], [ep], marker=arrow_marker, s=300,
               color=arrow_color, edgecolor="black", linewidth=1.2, zorder=7)
    er = trade["exit_reason"]
    exit_color = {"target": "#2e7d32", "stop": "#c62828",
                  "force_close": "#f9a825"}.get(er, "#424242")
    ax.scatter([xt_n], [xp], marker="X", s=260,
               color=exit_color, edgecolor="black", linewidth=1.2, zorder=7)

    ax.plot([et_n, xt_n], [stop, stop], color="#c62828", linewidth=1.6,
            linestyle="-", alpha=0.8, zorder=4)
    ax.plot([et_n, xt_n], [target, target], color="#2e7d32", linewidth=1.6,
            linestyle="-", alpha=0.8, zorder=4)
    ax.plot([et_n, xt_n], [ep, xp], color="black", linewidth=0.8,
            linestyle=":", alpha=0.6, zorder=4)

    label = (f"{side.upper()} @ {ep:.2f}\n"
             f"Entry — cluster of {trade['cluster_size']} levels\n"
             f"S {stop:.2f}  T {target:.2f}\n"
             f"{er}: ${trade['pnl_dollars']:+.0f}")
    ax.annotate(
        label, xy=(et_n, ep),
        xytext=(0, lbl_dy), textcoords="offset points",
        fontsize=8, ha="center", fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.4", fc="white",
                  ec=arrow_color, lw=1.5, alpha=0.95),
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
    ax.set_ylabel("Price (Panama back-adjusted)")
    ax.grid(True, alpha=0.25)

    title = (f"{session_date}  |  {trade['regime']}  |  {side.upper()}  |  "
             f"P&L ${trade['pnl_dollars']:+.0f}  |  exit: {er}  |  40/40 stop/target")
    ax.set_title(title, fontsize=13, fontweight="bold")

    fig.text(0.5, 0.012,
             "Prices are Panama-adjusted; do not match real-market quotes.",
             ha="center", fontsize=8, color="#666", style="italic")

    legend_handles = [
        mpatches.Patch(color="#fff176", alpha=0.6, label="ORB window (9:30–9:45)"),
        mpatches.Patch(color="#bdbdbd", alpha=0.5, label="Trading window (9:46–11:30)"),
        plt.Line2D([0], [0], color="#1565c0", linestyle="--", label="ORB high/low"),
        plt.Line2D([0], [0], color="#6a1b9a", linestyle=":", label="ORB close (ref)"),
        plt.Line2D([0], [0], color="#c62828", linestyle="--", linewidth=1.6,
                   label="Triggering cluster level"),
        plt.Line2D([0], [0], color="#616161", linestyle="--", linewidth=0.4,
                   label="Other cluster level (dim)"),
        plt.Line2D([0], [0], color="#2e7d32", linewidth=1.6, label="Target line (±40)"),
        plt.Line2D([0], [0], color="#c62828", linewidth=1.6, label="Stop line (±40)"),
        plt.Line2D([0], [0], marker="^", color="w", markerfacecolor="#1b5e20",
                   markeredgecolor="black", label="Buy entry", linestyle="None", markersize=11),
        plt.Line2D([0], [0], marker="v", color="w", markerfacecolor="#b71c1c",
                   markeredgecolor="black", label="Sell entry", linestyle="None", markersize=11),
        plt.Line2D([0], [0], marker="X", color="w", markerfacecolor="#424242",
                   markeredgecolor="black", label="Exit", linestyle="None", markersize=11),
    ]
    ax.legend(handles=legend_handles, loc="upper left", fontsize=8, framealpha=0.92, ncol=2)

    plt.tight_layout(rect=[0, 0.02, 1, 1])
    plt.savefig(save_path, dpi=120)
    plt.close(fig)
    return save_path


def main(selection_json_path: str, out_dir: Path) -> list[Path]:
    ensure_dirs()
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(selection_json_path) as f:
        trades = json.load(f)
    print(f"Loading bars and ORB table…")
    bars = pd.read_parquet(BARS_PARQUET)
    bars["ts_ny"] = pd.to_datetime(bars["ts_ny"], utc=False)
    bars["session_date"] = pd.to_datetime(bars["session_date"]).dt.date
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    orb_table["session_date"] = pd.to_datetime(orb_table["session_date"])
    paths_out = []
    for tr in trades:
        # Filename: trade_NN_YYYY-MM-DD_regime_exit.png
        label = tr["label"]
        sd = tr["session_date"]
        rgm = tr["regime"]
        er = tr["exit_reason"]
        # label already starts with NN_YYYY...; use it as-is plus details
        seq = label.split("_")[0]
        fname = f"trade_{seq}_{sd}_{rgm}_{er}.png"
        save_path = out_dir / fname
        print(f"  rendering {fname} …")
        r = plot_trade(tr, bars, orb_table, save_path)
        if r:
            paths_out.append(r)
    return paths_out


if __name__ == "__main__":
    sel = sys.argv[1] if len(sys.argv) > 1 else "/tmp/selection_4040.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT_ROOT / "results" / "charts" / "40_40_examples"
    paths = main(sel, out)
    print(f"\nWrote {len(paths)} PNG(s) to {out}/")
    for p in paths:
        print(f"  {p}")
