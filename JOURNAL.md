# May 1, 2026

Started Aurora India AQI benchmark project.

Today:
- Requested Azure A100 quota for South/West India
- Began data-source setup
- Created project repo

Goal:
Evaluate whether Aurora transfers meaningfully to Indian air-quality forecasting.
2. Write the benchmark spec before coding

---

# July 15, 2026

Credentials + first data client.

Done:
- Configured CDS API: `~/.cdsapirc` uses the new single personal-access-token
  format (not the old `uid:key` pair). Auth verified via `src/check_cds.py`.
- Filled `.env` with OpenAQ + CDS keys; added `.env` to `.gitignore`.
- Installed missing deps: python-dotenv, scikit-learn (netcdf4 already present).
- Wrote `src/data/openaq_client.py` — OpenAQ v3 client: station discovery by
  radius, hourly PM2.5 pull via `/sensors/{id}/hours`, data-quality cleaning,
  CSV output to `data/openaq/{city}_pm25.csv`. Verified end-to-end on Delhi for
  both a 2018 window (99 rows) and current data (Jul 2026, 319 rows / 2 stations).

Key API finding: use `datetime_from`/`datetime_to`, NOT `date_from`/`date_to`
(the latter is silently ignored). See COPILOT_CONTEXT.md section 4.1.

Also done:
- Wrote `src/data/era5_downloader.py` — dual-store cdsapi downloader (ERA5 from
  CDS, CAMS EAC4 PM2.5 from ADS; same token works for both). Request format
  validated: submission reaches the API's licence check, not a format error.

BLOCKED on one-time licence acceptance (must be done on the websites; these are
terms I can't accept on the user's behalf):
  1. ERA5: accept the licence at
     cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
     (Download tab -> Manage licences).
  2. CAMS: log in at ads.atmosphere.copernicus.eu, accept the data-protection
     policy, then accept the EAC4 licence on the cams-global-reanalysis-eac4
     dataset page.
Once accepted, re-run:
  python -m src.data.era5_downloader --dataset era5 --city delhi \
      --date-from 2018-02-01 --date-to 2018-02-01
  python -m src.data.era5_downloader --dataset cams --city delhi \
      --date-from 2018-02-01 --date-to 2018-02-01

Also BLOCKED: git push — no remote, gh not authenticated. Run `gh auth login`
then `gh repo create Aurora-for-India --private --source . --push`.

Later same day — pushed to GitHub (stafansanthosh/Aurora-for-India) and built
out the rest of the Phase 1 code while the downloads sit in the ECMWF queue:
- `src/utils/geo.py` — haversine + nearest-cell (unit-tested).
- `src/eval/metrics.py`, `src/eval/baseline.py` — MAE/RMSE/corr + skill vs
  persistence; persistence forecast (unit-tested: perfect->1.0, persist->0.0).
- `src/data/align.py` — ERA5/CAMS grid -> OpenAQ station alignment, coord-name
  auto-detect, nearest-cell + distance, hourly exact merge (ERA5) and 3-hourly
  merge_asof within 90min (CAMS), CAMS kg/m3 -> ug/m3 conversion. Validated on
  synthetic NetCDFs; caught two bugs pre-real-data (merge_asof us-vs-ns dtype
  mismatch under pandas 3.0; CAMS unit conversion).
- End-to-end align->metrics verified per-station on synthetic data. NOTE:
  metrics must be computed PER STATION (persistence shift is per-series; pooled
  timestamps are non-unique).

ERA5/CAMS jobs still queued at status=accepted (started=None) hours after
submission — Copernicus-side backlog, not a local hang. Download processes are
still alive; files will land when the queue clears.

STILL TODO once the NetCDFs arrive:
- Inspect real coord/var/units names; confirm align.py auto-detect matches.
- Run full pipeline for Delhi and produce the Phase 1 success metric: one MAE
  comparing CAMS PM2.5 to a real OpenAQ Delhi reading + persistence skill.
- Write a small Phase 1 evaluation runner (loops stations, writes
  results/metrics/).

---

# July 21, 2026 — PHASE 1 SUCCESS CRITERION MET

Both NetCDFs landed (ERA5 74 KB, CAMS 25 KB, Delhi 2018-02-01). Real files
matched align.py's auto-detection exactly (coords valid_time/latitude/longitude;
ERA5 vars u10/v10/t2m/sp/msl/tcwv; CAMS pm2p5 in 'kg m**-3').

Ran the full pipeline: openaq (2018-02-01..03) -> align -> run_phase1.
Caught + fixed one more real bug: the old DTU sensor reports twice per hour
(:00 and :30), so flooring created duplicate station-hours -> align.py now
averages OpenAQ per (station, hour) before merging.

