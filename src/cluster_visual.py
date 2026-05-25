"""
src/cluster_visual.py — Cluster diagnostic visualization.

For a given session_date:
  1. Build the 400-level OR pool from the trailing 200 sessions (highs + lows)
  2. Cluster at four settings via the real src.signals._cluster_levels:
       gap=3,  min_size=3
       gap=10, min_size=3
       gap=15, min_size=3
       gap=7,  min_size=2   (live "C" config)
  3. Plot raw levels + cluster bands + today's OR (dashed) + today's close (solid)
  4. Print counts of clusters inside / within 10pts / within 30pts of today's OR

Run from project root:
    python -m src.cluster_visual                       # most recent session, PNG
    python -m src.cluster_visual 2026-01-08            # specific session, PNG
    python -m src.cluster_visual 2026-01-08 --html     # interactive Plotly HTML
"""

import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.data import load_processed_bars
from src.signals import (
    LOOKBACK_SESSIONS,
    _cluster_levels,
    compute_opening_range,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "results"

# (key, gap, min_size, color, linewidth, legend label)
CONFIGS = [
    ("gap3_ms3", 3.0, 3, "tab:blue", 1.5, "gap=3,  ms=3"),
    ("gap10_ms3", 10.0, 3, "tab:orange", 1.5, "gap=10, ms=3"),
    ("gap15_ms3", 15.0, 3, "tab:green", 1.5, "gap=15, ms=3"),
    ("gap7_ms2", 7.0, 2, "red", 2.6, "gap=7,  ms=2  (C live)"),
]

# Matplotlib → CSS colors that Plotly accepts unambiguously.
PLOTLY_COLOR = {
    "tab:blue": "#1f77b4",
    "tab:orange": "#ff7f0e",
    "tab:green": "#2ca02c",
    "red": "#d62728",
}


def parse_session(arg, or_levels):
    if arg is None:
        return or_levels.index[-1]
    try:
        d = datetime.strptime(arg, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"Bad session_date '{arg}', expected YYYY-MM-DD")
    if d not in or_levels.index:
        raise SystemExit(f"Session {d} not in OR levels; most recent is {or_levels.index[-1]}")
    return d


def clusters_for(or_levels, session_date, gap, min_size, lookback=LOOKBACK_SESSIONS):
    """
    Mirror build_cluster_pool's per-session logic, calling _cluster_levels
    directly so we hit the exact same code path the strategy uses.
    """
    sessions = or_levels.index.tolist()
    i = sessions.index(session_date)
    if i < lookback:
        raise SystemExit(
            f"Need {lookback} prior sessions, only {i} available before {session_date}"
        )
    window = or_levels.iloc[i - lookback : i]
    levels = window["or_high"].tolist() + window["or_low"].tolist()
    raw_clusters = _cluster_levels(levels, gap=gap, min_size=min_size)
    rows = [
        {"low": min(c), "high": max(c), "center": sum(c) / len(c), "n_levels": len(c)}
        for c in raw_clusters
    ]
    return levels, pd.DataFrame(rows)


def count_near_or(clusters_df, or_low, or_high):
    if clusters_df.empty:
        return 0, 0, 0
    c = clusters_df["center"]
    inside = ((c >= or_low) & (c <= or_high)).sum()
    dist = (or_low - c).clip(lower=0) + (c - or_high).clip(lower=0)
    w10 = (dist <= 10).sum()
    w30 = (dist <= 30).sum()
    return int(inside), int(w10), int(w30)


def session_close(bars, session_date):
    rows = bars[bars["session_date"] == session_date]
    if rows.empty:
        return None
    return float(rows["close"].iloc[-1])


def compute_y_range(or_low, or_high, close, cluster_sets):
    """Same heuristic for PNG and HTML so both views frame the same window."""
    anchor_hi = max(or_high, close if close is not None else or_high)
    anchor_lo = min(or_low, close if close is not None else or_low)
    or_mid = (or_high + or_low) / 2
    nonempty = [cluster_sets[k][0]["center"] for k in cluster_sets if not cluster_sets[k][0].empty]
    if nonempty:
        all_centers = pd.concat(nonempty, ignore_index=True)
        nearest = all_centers.reindex((all_centers - or_mid).abs().sort_values().index).head(10)
        anchor_hi = max(anchor_hi, float(nearest.max()))
        anchor_lo = min(anchor_lo, float(nearest.min()))
    y_pad = max(80.0, (anchor_hi - anchor_lo) * 0.10)
    return anchor_lo - y_pad, anchor_hi + y_pad


def render_png(sess, pool_levels, cluster_sets, or_low, or_high, close):
    """Matplotlib slot layout: raw pool + 4 cluster columns, OR/close overlays."""
    fig, ax = plt.subplots(figsize=(12, 9))

    slot_w = 0.9
    n_slots = 1 + len(CONFIGS)

    for lvl in pool_levels:
        ax.hlines(lvl, xmin=0.0, xmax=slot_w, colors="lightgray", linewidth=0.6, alpha=0.7)

    for i, (key, gap, ms, color, lw, label) in enumerate(CONFIGS):
        x0 = (i + 1) * 1.0
        x1 = x0 + slot_w
        df, _, _, _ = cluster_sets[key]
        for _, row in df.iterrows():
            ax.fill_between([x0, x1], row["low"], row["high"], color=color, alpha=0.25)
            ax.hlines(row["center"], xmin=x0, xmax=x1, colors=color, linewidth=lw)

    ax.axhline(
        or_high,
        color="black",
        linestyle="--",
        linewidth=1.1,
        alpha=0.8,
        label=f"OR high {or_high:.1f}",
    )
    ax.axhline(
        or_low,
        color="black",
        linestyle="--",
        linewidth=1.1,
        alpha=0.8,
        label=f"OR low  {or_low:.1f}",
    )
    if close is not None:
        ax.axhline(
            close,
            color="purple",
            linestyle="-",
            linewidth=1.3,
            alpha=0.85,
            label=f"close   {close:.1f}",
        )

    y_lo, y_hi = compute_y_range(or_low, or_high, close, cluster_sets)
    ax.set_ylim(y_lo, y_hi)

    slot_labels = ["raw 400 levels"] + [c[5] for c in CONFIGS]
    ax.set_xticks([slot_w / 2] + [(i + 1) + slot_w / 2 for i in range(len(CONFIGS))])
    ax.set_xticklabels(slot_labels, rotation=18, ha="right")
    ax.set_xlim(-0.2, n_slots + 0.2)

    ax.set_ylabel("Price")
    ax.set_title(
        f"Cluster diagnostic  |  session {sess}\n"
        f"400 prior-OR levels + 4 cluster settings + today's OR/close"
    )
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    out_path = RESULTS / f"cluster_visual_{sess}.png"
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


def render_html(sess, pool_levels, cluster_sets, or_low, or_high, close):
    """
    Plotly: one toggleable trace per overlay.
      - raw 400 levels (gray, hover skipped)
      - one trace per cluster config (line at center, band fill, hover details)
      - OR-high / OR-low dashed
      - close solid

    Bands and centers for a config share a legendgroup so a single click hides
    both. customdata carries cluster metadata so hovertemplate can show it.
    """
    import plotly.graph_objects as go

    fig = go.Figure()
    x0, x1 = 0.0, 1.0

    # ── Raw 400 levels (single trace, None-separated segments) ───────────
    xs, ys = [], []
    for lvl in pool_levels:
        xs += [x0, x1, None]
        ys += [lvl, lvl, None]
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines",
            line=dict(color="lightgray", width=1),
            opacity=0.7,
            name=f"raw 400 levels  ({len(pool_levels)})",
            hoverinfo="skip",
            legendgroup="raw",
        )
    )

    # ── Cluster overlays ─────────────────────────────────────────────────
    for key, gap, ms, mpl_color, lw, label in CONFIGS:
        df = cluster_sets[key][0]
        color = PLOTLY_COLOR.get(mpl_color, mpl_color)
        group = f"cfg_{key}"
        legend_name = f"{label}  ({len(df)})"

        # Translucent bands — share legendgroup with the center line so a single
        # toggle hides both. showlegend=False keeps the legend uncluttered.
        band_x, band_y = [], []
        for _, row in df.iterrows():
            band_x += [x0, x1, x1, x0, x0, None]
            band_y += [row["low"], row["low"], row["high"], row["high"], row["low"], None]
        if band_x:
            fig.add_trace(
                go.Scatter(
                    x=band_x,
                    y=band_y,
                    fill="toself",
                    fillcolor=color,
                    opacity=0.18,
                    mode="lines",
                    line=dict(color="rgba(0,0,0,0)", width=0),
                    hoverinfo="skip",
                    showlegend=False,
                    legendgroup=group,
                    name=legend_name,
                )
            )

        # Center lines — one trace per config, hover carries cluster metadata.
        ctr_x, ctr_y, customs = [], [], []
        for _, row in df.iterrows():
            ctr_x += [x0, x1, None]
            ctr_y += [row["center"], row["center"], None]
            cd = [
                row["center"],
                int(row["n_levels"]),
                row["low"],
                row["high"],
                row["high"] - row["low"],
            ]
            customs += [cd, cd, [None] * 5]
        fig.add_trace(
            go.Scatter(
                x=ctr_x,
                y=ctr_y,
                mode="lines",
                line=dict(color=color, width=max(2, lw)),
                name=legend_name,
                legendgroup=group,
                customdata=customs,
                hovertemplate=(
                    "<b>" + label + "</b><br>"
                    "center = %{customdata[0]:.2f}<br>"
                    "n_levels = %{customdata[1]}<br>"
                    "low = %{customdata[2]:.2f}  high = %{customdata[3]:.2f}<br>"
                    "span = %{customdata[4]:.2f} pts"
                    "<extra></extra>"
                ),
            )
        )

    # ── OR + close overlays ──────────────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x=[x0, x1],
            y=[or_high, or_high],
            mode="lines",
            line=dict(color="black", width=1.5, dash="dash"),
            name=f"OR high {or_high:.1f}",
            hovertemplate="OR high = %{y:.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[x0, x1],
            y=[or_low, or_low],
            mode="lines",
            line=dict(color="black", width=1.5, dash="dash"),
            name=f"OR low  {or_low:.1f}",
            hovertemplate="OR low = %{y:.2f}<extra></extra>",
        )
    )
    if close is not None:
        fig.add_trace(
            go.Scatter(
                x=[x0, x1],
                y=[close, close],
                mode="lines",
                line=dict(color="purple", width=2.2),
                name=f"close   {close:.1f}",
                hovertemplate="close = %{y:.2f}<extra></extra>",
            )
        )

    y_lo, y_hi = compute_y_range(or_low, or_high, close, cluster_sets)

    fig.update_layout(
        title=dict(
            text=(
                f"Cluster diagnostic  |  session {sess}<br>"
                f"<sub>Toggle overlays in the legend  ·  hover a cluster "
                f"line for details</sub>"
            ),
            x=0.02,
            xanchor="left",
        ),
        yaxis=dict(title="Price", range=[y_lo, y_hi]),
        xaxis=dict(showticklabels=False, range=[x0 - 0.02, x1 + 0.02]),
        hovermode="closest",
        height=820,
        margin=dict(l=70, r=30, t=90, b=40),
        legend=dict(itemclick="toggle", itemdoubleclick="toggleothers"),
    )

    out_path = RESULTS / f"cluster_visual_{sess}.html"
    fig.write_html(str(out_path), include_plotlyjs="cdn")
    return out_path


