# IndiaAQBench

**IndiaAQBench built a rigorous station-level evaluation of Aurora in India; raw Aurora was not good enough to certify as a public city episode-warning system.**

The main completed contribution is the evaluation system and its honest negative findings: checking global forecasts against surface observations, exposing missed pollution episodes, and rejecting corrections that improve average error while weakening warnings.

## Outcome at a glance

The retrospective headline measures **Very Poor+ PM2.5 events: a forward-24-hour mean of at least 121 µg/m³**. These pooled temporal-test scores cover seven overlapping window starts from +0 to +72 hours, ending at +24 to +96 hours:

| Method | POD ↑ | FAR ↓ | CSI ↑ | Observed event windows |
|---|---:|---:|---:|---:|
| Actual CAMS forecast | 0.154 | 0.911 | 0.060 | 1,704 |
| Raw Aurora | 0.471 | 0.672 | 0.239 | 1,704 |
| Component A: locally anchored Aurora | 0.582 | 0.441 | 0.399 | 1,704 |

- **POD, probability of detection:** the fraction of observed events caught. Aurora caught about 47%.
- **FAR, false-alarm ratio:** the fraction of predicted events that did not occur. About 67% of Aurora's event predictions were false alarms.
- **CSI, critical success index:** hits divided by hits + misses + false alarms. It penalizes both kinds of error.

Counts represent station–forecast windows, not independent citywide episodes. Scores pool event counts rather than averaging lead-specific ratios. **Delhi supplies 89.1% of events across the full benchmark**; this pooled result cannot establish reliable transfer across India.

Component A uses recent local observations to adjust Aurora's level. It improves pooled results but **remains uncertified**: held-out-city (L2) POD falls from 0.798 to 0.755 across 94 events, and the separate hourly sensitivity has an L1 +84-hour POD regression. Raw Aurora is also not a certified warning product.

**Split disclosure:** the temporal cutoff was revised once, from 2025-07-01 to 2025-12-01, under a pre-registered contingency before adaptation was trained on the revised split. The original fit period lacked adequate severe-season coverage. These generated retrospective tables still need a frozen, versioned release. See the [benchmark specification](docs/BENCHMARK_SPEC.md).

## What was built

The pipeline brings together **1,489,534 OpenAQ observations, 159 stations, nine cities, and 56 forecast initializations**: 32 training dates and 24 temporal-test dates. It includes:

- Resumable collection, observation quality checks, a station registry, and station-to-grid matching.
- CAMS atmospheric initialization inputs, Aurora 0.4° inference at +12 through +96 hours, and an **actual lead-dependent CAMS forecast baseline**, alongside persistence and climatology.
- 80,136 current-registry rollout rows, including lead zero, and 71,232 positive-lead CAMS forecast rows.
- Time, station, and city splits; separate 24-hour and hourly evaluators; per-city/per-lead reporting and event counts.
- A 39-check integrity audit, leakage and fallback tests, and guardrails that refuse to save a concentration calibrator when event detection deteriorates.
- Reproducible provenance: frozen dates, registry stamps, acquisition requests, checksums, strict artifact loading, and worker manifests.

The fit/validation cities are Bangalore, Chennai, Delhi, Lucknow, Mumbai, and Patna. L1 holds out stations inside those cities; L2 holds out Kanpur, Kolkata, and Varanasi from ordinary fitting. Definitions live in [src/splits.py](src/splits.py). Component A can use earlier observations at a held-out station, so its results describe online local adaptation, not zero-shot transfer.

### How this relates to Aurora

Microsoft's original work, Bodnar et al., [*A foundation model for the Earth system* (Nature, 2025)](https://www.nature.com/articles/s41586-025-09005-y), demonstrates **global** air-pollution forecasting, including East Asia examples. Its pollution model is fine-tuned on CAMS analysis, supplemented by CAMS reanalysis, and largely evaluated against CAMS analysis. The [official Aurora repository](https://github.com/microsoft/aurora) supplies the implementation and model documentation.