### Phase 1 result — CAMS PM2.5 vs OpenAQ, Delhi, 2018-02-01 (8 stations, 159 hrs)
Sample-weighted mean MAE = **223.3 ug/m3**. Per-station MAE 115-282 ug/m3,
correlations 0.13-0.73, skill_vs_persistence strongly NEGATIVE everywhere
(-2.6 to -27). Interpretation: CAMS global reanalysis at 0.75 deg gives a single
regional PM2.5 value that cannot track the wide station-to-station variation
across Delhi, and is far worse than naive persistence. This is exactly the kind
of failure the benchmark exists to quantify — a strong motivation for the Aurora
+ local-adaptation phases.
Full table: results/metrics/delhi_phase1.csv (gitignored, regenerate with
`python -m src.eval.run_phase1 --city delhi`).

Scale-out (same day): added `src/eval/plots.py` (scatter/timeseries/MAE bar,
PNGs -> results/plots/, gitignored) and ran Phase 1 across 4 cities for
2018-02-01 (Kolkata had no OpenAQ for that window; skipped).

### Multi-city Phase 1 — CAMS vs OpenAQ, 2018-02-01 (weighted mean MAE)
| City      | Stations | Hours | MAE ug/m3 |
|-----------|----------|-------|-----------|
| Delhi     | 8        | 159   | 223       |
| Mumbai    | 1        | 23    | 218 (small sample) |
| Chennai   | 2        | 44    | 65        |
| Bangalore | 3        | 61    | 41        |

Finding: CAMS absolute error scales with pollution severity — large in the
heavily polluted cities (Delhi; Mumbai Feb), much smaller in cleaner southern
cities (Bangalore/Chennai). Delhi plots also show a diurnal PHASE error (CAMS
peaks evening, stations peak pre-dawn). Regenerate: run openaq -> align ->
run_phase1/plots per city (see commands above).

Compute decision (Phase 2): use AuroraSmallPretrained (~8GB) on a cheap cloud
GPU (T4/L4) or Colab to start — no A100 wait needed. Local torch is CPU-only
(2.11.0+cpu); any GPU box needs a CUDA torch reinstall. A100
(NC24ads_A100_v4) reserved for the full model later.

Phase 2 direction settled + scaffolded (same day):
- Discovery: installed aurora package has `AuroraAirPollution`
  (aurora-0.4-air-pollution.ckpt) that predicts pm2p5 DIRECTLY. The weather
  small model does not -> chose AuroraAirPollution (A100). Must run on CAMS
  *analysis* (not EAC4). Wrote src/model/aurora_runner.py (Batch construction
  validated on CPU via `--check`) + scripts/setup_a100.md.

Next:
- On the A100 box: extend downloader for ERA5 pressure-levels + static; add a
  CAMS-analysis composition downloader; fill assemble_inputs()/load_static_vars()
  and run the forward pass; evaluate predicted pm2p5 vs OpenAQ + Phase-1 CAMS.
- Extend Phase 1 to seasons (Apr/Jul/Oct); find a Kolkata window with data.

---

# July 22, 2026 — Phase 2 data path resolved (PAUSED mid-implementation)

Found the authoritative recipe (microsoft/aurora docs/example_cams.ipynb). Key
simplifications vs. earlier assumptions:
- AuroraAirPollution takes ALL inputs (met + composition) from ONE dataset:
  `cams-global-atmospheric-composition-forecasts` (ADS), analysis =
  `type=forecast, leadtime_hour=0`. **No separate ERA5 download needed.**
- Static emission fields come from HF pickle `aurora-0.4-air-pollution-static.pickle`
  (downloaded + inspected: 11 vars incl. static_ammonia/co/nox/so2, on the
  canonical global 0.4° grid **451x900**, lat 90→-90, lon 0→359.6). The model
  runs GLOBALLY on this grid; India is extracted from the output.
- Request = one retrieve, format `netcdf_zip` -> data_sfc.nc + data_plev.nc;
  12 surface vars + 10 atmos vars × 13 levels, times 00:00 & 12:00.
- Chosen benchmark date: **2025-11-15** (peak Delhi winter pollution + dense
  modern DPCC OpenAQ, ~46/48 hrs across 2 sensors).

DONE this session:
- `src/data/cams_composition.py` — the CAMS analysis downloader (committed, NOT
  yet run/validated).

RESUME HERE (remaining CPU-side work before any GPU spend):
1. Run `python -m src.data.cams_composition --date 2025-11-15` (needs the
   cams-global-atmospheric-composition-forecasts licence accepted on ADS; large
   global download, will queue).
