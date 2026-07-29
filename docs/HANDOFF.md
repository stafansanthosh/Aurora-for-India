# Handoff: IndiaAQBench current state

**Updated:** 2026-07-29
**Branch:** `master`
**Scientific blocker:** the 56-date Aurora rollout
**Product status:** interface preview and specifications exist; no live feed

## Objective and non-negotiables

IndiaAQBench tests whether Microsoft Aurora plus inexpensive, auditable
adaptation can provide useful multi-day PM2.5 forecasts for Indian cities that
lack a strong public forecasting system. Delhi is a dense diagnostic
environment, not the target.

Success means detecting **Very Poor+ events (at least 121 µg/m³)**. POD, FAR,
CSI, and event counts are headline results; MAE is secondary. Split constants
live only in `src/splits.py`. Run `python -m src.eval.audit` before trusting a
results table.

## Verified current state

| Item | State |
|---|---|
| OpenAQ archive | Complete: 1,489,534 observations |
| Station registry | Complete: 159 stations across 9 cities |
| Frozen dates | Complete: 56 dates, 32 train and 24 test |
| Integrity audit | Last recorded: 34 checks, 0 failures |
| Current test collection | 26/26 passing in GitHub Actions |
| Web preview | Install, build, and render tests passing in GitHub Actions |
| Current-registry pair files | **0** |
| Valid full benchmark table | **Absent** |
| Public live forecast | **Absent** |

The five pair files under `results/pairs/` are legacy pilot artifacts. They use
superseded 33- or 127-station registries; two dates are also outside the frozen
schedule. The strict loader correctly rejects all five.

The temporal cutoff changed once from 2025-07-01 to 2025-12-01 under the
pre-registered data-coverage contingency, before adaptation was fitted on the
revised split. Every public result must disclose that change. The frozen test
period has no post-monsoon dates, so the present benchmark cannot support a
year-round utility claim.

## Work completed in the current integration

- Component A exists in `src/model/anchor.py`. It uses only forecast errors
  whose verifying observations occur strictly before each initialization,
  isolates station histories, shrinks thin samples toward no correction, clips
  the multiplier, and reports fallback diagnostics.
- `src/eval/benchmark.py --anchor` adds Component A to the common scoring path.
- Sixteen Component A tests exist in `tests/test_anchor.py`; the full 26-test
  suite passes in GitHub Actions. They have not run locally because the Windows
  virtual environment points to a missing base Python interpreter.
- The public product and live-feed contracts are documented in
  `docs/PRODUCT_SPEC.md` and `docs/LIVE_FEED_SPEC.md`.
- An interactive product preview lives under `web/`. Every forecast value is
  illustrative and the UI states that no live forecast is being issued.
- Additional-data work is documented in `docs/DATA_EXPANSION_PLAN.md` and
  independently checked in `docs/DATA_SOURCE_AUDIT.md`.
- GitHub Actions run `30473089540` passed the 26-test Python job and the web
  install/build/render job on integration commit `48135cc`.

Component A is **implemented, not scientifically accepted**. It cannot be
scored until valid 159-station pairs exist. It uses trailing local
observations even in held-out cities, so report it as “held-out-city transfer
with trailing local observations,” never pure zero-shot transfer.
Its retrospective frame can enforce observation time but does not contain a
reliable source `retrieved_at`; the live adapter must enforce retrieval
availability separately.

## Additional-data decisions

1. Add the actual CAMS +12 to +96-hour forecast as a separate operational
   baseline. The current `raw_cams` method only carries the initialization
   field forward and must be labeled “CAMS starting field held constant.”
2. Pilot the official OGD India CPCB hourly feed as a live observation backup
   and latency/completeness check. It probably overlaps OpenAQ and is not
   automatically independent truth.
3. No licence-clear 2023/24 hourly Patna or Varanasi archive has been verified.
   Use a narrow official export test or formal request, not undocumented bulk
   scraping.
4. Start FIRMS fire detections and Sentinel-5P aerosol as explanatory UI
   context. Promote either to a predictive input only if a leakage-safe
   ablation improves held-out-city event skill.
5. Do not make the discontinued public GFAS v1.2 archive a live dependency.

## Publication boundary

The GitHub repository is private. It must not simply be switched to public:

- reachable Git history contains hundreds of megabytes of raw OpenAQ archive
  files even though they are no longer tracked at `HEAD`;
- there is no repository licence;
- the integrity audit has not been rerun after this integration.

The safest publication route is a new clean public mirror containing only an
approved source snapshot. A history rewrite is possible but destructive and
requires explicit owner approval. See `docs/PUBLICATION_READINESS.md`.

## Exact next scientific action

Run the 56 frozen dates on four temporary 48 GB GPU workers, each with a
disjoint date slice. On each configured worker, the command is:

```bash
python -m src.pipeline.orchestrate --dates-file slice_0N --device cuda
```

Replace `N` with that worker's slice number (`0` through `3`). Follow
`scripts/setup_gpu.md`; do not run all 56 dates on every worker.

After copying all pair files back, verify:

```bash
python -m src.eval.audit
python -m src.eval.benchmark
python -m src.eval.benchmark --anchor
```

Expected completeness is 1,431 rows per date and 80,136 rows total. Do not fit
or publish a calibration result before the audit passes.

## Local setup still required

The current `.venv` is not usable: its base Python 3.11 installation is
missing. Node.js is also absent. Repair/install those runtimes later or rely on
GitHub Actions for the source-only test and web-build checks. The local
data-dependent audit still requires a repaired Python environment.

## Rejected paths

- The v1 direct-target tree calibrator: it improved MAE while detecting 0 of 99
  pilot Very Poor+ events. It remains as a negative baseline with a no-harm
  save gate.
- OpenAQ pre-February-2025 backfill: unavailable at sensor level.
- An A100: unnecessary for 0.4° inference.
- Calling Component A zero-shot: it uses recent local observations.
- Publishing legacy pilot pair metrics as current results.
