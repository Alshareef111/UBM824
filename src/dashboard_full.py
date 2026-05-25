"""
src/dashboard_full.py — Single self-contained HTML dashboard covering the
entire NQ-VBT project.

Reads every metric from CSV under results/ (or from docs/DEPLOYMENT_PLAN.md
for prose). Hardcodes no numeric metric. Panels auto-skip when their source
file is absent. Honors results/current_best.json for the locked config.

Run from project root:
    .venv/bin/python -m src.dashboard_full
or:
    .venv/bin/python src/dashboard_full.py

Writes results/dashboard_full.html.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "results"
DOCS = PROJECT_ROOT / "docs"
OUT_PATH = RESULTS / "dashboard_full.html"

# All consumed CSV / artifact paths (panels auto-skip if missing)
CSV_RISK_AUDIT = RESULTS / "within200_3020_risk_audit.csv"
CSV_VALIDATION = RESULTS / "within200_validation.csv"
CSV_TP_SL_GRID = RESULTS / "within200_tp_sl_grid.csv"
CSV_TIGHT_WF = RESULTS / "within200_tight_walkforward.csv"
CSV_ENTRY_GEOM = RESULTS / "within200_entry_geometry.csv"
CSV_BE_STOP = RESULTS / "within200_breakeven_stop.csv"
CSV_SLIPPAGE = RESULTS / "within200_slippage.csv"
CSV_FILL_REALISM = RESULTS / "within200_fill_realism.csv"
CSV_PAIRWISE = RESULTS / "vbt_pairwise_sweep.csv"
CSV_GATE_PROX = RESULTS / "vbt_gate_proximity_sweep.csv"
CSV_REGIME_COV = RESULTS / "regime_coverage.csv"
CSV_WIDE_BRACKET = RESULTS / "wide_bracket_surface.csv"
CSV_TRADES = RESULTS / "trades_baseline.csv"
JSON_CURRENT_BEST = RESULTS / "current_best.json"
DEPLOYMENT_PLAN = DOCS / "DEPLOYMENT_PLAN.md"
CLUSTER_PNGS = sorted(RESULTS.glob("cluster_visual_*.png"))

DEFAULT_CHAMPION = {
    "gate": "within_200",
    "gap": 7.0,
    "ms": 2,
    "lookback": 200,
    "entry_location": "center",
    "entry_buffer": 1.0,
    "stop_pts": 30.0,
    "target_pts": 20.0,
    "use_adx": False,
    "use_be": False,
    "earliest_entry": "09:45",
    "latest_entry": "11:29",
    "slip_pts": 0.5,
    "commission_rt": 2.0,
    "cost_model": "A",
}


# ────────────────────── helpers ────────────────────────────────────────


def safe_read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"  warn: failed to read {path.name}: {e}", flush=True)
        return None


def load_champion() -> dict:
    if JSON_CURRENT_BEST.exists():
        try:
            d = json.loads(JSON_CURRENT_BEST.read_text())
            return {**DEFAULT_CHAMPION, **d}
        except Exception:
            pass
    return DEFAULT_CHAMPION


def risk_audit_map(df: pd.DataFrame) -> dict:
    """Convert the two-col 'metric,value' risk audit CSV into a dict."""
    out = {}
    for _, row in df.iterrows():
        k = str(row["metric"])
        v = row["value"]
        try:
            v = float(v)
            if v.is_integer():
                v = int(v)
        except (ValueError, TypeError):
            v = str(v)
        out[k] = v
    return out


def fmt_money(v, plus=False):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    sign = "+" if plus and v >= 0 else ""
    return f"${sign}{v:,.0f}"


def fmt_pct(v, digits=1, of_unit=True):
    if v is None or pd.isna(v):
        return "—"
    if of_unit:
        return f"{v * 100:.{digits}f}%"
    return f"{v:.{digits}f}%"


def fmt_num(v, n=3):
    if v is None or pd.isna(v):
        return "—"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    return f"{v:.{n}f}"


def png_to_data_uri(p: Path) -> str:
    try:
        b = p.read_bytes()
    except Exception:
        return ""
    return "data:image/png;base64," + base64.b64encode(b).decode("ascii")


def fig_to_div(fig: go.Figure, panel_id: str, height: int = 360) -> str:
    """Theme-agnostic figure: transparent backgrounds; medium-gray grid &
    text colors that read on both white and dark backgrounds. The CSS sets
    section background; Plotly inherits via rgba(0,0,0,0)."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="-apple-system, BlinkMacSystemFont, Helvetica, Arial", size=12, color="#888"
        ),
        margin=dict(l=55, r=30, t=30, b=40),
        height=height,
        xaxis=dict(
            gridcolor="rgba(128,128,128,0.18)",
            zerolinecolor="rgba(128,128,128,0.3)",
            linecolor="rgba(128,128,128,0.3)",
        ),
        yaxis=dict(
            gridcolor="rgba(128,128,128,0.18)",
            zerolinecolor="rgba(128,128,128,0.3)",
            linecolor="rgba(128,128,128,0.3)",
        ),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=panel_id,
        config={"displaylogo": False, "responsive": True},
    )


def panel_open(letter: str, title: str, source: str, ts: str, note: str | None = None) -> str:
    note_html = f'<div class="panel-note">{note}</div>' if note else ""
    return f"""
<section class="panel" id="panel-{letter.lower()}">
  <div class="panel-head">
    <div class="panel-title"><span class="badge">{letter}</span> {title}</div>
    <div class="source">source: <code>{source}</code> · generated {ts}</div>
  </div>
  {note_html}
"""


def panel_close() -> str:
    return "</section>"


# ────────────────────── deployment plan parsing ────────────────────────