2. Rewrite `src/model/aurora_runner.py` loaders to the example_cams recipe:
   load_static_vars() = HF pickle; assemble_inputs() = read data_sfc.nc +
   data_plev.nc, map short names (t2m/u10/v10/msl/pm1/pm2p5/pm10/tcco/tc_no/
   tcno2/gtco3/tcso2 surface; t/u/v/q/z/co/no/no2/go3/so2 atmos), [None] batch
   dim, lat descending, lon 0-360, time = last valid_time.
3. Validate the full Batch on CPU (shapes/units/grid vs the 451x900 static).
   Optionally attempt one CPU forward pass to prove end-to-end before GPU.
Only after (3) passes: rent the GPU (see scripts/setup_a100.md).

---

# July 22, 2026 (cont.) — PHASE 2 RESULT: Aurora ran, no GPU needed

Completed the whole Phase 2 chain in one session:
- `src/data/cams_composition.py` ran: global CAMS analysis for 2025-11-15
  (228 MB, <2 min). Real files matched the recipe + canonical 451x900 grid.
- `aurora_runner.assemble_inputs` built the full Batch from the real files;
  validated on CPU (shapes/grid/time all correct).
- Loaded the real checkpoint on CPU: 1273M params.
- **Ran the forward pass on CPU** (32 GB RAM, ~12 min) -> global PM2.5 forecast
  (450x900) at +12h = 2025-11-16 00:00 UTC. Saved to results/ (gitignored).
- `src/eval/run_phase2.py` + `plots_phase2.py`: sampled predicted pm2p5 at
  Delhi OpenAQ stations.

RESULT (Delhi, valid 2025-11-16 00 UTC, 6 stations):
  Aurora ~86 ug/m3 vs OpenAQ 187-370 ug/m3; MAE ~202 ug/m3.
Sanity check (key): CAMS analysis INPUT at Delhi was already 85-98 ug/m3, and
Aurora faithfully evolved it to 86. So the global INPUT under-represents Delhi's
extreme pollution 2-4x; Aurora inherits it. Not a model bug — same failure as
Phase 1's reanalysis, now confirmed for the operational model. Negatives are
1.6% of the global field (clean cells), India min -0.8 ~ 0; forward pass sound.

Implication: GPU is NOT required for single-timestep inference (ran on CPU).
A GPU only helps for throughput (many dates/rollouts). scripts/setup_a100.md
still valid for scale.

Next:
- Scale Phase 2 across dates/seasons + all 5 cities (loop the CPU runner, or a
  GPU for speed); build the Aurora-vs-CAMS-vs-OpenAQ three-way comparison.
- Phase 4: local bias-correction/calibration on Aurora output (the 2-4x gap is
  the target).

---

# July 22, 2026 (cont.) — Landscape research + strategy reset ("aim high")

Researched who forecasts AQ in India and how well (key source: Yadav 2025 JGR,
7-model eval vs 39 CPCB Delhi stations):
- Best: MoES AQEWS WRF-Chem 400m w/ assimilation, Delhi — Performance Index 87.
  Delhi-only, HPC, government.
- SAFAR: 4 megacities only. Global models (our raw peer group): IFS PI=60,
  GEOS-FP 52, GEFS 47, SILAM 58 — all miss high-pollution events (matches our
  2-4x finding). Academic ML (Bi-LSTM MAE 8-19): short-lead, per-station,
  non-operational, incomparable protocols.
- COVERAGE HOLE = the story: 1,296 stations / 473 cities monitored, but
  operational forecasts exist for ~4-10 metros. Patna/Lucknow/Kanpur/Varanasi
  (IGP, world-worst pollution) have stations but NO forecast.
- No standardized public eval benchmark for Indian AQ forecasting exists.
- Actionability bar = AQI *category* hit-rate (GRAP triggers on categories,
  bands are wide: Very Poor 121-250, Severe 250+), not MAE.

STRATEGY (aim-high, defensible):
1. IndiaAQBench — first open reproducible AQ-forecast benchmark for India:
   ~60 dates x 4 seasons, leads 12-96h, 9 cities (add Patna, Lucknow, Kanpur,
   Varanasi), baselines: persistence/climatology/raw CAMS/raw Aurora. Position
   against Yadav PI scores.
2. Calibrated Aurora (LightGBM/MLP on Aurora fields + time + station embed) —
   target: beat persistence + beat global-model tier at 24-96h; report category
   hit-rate/false-alarm. Claim if met: first warning-grade multi-day forecast
   for cities that have none, on a laptop.
