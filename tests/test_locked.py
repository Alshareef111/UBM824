"""
Regression test: the locked config's metrics must stay within tolerance.

A future edit that silently shifts the gate, the costs, the exit walk, or
any other part of the locked pipeline will fail this. Run:

    .venv/bin/python -m tests.test_locked

Exits 0 on PASS, 1 on FAIL — usable from a pre-commit hook or CI.
"""

import sys

from src.vbt_backtest import LOCKED_EXPECTED, run_locked


def main():
    print("Running locked-config regression check...\n", flush=True)
    m = run_locked(verbose=False)

    failures = []
    print(f"{'metric':<14}  {'actual':>14}  {'expected':>12}  {'tol':>8}  {'verdict':<8}")
    print("-" * 66)
    for key, (expected, tol) in LOCKED_EXPECTED.items():
        actual = m[key]
        ok = abs(actual - expected) <= tol
        if not ok:
            failures.append((key, actual, expected, tol))
        verdict = "OK" if ok else "DRIFT"
        print(f"{key:<14}  {actual:>14.4f}  {expected:>12.4f}  ±{tol:<7.2f}  {verdict}")

    print()
    if failures:
        print(f"FAIL — {len(failures)} metric(s) drifted:")
        for key, actual, expected, tol in failures:
            print(f"  {key}: actual={actual} expected={expected} (tol ±{tol})")
        sys.exit(1)

    print("PASS — locked config reproduces within tolerance")
    sys.exit(0)


if __name__ == "__main__":
    main()