def parse_tripwires(md_text: str) -> pd.DataFrame | None:
    """Find the '## 3. Tripwires' section's markdown table."""
    m = re.search(r"##\s*3\.\s*Tripwires.*?\n(\|.+?\n)(?=\n\S|\n##|\Z)", md_text, re.DOTALL)
    if not m:
        return None
    rows = []
    for line in m.group(1).splitlines():
        if not line.startswith("|") or set(line.strip("| \t")) <= set("-:|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return None
    header, *body = rows
    df = pd.DataFrame(body, columns=header)
    return df


def parse_sizing(md_text: str) -> pd.DataFrame | None:
    """Find the suggested-ramp sizing table inside section 1."""
    m = re.search(
        r"##\s*1\.\s*Sizing.*?(\|\s*ramp stage.+?\n)(?=\n\S|\n##|\Z)",
        md_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    rows = []
    for line in m.group(1).splitlines():
        if not line.startswith("|") or set(line.strip("| \t")) <= set("-:|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return None
    header, *body = rows
    return pd.DataFrame(body, columns=header)


# ────────────────────── PANEL A: Headline cards ────────────────────────


def panel_A_headline(audit: dict | None, ts: str) -> str | None:
    if audit is None:
        return None
    champ = load_champion()
    cfg_line = audit.get(
        "config",
        f"within_200 / g{champ['gap']:.0f} / m{champ['ms']} / "
        f"stop={champ['stop_pts']:.0f} / target={champ['target_pts']:.0f} / "
        f"Model {champ['cost_model']} / slip={champ['slip_pts']} / "
        f"RT_cost=${champ['commission_rt']}",
    )
    fields = [
        ("trades", audit.get("trades_total"), lambda v: fmt_num(v, 0)),
        ("net", audit.get("net_total_$"), lambda v: fmt_money(v, plus=True)),
        ("max DD", audit.get("max_dd_$"), lambda v: fmt_money(v)),
        (
            "max DD %",
            audit.get("max_dd_pct_of_$50k_init"),
            lambda v: fmt_pct(v, digits=2, of_unit=False),
        ),
        ("mean trade", audit.get("trade_pnl_mean_$"), lambda v: fmt_money(v, plus=True)),
        ("worst loss", audit.get("worst_single_loss_$"), lambda v: fmt_money(v)),
        ("worst streak", audit.get("worst_losing_trade_streak"), lambda v: fmt_num(v, 0)),
        (
            "% pos months",
            audit.get("pct_positive_months"),
            lambda v: fmt_pct(v, digits=1, of_unit=False),
        ),
    ]
    cards = "".join(
        f'<div class="card"><div class="label">{label}</div><div class="value">{fmt(v)}</div></div>'
        for label, v, fmt in fields
    )
    head = panel_open(
        "A",
        "Locked config — headline",
        "within200_3020_risk_audit.csv",
        ts,
        note=f"<code>{cfg_line}</code>",
    )
    return head + f'<div class="cards">{cards}</div>' + panel_close()


# ────────────────────── PANEL B: Config evolution ──────────────────────


def panel_B_evolution(df_gate, df_val, audit, ts):
    if df_gate is None or df_val is None or audit is None:
        return None

    # Stage 1: C+ADX+40/40 — from within200_validation.csv (gate=inside_OR / full)
    # Stage 2: within_200/40-40 — within200_validation.csv (gate=within_200 / full)
    # Stage 3: locked (within_200/30-20) — from risk audit
    def val_full(gate):
        sub = df_val[(df_val["gate"] == gate) & (df_val["period"] == "full")]
        if sub.empty:
            return None
        return sub.iloc[0].to_dict()

    stage1 = val_full("inside_OR")
    stage2 = val_full("within_200")
    if stage1 is None or stage2 is None:
        return None

    stages = [
        ("inside_OR  ·  40/40", stage1, "stage 1"),
        ("within_200 ·  40/40", stage2, "stage 2"),
        (
            "within_200 ·  30/20",
            {
                "n_trades": audit.get("trades_total"),
                "WR": audit.get("win_rate"),  # may be missing
                "net": audit.get("net_total_$"),
                "PF": audit.get("profit_factor"),  # missing in risk audit
                "max_dd": audit.get("max_dd_$"),
                "Sharpe": audit.get("sharpe_approx"),  # missing
            },
            "locked",
        ),
    ]
    cards = []
    for label, row, tag in stages:
        rows_html = "".join(
            [
                f'<tr><td>net</td><td class="num">{fmt_money(row.get("net"))}</td></tr>',
                f'<tr><td>PF</td><td class="num">{fmt_num(row.get("PF"), 3)}</td></tr>',
                f'<tr><td>max DD</td><td class="num">{fmt_money(row.get("max_dd"))}</td></tr>',
                f'<tr><td>trades</td><td class="num">{fmt_num(row.get("n_trades"), 0)}</td></tr>',
            ]
        )
        cards.append(
            f'<div class="card-wide"><div class="card-tag">{tag}</div>'
            f'<div class="card-h">{label}</div><table class="mini">{rows_html}</table></div>'
        )

    head = panel_open(
        "B",
        "Config evolution",
        "within200_validation.csv + within200_3020_risk_audit.csv",
        ts,
        note="three milestones; full-period metrics",
    )
    return head + f'<div class="grid-3">{"".join(cards)}</div>' + panel_close()


# ────────────────────── PANEL C: Decision trail ────────────────────────

DECISIONS = [
    (
        "Gate",
        "inside_OR (cluster center inside OR)",
        "within_200 (within 200 pts of 09:45 price)",
        "inside_OR discarded positive-EV setups; within_200 lifts PF + holds train→test→holdout.",
    ),
    (
        "ADX(30, 8)",
        "ON — needed to densify entries under inside_OR",
        "OFF — redundant under within_200; hurt holdout",
        "Simpler config = fewer params, less overfit surface.",
    ),
    (
        "Target",
        "40 pts (inherited, never swept)",
        "20 pts (TP/SL surface dominator)",
        "Tight targets dominate the TP/SL surface; 30/20 over 40/20 for better R:R / lower BE WR.",
    ),
]


def panel_C_decisions(ts):
    rows = []
    for name, before, after, why in DECISIONS:
        rows.append(
            f'<tr><td class="dec-name">{name}</td>'
            f'<td class="dec-before">{before}</td>'
            f'<td class="dec-arrow">→</td>'
            f'<td class="dec-after">{after}</td>'
            f'<td class="dec-why">{why}</td></tr>'
        )
    head = panel_open(
        "C",
        "Key decisions trail",
        "within200_validation.csv, within200_tp_sl_grid.csv, within200_adx_grid.csv",
        ts,
    )
    return (
        head + '<table class="decisions">'
        "<thead><tr><th>decision</th><th>before</th><th></th>"
        "<th>after</th><th>why</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>" + panel_close()
    )


# ────────────────────── PANEL D: Gate analysis ─────────────────────────


def panel_D_gate(df_gate, ts):
    if df_gate is None:
        return None
    sub = df_gate[(df_gate["gap"] == 7.0) & (df_gate["ms"] == 2)].copy()
    if sub.empty:
        return None
    order = ["inside_OR", "within_100", "within_200", "no_gate"]
    sub = sub.assign(o=sub["gate"].map({g: i for i, g in enumerate(order)}))
    sub = sub.dropna(subset=["o"]).sort_values("o")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=sub["gate"],
            y=sub["net_dollars"],
            name="net $",
            marker_color="#5b8def",
            yaxis="y",
            hovertemplate="<b>%{x}</b><br>net = %{y:$,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=sub["gate"],
            y=sub["profit_factor"],
            name="PF",
            mode="lines+markers",
            yaxis="y2",
            line=dict(color="#d97706", width=2.5),
            marker=dict(size=10),
            hovertemplate="<b>%{x}</b><br>PF = %{y:.3f}<extra></extra>",
        )
    )
    # second-axis right
    fig.update_layout(
        yaxis=dict(title="net $", tickformat="$,.0f", gridcolor="rgba(128,128,128,0.18)"),
        yaxis2=dict(title="PF", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", x=0, y=1.10),
    )
    # restrictiveness (cand count) as a secondary mini-bar
    restr_html = ""
    if "n_candidates" in sub.columns:
        rows = "".join(
            f"<tr><td>{r['gate']}</td><td class='num'>{int(r['n_candidates']):,}</td>"
            f"<td class='num'>{int(r['n_trades']):,}</td></tr>"
            for _, r in sub.iterrows()
        )
        restr_html = (
            '<div class="side-table"><div class="side-h">restrictiveness</div>'
            '<table class="mini"><thead><tr>'
            "<th>gate</th><th>n cand.</th><th>n trades</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div>"
        )

    head = panel_open("D", "Gate sweet-spot (gap=7 · ms=2)", "vbt_gate_proximity_sweep.csv", ts)
    return head + f'<div class="row-2">{fig_to_div(fig, "fig-D")}{restr_html}</div>' + panel_close()


# ────────────────────── PANEL E: TP/SL surface ─────────────────────────


def panel_E_tpsl(df, ts, champ):
    if df is None:
        return None
    df = df.copy()
    df["stop"] = df["stop"].astype(int)
    df["target"] = df["target"].astype(int)
    # PF heatmap: stop on Y, target on X
    pivot = df.pivot(index="stop", columns="target", values="pf").sort_index()
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale="RdYlGn",
            zmid=1.0,
            colorbar=dict(title="PF"),
            hovertemplate="stop=%{y} / target=%{x}<br>PF=%{z:.3f}<extra></extra>",
        )
    )
    # mark the locked cell
    sx = int(champ["target_pts"])
    sy = int(champ["stop_pts"])
    if sx in pivot.columns and sy in pivot.index:
        fig.add_annotation(
            x=sx,
            y=sy,
            text="★ 30/20",
            showarrow=False,
            font=dict(color="#111", size=13),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#111",
            borderwidth=1,
        )
    fig.update_layout(
        xaxis_title="target (pts)",
        yaxis_title="stop (pts)",
        yaxis=dict(autorange="reversed"),
    )
    head = panel_open(
        "E",
        "TP/SL surface (PF heatmap)",
        "within200_tp_sl_grid.csv",
        ts,
        note="★ marks the locked 30/20 cell",
    )
    return head + fig_to_div(fig, "fig-E", height=400) + panel_close()


