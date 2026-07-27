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

**Ground truth: ~1M station-hours over 9 cities.** Hourly OpenAQ PM2.5 for a
6-city train/val pool (Delhi, Mumbai, Chennai, Bangalore, Lucknow, Patna) plus 3
cities **held out entirely from training** (Kanpur, Varanasi, Kolkata) — so the
benchmark measures regional *transfer*, not just within-city interpolation.

Every response is snapshotted immutably under `data/openaq/archive/` with a full
pull manifest (spec §7 reproducibility contract): anyone re-running this scores
against the exact data we used, not whatever OpenAQ returns today. Pulls are
resumable per city-month, because a home connection loses ~1 window in 3.

> **Currently being re-pulled.** A sensor-selection bug (see Phase 4) was
> silently dropping whole stations; the fix recovers roughly 40% more of them in
> the thin-coverage cities that matter most. Station counts below are mid-flight.

**Evaluation harness built and run on pilot data.** `src/eval/benchmark.py`
joins Aurora's +12h→+96h rollout to these station observations and scores four
baselines (persistence, climatology, raw CAMS, raw Aurora) on both
concentration error and the metric that actually matters for action — Indian
AQI category skill, with "Very Poor or above" (≥121 µg/m³) event detection as
the headline number, since that's the threshold that triggers GRAP emergency
actions.

### What the pilot actually shows — including the part that looks bad

**Pooled over all leads and cities, raw Aurora is *worse* than persistence:**

| Method | POD ↑ | FAR ↓ | CSI ↑ | MAE ↓ |
|---|---|---|---|---|
| Persistence | 0.52 | **0.44** | **0.38** | **38.0** |
| Raw Aurora | **0.64** | 0.67 | 0.24 | 63.4 |

Aurora detects more events, but cries wolf about twice as often, and its
combined score (CSI) is clearly behind. Reporting POD alone would flatter it;
that would be the easiest way to mislead in this whole project, so the full row
stays.

**The interesting structure is in *where* it wins.** Persistence decays as lead
time grows while Aurora's synoptic signal holds, and the event-detection rates
cross over around +60 h:

| Lead | Persistence POD | Raw Aurora POD |
|---|---|---|
| +12h | 0.67 | 0.47 |
| +48h | 0.80 | 0.50 |
| +60h | 0.53 | **0.88** |
| +84h | 0.57 | **0.79** |
| +96h | 0.70 | **1.00** |

**Treat these as a hypothesis, not a result.** They rest on 2 init dates and 99
event rows, mostly November Delhi-region; and the two pilot dates were sampled
at a 33-station registry while later dates used 127, so pooled figures mix two
station populations (found by `src/eval/audit.py`, fixed by a registry-version
stamp, and being regenerated). The testable claim: **Aurora's value is long-lead
event detection, and the job of adaptation is to fix its level and false-alarm
rate without destroying that.**

## Results so far (Phase 4 — a calibrator that failed, and what it taught)

The obvious next step was a learned calibrator: map Aurora's output plus local
meteorology to observed PM2.5, leaving the 1.3B model frozen. We built it
(gradient boosting on `log1p(obs)`), and on the headline secondary metric it
looked like a win — **MAE on held-out cities fell 46.3 → 35.4 µg/m³**.

**It was a disaster, and the benchmark caught it:**

| Lead | Raw Aurora POD | Calibrated POD |
|---|---|---|
| +60h | 0.88 | **0.00** |
| +84h | 0.79 | **0.00** |
| +96h | 1.00 | **0.00** |

Of 99 severe events in the test set, raw Aurora caught 66. **The calibrator
caught zero.** Its predictions never exceeded 107 µg/m³ against observations
reaching 548 — it had regressed everything toward its training mean, and the MAE
"improvement" came *from* discarding the extremes. For an air-quality warning
system that is the worst possible trade.

Diagnosis, from four root causes:

1. **It predicted the target instead of correcting the forecast**, so its output
   could never exceed its training distribution.
2. **Tree ensembles cannot extrapolate** — under distribution shift they clamp
   rather than degrade gracefully. Our synthetic test missed this because train
   and test came from the *same* distribution.
3. **Training data held no severe season** (95th percentile 98 µg/m³ vs test
   values to 548).
4. **The fit-time check printed MAE only** — the one metric that rewards tail
   collapse.

