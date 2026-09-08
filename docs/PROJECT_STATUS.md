# IndiaAQBench project status

**Snapshot date:** 2026-08-12 (scientific snapshot; publication update 2026-09-08)
**Status:** active research; free GFS passed the forecast-BLH gate; no Aurora 1.5 run
**Public-use level:** code and benchmark design only—not a validated forecast
service

This page is the short, human-readable scoreboard. The
[benchmark specification](BENCHMARK_SPEC.md) defines the scientific task, and
the [development journal](../JOURNAL.md) preserves the full history.

> **2026-09-08 update:** the repository is already public and MIT-licensed. The
> README and [publication audit](PUBLICATION_READINESS.md) supersede older
> private/no-licence claims. Historical redistribution is unresolved; no push,
> visibility change, or history rewrite is authorized by this update.

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
| Current-registry pair files present | **56/56** |
| Current-registry pair rows | **80,136** |
| Pilot-only pair files rejected by the loader | 2 |
| Canonical manifest | 56 unique done records; zero errors |
| Integrity audit | 36 pass, 2 expected legacy warnings, 1 PM-bin ordering failure |
| Unit tests | 108/108 passing locally (2026-09-08) |
| Web preview | Local build, 2 tests and production audit pass after nanoid patch; remote CI awaits authorized push |
| Event-skill diagnosis | Complete on train-only/out-of-fold data; 89.1% of events are Delhi |
| Current direction | Option B kill-test **PASSED** (perfect-prognosis); see `BLH_CEILING_RESULT.md` |
| ERA5 Option B inputs | 7 months, 84 train-only days, 320,544 station-hours; validated and committed |
| GFS forecast-BLH gate | **FREE NWP SUFFICIENT**: ΔAUC +0.0336, ΔCSI +0.1620; 32/32 train cycles; no Aurora 1.5 run |

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
redistribution terms and attribution are reviewed. Historical raw blobs also remain reachable in the already-public repository's Git history; see the current publication audit.

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
- Implemented the separate forward-24-hour headline evaluation in
  [`src/eval/rolling24.py`](../src/eval/rolling24.py) and generated both the
  24-hour headline and the hourly-threshold sensitivity scorecards.
- Centralized all temporal and spatial split constants in
  [`src/splits.py`](../src/splits.py).
- Implemented registry-aware rollout resumption and strict pair-file loading.
- Implemented a 39-check integrity audit.
- Added calibrator guardrails that report event skill beside MAE and refuse to
  save a calibration model that harms Very Poor+ detection.
- Added regime-shift, seasonal-transfer, anchoring, leakage, event-count,
  acquisition, offline-input, and packaging tests; all 108 tests pass locally (2026-09-08).
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
- Diagnosed the concentration-calibration failure, Aurora dynamic-range cap,
  between-city discrimination, and Delhi-dominated event support using only
  train-split out-of-fold predictions.
- Re-evaluated and retired the false claim that Patna and Varanasi have no
  forecast service; recorded the broader AQEWS/SILAM incumbent context and its
  remaining direct-portal verification caveat.
- Pre-declared the Option B ERA5 perfect-prognosis decision rule before viewing
  its result and implemented the train-only ERA5 acquisition path.
- Ran the train-only out-of-fold kill-test. Adding ERA5 raised pooled AUC from
  0.927 to 0.973 and best CSI from 0.476 to 0.682; Patna rose from
  0.745/0.159 to 0.928/0.455. The pre-declared proceed gate passed, but these
  are perfect-prognosis ceiling results rather than operational forecast skill.
- Pre-declared and ran the forecast-versus-analysis gate on exact 12Z NOAA GFS
  cycles for all 32 train dates. GFS raised pooled AUC from 0.927 to 0.961 and
  CSI from 0.476 to 0.638, including +0.108/+0.101 in Patna, and passed the
  free-NWP-sufficient rule. Aurora 1.5 inference is not warranted for BLH.

## In progress

