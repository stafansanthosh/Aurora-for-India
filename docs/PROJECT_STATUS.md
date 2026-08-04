# IndiaAQBench project status

**Snapshot date:** 2026-08-04
**Status:** active research; rollout complete, audit and scoring pending
**Public-use level:** code and benchmark design only—not a validated forecast
service

This page is the short, human-readable scoreboard. The
[benchmark specification](BENCHMARK_SPEC.md) defines the scientific task, and
the [development journal](../JOURNAL.md) preserves the full history.

## At a glance

| Measure | Current verified state |
|---|---:|
| Cities | 9 |
| OpenAQ station-hours | 1,489,534 |
| Registered stations | 159 |
| Frozen initialization dates | 56 |
| Training dates | 32 |
| Test dates | 24 |
| Leads per initialization | 8 (+12 to +96 hours) |
| Expected full pair rows | 80,136 |
| Current-registry pair files present | **56/56; final audit pending** |
| Current-registry pair rows | **80,136** |
| Pilot-only pair files rejected by the loader | 2 |
| Integrity audit | **Pending after rollout completion** |
| Unit tests | 84/84 passing in the exact RunPod environment; local launcher broken |
| Web preview | CI build/render and owner-only deployment passing |

The expected pair count is 56 dates × 159 stations × 9 rows per station: one
lead-zero CAMS row plus eight Aurora forecast leads.

## Data coverage

The completed local OpenAQ archive covers the scoped nine-city benchmark:

| City | Benchmark role | Stations | Station-hours |
|---|---|---:|---:|
| Bangalore | Fit/validation pool | 16 | 112,258 |
| Chennai | Fit/validation pool | 8 | 78,154 |
| Delhi | Fit/validation pool; diagnostic city | 64 | 589,759 |
| Lucknow | Fit/validation pool | 6 | 66,828 |
| Mumbai | Fit/validation pool | 36 | 335,822 |
| Patna | Fit/validation pool | 7 | 74,507 |
| Kanpur | L2 held-out city | 3 | 33,393 |
| Kolkata | L2 held-out city | 15 | 155,484 |
| Varanasi | L2 held-out city | 4 | 43,329 |
| **Total** |  | **159** | **1,489,534** |

The bulk archive is not tracked at `HEAD`. It exists in the working data
archive; code, pull provenance, the station registry, and the frozen date
manifest are in the repository. No data release is authorized until
redistribution terms and attribution are reviewed. Historical raw blobs also
remain reachable in this private repository's Git history.

## Frozen evaluation schedule

The 56 dates in [`benchmark_dates.csv`](benchmark_dates.csv) are divided as
follows:

| Season | Train | Test |
|---|---:|---:|
| Winter | 8 | 8 |
| Pre-monsoon | 8 | 8 |
| Monsoon | 8 | 8 |
| Post-monsoon | 8 | 0 |
| **Total** | **32** | **24** |

The lack of a post-monsoon test period is a real limitation. OpenAQ provides
little usable history before roughly February 2025, and the post-cutoff archive
currently ends in July 2026. The current design puts October–November 2025 in
training so adaptation sees severe-season examples, but it does not demonstrate
independent post-monsoon transfer.

The temporal cutoff was revised once on 2026-07-24:

- original cutoff: 2025-07-01;
- current cutoff: 2025-12-01;
- reason: the original fit period lacked adequate severe-season coverage;
- timing: before any adaptation was trained on the revised split;
- obligation: disclose the change anywhere results are reported.

## Done

- Completed the nine-city OpenAQ archive: 1,489,534 station-hours.
- Fixed the sensor-selection bug and rebuilt the registry to 159 stations.
- Froze 56 dates under the revised cutoff: 32 train and 24 test.
- Implemented CAMS download, Aurora rollout, and station sampling.
- Implemented persistence, climatology, CAMS-start-held-constant, and raw
  Aurora baselines.
- Implemented and integrated the actual lead-dependent CAMS +12 to +96-hour
  operational forecast baseline with immutable request/provenance records.
- Downloaded and validated all 56 actual CAMS forecast cycles: 71,232
  station-lead rows with matching raw and extracted-file hashes.
- Downloaded and deep-validated all 56 CAMS atmospheric initialization
  archives: 12.397 GiB with exact date coverage and no missing or extra files.