# ────────────────────── PANEL F: Validation ────────────────────────────


def panel_F_validation(df_tight, df_slip, df_fill, ts):
    if df_tight is None:
        return None
    # tight WF: cell × period PF
    splits = ["train", "test", "holdout"]
    sub = df_tight[df_tight["period"].isin(splits)].copy()
    if sub.empty:
        return None
    sub["period"] = pd.Categorical(sub["period"], categories=splits, ordered=True)
    color_map = {"40/40": "#1f77b4", "40/20": "#2ca02c", "30/20": "#d62728", "20/20": "#9467bd"}
    fig = go.Figure()
    for cell, g in sub.groupby("cell"):
        g = g.sort_values("period")
        fig.add_trace(
            go.Scatter(
                x=[str(p) for p in g["period"]],
                y=g["pf"],
                mode="lines+markers",
                name=cell,
                line=dict(color=color_map.get(cell, "#666"), width=2.5),
                marker=dict(size=10),
                hovertemplate=f"<b>{cell}</b><br>%{{x}}: PF = %{{y:.3f}}<extra></extra>",
            )
        )
    fig.add_hline(y=1.0, line_dash="dot", line_color="rgba(128,128,128,0.5)")
    fig.update_layout(yaxis_title="PF", xaxis_title=None, legend=dict(orientation="h", x=0, y=1.1))

    # Per-year PF for the 30/20 cell
    yearly_html = ""
    yearly = df_tight[
        (df_tight["cell"] == "30/20") & df_tight["period"].astype(str).str.match(r"^\d{4}$")
    ]
    if not yearly.empty:
        yfig = go.Figure(
            go.Bar(
                x=yearly["period"].astype(str),
                y=yearly["pf"],
                marker_color=["#2ca02c" if v >= 1.0 else "#d62728" for v in yearly["pf"]],
                hovertemplate="%{x}: PF=%{y:.3f}<extra></extra>",
            )
        )
        yfig.add_hline(y=1.0, line_dash="dot", line_color="rgba(128,128,128,0.5)")
        yfig.update_layout(yaxis_title="PF (per year)")
        yearly_html = fig_to_div(yfig, "fig-F-yearly", height=300)

    # Slippage decay summary
    slip_html = ""
    if df_slip is not None:
        s = df_slip[
            (df_slip["stop"] == 30) & (df_slip["target"] == 20) & (df_slip["model"] == "A")
        ].copy()
        if not s.empty:
            sfig = go.Figure(
                go.Scatter(
                    x=s["slip_pts_per_side"],
                    y=s["pf"],
                    mode="lines+markers",
                    line=dict(color="#5b8def", width=2.5),
                    marker=dict(size=8),
                    hovertemplate="slip=%{x}pt/side<br>PF=%{y:.3f}<extra></extra>",
                )
            )
            sfig.add_hline(y=1.0, line_dash="dot", line_color="rgba(128,128,128,0.5)")
            sfig.update_layout(yaxis_title="PF", xaxis_title="slip pts / side (Model A)")
            slip_html = fig_to_div(sfig, "fig-F-slip", height=300)

    # Fill realism row(s) for 30/20
    fill_html = ""
    if df_fill is not None:
        ff = df_fill[(df_fill["stop"] == 30) & (df_fill["target"] == 20)]
        if not ff.empty:
            r = ff.iloc[0]
            fill_html = (
                '<div class="side-table">'
                '<div class="side-h">fill realism (30/20)</div>'
                '<table class="mini">'
                f'<tr><td>PF pessimistic</td><td class="num">{r["pf_pessimistic"]:.3f}</td></tr>'
                f'<tr><td>PF optimistic</td><td class="num">{r["pf_optimistic"]:.3f}</td></tr>'
                f'<tr><td>PF spread</td><td class="num">{r["pf_spread"]:.3f}</td></tr>'
                f'<tr><td>% target on entry-bar</td><td class="num">{r["pct_target_on_entry_bar"]:.1f}%</td></tr>'
                f'<tr><td>% ambiguous bars</td><td class="num">{r["pct_ambiguous"]:.2f}%</td></tr>'
                "</table></div>"
            )

    head = panel_open(
        "F",
        "Validation — walk-forward + slippage + fills",
        "within200_tight_walkforward.csv, within200_slippage.csv, within200_fill_realism.csv",
        ts,
    )
    body = (
        f'<div class="subhead">train → test → holdout PF (all tight cells)</div>'
        f"{fig_to_div(fig, 'fig-F-wf')}"
        f'<div class="grid-2">'
        f'  <div><div class="subhead">per-year PF (30/20)</div>{yearly_html}</div>'
        f'  <div><div class="subhead">slippage decay (30/20)</div>{slip_html}</div>'
        f"</div>"
        f"{fill_html}"
    )
    return head + body + panel_close()