- Capturing the rolling SILAM operational archive while cycles remain online.
- Freezing the generated 24-hour and hourly tables and connecting them to the
  reporting package.
- Resolving historical raw-data redistribution in the already-public repository before a
  public launch.

## Blocked or absent

These are not complete and must not be implied in public claims:

- **Fully clean audit:** one auxiliary PM-bin ordering check remains failed.
- **Published/versioned 24-hour table:** generated locally but not released.
- **Certified Component A:** absent; pooled metrics improve, but L1 +84-hour
  POD regresses relative to raw Aurora.
- **Fine-tuning design:** absent.
- **Scoped Aurora fine-tune:** not run.
- **Latest-cycle forecast runner:** absent.
- **Immutable live forecast ledger:** absent.
- **Public experimental forecast feed:** absent.
- **Independent post-monsoon test:** absent.
- **Transferable non-Delhi episode evidence:** absent; 89.1% of benchmark
  events are Delhi, L2 is mostly Kolkata, and Varanasi has zero events.
- **Resolved Varanasi observation level:** absent; independent CPCB/UPPCB
  cross-check remains required before any Varanasi claim.
- **Verified city-level incumbent comparison:** absent; AQEWS portal coverage
  and initialization-aligned SILAM comparison remain unresolved.

The forecast-BLH gate is complete: free GFS retains enough train-only episode
signal to pass. Do not spend GPU budget on Aurora 1.5 for BLH. This does not
unlock the temporal test split or establish year-round operational skill.
Product work may continue with clearly labeled illustrative data, but the
public target and default city must not preserve the falsified “unserved city”
story or imply Varanasi episode evidence that does not exist.

## Legacy pilot files

The current rollout replaced the scheduled pilot dates 2025-02-19, 2025-03-03,
and 2025-06-03 with 159-station outputs. Two pilot-only files remain:
2025-11-15 and 2025-11-20. Neither belongs to the frozen schedule. The strict
evaluator rejects them by date, which prevents silent contamination. Historical
pilot metrics may explain engineering decisions, but they are not valid
benchmark results.

## Next

The critical scientific sequence is:

1. Freeze per-city, per-window, pooled, L1, and L2 retrospective artifacts and
   connect the generated 24-hour table to the reporting package.
2. Preserve the rejected concentration calibrator and do not replace it with
   another concentration-regression-plus-threshold pipeline.
3. Resolve the Varanasi data anomaly and incumbent comparison before a
   city-specific public claim.
4. Review the SILAM provenance and pre-declare an initialization-aligned
   incumbent comparison.
5. Treat GFS as the qualified forecast-BLH source; do not run Aurora 1.5 for
   this purpose without a new incremental-value contract.

The public-product sequence can run beside it:

1. Define a stable forecast JSON schema.
2. Build an interactive city page against labeled example data.
3. Implement a latest-cycle runner and immutable forecast ledger.
4. Run privately in shadow mode.
5. Publish a clearly labeled experimental feed with raw forecasts, corrected
   forecasts, freshness indicators, and rolling verification.

## Claim boundary

It is accurate today to say:

> IndiaAQBench is an event-focused benchmark that completed a 56-date,
> 159-station comparison of Aurora, CAMS, persistence, and cheap local
> adaptation, exposed where pooled and average-error evaluation fail, and is
> showed with a pre-declared perfect-prognosis ceiling test that boundary-layer
> meteorology contains substantial episode-prediction headroom, and is now
> measuring how much survives in a real forecast before spending more compute.

It is not yet accurate to say:

- Aurora or an adapted method is generally better than persistence or a
  verified Indian incumbent;
- the benchmark demonstrates Patna, Kanpur, Lucknow, or Varanasi episode skill;
- Patna or Varanasi lacks an existing forecast product;
- the system has been validated across the full year;
- the system provides reliable forecasts for unmonitored cities;
- a public real-time forecast feed is operational;
- the project provides official air-quality or health warnings.

Return to the [README](../README.md) or read the
[benchmark specification](BENCHMARK_SPEC.md).
