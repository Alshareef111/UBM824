"""Cost-adjusted re-run for V2 + 40/40 on MNQ / NinjaTrader Free.

Cost model (conservative defaults):
  Commission: $0.87/side all-in ($0.35 broker + $0.37 exchange + $0.15 NFA)
              = $1.74/round-trip per contract
  Slippage:   1 tick/side at MNQ tick value $0.50 = $1.00/round-trip
  Total RT:   $2.74 per contract

Input:  results/40_40_v2_full/20260514_125349/trades.parquet (sha256 1ccf859e...feb)
Output: results/cost_adjusted/trades_cost_adjusted_mnq_20260516.parquet
        (with cost_commission, cost_slippage, cost_total, pnl_net columns added)

Read-only on the locked baseline (data/processed/trades.parquet).
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

CANDIDATE_TRADES = Path("results/40_40_v2_full/20260514_125349/trades.parquet")
LOCKED_BASELINE = Path("data/processed/trades.parquet")
OUT_DIR = Path("results/cost_adjusted")
OUT_PATH = OUT_DIR / "trades_cost_adjusted_mnq_20260516.parquet"

# Cost model (per contract per round-trip, in USD)
COMMISSION_RT = 0.87 * 2     # $1.74
SLIPPAGE_RT = 0.50 * 2       # $1.00  (1 tick/side x $0.50/tick)
COST_RT = COMMISSION_RT + SLIPPAGE_RT  # $2.74

CONTRACTS_PER_TRADE = 1  # implicit in simulator (sec5.5 of strategy-reference)


def sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def headline_metrics(pnl: pd.Series, session_dates: pd.Series) -> dict:
    """Compute headline stats from a P&L series + matching session_date series."""
    n = len(pnl)
    wins_mask = pnl > 0
    losses_mask = pnl < 0
    n_wins = int(wins_mask.sum())
    n_losses = int(losses_mask.sum())
    n_flats = n - n_wins - n_losses

    total = float(pnl.sum())
    avg_win = float(pnl[wins_mask].mean()) if n_wins else 0.0
    avg_loss = float(pnl[losses_mask].mean()) if n_losses else 0.0
    expectancy = float(pnl.mean())
    win_rate = n_wins / n if n else 0.0

    gross_win = float(pnl[wins_mask].sum())
    gross_loss_abs = -float(pnl[losses_mask].sum())
    if gross_loss_abs > 0:
        pf = gross_win / gross_loss_abs
    elif gross_win > 0:
        pf = float("inf")
    else:
        pf = 0.0

    # Daily-aggregated Sharpe
    daily = pd.DataFrame({"sd": pd.to_datetime(session_dates).dt.date, "pnl": pnl.values})
    daily = daily.groupby("sd")["pnl"].sum()
    if daily.std(ddof=1) > 0:
        sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(252))
    else:
        sharpe = 0.0

    # Max drawdown
    equity = pnl.cumsum().to_numpy()
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min())

    return {
        "n_trades": n, "n_wins": n_wins, "n_losses": n_losses, "n_flats": n_flats,
        "win_rate": win_rate, "total_pnl": total, "avg_win": avg_win, "avg_loss": avg_loss,
        "expectancy": expectancy, "profit_factor": pf, "sharpe_daily_annualized": sharpe,
        "max_drawdown": max_dd,
    }


def fmt_money(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    if x == float("inf"):
        return "inf"
    return f"${x:,.2f}"


def fmt_pct(x):
    return f"{x*100:.2f}%"


def print_comparison(label, gross_m, net_m):
    """Print | Metric | Gross | Net | Delta | Delta% |"""
    print(f"\n=== {label} ===")
    print(f"| {'Metric':<25} | {'Gross':>14} | {'Net':>14} | {'Delta':>14} | {'Delta%':>10} |")
    print(f"| {'-'*25} | {'-'*14} | {'-'*14} | {'-'*14} | {'-'*10} |")

    def row(name, g, n, fmt=fmt_money, pct_base=None):
        d = n - g
        if pct_base is None:
            pct_base = g
        dpct = (d / pct_base * 100) if (pct_base and abs(pct_base) > 1e-9) else 0.0
        print(f"| {name:<25} | {fmt(g):>14} | {fmt(n):>14} | {fmt(d):>14} | {dpct:>9.2f}% |")

    # Trades & WR are gross==net (cost doesn't change them)
    g_wlf = f"{gross_m['n_wins']}/{gross_m['n_losses']}/{gross_m['n_flats']}"
    n_wlf = f"{net_m['n_wins']}/{net_m['n_losses']}/{net_m['n_flats']}"
    wr_delta = f"{(net_m['win_rate']-gross_m['win_rate'])*100:+.2f}pp"
    print(f"| {'Trades':<25} | {gross_m['n_trades']:>14} | {net_m['n_trades']:>14} | {0:>14} | {'-':>10} |")
    print(f"| {'Wins / Losses / Flats':<25} | {g_wlf:>14} | {n_wlf:>14} | {'':>14} | {'-':>10} |")
    print(f"| {'Win rate':<25} | {fmt_pct(gross_m['win_rate']):>14} | {fmt_pct(net_m['win_rate']):>14} | {wr_delta:>14} | {'-':>10} |")
    row("Total P&L", gross_m["total_pnl"], net_m["total_pnl"])
    row("Avg winner", gross_m["avg_win"], net_m["avg_win"])
    row("Avg loser", gross_m["avg_loss"], net_m["avg_loss"])
    row("Expectancy / trade", gross_m["expectancy"], net_m["expectancy"])
    row("Profit factor", gross_m["profit_factor"], net_m["profit_factor"], fmt=lambda x: f"{x:.4f}")
    row("Sharpe (daily ann.)", gross_m["sharpe_daily_annualized"], net_m["sharpe_daily_annualized"], fmt=lambda x: f"{x:.4f}")
    row("Max drawdown", gross_m["max_drawdown"], net_m["max_drawdown"])


def main():
    print(f"Cost model:")
    print(f"  Commission RT:  ${COMMISSION_RT:.2f}  (${COMMISSION_RT/2:.2f}/side x 2)")
    print(f"  Slippage RT:    ${SLIPPAGE_RT:.2f}  (1 tick/side x $0.50/tick x 2)")
    print(f"  Total RT cost:  ${COST_RT:.2f}/contract")
    print(f"  Contracts/trade: {CONTRACTS_PER_TRADE} (implicit per simulator design - sec5.5)")
    print()
    print(f"Input candidate:  {CANDIDATE_TRADES}")
    print(f"Candidate sha256: {sha256(CANDIDATE_TRADES)}")
    print(f"Locked baseline:  {LOCKED_BASELINE}")
    print(f"Locked sha256:    {sha256(LOCKED_BASELINE)}")
    print()

    df = pd.read_parquet(CANDIDATE_TRADES).copy()
    assert len(df) == 908, f"expected 908 trades, got {len(df)}"

    # Add cost columns
    df["cost_commission"] = COMMISSION_RT * CONTRACTS_PER_TRADE
    df["cost_slippage"] = SLIPPAGE_RT * CONTRACTS_PER_TRADE
    df["cost_total"] = COST_RT * CONTRACTS_PER_TRADE
    df["pnl_gross"] = df["pnl_dollars"]
    df["pnl_net"] = df["pnl_gross"] - df["cost_total"]

    # === Overall metrics ===
    gross_all = headline_metrics(df["pnl_gross"], df["session_date"])
    net_all = headline_metrics(df["pnl_net"], df["session_date"])
    print_comparison("Overall (V2 + 40/40, 908 trades)", gross_all, net_all)

    # === Per-label metrics ===
    for label in ("FADE", "TREND"):
        sub = df[df["cluster_label"] == label]
        g = headline_metrics(sub["pnl_gross"], sub["session_date"])
        n = headline_metrics(sub["pnl_net"], sub["session_date"])
        print_comparison(f"{label} only ({len(sub)} trades)", g, n)

    # === Total cost breakdown ===
    total_cost = df["cost_total"].sum()
    print(f"\n=== Cost accounting ===")
    print(f"  Total cost applied:        ${total_cost:,.2f}  ({len(df)} trades x ${COST_RT:.2f})")
    print(f"  Commission portion:        ${df['cost_commission'].sum():,.2f}  ({COMMISSION_RT/COST_RT*100:.1f}% of total cost)")
    print(f"  Slippage portion:          ${df['cost_slippage'].sum():,.2f}  ({SLIPPAGE_RT/COST_RT*100:.1f}% of total cost)")
    print(f"  Gross headline P&L:        ${gross_all['total_pnl']:,.2f}")
    print(f"  Net headline P&L:          ${net_all['total_pnl']:,.2f}")
    print(f"  Cost-induced reduction:    {(1 - net_all['total_pnl']/gross_all['total_pnl'])*100:.2f}% of headline")

    # === 4-gate qualification check (net) ===
    # Gate 4 (net total > 0) is the only one impacted by per-trade cost; sharpe/sign/median needs
    # walk-forward - flagged for future re-run, not computed here.
    print(f"\n=== 4-gate qualification (net) - only gate 4 derivable here ===")
    print(f"  Gate 4 (total P&L > 0):    {'PASS' if net_all['total_pnl'] > 0 else 'FAIL'}  (net ${net_all['total_pnl']:,.2f})")
    print(f"  Gates 1-3 (median OOS, sign stability, WF Sharpe-like) - require walk-forward")
    print(f"    re-run with per-trade cost applied; not computed here (queued sec9.2).")

    # === Write parquet ===
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_cols = list(df.columns)
    df[out_cols].to_parquet(OUT_PATH, index=False)
    print(f"\nWrote: {OUT_PATH}")
    print(f"  rows: {len(df)} | cols: {len(out_cols)}")
    print(f"  output sha256: {sha256(OUT_PATH)}")

    # === Final sha256 verification ===
    print(f"\n=== Locked baseline integrity ===")
    print(f"  Pre-script:  d24f128ac88227900ac6d44047f0f51e5a5906011e683643a925c63feb15f4c6 (expected)")
    print(f"  Post-script: {sha256(LOCKED_BASELINE)}")
    print(f"  Match: {sha256(LOCKED_BASELINE) == 'd24f128ac88227900ac6d44047f0f51e5a5906011e683643a925c63feb15f4c6'}")


if __name__ == "__main__":
    main()
