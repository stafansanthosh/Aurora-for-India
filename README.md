# Aurora for India — IndiaAQBench

An openly reproducible benchmark testing whether [Microsoft Aurora](https://github.com/microsoft/aurora)
— a 1.3B-parameter atmospheric foundation model, run at a small fraction of the
compute of an operational NWP system — can be adapted into a **practically
useful multi-day PM2.5 forecaster** for Indian cities.

## The research question

> Can cheap post-processing or modest fine-tuning lift a global foundation
> model into a decision-useful tier for Indian air quality — and can we prove
> it with a fixed, public, reproducible benchmark rather than a one-off demo?

**What "useful" means here is not "beats Delhi's flagship system."** Delhi runs
AQEWS (MoES/IITM, WRF-Chem, 400 m, assimilating; Performance Index 87 —
Yadav et al. 2025, JGR), and 7 more
metros have deployments of varying maturity. Nationally, IMD runs a
SILAM-based layer (WRF-driven) covering ~140 cities, including Patna,
Varanasi, and Lucknow — but in the same 2025 seven-model Delhi evaluation,
SILAM's Performance Index is 58 (global-tier models: 47–60), with "notable
discrepancies during high-pollution events." **~465 of India's cities have no
comparable public forecasting infrastructure at all.** 1,601 monitoring
stations exist across 583 cities nationally, but 28 NCAP cities still lack
continuous stations.

So the claim IndiaAQBench tests is narrower and more defensible than "first
ever": *no widely adopted, openly reproducible India AQ-forecasting benchmark
with fixed public splits, shared code, and standard baselines currently
exists* — the literature is fragmented city-by-city and method-by-method.
We benchmark the public/global tier (CAMS + Aurora) and measure whether cheap
adaptation (calibration, then scoped fine-tuning) can close enough of the gap
to be genuinely actionable — decision-relevant AQI-category skill, not just
lower MAE. Full spec: [docs/BENCHMARK_SPEC.md](docs/BENCHMARK_SPEC.md).

## Results so far (Phase 1 — global-model baseline)

Before running Aurora itself, we measure what a global atmospheric model
*already* "knows" about Indian PM2.5, using the CAMS global reanalysis (EAC4,
0.75°) as the model-side field, evaluated against real ground-station readings
from OpenAQ (CPCB/DPCC stations), for 2018-02-01:

| City      | Stations | Matched hours | CAMS MAE (µg/m³) |
|-----------|----------|---------------|------------------|
| Delhi     | 8        | 159           | **223**          |
| Mumbai    | 1        | 23            | 218 *(small sample)* |
| Chennai   | 2        | 44            | 65               |
| Bangalore | 3        | 61            | **41**           |

Two concrete failure modes, visible in the figures:

**1. Coarse resolution can't resolve intra-city variation.** Every station in
Delhi receives essentially the same CAMS value per timestep (horizontal bands),
while real stations spread widely — and skill vs. a naive persistence baseline
is negative at every station.

![CAMS vs OpenAQ scatter, Delhi](docs/figures/delhi_scatter.png)

**2. The diurnal cycle is out of phase.** CAMS puts Delhi's pollution peak in
the evening; the stations peak pre-dawn. Correlation ≈ 0.15.

![Time series, Delhi station 13](docs/figures/delhi_timeseries.png)

**Headline finding:** the global model's error scales with pollution severity —
huge in the most polluted cities (Delhi), modest in cleaner southern cities
(Bangalore). This quantifies exactly the gap a fine-tuned or higher-resolution
model must close, and motivates Phase 2.

## Results so far (Phase 2 — Aurora Air Pollution, run directly)

We then ran Aurora itself — specifically **`AuroraAirPollution`** (the 1.3B-param
`aurora-0.4-air-pollution` checkpoint), which predicts PM2.5 *directly* — on
global CAMS analysis data, and forecast +12 h from 2025-11-15 12:00 UTC (peak
Delhi winter-pollution season). Aurora reproduces India's Indo-Gangetic
pollution belt, but at Delhi its predicted PM2.5 sits far below the ground
stations:

![Aurora PM2.5 over India vs OpenAQ](docs/figures/delhi_phase2_india_map.png)

The dark dots (OpenAQ stations, 187–370 µg/m³) sit on a pale model field
(~86 µg/m³) — Aurora predicts **~86 µg/m³** for the Delhi cell while stations
read **187–370 µg/m³** (mean absolute error ≈ **202 µg/m³**).

Crucially, this is *not* an Aurora bug: the CAMS analysis it was given already
reads only 85–98 µg/m³ at the Delhi cell, and Aurora faithfully evolves that
field (86 µg/m³ at +12 h). **The global input under-represents Delhi's extreme
local pollution by 2–4×, and Aurora inherits it** — the same failure Phase 1
found in the reanalysis, now confirmed for the operational model. This is the
concrete, quantified case for local adaptation (Phase 4).

> Notably, the full 1.3B-param model ran end-to-end on a **32 GB CPU** (~12 min
> per global forecast) — no GPU was required for single-timestep inference.

## Results so far (Phase 3 — IndiaAQBench ground truth + first pilot scores)

**Ground-truth archive complete.** Hourly OpenAQ PM2.5 pulled and versioned for
all 9 benchmark cities — the 6-city train/val pool (Delhi, Mumbai, Chennai,
Bangalore, Lucknow, Patna) plus 3 cities **held out entirely from training**
(Kanpur, Varanasi, Kolkata), to test regional transfer rather than just
interpolation:

| City | Stations | Rows | Role |
|---|---|---|---|
| Delhi | 55 | 354,032 | train pool |
| Mumbai | 32 | 245,469 | train pool |
| Kolkata | 9 | 93,039 | **held out** |
| Bangalore | 13 | 85,921 | train pool |
| Patna | 4 | 42,160 | train pool |
| Lucknow | 4 | 44,637 | train pool |
| Chennai | 6 | 32,799 | train pool |
| Kanpur | 2 | 22,118 | **held out** |
| Varanasi | 2 | 21,628 | **held out** |

**~942,000 station-hours across 127 stations**, snapshotted immutably under
`data/openaq/archive/` with a full pull manifest (spec §7 reproducibility
contract) — anyone re-running this benchmark scores against the exact data we
used, not whatever OpenAQ happens to return today.

**Evaluation harness built and run on pilot data.** `src/eval/benchmark.py`
joins Aurora's +12h→+96h rollout to these station observations and scores four
baselines (persistence, climatology, raw CAMS, raw Aurora) on both
concentration error and the metric that actually matters for action — Indian
AQI category skill, with "Very Poor or above" (≥121 µg/m³) event detection as
the headline number, since that's the threshold that triggers GRAP emergency
actions.

On the first 2 pilot init-dates (276 matched forecast rows, all 9 cities),
**raw Aurora trails simple persistence on short-lead MAE — expected, since it
inherits CAMS's known under-prediction of severe episodes — but its Very
Poor+ event detection rate improves with lead time while persistence's decays,
crossing over around +60h**:

| Lead | Persistence POD | Raw Aurora POD |
|---|---|---|
| +12h | 0.67 | 0.47 |
| +48h | 0.80 | 0.50 |
| +60h | 0.53 | **0.88** |
| +84h | 0.57 | **0.79** |
| +96h | 0.70 | **1.00** |

Two pilot dates is a hint, not a result — but it's the concrete, testable
hypothesis the full benchmark run will confirm or kill: Aurora's synoptic
signal may carry real skill at exactly the lead times where a naive baseline
runs out of memory of the current state. The calibrator's job (Phase 4) is to
fix the level/bias error while preserving that long-lead event skill.

## How it works

**Phase 1 pipeline** (single-day CAMS-vs-OpenAQ baseline):

```
OpenAQ v3 API ──► openaq_client.py ──► data/openaq/{city}_pm25.csv   (ground truth)
Copernicus CDS ─► era5_downloader.py ─► data/era5/*.nc               (meteorology)
Copernicus ADS ─► era5_downloader.py ─► data/cams/*.nc               (model PM2.5)
                        │
                        ▼
                  align.py  ── nearest-grid-cell matching (haversine),
                        │      hourly join, kg/m³ → µg/m³ conversion
                        ▼
          data/processed/{city}_aligned.csv
                        │
                        ▼
        run_phase1.py / plots.py ──► per-station MAE/RMSE/correlation,
                                     skill vs persistence, figures
```

**IndiaAQBench pipeline** (Phase 3+, multi-date, multi-lead):

```
OpenAQ v3 API ──► archive_pull.py ──► data/openaq/archive/{city}_*.csv  (versioned ground truth, 9 cities)
CAMS analysis  ─► cams_composition.py ─► data/cams_analysis/*.nc       (global 0.4° input)
                        │
                        ▼
        orchestrate.py  ── assembles Aurora Batch, rolls out +12h→+96h,
                        │   samples predictions at station cells
                        ▼
          results/pairs/pairs_{date}.parquet   (aurora + CAMS pm2.5 per station × lead)
                        │
                        ▼
        benchmark.py  ── joins pairs to archived obs, scores persistence /
                        │  climatology / raw CAMS / raw Aurora baselines
                        ▼
   results/metrics/indiaaqbench*.csv ──► MAE/RMSE/bias/corr + AQI category
                                         hit-rate + Very Poor+ POD/FAR/CSI,
                                         per lead × city × method
```

Full spec, city roles, and metric definitions: [docs/BENCHMARK_SPEC.md](docs/BENCHMARK_SPEC.md).

Everything is a CLI module. Reproduce the Delhi result:

```bash
python -m src.data.openaq_client   --city delhi --date-from 2018-02-01 --date-to 2018-02-03
python -m src.data.era5_downloader --dataset cams --city delhi --date-from 2018-02-01 --date-to 2018-02-01
python -m src.data.align           --city delhi --cams data/cams/delhi_cams_2018-02-01_2018-02-01.nc
python -m src.eval.run_phase1      --city delhi
python -m src.eval.plots           --city delhi
```

Reproduce the IndiaAQBench pilot (2 dates, all 9 cities — station registry and
2 days of pairs are already committed, so this just re-scores them):

```bash
python -m src.eval.benchmark --split all
```

Re-pull ground truth or extend to new init dates from scratch:

```bash
python -m src.data.archive_pull                                    # all 9 cities, full window
python -m src.pipeline.orchestrate --dates 2025-11-15 2025-11-20 --device cpu
python -m src.eval.benchmark
```

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
```

Credentials (never committed):
- `OPENAQ_API_KEY` in `.env` — register at [explore.openaq.org](https://explore.openaq.org)
- `~/.cdsapirc` with a Copernicus personal access token — works for both the
  Climate Data Store (ERA5) and Atmosphere Data Store (CAMS); accept each
  dataset's licence once on the website.

## Status and roadmap

- [x] **Phase 1 — data pipeline + global-model baseline.** OpenAQ / ERA5 / CAMS
      clients, spatial alignment, metrics, plots; 4-city CAMS-vs-OpenAQ
      benchmark (above).
- [x] **Phase 2 — Aurora inference.** `AuroraAirPollution`
      (`aurora-0.4-air-pollution.ckpt`) run end-to-end on global CAMS analysis
      data; predicted PM2.5 sampled at OpenAQ stations (`src/model/aurora_runner.py`,
      `src/eval/run_phase2.py`). First result above (Delhi, 2025-11-15).
      GPU setup for scaling: [scripts/setup_gpu.md](scripts/setup_gpu.md).
- [x] **Phase 3 — IndiaAQBench scaffold.** Spec frozen (v0.1), 9-city
      ground-truth archive complete (~942K station-hours, 127 stations),
      multi-date orchestrator (+12h→+96h rollout), AQI category metrics module,
      and evaluation harness — all validated on a 2-date pilot (above).
      **Next:** coverage audit to freeze the full benchmark date list and
      train/test/held-out splits (`src/eval/coverage_audit.py`), then scale
      the orchestrator run to the full date set.
- [ ] **Phase 4 — adaptation.** Pooled calibrator (frozen Aurora → station
      PM2.5) first — CPU/cheap-GPU, no backprop; then a scoped fine-tune
      experiment (the one case that wants a 40–80 GB card, since it backprops
      through the rollout) if the calibrator alone doesn't close the gap.
      The 56-date inference pass runs on a ~$0.5/hr 48 GB spot GPU — no A100
      needed: [scripts/setup_gpu.md](scripts/setup_gpu.md).
- [ ] **Phase 5 — transparent research dashboard.** Public, per-city,
      per-lead-time scorecards — the point being that anyone can see exactly
      where the adapted model is (and isn't) trustworthy, city by city.

## Honest limitations (so far)

- Phase 1 covers **one day** (2018-02-01) — chosen for OpenAQ sensor overlap;
  Phase 3 (IndiaAQBench) is the real seasonal scale-out, currently at 2
  pilot dates pending the coverage audit.
- Comparing a 0.4°–0.75° grid cell to a point station carries inherent
  representativeness error; that's part of what's being measured, not a bug,
  but it means "CAMS MAE" conflates model error with resolution mismatch.
- Hourly persistence is a deliberately harsh baseline at short leads; the
  IndiaAQBench pilot result (above) is the first evidence it stops being the
  harder baseline to beat as lead time grows.
- **The pilot's Very Poor+ POD numbers are computed on 2 dates only** — enough
  to validate the eval harness end-to-end and motivate the hypothesis, not
  enough to trust as a stable result. Treat them as a hint until the full
  benchmark-date run lands.
- The station registry is uneven across cities (2 stations in Kanpur/Varanasi
  vs. 55 in Delhi) — a known constraint of OpenAQ's real coverage, not a
  sampling choice, and part of why L2 (held-out city) transfer is scored
  separately from L1 (held-out station) interpolation.

## Data sources & credits

- Ground truth: [OpenAQ](https://openaq.org) (CPCB / DPCC / IMD station data).
- [ERA5](https://cds.climate.copernicus.eu) and [CAMS](https://ads.atmosphere.copernicus.eu)
  data © Copernicus Climate Change / Atmosphere Monitoring Service.
- Model: [Microsoft Aurora](https://github.com/microsoft/aurora)
  ([paper](https://arxiv.org/abs/2405.13063)).

Development journal with session-by-session decisions and findings: [JOURNAL.md](JOURNAL.md).