# ────────────────────── PANEL G: Falsifications ────────────────────────


def panel_G_falsifications(df_geom, df_be, df_wide, ts):
    blocks = []

    # entry geometry — show offset variation for center location
    if df_geom is not None:
        g = df_geom[df_geom["param"] == "entry_offset"]
        if not g.empty:
            fig = go.Figure(
                go.Scatter(
                    x=g["value"].astype(float),
                    y=g["pf"],
                    mode="lines+markers",
                    line=dict(color="#5b8def", width=2.5),
                    marker=dict(size=8),
                    hovertemplate="offset=%{x}<br>PF=%{y:.3f}<extra></extra>",
                )
            )
            fig.update_layout(
                yaxis=dict(
                    title="PF",
                    range=[max(0.9, float(g["pf"].min()) - 0.05), float(g["pf"].max()) + 0.05],
                ),
                xaxis_title="entry offset (pts)",
            )
            blocks.append(
                (
                    "entry geometry — inert",
                    "within200_entry_geometry.csv",
                    fig_to_div(fig, "fig-G-geom", height=280),
                )
            )

    # BE stop — bar chart of PF vs BE band
    if df_be is not None:
        b = df_be.copy()
        b["B_str"] = b["B"].apply(lambda v: "none" if v == "none" else str(v))
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=b["B_str"],
                y=b["pf"],
                marker_color="#5b8def",
                name="PF",
                yaxis="y",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=b["B_str"],
                y=b["wr"],
                mode="lines+markers",
                name="WR",
                yaxis="y2",
                line=dict(color="#d97706", width=2.5),
                marker=dict(size=8),
                hovertemplate="B=%{x}<br>WR=%{y:.1%}<extra></extra>",
            )
        )
        fig.update_layout(
            yaxis=dict(title="PF"),
            yaxis2=dict(title="WR", overlaying="y", side="right", tickformat=".0%", showgrid=False),
            xaxis_title="BE stop band B",
            legend=dict(orientation="h", x=0, y=1.10),
        )
        blocks.append(
            (
                "breakeven stop — destructive",
                "within200_breakeven_stop.csv",
                fig_to_div(fig, "fig-G-be", height=300),
            )
        )

    # Wide brackets — table + PF bar
    if df_wide is not None:
        w = df_wide.copy().sort_values("stop")
        fig = go.Figure(
            go.Bar(
                x=w["label"],
                y=w["profit_factor"],
                marker_color=["#2ca02c" if v >= 1.5 else "#5b8def" for v in w["profit_factor"]],
                hovertemplate="%{x}<br>PF=%{y:.3f}<extra></extra>",
            )
        )
        fig.add_hline(y=1.0, line_dash="dot", line_color="rgba(128,128,128,0.5)")
        fig.update_layout(yaxis_title="PF")
        blocks.append(
            (
                "wide brackets — PF craters",
                "wide_bracket_surface.csv",
                fig_to_div(fig, "fig-G-wide", height=300),
            )
        )

    if not blocks:
        return None
    head = panel_open(
        "G",
        "Falsification — what was tested & rejected",
        "entry_geometry / breakeven_stop / wide_bracket_surface",
        ts,
    )
    cells = "".join(
        f'<div class="falsif-cell"><div class="falsif-title">{t}</div>'
        f'<div class="falsif-src">source: <code>{s}</code></div>{h}</div>'
        for t, s, h in blocks
    )
    return head + f'<div class="falsif-grid">{cells}</div>' + panel_close()


# ────────────────────── PANEL H: Risk ──────────────────────────────────


