# Handoff: IndiaAQBench — calibration redesign after a documented failure

> Adapted from the `handoff` skill. Its template says paste work-in-progress
> **verbatim**, which is right when the next model has no repo access. Here the
> next session *has the repo*, so this points at files instead — pasted code
> would be huge and would go stale the moment a file changes. Everything below
> is verifiable in-tree; nothing is invented.

## Context & goal

Building **IndiaAQBench**: an open, reproducible benchmark for multi-day PM2.5
forecasting over Indian cities, testing whether cheap adaptation can lift
Microsoft Aurora (1.3B atmospheric foundation model) into a practically useful
tier. Target is **not** beating Delhi's AQEWS (WRF-Chem 400m, PI 87) — it is the
~465 Indian cities with no public forecast system. Success is measured by
**decision-relevant AQI category skill (Very Poor+ event POD/FAR), not MAE**,
because GRAP emergency actions trigger on forecast category.

## Key decisions made — do NOT re-litigate

- **Metrics**: category/event metrics are the headline; MAE is secondary. Spec §4.
- **No A100 needed.** Aurora's docs specify ~40 GB at 0.25° *inference*; the
  A100-80GB figure is for 0.1° + backprop. We run 0.4° inference → a ~$0.50/hr
  48 GB spot GPU (A6000) on RunPod/Vast/Lambda. Azure quota was denied and is
  irrelevant. Runbook: `scripts/setup_gpu.md`.
- **Temporal cutoff revised once: 2025-07-01 → 2025-12-01** (commit `0593506`),
  under the contingency pre-registered in spec §6, before any adaptation was
  trained on the new split. Rationale and numbers in `src/splits.py` docstring
  and spec §6. **This must be disclosed wherever results appear.**
- **Split constants live in `src/splits.py` only.** They were duplicated in three
  modules; that is now the single source of truth.