IndiaAQBench asks a complementary question: **what happens when those forecasts are checked against actual Indian surface stations and scored on dangerous episodes rather than global RMSE?** This is a different evaluation target, not a replication of the paper's global score or a claim to overturn it.

## What failed and what changed

A direct concentration calibrator reduced mean absolute error (MAE) while sharply weakening event detection. In the full-registry hourly evaluation, L1 MAE improved from 33.9 to 24.5 µg/m³ while POD fell from 0.474 to 0.125. L2 MAE improved from 34.2 to 20.2 while POD fell from 0.748 to 0.299. The save guard rejected the model; no accepted calibrator is available.

This was an observed failure in this benchmark, not a universal claim that improving MAE always destroys episode detection. The [diagnosis](docs/EPISODE_SKILL_DIAGNOSIS.md) investigated limited forecast dynamic range, within-station discrimination, persistence baselines, and sparse event support. It motivated predicting **the probability of a 24-hour exceedance directly**, with an explicit alert threshold, and testing boundary-layer features before spending more on inference.

The founding target premise changed too. The project initially treated Patna, Varanasi, Kanpur, and Lucknow as lacking forecasts. Evidence of national/regional AQEWS, SILAM, and bulletin products contradicted that premise. It was [retired explicitly](docs/TARGET_REEVALUATION.md); precise city-level coverage and an aligned incumbent comparison still need verification.

I started this because air pollution was changing places I knew, and I wanted to contribute something practical. I began with limited compute and learned the acquisition, calibration, and evaluation work as it became necessary. Publishing the failures lets others challenge the assumptions and improve the work.

## Two pre-declared boundary-layer experiments

Boundary-layer height describes the depth of air available for near-surface mixing. The experiments added height, wind-based ventilation, and dew-point-depression features to an exceedance classifier.

**Both experiments are train-only and out-of-fold by initialization date:** each scored group was excluded from that fold's fitting. They use 18,934 training windows and 2,167 events. The new boundary-layer classifier has not touched the temporal test split. The retrospective methods above have already been scored there.

### 1. ERA5: does the information contain useful signal?

