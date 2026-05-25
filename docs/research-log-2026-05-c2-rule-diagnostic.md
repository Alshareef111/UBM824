# C2 One-Position-Rule Diagnostic — Research Log

**Date:** 2026-05-11
**Scope:** Investigate why some active cluster setups don't generate trades when price reaches them during the trading window. Diagnostic case: 2024-08-12 (chart #08 of the 40/40 examples — BUY @ 20247.25, flat regime, cluster of 10, target hit).
**Conclusion:** No bug. The C2 one-position-at-a-time rule (`if open_pos is None:` gate at `simulator_hybrid.py` line 202) permanently skips higher-quality clusters when a lower-quality one fires first.

---

## Entry-logic review (simulator_hybrid.py)

For each cluster in the session pool:
- If `cluster.low > orb_close`: SELL setup, limit at `cluster.low`, trigger when `bar.high >= limit`
- If `cluster.high < orb_close`: BUY setup, limit at `cluster.high`, trigger when `bar.low <= limit`
- If cluster spans: skip

All non-spanning clusters become armed Setups simultaneously at 9:46. **No additional filters:** no minimum distance, no maximum distance, no same-side-as-9:46-open check, no nearest-only rule. Each Setup carries a `triggered: bool` flag that turns True on first fill.

**Fill loop (simulate_session, lines 201–225):**
```python
for bar in bar_records:
    if open_pos is None:
        fill = find_first_fill(setups, bar)  # candidate scan over un-triggered setups
        if fill is not None:
            fill.triggered = True
            open_pos = {...}
            # same-bar entry check (stop or target on entry bar)
    else:
        # ONLY exit logic runs here — find_first_fill is never called while a position is open
        exit_result = check_exit(open_pos[...], bar)
        ...
```

The `if open_pos is None: / else:` is mutually exclusive within each bar iteration. **While a trade is active, the engine literally doesn't check whether other setups are touched.** The tiebreaker for same-bar multi-touch is `closest limit_price to bar.open` (`find_first_fill` line 136).

---

## 2024-08-12 session — complete cluster + fill timeline

**Session features:**
- ORB high/low/close: 20324.75 / 20209.25 / 20214.75
- 9:46 NY open: 20218.75
- Lagged ATR-10: 665.12
- 26 non-spanning clusters; all become armed setups

**Setups within ±0.09 norm-distance of 9:46 open (hybrid-flipped to flat/breakout):**

| limit | size | fade_dir | hybrid-routed | norm_d |
|---:|---:|:---|:---|---:|
| 20181.00 | 4 | buy | sell | −0.0568 |
| 20196.00 | 7 | buy | sell | −0.0342 |
| 20214.25 | 4 | buy | sell | −0.0068 |
| 20229.75 | 3 | sell | buy | +0.0165 |
| 20247.25 | 10 | sell | buy | +0.0428 |

**Engine-replay (all 5 trades fired on the session — matches the trades_hybrid_4040 output):**

| entry | exit | side | entry_px | exit_px | reason | cluster_size | regime |
|---|---|:---|---:|---:|:---|---:|:---|
| 09:46:00 | 10:06:00 | sell | 20214.25 | 20254.25 | stop | **4** | flat |
| 10:07:00 | 10:09:00 | buy | 20247.25 | 20287.25 | target | **10** | flat |
| 10:10:00 | 10:10:00 | buy | 20229.75 | 20269.75 | target | 3 | flat |
| 10:16:00 | 10:23:00 | sell | 20322.25 | 20362.25 | stop | 3 | directional |
| 10:40:00 | 11:22:00 | sell | 20393.00 | 20353.00 | target | 3 | directional |

---

## Touch timeline up to chart #08's entry (10:07:00)

| first_touch | limit | size | routed_side | regime | outcome |
|---|---:|---:|:---|:---|---|
| 09:46:00 | **20214.25** | **4** | sell | flat | FIRED (first trade — became the C2 block source) |
| 09:47:00 | **20196.00** | **7** | sell | flat | **Never fired** — touched only during 9:46–10:06 C2 lockout; not re-touched after exit |
| 09:50:00 | 20229.75 | 3 | buy | flat | C2-blocked at 09:50; fired later at 10:10 when re-touched |
| 09:57:00 | **20181.00** | **4** | sell | flat | **Never fired** — touched only during C2 lockout; not re-touched |
| 10:06:00 | 20247.25 | 10 | buy | flat | Touched on the exit bar of the C2-active trade; engine in exit-only branch on bar 10:06; re-evaluated on next bar 10:07 → fired (chart #08) |

---

## The C2 skip pattern — central finding

**On 2024-08-12, a size-4 cluster fired first at 09:46 and locked the engine until 10:06.** During that 20-minute lockout, a size-7 cluster (20196.00, also flat-routed) and a size-4 cluster (20181.00, flat-routed) were both touched and permanently skipped. The size-10 cluster (20247.25) only fired on the next bar after C2 cleared.

Quality-of-signal hierarchy that day if no C2 existed:
- size-10 (20247.25) > size-7 (20196.00) > size-4 (20214.25 or 20181.00) > size-3 (rest)

But the engine fires them in **temporal-touch order**, not quality order. The size-4 at 20214.25 was touched first (at 09:46 itself, by virtue of being the closest to the open), so it won. Two higher-quality clusters never got a fill.

**Code citation:**
- `simulator_hybrid.py` line 202: `if open_pos is None:` gate prevents `find_first_fill` from ever evaluating new candidates while a position is active
- `simulator_hybrid.py` lines 219–225 (`else:` branch): only exit conditions are checked during the lockout — touched setups silently pass by

---

## Implication for the strategy

The C2 rule (locked in spec D-004) is documented as the simplest risk profile — one position at a time. But it interacts poorly with the cluster-fade design: when multiple high-quality clusters cluster around the 9:46 open (as on 2024-08-12 where five flat setups were within ±0.06 norm-dist), the first to be touched wins, regardless of quality. Larger clusters represent stronger historical level confluence and might be a better quality signal than membership-count-3 minimum clusters, but the simulator does not prioritize them.

**Possible future variants worth testing:**
1. **Quality-prioritized C2:** still one-position-at-a-time, but on each bar's candidate scan, prefer the cluster with highest `size` over the closest-to-open tiebreaker.
2. **Cluster-size minimum filter:** raise `MIN_CLUSTER_SIZE` from 3 to 4 or 5 — eliminate the lowest-quality signals entirely so they can't C2-block higher-quality ones.
3. **Sequential entry with risk capping:** allow multiple concurrent positions if total open risk stays below a cap — but this departs from the C2 spec.

---

## Verdict

**No bug.** The C2 rule is correctly implemented per spec D-004, and the diagnostic confirms it's working exactly as designed. The design itself has a known cost (high-quality signals can be permanently skipped) that's visible only in detail and worth flagging for future variants. The chart #08 case is a clean illustration: a +$80 target win on a cluster-of-10 was the second trade of the day, *after* a −$80 stop loss on a cluster-of-4 that fired purely because it was nearest the 9:46 open.

No code modified. Locked baseline `data/processed/trades.parquet` sha256 unchanged.