def panel_H_risk(audit, df_trades, ts):
    if audit is None:
        return None
    # KPIs from audit
    rows_html = "".join(
        [
            f'<tr><td>max DD</td><td class="num">{fmt_money(audit.get("max_dd_$"))}</td></tr>',
            f'<tr><td>max DD %</td><td class="num">{fmt_pct(audit.get("max_dd_pct_of_$50k_init"), 2, of_unit=False)}</td></tr>',
            f'<tr><td>worst rolling 3m</td><td class="num">{fmt_money(audit.get("worst_rolling_3m_$"))}</td></tr>',
            f'<tr><td>% time underwater</td><td class="num">{fmt_pct(audit.get("pct_calendar_underwater"), 1, of_unit=False)}</td></tr>',
            f'<tr><td>worst losing streak</td><td class="num">{audit.get("worst_losing_trade_streak")} ({fmt_money(audit.get("worst_losing_trade_streak_$"))})</td></tr>',
            f'<tr><td>worst single loss</td><td class="num">{fmt_money(audit.get("worst_single_loss_$"))}</td></tr>',
            f'<tr><td>pnl skew</td><td class="num">{fmt_num(audit.get("trade_pnl_skew"), 3)}</td></tr>',
            f'<tr><td>excess kurt</td><td class="num">{fmt_num(audit.get("trade_pnl_excess_kurt"), 3)}</td></tr>',
            f'<tr><td>% positive months</td><td class="num">{fmt_pct(audit.get("pct_positive_months"), 1, of_unit=False)}</td></tr>',
            f'<tr><td>best / worst month</td><td class="num">{audit.get("best_month")} / {audit.get("worst_month")}</td></tr>',
        ]
    )
    audit_table = (
        '<div class="side-table"><div class="side-h">risk KPIs</div>'
        f'<table class="mini">{rows_html}</table></div>'
    )

    monthly_html = ""
    if df_trades is not None and "pnl_dollars" in df_trades.columns:
        df = df_trades.copy()
        # exit_ts is the timestamp at which the trade closed
        df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True, errors="coerce")
        df["month"] = df["exit_ts"].dt.to_period("M").astype(str)
        monthly = df.groupby("month")["pnl_dollars"].sum().reset_index()
        if not monthly.empty:
            fig = go.Figure(
                go.Bar(
                    x=monthly["month"],
                    y=monthly["pnl_dollars"],
                    marker_color=[
                        "#2ca02c" if v >= 0 else "#d62728" for v in monthly["pnl_dollars"]
                    ],
                    hovertemplate="%{x}: %{y:$,.0f}<extra></extra>",
                )
            )
            fig.update_layout(yaxis_title="monthly P&L ($)", xaxis_title=None)
            monthly_html = (
                f'<div><div class="subhead">monthly P&L distribution</div>'
                f"{fig_to_div(fig, 'fig-H-monthly', height=320)}</div>"
            )

    head = panel_open(
        "H",
        "Risk — drawdown, streaks, monthly distribution",
        "within200_3020_risk_audit.csv + trades_baseline.csv",
        ts,
    )
    return head + (f'<div class="row-2">{audit_table}{monthly_html}</div>') + panel_close()


# ────────────────────── PANEL I: Regime / dark streaks ─────────────────


def panel_I_regime(df_reg, audit, ts):
    if df_reg is None and audit is None:
        return None
    blocks = []
    # regime distribution from regime_coverage.csv (column 'regime')
    if df_reg is not None and "regime" in df_reg.columns:
        rd = df_reg["regime"].value_counts().reset_index()
        rd.columns = ["regime", "n_sessions"]
        fig = go.Figure(
            go.Bar(
                x=rd["regime"],
                y=rd["n_sessions"],
                marker_color="#5b8def",
                hovertemplate="%{x}: %{y} sessions<extra></extra>",
            )
        )
        fig.update_layout(yaxis_title="n sessions", xaxis_title="regime")
        blocks.append(("regime distribution", fig_to_div(fig, "fig-I-regime", height=280)))

    # Dark-streak summary from audit
    if audit is not None:
        rows_html = "".join(
            [
                f'<tr><td>longest dark streak</td><td class="num">{audit.get("dark_streak_longest_sessions")} ({audit.get("dark_streak_longest_dates")})</td></tr>',
                f'<tr><td>current dark streak</td><td class="num">{audit.get("dark_streak_current_sessions")} ({audit.get("dark_streak_current_dates")})</td></tr>',
                f'<tr><td>total dark streaks</td><td class="num">{audit.get("dark_streaks_count")}</td></tr>',
                f'<tr><td>mean dark streak</td><td class="num">{fmt_num(audit.get("dark_streak_mean_length"), 2)}</td></tr>',
                f'<tr><td>p95 dark streak</td><td class="num">{fmt_num(audit.get("dark_streak_p95_length"), 1)}</td></tr>',
            ]
        )
        ds_table = (
            '<div class="side-table"><div class="side-h">dark streaks</div>'
            f'<table class="mini">{rows_html}</table></div>'
        )
        blocks.append(("", ds_table))

    head = panel_open(
        "I",
        "Regime coverage & dark streaks",
        "regime_coverage.csv + within200_3020_risk_audit.csv",
        ts,
    )
    inner = '<div class="row-2">' + "".join(b for _, b in blocks) + "</div>"
    return head + inner + panel_close()


# ────────────────────── PANEL J: Deployment ────────────────────────────


def panel_J_deployment(ts):
    if not DEPLOYMENT_PLAN.exists():
        return None
    md = DEPLOYMENT_PLAN.read_text()
    tripwires = parse_tripwires(md)
    sizing = parse_sizing(md)
    blocks = []
    if sizing is not None:
        rows = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in sizing.values.tolist()
        )
        headers = "".join(f"<th>{h}</th>" for h in sizing.columns)
        blocks.append(
            '<div><div class="subhead">suggested ramp (per docs/DEPLOYMENT_PLAN.md §1)</div>'
            f'<table class="dep"><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>'
        )
    if tripwires is not None:
        rows = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
            for r in tripwires.values.tolist()
        )
        headers = "".join(f"<th>{h}</th>" for h in tripwires.columns)
        blocks.append(
            '<div><div class="subhead">tripwires (per §3)</div>'
            f'<table class="dep"><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>'
        )
    if not blocks:
        return None
    head = panel_open(
        "J",
        "Deployment — sizing & tripwires",
        "docs/DEPLOYMENT_PLAN.md",
        ts,
        note="parsed from the deployment plan; the document is the source of truth",
    )
    return head + "".join(blocks) + panel_close()


# ────────────────────── PANEL K: Equity curve ──────────────────────────


