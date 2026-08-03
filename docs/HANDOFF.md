# Handoff: IndiaAQBench current state

**Updated:** 2026-08-03
**Branch:** `master`
**Scientific blocker:** the remaining 42 dates of the Aurora rollout
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
| Integrity audit | Not rerun after worker 0; last run was 39 checks: 36 pass, 2 legacy warnings, 1 GPU blocker |
| Current test collection | 84/84 passed on the exact RunPod environment; local launcher currently broken |
| Web preview | CI build/render pass; private owner-only deployment succeeds |
| Current-registry pair files | **14/56: 20,034 rows, worker 0 validated and copied locally** |
| Valid full benchmark table | **Absent** |
| Public live forecast | **Absent** |

Worker 0 (`slice_00`) now supplies 14 valid current-registry pair files. The
three remaining pilot-only pair files use superseded 33- or 127-station
registries; two dates are also outside the frozen schedule. The strict loader
must continue to reject those three.

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
- The RunPod RTX A6000 canary and all of `slice_00` completed at commit
  `181487e3de886cd9919c52a47dd7fac6fdc191e6`: 14 dates, 20,034 unique
  date-station-lead rows, 159 stations, nine leads, 14 current-registry success
  records, and zero current-registry errors. All 15 retrieved artifacts (14
  pairs plus the original worker manifest) matched the remote copies by
  SHA-256. The curated `manifest_worker_0.jsonl` retains only the 14 valid
  current-registry successes.
- The canary exposed a missing runtime dependency: Pandas could compute all
  eight steps but could not write Parquet because no engine was declared.
  `pyarrow` is now in `requirements.txt`. The runbook also starts disposable
  workers with an empty output ledger so tracked pilot manifests cannot leak
  into per-worker provenance.
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

Stop the completed worker-00 Pod after confirming `/workspace` is retained.
Then run the remaining three disjoint bundles on temporary 48 GB workers using
the updated source snapshot and runbook. Each worker starts with a clean output
ledger, verifies the assigned offline inputs before loading Aurora, and receives
no provider credentials. On workers 1 through 3, run:

```bash
python -m src.pipeline.orchestrate --dates-file slice_0N --device cuda --offline-inputs
```

Replace `N` with that worker's slice number (`1` through `3`). Follow
`scripts/setup_gpu.md`; do not rerun slice 00 or send all bundles to one worker.
Each remaining worker must produce 20,034 rows; together they add 60,102 rows.

After copying all pair files back, verify:

```bash
python -m src.eval.audit
python -m src.eval.benchmark
python -m src.eval.benchmark --anchor
```

Expected completeness is 1,431 rows per date and 80,136 rows total. Do not fit
or publish a calibration result before the audit passes.

## Local environment

The project `.venv` is not currently executable from the Codex shell: its
launcher targets a missing Python 3.11 base executable, and neither `python`
nor `py` is on `PATH`. This does not affect the SHA-verified worker-00 outputs,
which passed structural validation remotely, but it blocks the required local
audit and benchmark until the base runtime is repaired again. The exact RunPod
environment passed all 84 tests, CUDA execution, Aurora/GRIB imports, and `pip
check`.
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