def print_count_table(cluster_sets, or_low, or_high):
    rows = []
    for key, gap, ms, color, lw, label in CONFIGS:
        df, _, _, _ = cluster_sets[key]
        inside, w10, w30 = count_near_or(df, or_low, or_high)
        rows.append(
            {
                "config": label,
                "n_clusters": len(df),
                "inside_OR": inside,
                "within_10pts": w10,
                "within_30pts": w30,
            }
        )
    table = pd.DataFrame(rows)
    print("\nCluster counts vs today's OR:")
    print(table.to_string(index=False))


def main():
    args = sys.argv[1:]
    html_mode = "--html" in args
    args = [a for a in args if a != "--html"]
    arg = args[0] if args else None

    bars = load_processed_bars()
    or_levels = compute_opening_range(bars)

    sess = parse_session(arg, or_levels)
    or_high = float(or_levels.loc[sess, "or_high"])
    or_low = float(or_levels.loc[sess, "or_low"])
    close = session_close(bars, sess)

    print(f"Session: {sess}")
    print(f"OR low={or_low:.2f}  high={or_high:.2f}  (range={or_high - or_low:.2f})")
    if close is not None:
        print(f"Close: {close:.2f}")

    pool_levels, _ = clusters_for(or_levels, sess, gap=3.0, min_size=3)
    cluster_sets = {}
    for key, gap, ms, color, lw, label in CONFIGS:
        _, df = clusters_for(or_levels, sess, gap=gap, min_size=ms)
        cluster_sets[key] = (df, color, lw, label)

    RESULTS.mkdir(parents=True, exist_ok=True)

    if html_mode:
        out_path = render_html(sess, pool_levels, cluster_sets, or_low, or_high, close)
        print_count_table(cluster_sets, or_low, or_high)
        print(f"\nHTML DONE  {out_path}")
    else:
        out_path = render_png(sess, pool_levels, cluster_sets, or_low, or_high, close)
        print_count_table(cluster_sets, or_low, or_high)
        print(f"\nVISUAL DONE  {out_path}")


if __name__ == "__main__":
    main()
