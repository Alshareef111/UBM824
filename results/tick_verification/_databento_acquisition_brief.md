# Databento tick-data acquisition brief — Phase 2 expansion

**Purpose:** Specify what tick data is needed to extend Phase 2 verification (`src/experimental/tick_replay_v2.py`) from the current 2-trade local subset to the full canonical Phase 1 sample of 40 dates spanning 7 years.

**Owner action:** Use this brief to scope a Databento purchase. Pricing figures below are *order-of-magnitude estimates only* — confirm on the Databento checkout flow before purchase.

---

## What the replayer needs

The Phase 2 replayer requires **trade prints with sub-second timestamps** for MNQ continuous front-month, matching the semantics of the existing `data/processed/ticks_overlap.parquet`:

| Column | Source | Phase 2 use |
|---|---|---|
| `ts_utc` | Tick timestamp, UTC, nanosecond-precision | Entry-minute fill detection, chronological exit walk, Bug B pre-fill check |
| `last` | Executed trade price | All threshold-cross checks (fill, stop, target, force-close) |
| `bid` / `ask` (optional) | NBBO | Phantom-fill diagnosis (a future v2 of the replayer; not strictly needed for Bug B) |
| `volume` (optional) | Per-tick size | Slippage / cost analysis (out of scope for Phase 2) |

The replayer does **not** need:
- Full Market By Order (MBO) book data
- Implied / RFQ prints (these are the *source* of Bug B / phantom mismatches; the replayer compares against trade-only ticks to expose them)
- Aggregated OHLCV bars (already have these in `data/processed/mnq_adjusted_1m.parquet`)

---

## Recommended Databento schema

Databento offers MNQ futures data on the **GLBX.MDP3** dataset (CME Globex MDP 3.0). Schema options, ranked by fit-to-task:

| Schema | What's in it | Cost rank | Recommendation |
|---|---|---|---|
| **`trades`** | Trade prints only: `ts_event`, `price`, `size`, `side` | Cheapest | **Primary recommendation** — sufficient for Bug B and basic phantom detection |
| `tbbo` | Top-of-book bid/ask + trades | Mid | Use if phantom-fill diagnosis becomes a v2 priority and you want bid/ask context for non-trade prints |
| `mbp-1` | Full L1 order book + trades | Higher | Overkill for Phase 2; right call only if v3 slippage modelling is on the roadmap |
| `mbo` | Full Market By Order | Highest | Not needed |

**Action:** Order `trades` schema first. If v2 phantom-fill diagnosis demands bid/ask, top up to `tbbo` for the same window (Databento allows incremental schema purchases on the same date range).

---

## Symbol selection

Two equivalent options:

1. **Continuous front-month** — Databento exposes this as `MNQ.c.0` (continuous, front contract). Single download, matches the way `src/data_prep.py` already constructs the Panama-adjusted series.
2. **Per-contract list** — explicit list of front-month contracts spanning the period (MNQM4, MNQU4, MNQZ4, MNQH5, MNQM5, MNQU5, MNQZ5, MNQH6, MNQM6). Roll boundaries must align with the existing `src/data_prep.py` rollover logic; requires `src/build_tick_cache.py` to be extended to handle multi-file ingest.

**Recommendation:** option 1 (`MNQ.c.0`) — single file, single download, one symbol parameter. Saves a day of cache-builder generalization work.

---

## Date range

The V2 + 40/40 backtest window per `CLAUDE.md`: **2024-04-01 → 2026-05-01** (the 2-year in-sample window that produced the 908-trade headline).

The canonical Phase 1 sample, however, was drawn from the **7-year extended window** (2019-05-15 → 2026-04-15) — dates in the sample go back to 2020-03-03.

Two scoping options:

| Window | Span | Verifies | Defers |
|---|---|---|---|
| **Full Phase 1 (2020-03-01 → 2026-05-01)** | ~6.2 years | 40/40 Phase 1 sample dates (excluding those already covered locally) | Nothing |
| **In-sample only (2024-04-01 → 2026-05-01)** | ~25 months | ~17 of 40 Phase 1 dates (subset that falls in V2 + 40/40 in-sample) | The pre-2024 historical OOS sample dates |

**Recommendation:** **start with in-sample only (2024-04-01 → 2026-05-01).** Rationale:
1. The V2 + 40/40 deployment-candidate headline (+$8,808) is defined on this window; tick verification of *this* window is what gates deployment per `strategy-reference.md` §9.2.
2. ~25 months vs ~75 months is roughly **3× cheaper** at Databento's typical date-range pricing.
3. Pre-2024 sample dates are useful for "did Bug B incidence drift over time?" but not for deployment sign-off — they can be added later.
4. Local coverage (`ticks_overlap.parquet`, 2026-03-17 → 2026-04-15) already covers ~4 weeks of the in-sample window; the new acquisition extends backward from there.

The narrower window also keeps the first tick-cache builder simple — no rollover logic across 7 contract boundaries, only ~6-7 contracts in the 25-month span.

