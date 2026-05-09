"""Robustness checks on trades.parquet from the reverted best-config backtest."""

from pathlib import Path

import pandas as pd

from paths import TRADES_PARQUET


def fmt_money(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.2f}"


def yearly_split(df: pd.DataFrame) -> None:
    print("=" * 72)
    print("1) YEARLY P&L SPLIT")
    print("=" * 72)
    df = df.copy()
    df["year"] = df["session_date"].dt.year

    rows = []
    for year, sub in df.groupby("year", sort=True):
        n = len(sub)
        wins = (sub["pnl_points"] > 0).sum()
        wr = wins / n * 100 if n else 0.0
        pts = sub["pnl_points"].sum()
        usd = sub["pnl_dollars"].sum()
        exp_pts = sub["pnl_points"].mean() if n else 0.0
        exp_usd = sub["pnl_dollars"].mean() if n else 0.0
        rows.append((year, n, wr, pts, usd, exp_pts, exp_usd))

    print(f"{'Year':<6} {'Trades':>7} {'WinRate':>8} {'PnL pts':>10} "
          f"{'PnL $':>12} {'E[pts]':>9} {'E[$]':>9}")
    print("-" * 72)
    for year, n, wr, pts, usd, exp_pts, exp_usd in rows:
        print(f"{year:<6} {n:>7} {wr:>7.1f}% {pts:>10.2f} "
              f"{fmt_money(usd):>12} {exp_pts:>9.3f} {exp_usd:>9.3f}")
    print()


def monthly_split(df: pd.DataFrame) -> None:
    print("=" * 72)
    print("2) MONTHLY P&L BREAKDOWN")
    print("=" * 72)
    df = df.copy()
    df["month"] = df["session_date"].dt.to_period("M")

    rows = []
    for m, sub in df.groupby("month", sort=True):
        n = len(sub)
        wins = (sub["pnl_points"] > 0).sum()
        wr = wins / n * 100 if n else 0.0
        usd = sub["pnl_dollars"].sum()
        rows.append((str(m), n, wr, usd))

    print(f"{'Month':<10} {'Trades':>7} {'WinRate':>8} {'PnL $':>12}")
    print("-" * 42)
    for m, n, wr, usd in rows:
        print(f"{m:<10} {n:>7} {wr:>7.1f}% {fmt_money(usd):>12}")

    profitable = sum(1 for _, _, _, u in rows if u > 0)
    losing = sum(1 for _, _, _, u in rows if u < 0)
    flat = sum(1 for _, _, _, u in rows if u == 0)
    best_m, best_usd = max(((m, u) for m, _, _, u in rows), key=lambda x: x[1])
    worst_m, worst_usd = min(((m, u) for m, _, _, u in rows), key=lambda x: x[1])

    print()
    print(f"  Profitable months: {profitable}")
    print(f"  Losing months:     {losing}")
    if flat:
        print(f"  Flat months:       {flat}")
    print(f"  Best month:  {best_m}  {fmt_money(best_usd)}")
    print(f"  Worst month: {worst_m}  {fmt_money(worst_usd)}")
    print()


def drawdown_analysis(df: pd.DataFrame) -> None:
    print("=" * 72)
    print("3) MAXIMUM DRAWDOWN")
    print("=" * 72)
    df = df.sort_values("entry_time").reset_index(drop=True).copy()
    df["equity"] = df["pnl_dollars"].cumsum()
    df["peak"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] - df["peak"]

    max_dd = df["drawdown"].min()
    trough_idx = df["drawdown"].idxmin()
    trough_equity = df.loc[trough_idx, "equity"]
    trough_peak = df.loc[trough_idx, "peak"]
    trough_date = df.loc[trough_idx, "session_date"]

    # Find the peak that preceded this trough (last index <= trough_idx where equity == peak at that point)
    pre_trough = df.loc[:trough_idx]
    peak_idx = pre_trough[pre_trough["equity"] == trough_peak].index[0]
    peak_date = df.loc[peak_idx, "session_date"]

    # Recovery: first index after trough where equity returns to peak
    after_trough = df.loc[trough_idx:]
    recovered = after_trough[after_trough["equity"] >= trough_peak]
    if not recovered.empty:
        recovery_idx = recovered.index[0]
        recovery_date = df.loc[recovery_idx, "session_date"]
        underwater_days = (recovery_date - peak_date).days
        recovered_str = f"recovered on {recovery_date.date()}"
    else:
        recovery_date = df["session_date"].iloc[-1]
        underwater_days = (recovery_date - peak_date).days
        recovered_str = "NOT yet recovered (still underwater at end)"

    final_equity = df["equity"].iloc[-1]
    final_peak = df["peak"].iloc[-1]
    current_dd = final_equity - final_peak
    final_date = df["session_date"].iloc[-1]
    final_peak_idx = df[df["equity"] == final_peak].index[-1]
    final_peak_date = df.loc[final_peak_idx, "session_date"]
    current_dd_days = (final_date - final_peak_date).days

    print(f"  Final equity:        {fmt_money(final_equity)}")
    print(f"  Peak equity:         {fmt_money(final_peak)}  on {final_peak_date.date()}")
    print()
    print(f"  Max drawdown:        {fmt_money(max_dd)}")
    print(f"  Peak before trough:  {fmt_money(trough_peak)}  on {peak_date.date()}")
    print(f"  Trough equity:       {fmt_money(trough_equity)}  on {trough_date.date()}")
    print(f"  Drawdown duration:   {underwater_days} days ({recovered_str})")
    print()
    print(f"  Current drawdown:    {fmt_money(current_dd)}")
    print(f"  Days at current DD:  {current_dd_days} days since last peak ({final_peak_date.date()})")
    print()


def clustering_check(df: pd.DataFrame) -> None:
    print("=" * 72)
    print("4) TRADE CLUSTERING / CONCENTRATION CHECK")
    print("=" * 72)
    df = df.copy()
    daily = df.groupby("session_date")["pnl_dollars"].sum().sort_values(ascending=False)
    total = daily.sum()

    top5 = daily.head(5)
    top10 = daily.head(10)
    without_top5 = total - top5.sum()
    without_top10 = total - top10.sum()

    print(f"  Trading days with activity: {len(daily)}")
    print(f"  Total P&L:                  {fmt_money(total)}")
    print()
    print(f"  Top 5 days sum:             {fmt_money(top5.sum())}")
    print(f"  P&L without top 5 days:     {fmt_money(without_top5)}")
    print()
    print(f"  Top 10 days sum:            {fmt_money(top10.sum())}")
    print(f"  P&L without top 10 days:    {fmt_money(without_top10)}")
    print()

    pct_top5 = top5.sum() / total * 100 if total else 0.0
    pct_top10 = top10.sum() / total * 100 if total else 0.0
    print(f"  Top 5 days   = {pct_top5:.1f}% of total P&L")
    print(f"  Top 10 days  = {pct_top10:.1f}% of total P&L")
    print()
    print("  Top 10 best days:")
    for d, v in top10.items():
        print(f"    {d.date()}  {fmt_money(v)}")
    print()


def main() -> None:
    df = pd.read_parquet(TRADES_PARQUET)
    df["session_date"] = pd.to_datetime(df["session_date"])
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    print(f"Loaded {len(df)} trades from {TRADES_PARQUET.name}")
    print(f"Date range: {df['session_date'].min().date()} -> {df['session_date'].max().date()}")
    print()

    yearly_split(df)
    monthly_split(df)
    drawdown_analysis(df)
    clustering_check(df)


if __name__ == "__main__":
    main()