This is why the benchmark scores category events rather than error: **a
metric-design choice caught a failure that would have shipped silently.**

### What the failure forced us to fix

- **Went looking for better data and found a bug instead.** `find_pm25_stations`
  took only the *first* PM2.5 sensor per station; most Indian CPCB stations
  expose two (a retired unit plus its replacement), so whole stations were
  silently dropped. Recovered: Chennai 6→8 stations, Lucknow 4→6, Varanasi 2→4,
  Kanpur 2→3, Bangalore 13→16 — concentrated in exactly the thin-coverage cities
  the benchmark depends on.
- **Proved a tempting fix was impossible.** OpenAQ advertises coverage since
  2016, but its hourly endpoint serves nothing before ~Feb 2025 for *any* sensor.
  Verified at sensor level and documented, so nobody re-investigates it.
- **Revised the train/test cutoff once, and disclosed it.** Moving 2025-07-01 →
  2025-12-01 (a contingency pre-registered in the spec, exercised before any
  adaptation was trained on the new split) puts a severe season on both sides:
  training events 13,844 → 40,538, training p95 142 → 360 µg/m³.
- **Consolidated split constants into one module.** They had been duplicated
  across three files — the setup where definitions drift until one module trains
  on rows another calls "test".
- **Wrote an integrity audit** (`python -m src.eval.audit`) that re-derives what
  everything else assumes: nearest-grid-cell matching brute-forced against the
  full 451×900 Aurora grid (0 mismatches), unit conversions, `valid_time ==
  init + lead`, POD/FAR recomputed by hand, and split-leakage checks. 34 checks.
  It is what found the registry-version skew noted above.

The redesign is a per-station trailing-ratio anchor — the approach operational
air-quality systems actually use ([Kalman/analog post-processing](https://www.sciencedirect.com/science/article/abs/pii/S1352231015001405))
— which uses no training set and therefore cannot inherit a training-distribution
ceiling. Fine-tuning remains planned; this establishes the bar it must clear.

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
- [x] **Phase 4a — first calibrator: rejected, documented.** A learned pooled
      calibrator improved MAE while collapsing Very Poor+ event detection to
      zero (above). Kept in-tree as a negative baseline, with the four root
      causes and the fixes it forced.
- [ ] **Phase 4b — adaptation, redesigned.** Per-station trailing-ratio
      anchoring (no training set, cannot flatten the tail), gated by a
      no-harm-on-events rule; then a scoped fine-tune experiment — the one step
      that genuinely wants a 40–80 GB card, since it backprops through the
      rollout. The 56-date inference pass runs on a ~$0.5/hr 48 GB spot GPU, no
      A100 needed: [scripts/setup_gpu.md](scripts/setup_gpu.md).
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
- **The pilot's Very Poor+ POD numbers are computed on 2 dates / 99 event rows**
  — enough to validate the harness end-to-end and motivate a hypothesis, not
  enough to trust. They also mix two station registries (see below). Treat them
  as a hint until the full benchmark-date run lands.
- **Registry-version skew, found by our own audit:** the two pilot dates were
  sampled at 33 stations, later dates at 127, so pooled metrics span two station
  populations. This does not overturn the calibrator post-mortem (that concerned
  the value distribution — training p95 98 vs test max 548) but those dates are
  being regenerated before any figure is published.
- The station registry is uneven across cities (a handful in Kanpur/Varanasi vs
  ~55 in Delhi) — a real constraint of OpenAQ coverage, not a sampling choice,
  and part of why held-out-city transfer is scored separately from held-out-
  station interpolation.
- **Post-monsoon is the season we can least afford to get wrong and have least
  data for.** OpenAQ serves nothing before ~Feb 2025, so severe-season coverage
  is thin by construction; the cutoff revision mitigates this but does not
  eliminate it.

## Data sources & credits

- Ground truth: [OpenAQ](https://openaq.org) (CPCB / DPCC / IMD station data).
- [ERA5](https://cds.climate.copernicus.eu) and [CAMS](https://ads.atmosphere.copernicus.eu)
  data © Copernicus Climate Change / Atmosphere Monitoring Service.
- Model: [Microsoft Aurora](https://github.com/microsoft/aurora)
  ([paper](https://arxiv.org/abs/2405.13063)).

Development journal with session-by-session decisions and findings: [JOURNAL.md](JOURNAL.md).