3. Compute-equity experiment: $50 station-supervised LoRA fine-tune vs $0.50
   calibrator — either outcome is a finding re: where fine-tuning pays.
4. Capstone: "State of AI for Indian Air Quality" + cost ledger + coverage map.
Explicit non-goal: beating AQEWS in Delhi (include it; show it winning in
Delhi and us winning everywhere it doesn't exist).

---

# July 22, 2026 (cont.) — Deep-research corrections + IndiaAQBench build started

User ran external deep research; verdict: project is sound IF centered on the
benchmark + validation protocol, not a coverage-hero narrative. Corrections
adopted (all now in docs/BENCHMARK_SPEC.md v0.1):
- Patna/Varanasi/etc DO have forecasts (IMD national SILAM-based layer, ~140
  cities); grid spacing 3km-vs-5km inconsistent in public docs; AOD
  assimilation unverified for national SILAM. My earlier "no forecast" claim
  retracted.
- Only Delhi confirmed 400m WRF-Chem; other 7 AQEWS cities = varying maturity
  (Mumbai AIRWISE announced 2km; Jaipur 400m).
- Network numbers updated: 1,601 stations (566 continuous) / 583 cities (2026
  parliamentary answer).
- OpenAQ India "not fully open" -> reproducibility = archived raw pulls +
  versioned station registry + extraction scripts, not "use the API".
- Claim discipline: "no widely adopted open standard benchmark" (NOT "first").
- Validation: TWO spatial holdout levels — L1 held-out stations in seen
  cities, L2 held-out cities (Kanpur, Varanasi, Kolkata). Plus strict temporal
  cutoff 2025-07-01 (provisional).
- Headline metrics: AQI category hit rate, Very Poor+ POD/FAR/miss/CSI,
  Brier; MAE/RMSE secondary; extremes subset mandatory.
- Deployment framing: transparent research second-opinion w/ rolling
  scorecard; never an official warning system (Aurora responsible-use).

BUILT this session:
- docs/BENCHMARK_SPEC.md v0.1 (supersedes May scaffold).
- src/eval/aqi.py — CPCB PM2.5 bands + category/event metrics + Brier
  (unit-tested, incl. the Phase-2 missed-Severe failure case).
- CITIES + lucknow/patna/kanpur/varanasi; OpenAQ pulled for pilot window:
  kolkata 9, patna 4, lucknow 3, kanpur 3, varanasi 2 stations — held-out
  cities have live ground truth.
- src/data/build_station_registry.py -> data/stations.csv (33 stations,
  9 cities, committed).
- aurora_runner.run_rollout (aurora.rollout, +12h..+96h, CPU-safe generator).
- src/pipeline/orchestrate.py — resumable multi-date pipeline: download ->
  batch -> rollout -> station samples (7 surf feature vars, pairs parquet)
  + India-region pm2p5 NetCDF per date + manifest.jsonl; --cleanup deletes
  456MB/day globals. Lead 0 row = raw CAMS input (baseline #3).
- PILOT RUNNING (background): 2025-11-15 + 2025-11-20, 8 steps, CPU (~3.5h).

Next: pilot verification -> full archival OpenAQ pull (9 cities, Oct 2024..
Jul 2026) -> coverage audit -> freeze ~60 dates -> scale orchestrator (GPU
decision) -> calibrator.

PILOT VALIDATED (2 dates, 2025-11-15 + 2025-11-20, CPU ~1h/date each):
- pairs parquet schema correct: 297 rows/date = 33 stations x 9 leads
  (0,12,..,96h), 7 surf feature vars, valid_time, cell_dist_km. Lead 0 =
  raw CAMS input baseline.
- Rollout carries real multi-day episode dynamics (a Delhi station climbs
  95->218 ug/m3 over +0..+84h) — calibrator will have cross-lead signal.
- Self-cleaning works: cams_analysis/ left with only .gitkeep (456MB/day
  globals deleted). Disk stays flat at scale.
- Held-out cities produce sensible values (Varanasi 193, Kanpur 204,
  Kolkata 107 ug/m3 @ +12h) — L2 transfer test viable.
- India-region pm2p5 NetCDF ~200KB/date (kept).
Scale cost: ~1h CPU/date x8 steps -> 60 dates ~= 60 CPU-h OR ~2-4 A100-h.
This is the GPU decision point once dates are frozen.

ARCHIVAL PULL running (bg): bangalore done = 85,921 rows/13 stations over
22 months (dense). ~40 min/city -> ~6h for 9 cities. Then coverage audit.