---

## Cost estimate (verify before purchase)

I don't have Databento's current pricing memorized accurately enough to commit numbers. Order-of-magnitude expectations based on prior experience with the platform:

- **Trades schema, ~25 months, 1 symbol (MNQ.c.0):** likely in the **low-to-mid hundreds USD** range. Possibly less under the trial / new-account credit.
- **Free tier:** Databento offers some historical data free; check whether GLBX trades for MNQ falls under the free tier for any portion of the window.
- **Pricing model:** Databento charges by `bytes_billed` for historical downloads, not per-day. Trades for MNQ continuous over 25 months should be well under 1 GB at trades-schema density.

**Action:** Before purchase, run a `metadata.get_billable_size` query (Databento CLI / Python SDK) on the exact symbol + schema + date range to get the actual figure. Set a budget cap on the account; the platform exits cleanly if exceeded.

---

## Fastest path to acquisition

1. **Sign up / log in** at databento.com. Free-tier account is sufficient to start; paid tier needed for the actual download.
2. **Install the Python SDK**: `pip install databento` into the project's virtualenv.
3. **Generate an API key** in the Databento console; export as `DATABENTO_API_KEY` env var.
4. **Dry-run the cost estimate**:
   ```python
   import databento as db
   client = db.Historical()
   cost = client.metadata.get_cost(
       dataset="GLBX.MDP3",
       symbols=["MNQ.c.0"],
       schema="trades",
       start="2024-04-01",
       end="2026-05-01",
       stype_in="continuous",
   )
   print(cost)
   ```
5. **If cost is acceptable**, download to `data/raw/MNQ_trades_2024-04_to_2026-05.dbn.zst`:
   ```python
   data = client.timeseries.get_range(
       dataset="GLBX.MDP3",
       symbols=["MNQ.c.0"],
       schema="trades",
       start="2024-04-01",
       end="2026-05-01",
       stype_in="continuous",
       path="data/raw/MNQ_trades_2024-04_to_2026-05.dbn.zst",
   )
   ```
6. **Extend `src/build_tick_cache.py`** to ingest the `.dbn.zst` file alongside the existing `.LastT.txt` symlink. The Databento DBN format requires `db.DBNStore.from_file(...).to_df()`; the existing tick-cache schema (`ts_utc`, `last`, `bid`, `ask`, `volume`) needs to be mapped from Databento's column names (`ts_event`, `price`, `size`, optionally `bid_px_00` / `ask_px_00`).
7. **Write the extended parquet** to a new path (do **not** overwrite `data/processed/ticks_overlap.parquet` — keep the existing 6-week cache distinct for reproducibility). Suggested path: `data/processed/ticks_extended_2024-04_to_2026-05.parquet`.
8. **Update `src/paths.py`** to expose the new path; update `src/experimental/tick_replay_v2.py`'s `TICKS_PATH` constant (or accept it as a CLI arg).

**Total time estimate** once the API key is in hand: ~1-2 hours for SDK install + cost-check + download + cache builder + re-run of Phase 2.

---

## Open items requiring your decision

1. **Schema:** confirm `trades` (recommended) vs `tbbo` vs `mbp-1`.
2. **Date range:** confirm in-sample only (2024-04-01 → 2026-05-01, recommended) vs full Phase 1 window.
3. **Symbol method:** confirm `MNQ.c.0` continuous (recommended) vs per-contract list.
4. **Budget cap:** Databento allows a per-account spending cap. Set it before purchase.
5. **License terms:** Databento data is licensed per-user; confirm the license allows the intended use (backtesting / academic research / personal deployment evaluation).
6. **Price-frame compatibility with simulator bar data (OQ-6).** Databento's continuous (`MNQ.c.0`) returns *raw* front-month prices. The simulator bars at `data/processed/mnq_adjusted_1m.parquet` are *Panama back-adjusted* (`raw + offset[contract]`, offsets accumulating per rollover, newest contract = 0). The tick cache builder **must apply the same offset table** (`src/data_prep.build_adjustments` on `data/processed/rolls.parquet`) at cache-build time, or the verifier will compare two incompatible price series and produce false phantoms / Bug B classifications. Lesson learned the hard way: the initial Phase 2 result committed as `22a2147` reported a 50.9% phantom rate, 15.5% Bug B rate, and MATCH 12.7% — **~85% of which was price-frame artifact**. After applying Panama adjustment per-tick (via the existing `rolls.parquet` boundaries), the corrected run at `phase2_window_20260517_165641/` reports MATCH 90.0%, phantom 2.7%, Bug B 7.3%. Additionally: rollover-transition windows (where Databento's continuous and project's rolls disagree on which contract is front-month for a few days) leave a small residual error — handle separately or accept as a tiny known artifact. See `phase2_window_20260517_161935/SUPERSEDED.md` for the full diagnostic.

Once those six items are resolved, the acquisition can proceed end-to-end in under half a day.