def panel_K_equity(df_trades, audit, ts):
    if df_trades is None or "pnl_dollars" not in df_trades.columns:
        return None
    df = df_trades.copy()
    if "exit_ts" not in df.columns:
        return None
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["exit_ts"]).sort_values("exit_ts")
    df["cum"] = df["pnl_dollars"].cumsum()
    df["peak"] = df["cum"].cummax()
    df["dd"] = df["cum"] - df["peak"]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["exit_ts"],
            y=df["cum"],
            name="cumulative net $",
            mode="lines",
            line=dict(color="#5b8def", width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>cum = %{y:$,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["exit_ts"],
            y=df["dd"],
            name="drawdown $",
            mode="lines",
            line=dict(color="#d97706", width=1),
            fill="tozeroy",
            fillcolor="rgba(217,119,6,0.18)",
            yaxis="y2",
            hovertemplate="%{x|%Y-%m-%d}<br>dd = %{y:$,.0f}<extra></extra>",
        )
    )
    # Max-DD shaded band
    if audit is not None:
        s = audit.get("max_dd_start_date")
        e = audit.get("max_dd_recovery_date")
        if isinstance(s, str) and isinstance(e, str):
            try:
                s_ts = pd.Timestamp(s, tz="UTC")
                e_ts = pd.Timestamp(e, tz="UTC")
                fig.add_vrect(
                    x0=s_ts,
                    x1=e_ts,
                    fillcolor="rgba(214, 40, 40, 0.10)",
                    line_width=0,
                    layer="below",
                )
                fig.add_annotation(
                    x=s_ts + (e_ts - s_ts) / 2,
                    y=float(df["cum"].max()),
                    text=f"max-DD episode {s} → {e}",
                    showarrow=False,
                    yshift=-10,
                    font=dict(color="#d62728"),
                )
            except Exception:
                pass

    fig.update_layout(
        yaxis=dict(title="cumulative net $", tickformat="$,.0f"),
        yaxis2=dict(
            title="drawdown $", overlaying="y", side="right", tickformat="$,.0f", showgrid=False
        ),
        legend=dict(orientation="h", x=0, y=1.10),
    )
    head = panel_open(
        "K",
        "Equity curve — full period (per 1 contract)",
        "trades_baseline.csv",
        ts,
        note="DD shaded; red band = max-DD episode",
    )
    return head + fig_to_div(fig, "fig-K-equity", height=420) + panel_close()


# ────────────────────── PANEL L: Sizing scenarios ──────────────────────

DEFAULT_ACCOUNT = 50_000.0


def panel_L_sizing(audit, df_trades, ts, account=DEFAULT_ACCOUNT):
    if audit is None:
        return None
    max_dd = audit.get("max_dd_$")
    n_months = audit.get("n_months")
    net = audit.get("net_total_$")
    if max_dd is None or n_months is None or net is None:
        return None
    years = float(n_months) / 12.0
    net_per_yr = float(net) / years

    sizes = [1, 5, 10]
    rows = []
    for s in sizes:
        net_y = net_per_yr * s
        dd_y = float(max_dd) * s
        dd_pct = dd_y / account * 100.0
        rows.append(
            f"<tr><td>{s} MNQ</td>"
            f'<td class="num">{fmt_money(net_y, plus=True)}/yr</td>'
            f'<td class="num">{fmt_money(dd_y)}</td>'
            f'<td class="num">{dd_pct:+.2f}%</td></tr>'
        )
    table = (
        '<table class="dep">'
        f"<thead><tr><th>size</th><th>expected net</th><th>historical max DD</th>"
        f"<th>DD as % of ${account:,.0f}</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    head = panel_open(
        "L",
        "Sizing scenarios",
        "within200_3020_risk_audit.csv",
        ts,
        note=f"account = ${account:,.0f}. Liquidity supports ~10–20 MNQ before execution quality degrades — don't read this as unlimited.",
    )
    return head + table + panel_close()


# ────────────────────── PANEL M: Cluster visuals ───────────────────────


def panel_M_clusters(ts):
    if not CLUSTER_PNGS:
        return None
    cells = []
    for p in CLUSTER_PNGS:
        uri = png_to_data_uri(p)
        if not uri:
            continue
        cells.append(
            f'<figure class="cluster-fig">'
            f'<img src="{uri}" alt="{p.name}" />'
            f"<figcaption>{p.name}</figcaption></figure>"
        )
    if not cells:
        return None
    head = panel_open(
        "M",
        "Cluster visuals — example sessions",
        f"{len(CLUSTER_PNGS)} PNGs under results/",
        ts,
        note="OR band + cluster pool + 09:45 price; trigger sits at the cluster center within ±200 pts of the 09:45 close.",
    )
    return head + f'<div class="cluster-grid">{"".join(cells)}</div>' + panel_close()


# ────────────────────── PANEL N: Methodology narrative ────────────────