- **Calibration comes before fine-tuning** — not instead of it. Fine-tuning is
  still planned (task #14); it needs the baseline as a bar to beat.
- **OpenAQ backfill is impossible.** Location metadata claims coverage since
  2016, but the hours endpoint serves nothing before ~Feb 2025 for *any* sensor,
  old or new. Verified at sensor level. Do not spend time re-checking this;
  see `src/data/archive_probe.py`.

## Current state

**Done and pushed** (through commit `cb19d45` on `ws4-dashboard`):
- Full pipeline: CAMS download → Aurora rollout (+12h…+96h) → station sampling →
  eval harness with 4 baselines + category/event metrics.
- **WS-4 Dashboard & Reporting Package** (`src/report/`): `scorecard.py` and `plots.py`
  for generating per-city/per-lead scorecards and matplotlib dashboard figures.
- **5 dates of pairs** in `results/pairs/` (2025-02-19, 2025-03-03, 2025-06-03,
  2025-11-15, 2025-11-20), 1,143 rows each at 127 stations.
- **56 benchmark dates frozen** in `docs/benchmark_dates.csv` — **stale, must be
  re-run** after the pull (it used the old cutoff and the old registry).
- **v1 calibrator: documented NEGATIVE result.** See "Rejected paths".

**Mid-flight right now — re-pull pass 1 finished, pass 2 REQUIRED:**

65 of 198 windows failed on the flaky home connection. Three cities are complete
and show exactly the gains the sensor fix predicted; six need another pass.

| City | Status | Rows | Stations (was) | Failed windows |
|---|---|---|---|---|
| bangalore | **ok** | 112,258 | 16 (13) | 0 |
| chennai | **ok** | 78,154 | 8 (6) | 0 |
| varanasi | **ok** | 43,329 | 4 (2) | 0 |
| mumbai | partial | 327,694 | 36 (32) | 2 |
| kanpur | partial | 31,353 | 3 (2) | 1 |
| patna | partial | — | — (4) | 12 |
| delhi | partial | — | — (55) | 13 |
| kolkata | partial | — | — (9) | 15 |
| lucknow | partial | — | — (4) | **22 (all)** |

**Delhi and Patna were degraded and have been restored from
`data/openaq/_backup_pre_sensorfix/`.** The no-overwrite-on-partial guard was
added *during* the run, so the already-loaded module never used it. It is active
now, so this cannot recur. Kolkata was restored earlier; Lucknow wrote nothing
(0 rows), so it is untouched. **All 121 part files are preserved** — the re-run
only fetches the missing windows and then assembles complete + station-enriched
data.

## Work in progress

**The one command that matters** — resumable, skips completed windows:
```bash
python -m src.data.archive_pull --cities varanasi kanpur patna lucknow kolkata chennai bangalore mumbai delhi
```
- Progress: `ls data/openaq/archive/parts/*.csv | wc -l` (198 windows total)
- Offline rebuild from parts, no network: `python -m src.data.archive_pull --assemble-only`
- Backup of pre-re-pull CSVs: `data/openaq/_backup_pre_sensorfix/`
- A partial pass no longer overwrites a good CSV (fixed after Kolkata was
  degraded 93k → 55k rows and restored from backup).

**Why the re-pull exists:** `find_pm25_stations` took only the *first* PM2.5
sensor per station; most Indian CPCB stations expose two (retired + active), so
whole stations were silently dropped. Fixed in `8d4ec33`. Recovers:
patna 4→7, varanasi 2→4, kanpur 2→3, lucknow 4→6, kolkata 9→15.

## Rejected paths — do not propose again

- **v1 pooled calibrator** (HistGradientBoosting predicting `log1p(obs)` directly
  from Aurora features). Scored **Very Poor+ POD 0.00 at every lead**, caught
  **0 of 99** test events, vs raw Aurora's 0.64. Causes: (RC1) predicting the
  target instead of a *correction* caps output at the training distribution;
  (RC2) trees cannot extrapolate; (RC3) calm-season-only training data;
  (RC4) the fit-time check printed MAE only, which *rewards* tail collapse.
  Code kept at `src/model/calibrator.py` as the documented baseline #5.
- **Backfilling OpenAQ history** — proven unavailable (see Key decisions).
- **Azure A100 / any A100** — unnecessary and unavailable on this subscription.
- **Serial 56-date rollout on one box** (~10 h) — dates are independent; split
  across 4 GPUs for ~2.5 h, ~$5.

## Tone & working preferences

- Wants to understand *why*, not just what — explain vocabulary (POD/FAR/MAE/
  persistence) and reasoning, don't assume.
- **Challenges premises and expects push-back with data.** Correctly pushed on
  "are we concerned with Delhi?" (we are not — it has AQEWS) and on whether
  fine-tuning deserved more weight.
- Wants negative results surfaced honestly, not smoothed over.
- Verify before asserting; run the check rather than reasoning from memory.
- Prefers work to continue autonomously; do not block on questions that data
  can answer. Do surface genuinely irreversible or scope-changing decisions.

## Immediate next step

Fill the 65 failed windows. Only these six cities need it — the other three are
done, so naming them saves hours:

```bash
python -m src.data.archive_pull --cities lucknow kolkata patna delhi kanpur mumbai
```

**Expect to run this more than once.** Each pass fetches only what is still
missing, so passes get progressively shorter. Repeat until every city reports
`"status": "ok"`. Check with:

```bash
python -c "import json;[print(r['city'],r['status'],r['windows']) for r in map(json.loads,open('data/openaq/archive/pull_manifest.jsonl')) if 'windows' in r]" | tail -9
```

Then, and only once all nine are `ok`:

```bash
python -m src.data.build_station_registry   # 127 -> ~170 stations expected
python -m src.eval.coverage_audit --n 56    # re-freeze dates under cutoff 2025-12-01
python -m src.eval.audit                    # must pass before trusting anything
```

**Sanity gate before moving on:** no city may end up with fewer rows than
`data/openaq/_backup_pre_sensorfix/`. Station counts should rise (that is the
sensor fix); row counts must not fall.

The coverage audit should now yield **post-monsoon training dates** for the first
time — that is the entire point of the cutoff revision, and what unblocks a
calibrator able to survive severe episodes.