The rule was committed in [`2ab1c50`](https://github.com/stafansanthosh/Aurora-for-India/commit/2ab1c50), before the result in [`e0a3487`](https://github.com/stafansanthosh/Aurora-for-India/commit/e0a3487): require AUC gain ≥0.020, CSI gain ≥0.030, and improvement in a non-Delhi city with at least 50 events.

Adding ERA5 raised pooled AUC from **0.927 to 0.973** and best CSI from **0.476 to 0.682**. AUC measures how well probabilities rank event windows above non-events; “best CSI” selects a threshold on development predictions, not an approved operating point. The gate passed.

ERA5 is reanalysis valid at the target time: **perfect-prognosis hindsight, not forecast skill**. This ceiling experiment tested whether the feature direction deserved further work. [Result and caveats](docs/BLH_CEILING_RESULT.md).

### 2. GFS: does an actual forecast retain enough gain?

The follow-on contract was committed in [`b78479b`](https://github.com/stafansanthosh/Aurora-for-India/commit/b78479b), before acquisition and the result in [`bcef006`](https://github.com/stafansanthosh/Aurora-for-India/commit/bcef006). Free NOAA GFS supplied matching 12Z forecast cycles for all 32 training dates.

GFS added **+0.0336 AUC and +0.1620 CSI**, retaining about **76% and 81%** of the like-for-like ERA5 gain on the same three-hour sampling grid. It passed the pre-declared gate, so the planned **Aurora 1.5 GPU rollout for boundary-layer height was cancelled**.

This establishes useful train-only classifier signal. GFS height remains strongly biased against ERA5, Lucknow regresses on a small sample, and no operational result is established. [Forecast gate and per-city evidence](docs/FORECAST_BLH_RESULT.md).

## Limitations and current status

**The benchmark and evaluation pipeline are the completed work; a validated public forecast is absent.** The web interface uses illustrative data. There is no live forecast feed, immutable live ledger, or prospective operating-point validation.

Delhi dominates event support. L2's 94 test events comprise 92 in Kolkata, two in Kanpur, and zero in Varanasi; Patna has five temporal-test events. Varanasi has **zero events in 1,516 benchmark windows**. Its low observation levels and exact-zero frequency remain an unresolved data question requiring an independent CPCB/UPPCB cross-check. None of this supports transferable Patna/Varanasi episode skill.

There is no independent post-monsoon test. Overlapping windows and repeated stations limit independence. The 24-hour headline integrates forecast snapshots and requires at least 12 observed hours per window; hourly threshold scores are a separate sensitivity analysis and must never be pooled with it. Reporting still needs wiring to the 24-hour artifact.

The integrity audit retains **one failure: PM1 ≤ PM2.5 ≤ PM10 is violated on 463 of 80,730 stored rows**, including legacy artifacts. PM2.5 scoring paths do not consume PM1/PM10, but the full output is not physically clean. Two out-of-schedule pilot files remain excluded by the strict loader.

## Reproduction entry points

Use Python 3.11 and install [requirements.txt](requirements.txt) in a virtual environment. On Windows, use `.venv/Scripts/python.exe` in place of `python`:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m src.eval.audit
```

Run the audit before interpreting results; inspect its printed checks, not just its exit status. The retained PM-bin failure must remain disclosed. With the required local observations and forecast artifacts available:

```bash
python -m src.eval.rolling24 --anchor --out results/metrics/indiaaqbench_24h_anchor.csv
python -m src.eval.benchmark --anchor --out results/metrics/indiaaqbench_anchor.csv
```

These produce separate headline and sensitivity files. Full scientific reproduction requires upstream data access, appropriate credentials and terms, and the [controlled rollout runbook](scripts/setup_gpu.md). Bulk observations are absent from the current tracked tree; a fresh clone alone cannot regenerate every result. GPU workers use validated offline inputs without provider credentials.

For the illustrative web preview, use Node 22.13+ and run `npm ci`, `npm test`, and `npm audit --omit=dev` inside [web/](web/). The test command includes the production build.

## Ways to contribute

- Freeze scorecards with input hashes, exact populations, and per-city/per-window counts; connect the 24-hour headline to reporting.
- Independently cross-check Varanasi observations and document station identity, units, missingness, and source terms.
- Review prospective SILAM provenance and pre-declare a comparison aligned by forecast initialization and observation availability.
- Design probability calibration, alert thresholds, uncertainty estimates, and city/lead guardrails before temporal-test evaluation of the new classifier.
- Test whether Aurora adds value beyond local observations and GFS through pre-declared ablations; GPU spending needs an incremental-value case.

## Documentation and reuse

| Read | Purpose |
|---|---|
| [Benchmark specification](docs/BENCHMARK_SPEC.md) | Metrics, windows, splits, and exclusions |
| [Current handoff](docs/HANDOFF.md) | Verified state and next actions |
| [Diagnosis](docs/EPISODE_SKILL_DIAGNOSIS.md) / [target review](docs/TARGET_REEVALUATION.md) | Negative findings and corrected assumptions |
| [ERA5 result](docs/BLH_CEILING_RESULT.md) / [GFS result](docs/FORECAST_BLH_RESULT.md) | Experiments and limitations |
| [Publication audit](docs/PUBLICATION_READINESS.md) | Public-history risks and unresolved decisions |
| [Journal](JOURNAL.md) / [NOTICE](NOTICE.md) | Decision history and third-party terms |

Source code and authored documentation use the [MIT licence](LICENSE). OpenAQ and its underlying providers, Copernicus CAMS/ERA5, NOAA GFS, and Microsoft Aurora retain their respective terms. Large OpenAQ and ERA5 artifacts remain reachable in public Git history; redistribution review is unresolved. MIT does not authorize reuse of those datasets.

**Research use only.** This is not an official air-quality warning service or a validated operational forecast. Do not use it as the sole basis for health or emergency decisions.