- Implemented fail-closed offline GPU input checks and deterministic four-way
  worker bundle packaging; no provider credentials are placed on GPU workers.
- Implemented PM2.5 concentration, AQI category, and Very Poor+ event metrics.
- Centralized all temporal and spatial split constants in
  [`src/splits.py`](../src/splits.py).
- Implemented registry-aware rollout resumption and strict pair-file loading.
- Implemented a 39-check integrity audit.
- Added calibrator guardrails that report event skill beside MAE and refuse to
  save a calibration model that harms Very Poor+ detection.
- Added regime-shift, seasonal-transfer, anchoring, leakage, event-count,
  acquisition, offline-input, and packaging tests; all 83 tests pass locally.
- Implemented the reporting package under [`src/report/`](../src/report/).
- Preserved the first failed calibrator as a documented negative baseline.
- Implemented a public-interface preview with illustrative data and explicit
  non-operational labeling; its install, build, and render tests pass in CI.
- Specified the public product, immutable live-feed contract, and
  additional-data experiments.
- Implemented the bounded official OGD India CPCB Patna/Varanasi live-feed
  diagnostic; it remains optional and is not claimed as independent truth.
- Completed the four-slice Aurora GPU rollout: 56 dates, 80,136 rows, 159
  stations, and zero worker errors. All returned pairs and worker manifests
  matched their remote SHA-256 hashes.

## In progress

- Repairing the local Python environment, merging the four worker manifests,
  and preparing the required post-rollout integrity audit.
- Resolving repository licensing and historical raw-data publication before a
  public launch.

## Blocked or absent

These are not complete and must not be implied in public claims:

- **Post-rollout integrity audit:** not yet run.
- **Canonical manifest:** four worker manifests exist but are not yet merged.
- **Valid full-registry results table:** absent.
- **Valid full-registry Component A score:** absent; the implementation exists
  but has not been evaluated on the completed, audited pair set.
- **Fine-tuning design:** absent.
- **Scoped Aurora fine-tune:** not run.
- **Latest-cycle forecast runner:** absent.
- **Immutable live forecast ledger:** absent.
- **Public experimental forecast feed:** absent.
- **Independent post-monsoon test:** absent.

The scientific results are now blocked by local validation and scoring, not by
GPU inference. Product work can proceed in parallel using clearly labeled
synthetic or historical example data, but it cannot display final metrics yet.

## Legacy pilot files

The current rollout replaced the scheduled pilot dates 2025-02-19, 2025-03-03,
and 2025-06-03 with 159-station outputs. Two pilot-only files remain:
2025-11-15 and 2025-11-20. Neither belongs to the frozen schedule. The strict
evaluator rejects them by date, which prevents silent contamination. Historical
pilot metrics may explain engineering decisions, but they are not valid
benchmark results.

## Next

The critical scientific sequence is:

1. Repair or recreate the local Python 3.11 environment.
2. Merge `manifest_worker_0.jsonl` through `manifest_worker_3.jsonl`.
3. Run `python -m src.eval.audit` and require it to pass.
4. Produce raw baseline tables by city, lead, L1 holdout, and L2 holdout.
5. Evaluate the implemented Component A without future-data leakage.
6. Apply the guarded calibrator only if it protects event detection.
7. Compare Aurora against the actual CAMS forecasts already attached by the
   integrated rollout.
8. Publish versioned tables and figures with the cutoff revision disclosed.

The public-product sequence can run beside it:

1. Define a stable forecast JSON schema.
2. Build an interactive city page against labeled example data.
3. Implement a latest-cycle runner and immutable forecast ledger.
4. Run privately in shadow mode.
5. Publish a clearly labeled experimental feed with raw forecasts, corrected
   forecasts, freshness indicators, and rolling verification.

## Claim boundary

It is accurate today to say:

> IndiaAQBench is an open benchmark under active development for testing
> low-compute adaptation of Aurora for multi-day PM2.5 forecasting across nine
> Indian cities.

It is not yet accurate to say:

- the adapted model is better than persistence, CAMS, or raw Aurora;
- the system has been validated across the full year;
- the system provides reliable forecasts for unmonitored cities;
- a public real-time forecast feed is operational;
- the project provides official air-quality or health warnings.

Return to the [README](../README.md) or read the
[benchmark specification](BENCHMARK_SPEC.md).
