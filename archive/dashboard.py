"""
src/dashboard.py — Build a single self-contained HTML dashboard from result CSVs.

Reads result CSVs from results/ (no hardcoded metrics, just panel structure).
Panels auto-skip if their source CSV is absent, so the dashboard runs in any
state of the pipeline.

Run from project root:
    python -m src.dashboard
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "results"

CSV_GATE       = RESULTS / "vbt_gate_proximity_sweep.csv"
CSV_VALIDATION = RESULTS / "within200_validation.csv"
CSV_PAIRWISE   = RESULTS / "vbt_pairwise_sweep.csv"
CSV_ADX_GRID   = RESULTS / "within200_adx_grid.csv"
CHAMPION_HINT  = RESULTS / "current_best.json"

# Fallback champion / baseline if no override file is present.
DEFAULT_CHAMPION = {"gate": "within_200", "gap": 7.0, "ms": 2}
BASELINE_C       = {"gate": "inside_OR",  "gap": 7.0, "ms": 2}

OUT_PATH = RESULTS / "dashboard.html"


# ─── Helpers ──────────────────────────────────────────────────────────────

def safe_read_csv(path):
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"  warn: failed to read {path}: {e}", flush=True)
        return None


def load_champion():
    """Prefer results/current_best.json if it exists, else DEFAULT_CHAMPION."""
    if CHAMPION_HINT.exists():
        try:
            return json.loads(CHAMPION_HINT.read_text())
        except Exception:
            pass
    return DEFAULT_CHAMPION


def fmt_money(v):
    if v is None or pd.isna(v):
        return "—"
    return f"${v:+,.0f}"


def fmt_pct(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{v * 100:.1f}%"


def fmt_num(v, n=3):
    if v is None or pd.isna(v):
        return "—"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    return f"{v:.{n}f}"


def fig_to_div(fig, panel_id):
    """Embed figure without including plotly.js (loaded once in <head>)."""
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="-apple-system, BlinkMacSystemFont, Helvetica, Arial",
                  size=12, color="#333"),
        margin=dict(l=50, r=30, t=40, b=40),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=panel_id)


def gate_row(df_gate, gate, gap, ms):
    """Return the single row from vbt_gate_proximity_sweep.csv at this combo."""
    m = (df_gate["gate"] == gate) & (df_gate["gap"] == gap) & (df_gate["ms"] == ms)
    if not m.any():
        return None
    return df_gate.loc[m].iloc[0].to_dict()


# ─── Panel builders (each returns an HTML string or None) ─────────────────

def panel_headline(df_gate, ts):
    if df_gate is None:
        return None
    champ = load_champion()
    c_row = gate_row(df_gate, champ["gate"], float(champ["gap"]), int(champ["ms"]))
    b_row = gate_row(df_gate, BASELINE_C["gate"], BASELINE_C["gap"], BASELINE_C["ms"])
    if c_row is None or b_row is None:
        return None

    # (label, key_in_csv, formatter, higher_is_better)
    fields = [
        ("net",     "net_dollars",   fmt_money, True),
        ("PF",      "profit_factor", lambda v: fmt_num(v, 3), True),
        ("Sharpe",  "sharpe_approx", lambda v: fmt_num(v, 2), True),
        ("max_dd",  "max_drawdown",  fmt_money, True),  # less negative = better
        ("trades",  "n_trades",      lambda v: fmt_num(int(v) if pd.notna(v) else v, 0), True),
        ("WR",      "win_rate",      fmt_pct, True),
    ]

    cards_html = []
    for label, key, fmt, higher_better in fields:
        v_c = c_row.get(key)
        v_b = b_row.get(key)
        delta = v_c - v_b if (v_c is not None and v_b is not None
                              and pd.notna(v_c) and pd.notna(v_b)) else None
        if delta is None:
            delta_cls = ""
            delta_str = "—"
        else:
            better = (delta > 0) if higher_better else (delta < 0)
            delta_cls = "up" if better else ("down" if delta != 0 else "")
            if key in ("net_dollars", "max_drawdown"):
                delta_str = f"{delta:+,.0f}"
            elif key == "n_trades":
                delta_str = f"{int(delta):+,}"
            elif key == "win_rate":
                delta_str = f"{delta * 100:+.1f}pp"
            else:
                delta_str = f"{delta:+.3f}"
        cards_html.append(
            f'<div class="card">'
            f'  <div class="label">{label}</div>'
            f'  <div class="value">{fmt(v_c)}</div>'
            f'  <div class="delta {delta_cls}">vs C: {delta_str}</div>'
            f'</div>'
        )

    champion_tag = (
        f'{champ["gate"]} · gap={champ["gap"]} · ms={champ["ms"]}'
    )
    baseline_tag = (
        f'{BASELINE_C["gate"]} · gap={BASELINE_C["gap"]} · ms={BASELINE_C["ms"]}'
    )
    return f'''
<div class="panel">
  <div class="panel-head">
    <h2>1 · Champion vs prior baseline</h2>
    <div class="source">champion: <code>{champion_tag}</code>  ·  baseline (C): <code>{baseline_tag}</code></div>
    <div class="source">source: <code>results/vbt_gate_proximity_sweep.csv</code>  ·  generated {ts}</div>
  </div>
  <div class="cards">
    {''.join(cards_html)}
  </div>
</div>
'''


def panel_gate_sweet_spot(df_gate, ts):
    if df_gate is None:
        return None
    sub = df_gate[(df_gate["gap"] == 7.0) & (df_gate["ms"] == 2)].copy()
    if sub.empty:
        return None

    gate_order = ["inside_OR", "within_100", "within_200", "no_gate"]
    sub = sub.assign(
        order=sub["gate"].map({g: i for i, g in enumerate(gate_order)})
    ).dropna(subset=["order"]).sort_values("order")
    if sub.empty:
        return None

    pf_peak_idx = sub["profit_factor"].idxmax()
    pf_peak_gate = sub.loc[pf_peak_idx, "gate"]
    pf_peak_val = sub.loc[pf_peak_idx, "profit_factor"]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=sub["gate"], y=sub["net_dollars"],
        name="net $",
        marker_color="#5b8def",
        yaxis="y",
        hovertemplate="<b>%{x}</b><br>net = %{y:$,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=sub["gate"], y=sub["profit_factor"],
        name="PF",
        mode="lines+markers",
        line=dict(color="#d97706", width=2.5),
        marker=dict(size=9),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>PF = %{y:.3f}<extra></extra>",
    ))
    fig.add_annotation(
        x=pf_peak_gate, y=pf_peak_val,
        text=f"PF peak {pf_peak_val:.3f}",
        showarrow=True, arrowhead=2, arrowsize=1.0, arrowcolor="#d97706",
        ax=0, ay=-30,
        font=dict(color="#a04a00"),
        yref="y2",
    )
    fig.update_layout(
        title=None,
        barmode="group",
        yaxis=dict(title="net $", tickformat=",.0f", gridcolor="#eee"),
        yaxis2=dict(title="PF", overlaying="y", side="right",
                    showgrid=False),
        legend=dict(orientation="h", x=0, y=1.12),
        height=380,
    )

    return f'''
<div class="panel">
  <div class="panel-head">
    <h2>2 · Gate sweet-spot (gap=7 · ms=2)</h2>
    <div class="source">source: <code>results/vbt_gate_proximity_sweep.csv</code>  ·  generated {ts}</div>
  </div>
  {fig_to_div(fig, "panel-gate-sweet")}
</div>
'''


def panel_walkforward_pf(df_val, ts):
    if df_val is None:
        return None
    splits = ["train", "test", "holdout"]
    sub = df_val[df_val["period"].isin(splits)].copy()
    if sub.empty:
        return None

    sub["period"] = pd.Categorical(sub["period"], categories=splits, ordered=True)
    sub = sub.sort_values(["gate", "period"])

    color_map = {
        "inside_OR":  "#1f77b4",
        "within_100": "#ff7f0e",
        "within_200": "#2ca02c",
        "no_gate":    "#d62728",
    }

    fig = go.Figure()
    for gate, g in sub.groupby("gate"):
        fig.add_trace(go.Scatter(
            x=[str(p) for p in g["period"]],
            y=g["PF"],
            mode="lines+markers",
            name=gate,
            line=dict(color=color_map.get(gate, "#888"), width=2.5),
            marker=dict(size=10),
            hovertemplate=f"<b>{gate}</b><br>%{{x}}: PF = %{{y:.3f}}<extra></extra>",
        ))

    fig.add_hline(y=1.0, line=dict(color="#999", dash="dash", width=1),
                  annotation_text="breakeven", annotation_position="bottom right")

    fig.update_layout(
        yaxis=dict(title="profit factor", gridcolor="#eee"),
        xaxis=dict(title="split"),
        legend=dict(orientation="h", x=0, y=1.12),
        height=380,
    )

    return f'''
<div class="panel">
  <div class="panel-head">
    <h2>3 · Walk-forward PF — train → test → holdout</h2>
    <div class="source">source: <code>results/within200_validation.csv</code>  ·  generated {ts}</div>
  </div>
  {fig_to_div(fig, "panel-wf")}
</div>
'''


def panel_2024_stress(df_val, ts):
    if df_val is None:
        return None
    sub = df_val[df_val["period"] == "2024_Mar_Oct"].copy()
    sub = sub[sub["gate"].isin(["inside_OR", "within_200"])]
    if sub.empty:
        return None

    c = sub[sub["gate"] == "inside_OR"].iloc[0] if (sub["gate"] == "inside_OR").any() else None
    w = sub[sub["gate"] == "within_200"].iloc[0] if (sub["gate"] == "within_200").any() else None
    if c is None or w is None:
        return None

    metrics = [
        ("trades",  "n_trades",      lambda v: fmt_num(int(v) if pd.notna(v) else v, 0), True),
        ("net",     "net",           fmt_money, True),
        ("PF",      "PF",            lambda v: fmt_num(v, 3), True),
        ("max_dd",  "max_dd",        fmt_money, True),
    ]
    rows_html = []
    for label, key, fmt, higher_better in metrics:
        v_c, v_w = c[key], w[key]
        if pd.notna(v_c) and pd.notna(v_w):
            delta = v_w - v_c
            better = (delta > 0) if higher_better else (delta < 0)
            cls = "up" if better else ("down" if delta != 0 else "")
            if key in ("net", "max_dd"):
                delta_s = f"{delta:+,.0f}"
            elif key == "n_trades":
                delta_s = f"{int(delta):+,}"
            else:
                delta_s = f"{delta:+.3f}"
        else:
            cls, delta_s = "", "—"
        rows_html.append(
            f"<tr><td>{label}</td>"
            f"<td>{fmt(v_c)}</td>"
            f"<td>{fmt(v_w)}</td>"
            f"<td class='{cls}'>{delta_s}</td></tr>"
        )

    return f'''
<div class="panel">
  <div class="panel-head">
    <h2>4 · 2024 Mar-Oct stress window</h2>
    <div class="source">source: <code>results/within200_validation.csv</code>  ·  generated {ts}</div>
  </div>
  <table class="stress">
    <thead><tr><th>metric</th><th>C (inside_OR)</th><th>within_200</th><th>Δ</th></tr></thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</div>
'''


def panel_leaderboard(df_pair, ts):
    if df_pair is None:
        return None
    df = df_pair.rename(columns={
        "lookback": "lb", "min_size": "ms", "n_trades": "trades",
        "win_rate": "WR", "net_dollars": "net", "profit_factor": "PF",
        "max_drawdown": "max_dd", "sharpe_approx": "Sharpe",
    })
    valid = df[df["trades"] >= 200].copy()
    if valid.empty:
        return None
    cols = ["lb", "gap", "ms", "trades", "PF", "net", "max_dd", "Sharpe"]
    top_net = valid.sort_values("net", ascending=False).head(10)[cols]
    top_pf  = valid.sort_values("PF",  ascending=False).head(10)[cols]

    def table_html(df_top, headline):
        rows = []
        for _, r in df_top.iterrows():
            rows.append(
                "<tr>"
                f"<td>{int(r['lb'])}</td>"
                f"<td>{r['gap']:.1f}</td>"
                f"<td>{int(r['ms'])}</td>"
                f"<td>{int(r['trades'])}</td>"
                f"<td>{r['PF']:.3f}</td>"
                f"<td>{r['net']:+,.0f}</td>"
                f"<td>{r['max_dd']:+,.0f}</td>"
                f"<td>{r['Sharpe']:.2f}</td>"
                "</tr>"
            )
        return (
            f"<div class='lb-block'>"
            f"<h3>{headline}</h3>"
            f"<table>"
            f"<thead><tr><th>lb</th><th>gap</th><th>ms</th><th>trades</th>"
            f"<th>PF</th><th>net</th><th>max_dd</th><th>Sharpe</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table></div>"
        )

    return f'''
<div class="panel">
  <div class="panel-head">
    <h2>5 · Cluster sweep leaderboard (trades ≥ 200)</h2>
    <div class="source">source: <code>results/vbt_pairwise_sweep.csv</code>  ·  generated {ts}</div>
  </div>
  <div class="grid-2">
    {table_html(top_net, "Top 10 by net")}
    {table_html(top_pf,  "Top 10 by PF")}
  </div>
</div>
'''


def panel_adx_grid(df_adx, ts):
    if df_adx is None:
        return None
    # Try to be flexible about the schema — accept any of these for the "best"
    # selection metric and surface top-3 by each.
    metric_cols = [c for c in ("profit_factor", "net_dollars", "sharpe_approx")
                   if c in df_adx.columns]
    if not metric_cols:
        return None

    body_parts = ["<table><thead><tr>"]
    body_parts.append(
        "".join(f"<th>{c}</th>" for c in df_adx.columns) + "</tr></thead><tbody>"
    )
    # Highlight rows: no-filter (adx=0 or label) and (30,8) when present.
    for _, r in df_adx.head(20).iterrows():
        body_parts.append("<tr>")
        for c in df_adx.columns:
            v = r[c]
            if isinstance(v, float):
                if abs(v) >= 1000:
                    s = f"{v:+,.0f}"
                else:
                    s = f"{v:.3f}"
            else:
                s = str(v)
            body_parts.append(f"<td>{s}</td>")
        body_parts.append("</tr>")
    body_parts.append("</tbody></table>")

    return f'''
<div class="panel">
  <div class="panel-head">
    <h2>6 · ADX-on-within_200 grid</h2>
    <div class="source">source: <code>results/within200_adx_grid.csv</code>  ·  generated {ts}</div>
  </div>
  {''.join(body_parts)}
</div>
'''


# ─── Page template ────────────────────────────────────────────────────────

CSS = """
:root {
  --bg: #fdfdfd;
  --fg: #1d1d1f;
  --muted: #6b6b6b;
  --panel-bg: #ffffff;
  --panel-border: #e7e7e7;
  --card-bg: #f7f7f9;
  --card-border: #e3e3e6;
  --row-stripe: #fafafa;
  --good: #157f3c;
  --bad: #b2241a;
  --link: #2962ff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115;
    --fg: #e9eaee;
    --muted: #9aa0aa;
    --panel-bg: #181b22;
    --panel-border: #2a2e38;
    --card-bg: #1f232c;
    --card-border: #2f343f;
    --row-stripe: #1c1f27;
    --good: #57d27e;
    --bad: #ff7867;
    --link: #6b9bff;
  }
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--fg);
  margin: 0;
  padding: 28px 32px 60px;
  line-height: 1.45;
}
h1 { margin: 0 0 6px; font-size: 22px; }
.page-meta { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
.panel {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 10px;
  padding: 18px 22px 22px;
  margin-bottom: 22px;
}
.panel-head { margin-bottom: 14px; }
.panel h2 { margin: 0 0 4px; font-size: 15px; font-weight: 600; }
.source { color: var(--muted); font-size: 12px; }
.source code { background: var(--card-bg); padding: 1px 6px; border-radius: 3px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; }
.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 12px 16px;
  min-width: 130px;
  flex: 0 0 auto;
}
.card .label {
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  font-weight: 600;
}
.card .value { font-size: 21px; font-weight: 600; margin-top: 3px; }
.card .delta { font-size: 12px; margin-top: 3px; color: var(--muted); }
.delta.up { color: var(--good); }
.delta.down { color: var(--bad); }
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
}
th, td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--panel-border);
  text-align: right;
}
th { color: var(--muted); font-weight: 600; }
th:first-child, td:first-child { text-align: left; }
tbody tr:nth-child(even) { background: var(--row-stripe); }
td.up { color: var(--good); }
td.down { color: var(--bad); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.lb-block h3 { margin: 0 0 6px; font-size: 13px; color: var(--muted); font-weight: 600; }
table.stress { max-width: 560px; }
.skipped { color: var(--muted); font-size: 13px; padding: 8px 0; }
"""


def build_html(panels_html, panels_skipped, ts):
    head = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NQ-VBT Strategy Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-3.5.0.min.js" charset="utf-8"></script>
  <style>{CSS}</style>
</head>
<body>
  <h1>NQ-VBT Strategy Dashboard</h1>
  <div class="page-meta">generated <strong>{ts}</strong></div>
"""
    skipped_html = ""
    if panels_skipped:
        items = "".join(f"<li><code>{p}</code></li>" for p in panels_skipped)
        skipped_html = (
            f'<div class="panel"><div class="panel-head"><h2>Skipped panels</h2>'
            f'<div class="source">missing source CSVs</div></div>'
            f'<ul class="skipped">{items}</ul></div>'
        )
    tail = "</body></html>"
    return head + "\n".join(panels_html) + skipped_html + tail


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    df_gate = safe_read_csv(CSV_GATE)
    df_val  = safe_read_csv(CSV_VALIDATION)
    df_pair = safe_read_csv(CSV_PAIRWISE)
    df_adx  = safe_read_csv(CSV_ADX_GRID)

    builders = [
        ("Panel 1: headline cards",        lambda: panel_headline(df_gate, ts),
         CSV_GATE if df_gate is None else None),
        ("Panel 2: gate sweet-spot",       lambda: panel_gate_sweet_spot(df_gate, ts),
         CSV_GATE if df_gate is None else None),
        ("Panel 3: walk-forward PF",       lambda: panel_walkforward_pf(df_val, ts),
         CSV_VALIDATION if df_val is None else None),
        ("Panel 4: 2024 Mar-Oct stress",   lambda: panel_2024_stress(df_val, ts),
         CSV_VALIDATION if df_val is None else None),
        ("Panel 5: cluster leaderboard",   lambda: panel_leaderboard(df_pair, ts),
         CSV_PAIRWISE if df_pair is None else None),
        ("Panel 6: ADX-on-within_200",     lambda: panel_adx_grid(df_adx, ts),
         CSV_ADX_GRID if df_adx is None else None),
    ]

    panels_html = []
    skipped = []
    for name, build, missing_csv in builders:
        if missing_csv is not None:
            print(f"  skip  {name}: missing {missing_csv.name}", flush=True)
            skipped.append(str(missing_csv.relative_to(PROJECT_ROOT)))
            continue
        html = build()
        if html is None:
            print(f"  skip  {name}: build returned nothing", flush=True)
            continue
        panels_html.append(html)
        print(f"  ok    {name}", flush=True)

    page = build_html(panels_html, skipped, ts)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page)

    print(f"\n{OUT_PATH.resolve()}")
    print("DASHBOARD DONE")


if __name__ == "__main__":
    main()