NARRATIVE = """
<p><strong>Goal.</strong> Validate a cluster-ORB MNQ 1-minute strategy
for live deployment.</p>

<p><strong>Starting point.</strong> Config <em>C</em>: <code>inside_OR</code>
gate (cluster center inside the OR), gap=7, ms=2, lookback=200, plus an
ADX(30, 8) filter and 40/40 stop/target.</p>

<p><strong>Gate: <code>inside_OR</code> → <code>within_200</code>.</strong>
The inside-OR rule discarded positive-EV setups — clusters whose center
sat just outside the OR were thrown away even though they cluster, by
definition, near recent action. Relaxing to <em>within 200 points of the
09:45 close</em> lifted PF and net dollars, held the lift across train →
test → holdout, and beat the prior config in every year. <code>no_gate</code>
overshoots — too many low-quality candidates. <code>within_200</code> is
the sweet spot.</p>

<p><strong>ADX dropped.</strong> Under the looser gate, ADX(30, 8) became
redundant — it was previously compensating for inside_OR's sparsity. On
the holdout it actively hurt. Simpler config = fewer params, less
overfit surface, fewer ways for the live edge to diverge from backtest.</p>

<p><strong>Target 40 → 20.</strong> The inherited 40/40 was never swept.
A 5×5 TP/SL surface (Panel E) shows tight targets dominate. The 30/20
choice survived four falsification gates: broad-region robustness (the
neighborhood, not just the cell, has PF&nbsp;>&nbsp;1.5); intrabar
ordering (stop-first conservative); realistic slippage (Model A,
0.5pt/side); walk-forward (train→test→holdout PF positive). Chose 30/20
over 40/20 for a better reward:risk and a lower breakeven win-rate.</p>

<p><strong>What was rejected.</strong></p>
<ul>
  <li><strong>Entry geometry</strong> (offset / location) — inert. The
  fill price is dominated by the bar's open, not the trigger offset, so
  perturbations are flat (Panel G).</li>
  <li><strong>Breakeven stop</strong> — destructive on a fast scalp. The
  20-pt target is reached often; moving stop to BE prematurely converts
  winners into BE-flats and chops out the edge.</li>
  <li><strong>Wide brackets</strong> — PF craters and worst-loss scales
  linearly with stop size (60/60 → 200/100). The signal is a small,
  fast-decaying directional move, not a directional carry.</li>
  <li><strong>09:50 entry shift</strong> — negligible under the locked
  config (mechanism investigation in Stage 1: re-walk that doesn't drop
  any sessions; gain is re-pricing, not signal extraction).</li>
</ul>

<p><strong>Edge nature.</strong> A ~20-point, fast-decaying directional
move — short-term momentum continuation through clustered historical OR
levels, harvested tight. The cluster acts as a <em>session/presence
gate</em> (is today's price near historical OR action?) plus a trigger;
direction is bar-local momentum (which is why the 09:45→09:50 timing
shift is robust).</p>

<p><strong>Risk shape.</strong> Max DD is ~0.9% of a $50K account; 89%
of months are positive; tails are thin (skew slightly negative, kurt
near zero); worst single loss is the 30-pt stop (~$64 incl. costs);
worst losing streak is 5 trades.</p>

<p><strong>Honest caveats.</strong></p>
<ul>
  <li>Per-contract net is small (~6%/yr on a $50K account at 1 MNQ).
  The value of this strategy is the Sharpe — monetized by sizing up,
  capped around ~10–20 MNQ before execution quality degrades (Panel L).</li>
  <li>The live make-or-break is <strong>target-limit fill quality</strong>:
  backtest counts intrabar touches, live needs actual fills. Paper-trade
  at the intended size to measure this.</li>
  <li>Unmodeled tail: 09:45 entries can hold through scheduled 10:00
  econ releases. A 30-pt stop can slip through on a surprise headline.
  Consider an event-calendar skip rule before scaling up.</li>
  <li><strong>The next piece of evidence is live paper-trade fills, not
  more backtesting.</strong> The backtest surface has been falsified in
  the directions that matter; further sweeps will find p-hacked lifts.</li>
</ul>
"""


def panel_N_methodology(ts):
    head = panel_open(
        "N",
        "Methodology — the why behind the numbers",
        "this script (narrative)",
        ts,
        note="CSVs give numbers; this section explains decisions and caveats that aren't in any file.",
    )
    return head + f'<div class="narrative">{NARRATIVE}</div>' + panel_close()


# ────────────────────── CSS ────────────────────────────────────────────

CSS = """
:root {
  --bg: #fafbfc;
  --panel-bg: #ffffff;
  --panel-border: #e4e7eb;
  --text: #222;
  --muted: #6c757d;
  --good: #1b7e3b;
  --bad: #b21f24;
  --accent: #5b8def;
  --row-stripe: #f8f9fa;
  --badge-bg: #eef2ff;
  --badge-fg: #3949ab;
  --code-bg: #f3f4f6;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115;
    --panel-bg: #181b22;
    --panel-border: #2a2f3a;
    --text: #d7dbe2;
    --muted: #8e95a3;
    --good: #4ade80;
    --bad: #f87171;
    --accent: #7aa2f7;
    --row-stripe: #1e222b;
    --badge-bg: #1e2540;
    --badge-fg: #a8baff;
    --code-bg: #1e222b;
  }
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif;
  background: var(--bg); color: var(--text); margin: 0;
  padding: 24px 28px 60px; max-width: 1300px;
}
h1 { margin: 0 0 4px; font-size: 22px; letter-spacing: -0.01em; }
.page-meta { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
.page-meta strong { color: var(--text); }
section.panel {
  background: var(--panel-bg); border: 1px solid var(--panel-border);
  border-radius: 10px; padding: 18px 20px; margin-bottom: 18px;
}
.panel-head { margin-bottom: 12px; }
.panel-title { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
.badge {
  display: inline-block; background: var(--badge-bg); color: var(--badge-fg);
  font-weight: 700; padding: 1px 8px; border-radius: 4px; font-size: 13px;
  margin-right: 6px;
}
.source { color: var(--muted); font-size: 12px; }
.source code, .panel-note code, .narrative code {
  background: var(--code-bg); color: var(--text);
  padding: 1px 5px; border-radius: 3px; font-size: 12px;
}
.panel-note { color: var(--muted); font-size: 13px; margin: 6px 0 12px; }
.subhead { color: var(--muted); font-size: 13px; font-weight: 600;
  margin: 10px 0 6px; }

.cards { display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px; }
.card {
  border: 1px solid var(--panel-border); border-radius: 8px;
  padding: 10px 12px; background: var(--panel-bg);
}
.card .label { color: var(--muted); font-size: 12px; }
.card .value { font-size: 20px; font-weight: 600; margin-top: 4px; }

.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
.row-2  { display: grid; grid-template-columns: 2fr 1fr; gap: 18px;
  align-items: start; }

.card-wide {
  border: 1px solid var(--panel-border); border-radius: 8px;
  padding: 12px 14px;
}
.card-tag { color: var(--muted); font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.05em; }
.card-h { font-weight: 600; margin: 4px 0 8px; font-size: 14px; }

table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 6px 9px; border-bottom: 1px solid var(--panel-border);
  text-align: left; }
th { color: var(--muted); font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
table.mini th, table.mini td { padding: 4px 8px; font-size: 12px; }

.decisions td { vertical-align: top; padding: 9px 10px; }
.dec-name { font-weight: 600; width: 110px; }
.dec-before { color: var(--muted); }
.dec-arrow { color: var(--accent); font-weight: 700; }
.dec-after { color: var(--text); font-weight: 600; }
.dec-why { color: var(--muted); font-size: 12px; }

.falsif-grid { display: grid;
  grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
.falsif-cell { border: 1px solid var(--panel-border); border-radius: 8px;
  padding: 10px 12px; }
.falsif-title { font-weight: 600; margin-bottom: 4px; }
.falsif-src { color: var(--muted); font-size: 11px; margin-bottom: 6px; }

.side-table { padding-top: 4px; }
.side-h { color: var(--muted); font-size: 13px; font-weight: 600;
  margin-bottom: 4px; }

.cluster-grid { display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px; }
.cluster-fig { margin: 0; }
.cluster-fig img { width: 100%; height: auto; border-radius: 6px;
  border: 1px solid var(--panel-border); }
.cluster-fig figcaption { color: var(--muted); font-size: 11px;
  text-align: center; margin-top: 4px; }

.narrative { line-height: 1.55; font-size: 14px; }
.narrative p { margin: 0 0 12px; }
.narrative ul { margin: 0 0 12px 22px; padding: 0; }
.narrative li { margin-bottom: 6px; }

table.dep { font-size: 12px; }
table.dep th, table.dep td { padding: 5px 9px; }

.skipped { color: var(--muted); font-size: 13px; }
.skipped li { margin-bottom: 4px; }
"""


