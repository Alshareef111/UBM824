"""Full backtest runner: V2 ADX(15,30) AND DI(15,8) unanimous + 40/40 R:R.

Reuses the R-012 deployment-winner classifier (ADX-DI unanimous AND-gate)
but on the 40/40 fork of simulator_v2. Saves the trade log, summary
metrics JSON, equity-curve PNG, and a markdown summary to:

    results/40_40_v2_full/<YYYYMMDD_HHMMSS>/
"""
from __future__ import annotations

import json
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from indicators.adx import AdxClassifier, precompute_lookup as adx_lookup
from indicators.di import DiClassifier, precompute_lookup as di_lookup
from indicators.base import UnanimousClassifier
from paths import BARS_PARQUET, ORB_TABLE_PARQUET, RESULTS_DIR, ensure_dirs
from simulator_v2_4040 import (
    POINT_VALUE_USD, STOP_POINTS, TARGET_POINTS,
    run_backtest, trades_to_dataframe,
)


def compute_metrics(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {"n_trades": 0}

    pnl = df["pnl_dollars"].to_numpy()
    wins = pnl > 0
    losses = pnl < 0
    flats = pnl == 0
    n = len(pnl)
    n_wins = int(wins.sum())
    n_losses = int(losses.sum())
    n_flats = int(flats.sum())

    total = float(pnl.sum())
    gross_win = float(pnl[wins].sum())
    gross_loss = float(-pnl[losses].sum())
    avg_win = float(pnl[wins].mean()) if n_wins else 0.0
    avg_loss = float(pnl[losses].mean()) if n_losses else 0.0
    expectancy = float(pnl.mean())
    win_rate = n_wins / n

    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    equity = pnl.cumsum()
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min())

    df_ = df.copy()
    df_["session_date_only"] = pd.to_datetime(df_["session_date"]).dt.date
    daily = df_.groupby("session_date_only")["pnl_dollars"].sum()
    if daily.std(ddof=1) > 0:
        sharpe_daily = float(daily.mean() / daily.std(ddof=1) * np.sqrt(252))
    else:
        sharpe_daily = 0.0
    if pnl.std(ddof=1) > 0:
        sharpe_trade = float(pnl.mean() / pnl.std(ddof=1))
    else:
        sharpe_trade = 0.0

    exits = {str(k): int(v) for k, v in df["exit_reason"].value_counts().items()}
    labels = (
        {str(k): int(v) for k, v in df["cluster_label"].value_counts().items()}
        if "cluster_label" in df.columns else {}
    )

    yearly = (
        df_.assign(year=pd.to_datetime(df_["session_date"]).dt.year)
           .groupby("year")["pnl_dollars"].agg(["sum", "count"])
           .rename(columns={"sum": "pnl", "count": "trades"})
    )
    yearly_dict = {int(y): {"pnl": float(r["pnl"]), "trades": int(r["trades"])}
                   for y, r in yearly.iterrows()}

    first_date = str(pd.to_datetime(df["session_date"]).min().date())
    last_date = str(pd.to_datetime(df["session_date"]).max().date())

    return {
        "n_trades": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "n_flats": n_flats,
        "win_rate": win_rate,
        "total_return_dollars": total,
        "total_return_points": float(df["pnl_points"].sum()),
        "expectancy_per_trade_dollars": expectancy,
        "avg_win_dollars": avg_win,
        "avg_loss_dollars": avg_loss,
        "gross_win_dollars": gross_win,
        "gross_loss_dollars": gross_loss,
        "profit_factor": profit_factor,
        "max_drawdown_dollars": max_dd,
        "sharpe_daily_annualized": sharpe_daily,
        "sharpe_per_trade": sharpe_trade,
        "exits": exits,
        "cluster_label_split": labels,
        "yearly_pnl": yearly_dict,
        "first_session": first_date,
        "last_session": last_date,
        "stop_points": STOP_POINTS,
        "target_points": TARGET_POINTS,
        "point_value_usd": POINT_VALUE_USD,
    }


def plot_equity_curve(df: pd.DataFrame, path, title_suffix: str) -> None:
    if len(df) == 0:
        return
    df = df.sort_values("entry_time").reset_index(drop=True)
    equity = df["pnl_dollars"].cumsum().to_numpy()
    x = pd.to_datetime(df["entry_time"]).to_numpy()
    peak = np.maximum.accumulate(equity)
    dd = equity - peak

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    ax1.plot(x, equity, color="#1f77b4", linewidth=1.2)
    ax1.axhline(0, color="black", linewidth=0.5, alpha=0.5)
    ax1.set_ylabel("Cumulative P&L ($)")
    ax1.set_title(f"40/40 R:R V2 ADX-DI unanimous — Equity Curve  ({title_suffix})")
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(x, dd, 0, color="#d62728", alpha=0.5)
    ax2.set_ylabel("Drawdown ($)")
    ax2.set_xlabel("Entry time")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close()


