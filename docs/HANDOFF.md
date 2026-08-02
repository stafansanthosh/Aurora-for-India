# Handoff: IndiaAQBench current state

**Updated:** 2026-08-02
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
| Actual CAMS forecasts | Complete: 56 dates, 71,232 station-lead rows |
| Aurora CAMS analysis inputs | Complete: 56 dates, 12.397 GiB, deep validated |
| Integrity audit | 39 checks: 36 pass, 2 legacy warnings, 1 expected GPU blocker |
| Current test collection | 83/83 passing locally |
| Web preview | CI build/render pass; private owner-only deployment succeeds |
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
- Sixteen Component A tests exist in `tests/test_anchor.py`; the full 83-test
  suite passes locally in the restored Python 3.11.9 environment.
- The public product and live-feed contracts are documented in
  `docs/PRODUCT_SPEC.md` and `docs/LIVE_FEED_SPEC.md`.
- An interactive product preview lives under `web/`. Every forecast value is
  illustrative and the UI states that no live forecast is being issued.
- The preview has an owner-only Sites production deployment. Deployment
  succeeded; CI and the restored local Node runtime verify build/render
  behavior. Browser interaction checks passed for city selection, method
  selection, and forecast-day selection with no client errors. The production
  dependency audit reports zero known vulnerabilities after patching Next.js
  and its vulnerable transitive dependencies.
- Additional-data work is documented in `docs/DATA_EXPANSION_PLAN.md` and
  independently checked in `docs/DATA_SOURCE_AUDIT.md`.
- All 56 CAMS atmospheric initialization archives are stored locally and have
  passed ZIP CRC, hash, NetCDF, coordinate, dimension, and required-variable
  validation. GPU workers therefore run in fail-closed offline-input mode and
  receive no Copernicus or OpenAQ credentials.
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

**Implementation update:** the actual CAMS +12 to +96-hour retriever, GRIB
sampler, provenance record, exact-support pair attachment, and evaluator method
are complete. All 56 frozen CAMS cycles have been downloaded and validated:
71,232 station-lead rows, 159 stations per date, eight leads, matching raw and
sample hashes, and no missing or extra dates. The former `raw_cams` label is
now `cams_lead0_fixed`.
The bounded official OGD India CPCB Patna/Varanasi live-feed diagnostic is also
implemented. A live probe needs the owner's `DATA_GOV_IN_API_KEY`; it remains
optional and is not a frozen-benchmark blocker.

1. Preserve the locally validated CAMS forecast and atmospheric-analysis
   archives. Copy only the assigned 14-date bundle to each GPU worker.
2. Run the implemented official OGD India CPCB live probe only when the owner
   supplies an API key. It probably overlaps OpenAQ and is not independent
   truth.
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
disjoint 14-date input bundle. The orchestrator hash-checks every assigned CAMS
forecast and analysis file before loading Aurora, runs without provider
credentials, and writes both methods into each current-registry pair file. On
each configured worker, the command is:

```bash
python -m src.pipeline.orchestrate --dates-file slice_0N --device cuda --offline-inputs
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

## Local environment

The Windows Python 3.11.9 base runtime was restored and the project `.venv`
is healthy. The complete 83-test suite and local data-dependent audit run.
A checksum-verified portable Node.js 24 runtime is available locally; the web
build/render tests, production dependency audit, browser interactions, and
owner-only Sites deployment all pass.

## Rejected paths

- The v1 direct-target tree calibrator: it improved MAE while detecting 0 of 99
  pilot Very Poor+ events. It remains as a negative baseline with a no-harm
  save gate.
- OpenAQ pre-February-2025 backfill: unavailable at sensor level.
- An A100: unnecessary for 0.4° inference.
- Calling Component A zero-shot: it uses recent local observations.
- Publishing legacy pilot pair metrics as current results.