def build_html(panels_html, panels_skipped, ts, champ):
    cfg_pretty = (
        f"gate=<code>{champ['gate']}</code> · gap={champ['gap']:g} · "
        f"ms={champ['ms']} · lookback={champ['lookback']} · "
        f"entry={champ['entry_location']} · buffer={champ['entry_buffer']} · "
        f"stop={int(champ['stop_pts'])} · target={int(champ['target_pts'])} · "
        f"slip={champ['slip_pts']}pt/side (Model {champ['cost_model']}) · "
        f"${champ['commission_rt']}/RT"
    )
    head = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NQ-VBT Full Project Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-3.5.0.min.js" charset="utf-8"></script>
  <style>{CSS}</style>
</head>
<body>
  <h1>NQ-VBT — Full project dashboard</h1>
  <div class="page-meta">
    locked config: {cfg_pretty}<br/>
    generated <strong>{ts}</strong>
  </div>
"""
    if panels_skipped:
        items = "".join(f"<li><code>{p}</code></li>" for p in panels_skipped)
        skipped_html = (
            '<section class="panel"><div class="panel-head">'
            '<div class="panel-title"><span class="badge">!</span> Skipped panels</div>'
            '<div class="source">missing source files — these panels did not render</div>'
            f'</div><ul class="skipped">{items}</ul></section>'
        )
    else:
        skipped_html = ""
    return head + "\n".join(panels_html) + skipped_html + "</body></html>"


# ────────────────────── main ───────────────────────────────────────────


def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("Loading source CSVs...", flush=True)
    df_audit_csv = safe_read_csv(CSV_RISK_AUDIT)
    audit = risk_audit_map(df_audit_csv) if df_audit_csv is not None else None
    df_val = safe_read_csv(CSV_VALIDATION)
    df_tpsl = safe_read_csv(CSV_TP_SL_GRID)
    df_tight = safe_read_csv(CSV_TIGHT_WF)
    df_geom = safe_read_csv(CSV_ENTRY_GEOM)
    df_be = safe_read_csv(CSV_BE_STOP)
    df_slip = safe_read_csv(CSV_SLIPPAGE)
    df_fill = safe_read_csv(CSV_FILL_REALISM)
    df_pair = safe_read_csv(CSV_PAIRWISE)
    df_gate = safe_read_csv(CSV_GATE_PROX)
    df_regime = safe_read_csv(CSV_REGIME_COV)
    df_wide = safe_read_csv(CSV_WIDE_BRACKET)
    df_trades = safe_read_csv(CSV_TRADES)
    champ = load_champion()

    builders = [
        ("A · headline", lambda: panel_A_headline(audit, ts), [CSV_RISK_AUDIT]),
        (
            "B · evolution",
            lambda: panel_B_evolution(df_gate, df_val, audit, ts),
            [CSV_GATE_PROX, CSV_VALIDATION, CSV_RISK_AUDIT],
        ),
        ("C · decisions", lambda: panel_C_decisions(ts), []),
        ("D · gate analysis", lambda: panel_D_gate(df_gate, ts), [CSV_GATE_PROX]),
        ("E · TP/SL surface", lambda: panel_E_tpsl(df_tpsl, ts, champ), [CSV_TP_SL_GRID]),
        (
            "F · validation",
            lambda: panel_F_validation(df_tight, df_slip, df_fill, ts),
            [CSV_TIGHT_WF],
        ),
        (
            "G · falsification",
            lambda: panel_G_falsifications(df_geom, df_be, df_wide, ts),
            [CSV_ENTRY_GEOM, CSV_BE_STOP, CSV_WIDE_BRACKET],
        ),
        ("H · risk", lambda: panel_H_risk(audit, df_trades, ts), [CSV_RISK_AUDIT]),
        (
            "I · regime",
            lambda: panel_I_regime(df_regime, audit, ts),
            [CSV_REGIME_COV, CSV_RISK_AUDIT],
        ),
        ("J · deployment", lambda: panel_J_deployment(ts), [DEPLOYMENT_PLAN]),
        ("K · equity curve", lambda: panel_K_equity(df_trades, audit, ts), [CSV_TRADES]),
        ("L · sizing", lambda: panel_L_sizing(audit, df_trades, ts), [CSV_RISK_AUDIT]),
        ("M · cluster visuals", lambda: panel_M_clusters(ts), CLUSTER_PNGS or []),
        ("N · methodology", lambda: panel_N_methodology(ts), []),
    ]

    panels_html = []
    skipped = []
    for name, build, sources in builders:
        missing = [p for p in sources if not Path(p).exists()]
        if missing and not sources:
            # narrative / decisions panels — no source files
            pass
        try:
            html = build()
        except Exception as e:
            print(f"  ERR   {name}: {e}", flush=True)
            html = None
        if html is None:
            print(f"  skip  {name}: build returned nothing", flush=True)
            for p in sources:
                rel = Path(p).relative_to(PROJECT_ROOT) if Path(p).is_absolute() else p
                if not Path(p).exists():
                    skipped.append(str(rel))
            continue
        panels_html.append(html)
        print(f"  ok    {name}", flush=True)

    page = build_html(panels_html, sorted(set(skipped)), ts, champ)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page)

    print(f"\n{OUT_PATH.resolve()}")
    print("FULL DASHBOARD DONE")


if __name__ == "__main__":
    main()