def render_summary_md(m: dict, classifier_name: str) -> str:
    if m.get("n_trades", 0) == 0:
        return "# 40/40 R:R V2 backtest\n\n**No trades produced.**\n"

    yearly_lines = [f"- {y}: ${r['pnl']:,.2f}  ({r['trades']} trades)"
                    for y, r in sorted(m["yearly_pnl"].items())]
    exit_lines = [f"- {k}: {v}" for k, v in m["exits"].items()]
    label_lines = [f"- {k}: {v}" for k, v in m["cluster_label_split"].items()]

    return (
        f"# 40/40 R:R V2 backtest summary\n\n"
        f"**Classifier:** {classifier_name}\n"
        f"**Bracket:** stop={m['stop_points']:.0f}pts / target={m['target_points']:.0f}pts "
        f"(${m['point_value_usd']:.2f}/pt)\n"
        f"**Period:** {m['first_session']} -> {m['last_session']}\n\n"
        f"## Headline\n"
        f"- Total trades: **{m['n_trades']:,}** ({m['n_wins']} W / {m['n_losses']} L / {m['n_flats']} flat)\n"
        f"- Win rate: **{m['win_rate']*100:.2f}%**\n"
        f"- Total return: **${m['total_return_dollars']:,.2f}** "
        f"({m['total_return_points']:.2f} pts)\n"
        f"- Profit factor: **{m['profit_factor']:.3f}**\n"
        f"- Expectancy: **${m['expectancy_per_trade_dollars']:.2f}/trade**\n"
        f"- Avg win: **${m['avg_win_dollars']:.2f}**  |  "
        f"Avg loss: **${m['avg_loss_dollars']:.2f}**\n"
        f"- Gross win: ${m['gross_win_dollars']:,.2f}  |  "
        f"Gross loss: ${m['gross_loss_dollars']:,.2f}\n"
        f"- Max drawdown: **${m['max_drawdown_dollars']:,.2f}**\n"
        f"- Sharpe (daily, annualized): **{m['sharpe_daily_annualized']:.3f}**\n"
        f"- Sharpe (per-trade): **{m['sharpe_per_trade']:.3f}**\n\n"
        f"## Yearly P&L\n" + "\n".join(yearly_lines) + "\n\n"
        f"## Exit reasons\n" + "\n".join(exit_lines) + "\n\n"
        f"## Classifier label split (clusters that traded)\n" + "\n".join(label_lines) + "\n"
    )


def main() -> None:
    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RESULTS_DIR / "40_40_v2_full" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output dir: {out_dir}", flush=True)
    print("Loading bars + ORB table...", flush=True)
    bars = pd.read_parquet(BARS_PARQUET)
    orb_table = pd.read_parquet(ORB_TABLE_PARQUET)
    print(f"  {len(bars):,} bars, {len(orb_table)} ORB sessions", flush=True)

    print("Precomputing ADX(15) and DI(15) lookups...", flush=True)
    adx_lk = adx_lookup(bars, n=15)
    di_lk = di_lookup(bars, n=15)
    clf_adx = AdxClassifier(adx_lk, n=15, threshold=30)
    clf_di = DiClassifier(di_lk, n=15, threshold=8)
    classifier = UnanimousClassifier(
        [clf_adx, clf_di],
        name="V2 ADX(15,30) AND DI(15,8) unanimous @ 40/40",
    )

    print(f"Running backtest  (STOP={STOP_POINTS}, TARGET={TARGET_POINTS})...", flush=True)
    trades = run_backtest(bars, orb_table, classifier)
    df = trades_to_dataframe(trades)
    print(f"  {len(df)} trades", flush=True)

    df.to_parquet(out_dir / "trades.parquet", index=False)
    df.to_csv(out_dir / "trades.csv", index=False)
    print(f"Wrote trades.parquet and trades.csv", flush=True)

    metrics = compute_metrics(df)
    (out_dir / "summary.json").write_text(json.dumps(metrics, indent=2, default=str))
    print("Wrote summary.json", flush=True)

    title_suffix = (
        f"{metrics['n_trades']} trades, "
        f"${metrics['total_return_dollars']:,.0f}, "
        f"{metrics['win_rate']*100:.1f}% WR"
    )
    plot_equity_curve(df, out_dir / "equity_curve.png", title_suffix)
    print("Wrote equity_curve.png", flush=True)

    md = render_summary_md(metrics, classifier.name)
    (out_dir / "summary.md").write_text(md)
    print("Wrote summary.md", flush=True)

    print("\n" + "=" * 70, flush=True)
    print(md, flush=True)
    print("=" * 70, flush=True)
    print(f"\nArtifacts: {out_dir}", flush=True)


if __name__ == "__main__":
    main()
