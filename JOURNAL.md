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

---

# July 25, 2026 — 3-date train completion, first real calibrator result, and redesign decision

Status update and outcomes from the first real calibration pass:

- Orchestrator status:
  - 2025-02-19 and 2025-06-03 completed first.
  - 2025-03-03 initially failed due to a corrupted cached CAMS zip (wrong
    file size).
  - Cleared bad cache and reran the single date; rerun completed cleanly.
  - Train split is now complete for 3 dates (winter, pre-monsoon, monsoon),
    with 2 post-monsoon test dates already available.

- Calibrator implementation/compatibility fix:
  - Hit a pickle module-resolution issue when loading a model fit via module
    execution as __main__.
  - Fixed model save behavior in [src/model/calibrator.py](src/model/calibrator.py) so saved objects resolve to
    the proper qualified module path and can be loaded from different entry
    points (including benchmark runner).

- First real calibrator result (pooled learned regressor):
  - Training rows: 1,818 (initial fit window before 2025-03-03 completion).
  - L2 held-out-city MAE improved in quick look (about 46.3 -> 35.4 ug/m3).
  - Full benchmark exposed catastrophic event regression:
    - Very-Poor+ POD dropped to 0.00 at all evaluated leads.
    - On 99 severe events in test, raw Aurora detected 66; calibrated detected 0.
  - Key behavior: calibrated predictions were compressed and did not reproduce
    extreme concentrations, indicating tail collapse.

- Post-mortem conclusion:
  - MAE-only improvement was misleading; event metrics are the operational
    priority for warning use.
  - Root causes:
    1. Structural objective mismatch (predicting observations directly instead
       of correcting Aurora signal).
    2. Tree regressor non-extrapolation under seasonal distribution shift.
    3. Train/test regime mismatch (no post-monsoon training dates by split
       design constraints).
    4. Process gap: fit-time summary emphasized MAE and lacked event-safety
       gate at decision time.

- Redesign direction agreed for next implementation phase:
  - Component A first: online per-station multiplicative anchoring based on
    trailing obs/Aurora ratios, with shrinkage toward 1.0 and ratio clipping.
  - Mandatory no-harm guardrail: calibrated event POD must not underperform raw
    Aurora POD.
  - Keep a constrained learned residual as optional Component B only after
    Component A is benchmarked and passes guardrails.

- Current metric artifact location:
  - Latest benchmark outputs written to
    [results/metrics/indiaaqbench.csv](results/metrics/indiaaqbench.csv).

# July 25, 2026 (cont.) — Data forensics, split revision, and an integrity audit

Triggered by the calibrator post-mortem: before building the redesign, we went
looking for *better data* and for mistakes we might already have made.

### Archive probe — two findings, one bad, one very good

Ran a new metadata probe ([src/data/archive_probe.py](src/data/archive_probe.py))
to test whether OpenAQ history could be backfilled to give the calibrator
severe-season training data.

- **Backfill is impossible.** OpenAQ location metadata advertises coverage since
  2016, but the `/sensors/{id}/hours` endpoint returns **zero rows before
  ~Feb 2025 for every sensor tested — retired and active alike**, across all
  target cities. The post-monsoon training gap is real, not a pull bug. Recorded
  so nobody re-investigates it.
- **We were silently losing ~40% of our stations.** `find_pm25_stations` took
  only the *first* PM2.5 sensor per location via `next(...)`. Most Indian CPCB
  stations expose **two** (a retired unit plus its replacement); whenever the
  first-listed one was dormant it returned 0 rows and the entire station
  vanished from the dataset. Fixed by merging all sensors per station.
  Recoverable: patna 4→7, varanasi 2→4, kanpur 2→3, lucknow 4→6, kolkata 9→15 —
  concentrated in exactly the thin-coverage cities the benchmark depends on.
  Verified live: varanasi 21,628 rows / 2 stations → 43,329 / 4.

### Temporal cutoff revised 2025-07-01 → 2025-12-01 (disclosed)

Monthly severe-event density showed the original split gave training only
Feb–Jun 2025 — the calm half of the year, p95 ≈ 142 µg/m³, **no severe season at
all**. That is precisely why the v1 calibrator never learned values above 107.

Exercised the contingency pre-registered in spec §6, once, before any adaptation
was trained on the new split:

| | train obs | train events ≥121 | train p95 | test events |
|---|---|---|---|---|
| Original | 245K | 13,844 | ~142 | 78,569 |
| **Revised** | **507K** | **40,538** | **~360** | **51,875** |

Post-monsoon 2025 (Diwali + stubble burning) moves into train; winter 2025-26
stays in test — both sides now contain the severe regime. The frozen date list
survives the change (32 train / 24 test, test still spanning winter/pre-monsoon/
monsoon), though it must be re-run once the registry settles.

Split constants had been **duplicated across three modules** — the setup where
definitions drift until one module trains on rows another calls "test".
Consolidated into [src/splits.py](src/splits.py) as the single source of truth.

### Pull hardening (learned the hard way, mid-run)

The re-pull immediately hit the flaky home connection: **Lucknow 22/22 windows
failed, Kolkata 15/22**. Two fixes:

- Monthly windows, each written to its own part file atomically the moment it
  lands; re-running skips completed windows; `.empty` markers; per-window
  accounting so an incomplete city logs `partial`, never a silent `ok`.
- **A partial pass must not overwrite good data.** Assembling Kolkata from its
  surviving 7 windows replaced a complete 93k-row CSV with 55k. Assembly is now
  deferred until a pull is whole (or `--assemble-only` is passed explicitly);
  Kolkata was restored from `data/openaq/_backup_pre_sensorfix/`.

### Integrity audit — 32/33 checks pass

New [src/eval/audit.py](src/eval/audit.py) independently re-derives the
quantities everything else depends on, rather than trusting them:

- **Grid matching brute-forced** against the full 451×900 Aurora grid — 0
  mismatches, worst cell distance 22.9 km (max possible 32.0).
- Registry coordinates match observation coordinates to 1e-6 km.
- `valid_time == init(12:00 UTC) + lead_h` exactly; leads exactly 0…96 step 12.
- Unit conversion sound: pm2p5 median 49 µg/m³ (a missing 1e9 would read ~1e-8);
  temperature in Kelvin; pressure in Pa; pm1 ≤ pm2p5 ≤ pm10 everywhere.
- POD/FAR recomputed by hand against the module — exact match. CPCB band edges
  (30/60/90/120/250) correct.
- No split leakage: no held-out city and no test-period row in train.

**The one real finding: registry-version skew.** The two Nov-2025 pilot dates
were sampled at 33 stations (some Phase-1 era, since retired) while the three
train dates used 127 — so pooled metrics mixed two station populations. This
does not overturn the v1 post-mortem (the tail collapse was about the *value*
distribution: training p95 98 vs test max 548), but the exact POD figures rest
on inconsistent footing and those dates must be regenerated. Orchestrator now
stamps a `registry_version` fingerprint into the manifest so skew is detectable
instead of silent.

### Session infrastructure

Added `CLAUDE.md` (auto-loaded, so any session knows the project, ground rules
and settled decisions without being told), [docs/HANDOFF.md](docs/HANDOFF.md),
[docs/WORKSTREAMS.md](docs/WORKSTREAMS.md) (six workstreams with exclusive file
ownership so parallel agents cannot collide), and
[docs/SESSION_STARTERS.md](docs/SESSION_STARTERS.md) (copy-paste prompts).
Honest note recorded there: the critical path is serial — parallelism helps
*beside* it, not *on* it.

---

# July 27, 2026 — WS-4: Reporting & Dashboard Package Built

Built `src/report/` on branch `ws4-dashboard` according to WS-4 specification (`docs/WORKSTREAMS.md`):

- **Package architecture** (`src/report/`):
  - `src/report/__init__.py`: Clean public exports.
  - `src/report/scorecard.py`: Metrics loader, summary aggregator, Markdown report renderer (`generate_markdown_report`), and CLI with `--selftest`. Emphasizes Very Poor+ (≥121 µg/m³) event skill (POD, FAR, CSI) and AQI category hit rate as headline metrics over secondary MAE.
  - `src/report/plots.py`: Publication-ready static matplotlib figures rendered to `docs/figures/` (Very Poor+ event skill vs lead, AQI 6-band category accuracy vs lead, per-city breakdown, executive dashboard summary).
- **Self-test & verification**: Added `scorecard._test()` self-test that verifies metrics loading, table pivoting, markdown generation, and figure generation on synthetic benchmark data.


# July 28, 2026 — Re-pull COMPLETE: 1.49M station-hours, dates re-frozen with post-monsoon train

### The last three windows, and a lesson about rate limits

Delhi's final 3 windows (Oct/Nov/Dec 2024) failed identically on every pass with
`HTTPError` while everything else converged. Root cause was elegant: those are
the *empty* months, so all ~170 Delhi sensor requests return instantly — no
download time to pace them — firing fast enough to trip OpenAQ's per-minute
rate limit (HTTP 429). Data-rich windows self-pace; smaller cities never burst
that hard. Our retry budget (4 tries, 15 s total) could not outlast a per-minute
window, so the failure was deterministic. Fix in `openaq_client.py`: honor
`Retry-After`, extend 429 backoff past the rate window (8 tries, ≤75 s), and
pace sensor fetches at 0.35 s. Delhi completed on the next pass.

### Final archive (sanity gate: every city gained stations, none lost rows)

| city | rows | stations (pre-fix) |
|---|---|---|
| delhi | 589,759 | 64 (55) |
| mumbai | 335,822 | 36 (32) |
| kolkata | 155,484 | **15 (9)** |
| bangalore | 112,258 | 16 (13) |
| chennai | 78,154 | 8 (6) |
| patna | 74,507 | **7 (4)** |
| lucknow | 66,828 | 6 (4) |
| varanasi | 43,329 | **4 (2)** |
| kanpur | 33,393 | 3 (2) |

**~1.49M station-hours, 159 registry stations** (was ~942K / 127). The held-out
cities — the benchmark's weakest point — roughly doubled.

### Dates re-frozen under cutoff 2025-12-01

`coverage_audit --n 56`: 32 train / 24 test, 8 per stratum — and **post-monsoon
now has 8 TRAIN dates** (Oct–Nov 2025), the entire point of the cutoff revision.
Post-monsoon has no *test* dates (Oct–Nov 2026 hasn't happened); the severe test
season is winter 2025-26, present with 8 dates. Both sides of the split now
contain the severe regime. Held-out cities: 288–320 usable train dates, 224–226
test — L2 validation is comfortably feasible.

Audit: 34 checks, 0 failures; the 2 expected warnings (pilot dates on the old
33-station registry) stand until those dates are regenerated in the full run.
Also declared `pytest` in requirements (tests existed but could not run on a
fresh clone) and untracked ~380 MB of data blobs after fixing the gitignore
subdirectory gap (`26d6005`).

**Next:** WS-6 — the 56-date rollout (`scripts/setup_gpu.md`), which regenerates
the two stale pilot dates on the 159-station registry as a side effect. Then
Component A + calibrator re-fit on data that finally contains a severe season.

---

# July 29, 2026 — Integration, public-product design, and pre-publication audit

All completed Claude/Codex workstreams were reviewed together on `master`.

### Component A

Integrated the chronological per-station trailing-ratio anchor in
`src/model/anchor.py` and its benchmark hook. It uses only forecast errors whose
verifying observations occur strictly before initialization, isolates station
histories, shrinks thin support toward no correction, clips multipliers, and
reports sample count, support age, and fallback status.

Independent review found two edge cases before merge:

- a zero Aurora forecast is valid maximum-underprediction evidence, so the
  estimator now uses `max(raw, epsilon)` rather than discarding zero;
- twice-daily cycles can verify multiple forecast leads against one observation,
  so support is deduplicated by verifying time and the shorter lead is retained.

The source now states an important boundary: retrospective timestamps can
prevent future-observation leakage, but the archive cannot prove when an
observation was retrieved. A live adapter must additionally enforce
`retrieved_at <= init_time`.

### Evaluation and provenance hardening

The strict evaluator previously filtered registry versions but still admitted
any extra pair date produced with the current registry. It now requires the
exact frozen 56-date manifest, all 159 stations, all nine lead rows, no duplicate
keys, 1,431 rows per date, and no missing dates.

Registry fingerprints previously hashed station IDs only. A city or coordinate
correction with the same IDs could therefore reuse stale samples. The
fingerprint now canonicalizes and hashes station ID, city, latitude, and
longitude.

Event metrics now preserve hits, misses, false alarms, observed events, and
forecast events beside POD/FAR/CSI. The observed-extremes-only table no longer
reports FAR, which is undefined as a diagnostic after all non-event rows have
been removed.

### Scientific documentation correction

The earlier journal entry's revised-training “p95 ≈360” was a provisional
mislabel. Recalculation on the completed archive gives:

| Population | Rows | Very Poor+ events | p95 | p99 |
|---|---:|---:|---:|---:|
| All pre-cutoff archive | 824,615 | 68,519 | 163 | 334 |
| Six-city train pool | 691,327 | 63,188 | 175 | 352 |
| Calibrator spatial fit pool | 578,113 | 52,024 | 171 | 343 |

The old value was effectively p99, not p95. The split rationale remains valid
because fitting still contains tens of thousands of severe observations.
`docs/BENCHMARK_SPEC.md` and `src/splits.py` now carry the correction.

### Product and additional data

Added a non-operational interactive preview under `web/`, with every number
labeled illustrative. Added the public product, immutable live-feed, data
expansion, and independently verified source-audit documents. The first
additional scientific baseline is actual CAMS forecasts at +12 through +96
hours; the existing `raw_cams` field is only the CAMS starting field held
constant. The official OGD India CPCB feed is suitable for a small live
Patna/Varanasi redundancy pilot, not verified historical backfill. FIRMS and
Sentinel-5P remain explanatory until a leakage-safe ablation proves predictive
value.

### Publication gate

GitHub is still private. A history audit found hundreds of megabytes of raw
OpenAQ files in reachable earlier commits, despite their removal from `HEAD`.
There is also no software licence and the local Python/Node runtimes are
unavailable. The repository must remain private until the remaining gates pass
and the owner chooses a clean public mirror or explicitly authorizes a reviewed
destructive history rewrite.

Static integration checks completed here: no credential-pattern candidates in
119 tracked/new files, no candidate file above 5 MB, no broken relative links
across 23 Markdown files, all documentation JSON blocks parse, package/lock
metadata agree, and `git diff --check` passes. Python tests, the data audit, and
the web build were not runnable in this local environment.

After private push, GitHub Actions run `30473089540` passed all 26 Python tests
and the web install/build/render tests on commit `48135cc`. The data-dependent
integrity audit remains unrun because it needs the complete local archive plus
a repaired Python interpreter. The workflow actions were then updated to their
current official v7 major releases to remove the runner's Node 20 deprecation
warning.

## 2026-07-29 — Final non-GPU integration and data acquisition

Integrated and independently reviewed every completed workstream on `master`.
Component A, calibrator guardrails, reporting, public-product documentation,
the interface preview, actual CAMS forecasts, and the bounded official OGD
diagnostic now share one tested repository state.

The operational CAMS baseline is no longer the Aurora lead-zero input carried
forward. `src/data/cams_forecast.py` retrieves the actual +12 through +96-hour
CAMS PM2.5 forecast, retains the exact request and raw GRIB, records checksums
and retrieval provenance, performs a guarded single unit conversion, and
samples the same 159-station support as Aurora. The evaluator now labels the
two comparisons separately as `cams_lead0_fixed` and `cams_forecast`.

Downloaded all 56 frozen CAMS cycles locally in disjoint resumable workers.
The reusable validator confirmed:

- 56/56 exact frozen dates, with no extras;
- 159 stations and eight positive leads per date;
- 71,232 station-lead rows;
- matching raw-GRIB and extracted-sample SHA-256 records;
- PM2.5 range 1.59 to 363.62 ug/m3;
- maximum station-to-grid-cell distance 27.75 km;
- no retrieval failures.

The GPU workers must receive this validated `data/cams_forecast/` directory
before Aurora inference. The orchestrator re-verifies and re-extracts the
archive at the current registry version. Its resume path now checks that the
referenced pair artifact actually exists and has the correct date, registry,
station support, leads, row count, and CAMS coverage. Four-worker manifest
collection is append-only through `scripts/merge_worker_manifests.py`, avoiding
the prior overwrite risk.

The interface preview passed a real browser interaction check for city,
method, and forecast-day controls. Its production dependencies were patched:
the production-only audit reports zero known vulnerabilities. The owner-only
Sites deployment succeeds; every displayed forecast remains explicitly
illustrative.

The Windows Python 3.11.9 base runtime and project virtual environment were
restored, and a checksum-verified portable Node.js 24 runtime was used for
local web verification. Final local results:

- Python tests: 64/64 passed;
- CAMS archive validator: passed;
- report self-test: passed;
- Python dependency check: clean;
- web build/render tests: passed;
- production web dependency audit: zero vulnerabilities;
- integrity audit: 39 checks, 36 pass, two expected legacy-pair warnings, and
  one expected failure — zero of 56 current-registry Aurora rollout dates.

That sole audit failure is now the exact scientific boundary. All required
observations and the actual CAMS comparator are local; only the paid GPU Aurora
inference remains before raw, Component A, and calibrated scorecards can be
trusted. Public release remains a separate governance decision because the
private repository has no licence and reachable history contains raw OpenAQ
archives.

## 2026-08-02 — Credential-free GPU input preparation

Downloaded the complete global CAMS atmospheric initialization archive needed
by Aurora for all 56 frozen dates. The retained immutable ZIPs total
13,310,703,591 bytes (12.397 GiB). A deep validation extracted every archive,
opened both surface and pressure-level NetCDFs, checked all Aurora-required
variables, coordinates, and dimensions, checked ZIP integrity and stored
hashes, and confirmed exact date coverage with no missing or extra files.

The final date, 2026-06-26, exposed an operational edge case: Copernicus jobs
continue server-side after a local client process exits. Several client waits
were interrupted before the provider finished, creating duplicate remote jobs.
The provider job ledger showed that the surface results had succeeded and two
pressure jobs were still running. Recovered one existing surface result and one
existing pressure result by job ID rather than submitting further work, checked
both ZIP CRCs, combined them into the canonical two-member archive, and stored
the provider IDs and component hashes in provenance. No completed date was
overwritten.

Added guarded acquisition and execution infrastructure:

- atomic CAMS analysis downloads with request/provenance records and SHA-256;
- safe ZIP extraction and complete NetCDF variable validation;
- bounded multi-date acquisition, offline validation, and split-request
  recovery for provider queue failures;
- fail-closed `--offline-inputs` orchestration that verifies every assigned
  CAMS forecast and analysis before loading Aurora;
- deterministic four-worker packaging, 14 dates per worker, with per-file and
  whole-bundle hashes;
- a GPU runbook that sends no Copernicus, OpenAQ, GitHub, or private SSH
  credentials to disposable workers.

Verification before packaging:

- atmospheric inputs: 56/56 dates, 12.397 GiB, deep validation passed;
- Python tests: 83/83 passed;
- Python dependency check: clean;
- integrity audit: 39 checks, 36 pass, two expected stale-pilot warnings, and
  one expected blocker — no current-registry Aurora pairs yet.

The next irreversible-cost boundary is unchanged: launch one GPU worker as a
single-date canary from a validated offline bundle, inspect its pair file and
manifest, then launch the remaining disjoint workers only if the canary passes.

## 2026-08-03 — RunPod canary and worker-00 completion

Provisioned one on-demand RunPod RTX A6000 (46,068 MiB VRAM) and connected by
passphrase-protected SSH. No provider, OpenAQ, GitHub, or RunPod account
credential was copied to the worker. The source snapshot and worker-00 bundle
passed whole-file SHA-256 verification before extraction; the bundle contained
exactly 14 dates and 98 manifest-listed input files from source commit
`181487e3de886cd9919c52a47dd7fac6fdc191e6`. Deep validation opened all 14 real
CAMS NetCDF inputs. That validator legitimately refreshed each analysis
provenance `extraction` block; comparison with the TAR proved no other field
changed, after which the verified originals were restored and all 98 manifest
hashes passed.

The official RunPod PyTorch template already provided PyTorch 2.8.0 + CUDA
12.8. Reusing it through a local-container-disk venv avoided a severe network
volume installation stall and dependency drift to a newer CUDA stack. Runtime
gates passed: a real CUDA tensor operation, RTX A6000 detection, Aurora 2.0.0,
`cfgrib`, `eccodes`, `pip check`, and the then-current 83-test suite. The
official 5.10 GB Aurora air-pollution checkpoint was cached under persistent
`/workspace`; model loading used about 4.86 GB for parameters.

The first 2025-02-19 canary completed all eight GPU steps but failed while
writing Parquet because `requirements.txt` did not declare a Parquet engine.
This was a valuable fail-before-scale result: added `pyarrow`, installed it on
the worker, and reran the canary. The corrected canary produced exactly 1,431
rows (159 stations × nine leads) in 59 seconds, with current registry
`159:4c0b55ad238f`, unique station-lead keys, exact valid-time alignment,
finite non-negative Aurora PM2.5, and finite non-negative CAMS PM2.5 at all
positive leads.

After that gate passed, resume skipped the accepted canary and ran the other 13
dates in `slice_00`. Every date completed in 59–66 seconds at 29.2 GB peak VRAM;
worker 0 finished with 14 dates, 20,034 unique date-station-lead rows, 14
current-registry success records, and zero current-registry errors. Aurora
PM2.5 spans 2.79–237.56 µg/m³ across the slice. Copied only those 14 pair files
and a distinct worker manifest home; all 15 copies matched the remotely
validated originals byte-for-byte by SHA-256.

Two more automation defects were caught before workers 1–3. First, the source
archive carried tracked pilot pairs and its legacy manifest, so a copied worker
manifest would contain stale records. Curated `manifest_worker_0.jsonl` to its
14 valid records and updated the runbook to clean disposable output ledgers
before launch. Second, the orchestrator caught per-date exceptions and exited
zero after a failed batch, while error records omitted `registry_version`.
It now continues through later dates but exits non-zero after the loop if any
date failed, and stamps every error with the current registry. The focused
regression test plus the full remote suite pass: 84/84 tests and `pip check`
clean.

The local pair files are preserved, but the Windows project `.venv` is not
currently executable: its launcher points at a missing Python 3.11 base and no
`python`/`py` command is on `PATH`. Therefore the data-dependent local audit was
not rerun. Next: stop worker 0, run only bundles 01–03 on three clean temporary
workers using the updated source/runbook, retrieve 60,102 additional rows, then
repair local Python and require the audit before scoring or adaptation.

## 2026-08-04 — Full four-slice Aurora rollout returned and verified

Completed slices 01, 02, and 03 concurrently on a RunPod machine with three
RTX A6000 GPUs, using isolated `/workspace/workers/01`, `/02`, and `/03` trees
and `CUDA_VISIBLE_DEVICES=0`, `1`, and `2`. Each worker received only its exact
14-date offline bundle. Before extraction, every outer archive matched its
documented byte size and SHA-256; after extraction, all 98 inner-file hashes
and all 14 deep CAMS date checks passed per bundle. Original inputs were
restored after the deep validator's provenance mutation and rechecked.

Each of the four slices now has 14 dates, 20,034 unique
date-station-lead rows, 159 stations, a current registry stamp, and zero
errors. The combined inventory is 56 unique frozen dates and 80,136 rows. The
14 pair files and distinct manifest from each new worker were copied locally;
every local artifact matched its remote source by SHA-256. Worker 0's earlier
14 files and curated manifest remain preserved and verified the same way.

No provider credentials, SSH private key, or OpenAQ observation archive were
placed on a GPU worker. The GPU phase is complete; further work is local and
CPU-side. The four manifests remain deliberately separate until
`scripts/merge_worker_manifests.py` runs. The full data-dependent integrity
audit has not yet been rerun because the local `.venv` launcher points to a
missing Python 3.11 base runtime. Therefore no calibration was fitted and no
metrics were published. The exact RunPod environment passed 84/84 tests.

Next: repair or recreate local Python 3.11, merge manifests 0–3, run
`python -m src.eval.audit`, and proceed to raw, Component A, and guarded
calibrator scorecards only if the audit passes.

## 2026-08-04 — Post-rollout validation: environment recovered, audit run, gates split

Re-derived the post-GPU state from the artifacts rather than from the
documentation. Every figure below was reproduced independently before being
recorded.

The recorded environment blocker was wrong. The project `.venv` is executable:
Python 3.11.9, 84/84 tests passing locally, and `python -m src.eval.audit`
running to completion. The earlier failure was a restricted-sandbox path to the
base Python executable, not a missing runtime or a broken interpreter. The
entries above and `docs/HANDOFF.md` overstated it as a repository-level
blocker; that claim is retracted here.

The four-slice rollout reconciles exactly. Each worker manifest holds 14 `done`
records at 20,034 rows, all stamped `159:4c0b55ad238f`. Across the four: 56
unique dates, 80,136 rows, no date claimed by two workers, no frozen date
uncovered, no worker date outside the frozen schedule, and every referenced
pair file present on disk. The nine OpenAQ archive CSVs sum to 1,489,534
observations, matching the audit's independent count exactly. The three frozen
dates that previously held pilot artifacts — 2025-02-19, 2025-03-03 and
2025-06-03 — now each carry 1,431 rows over 159 stations with the actual CAMS
forecast column. The two legacy pilot files remain at 297 rows over 33 stations
with no CAMS column, and both audit warnings trace entirely to them.

The integrity audit was run on the completed rollout: 39 checks, 36 pass, two
expected legacy-pair warnings, one failure. The failure is the particulate
size-fraction ordering check, now characterised rather than assumed:

- 463 of 80,730 examined rows violate an inequality (0.5735%);
- 411 rows have `pm1 > pm2p5`, 64 have `pm2p5 > pm10`, 12 violate both;
- median excess 0.265 µg/m³, maximum 6.269 µg/m³, against a median Aurora
  PM2.5 of 54.09 µg/m³;
- 23 dates and every positive lead from +12 to +96 are affected;
- zero violations come from the two legacy pilot files — all 463 belong to the
  current 159-station rollout.

The likely cause is Aurora emitting its particulate channels without a
monotonicity constraint across size bins. **That remains an inference.** It has
not been proven as a model property and must not be written up as one until it
is tested.

Blast radius, checked in source rather than assumed. `src/eval/benchmark.py`
never reads `aurora_pm1` or `aurora_pm10`; it scores `aurora_pm2p5` against
observations, so the raw Aurora and Component A paths do not consume the
inconsistent channels. `src/model/calibrator.py` does: `RAW_FEATURES` includes
both `aurora_pm1` and `aurora_pm10`, so the affected rows enter the calibrator
as feature noise. There is no evidence that the PM2.5 forecast itself is
corrupted.

`scripts/merge_worker_manifests.py` must not run unchanged. It appends, and the
canonical `results/pairs/manifest.jsonl` already carries repeated dates from the
pilot era: 2025-02-19 twice, 2025-03-03 three times, 2025-06-03 twice, plus the
two November legacy records. Appending the 56 worker records would yield 65
records over 58 unique dates, with those three frozen dates at three, four and
three copies respectively. Resume stays correct because the stale records lack a
`registry_version` and `_completed_dates` filters on it, but the provenance
would be needlessly ambiguous. The merger should atomically rebuild a clean
56-record canonical manifest, or explicitly retire superseded records, before it
is run.

Decision — the scoring gate is split rather than waived:

- the failed audit check is **not** waived and `src/eval/audit.py` is not
  edited to downgrade it;
- raw Aurora and Component A scorecards may proceed **only after** the
  PM1/PM10-independence of their PM2.5 path is formally documented;
- the v1 calibrator stays **blocked** until `aurora_pm1` and `aurora_pm10` are
  removed from `RAW_FEATURES`, repaired, or their effect is measured;
- no scorecard is published before that decision is recorded in the repository.

Next: fix the manifest merger to rebuild rather than append, then merge, then
document the PM2.5-path independence before any scoring run. No repository state
other than these notes and `docs/HANDOFF.md` changed in this pass; the 42 pair
artifacts and three worker manifests remain uncommitted.

## 2026-08-04 — Canonical merge and first full-registry scorecards

Implemented the previously recorded gate decision without erasing the negative
signal. `scripts/merge_worker_manifests.py` now ignores an existing pilot-era
output, rejects conflicting records for one date, writes a deterministic
date-sorted manifest through a temporary file, fsyncs it, and atomically
replaces the canonical path. Two regression tests cover stale-output removal
and conflict refusal. The real merge produced exactly 56 `done` records, 56
unique dates, zero duplicates, zero errors, 80,136 total rows, and one registry
version (`159:4c0b55ad238f`).

The PM1/PM10 size-ordering audit remains a failure. It was not downgraded and
the model outputs were not clipped or rewritten. The PM2.5 scoring carve-out is
now explicit in `docs/BENCHMARK_SPEC.md`: persistence, both CAMS comparators,
raw Aurora, and Component A consume only PM2.5. PM1 and PM10 were removed from
the calibrator feature set, with a regression test proving that arbitrarily
changing those columns cannot change its feature matrix.

The full suite now passes 86/86 locally. The audit remains 39 checks: 36 pass,
two expected warnings from the two excluded legacy dates, and the one retained
size-bin failure.

Generated separate raw and Component A metric files locally. These are hourly
nearest-observation threshold results, not the 24-hour CPCB headline. Across
the pooled temporal test, raw Aurora scores MAE 32.76, POD 0.483, FAR 0.721,
CSI 0.215 on 2,113 events; Component A scores MAE 26.52, POD 0.566, FAR 0.585,
CSI 0.315 on the same support. Pooled L1 and L2 also improve, but L1 +84-hour
POD falls from 0.750 to 0.688 across 64 events. Component A is therefore
promising but not certified for public selection.

Refit the direct-target calibrator without PM1/PM10. It still improved MAE and
destroyed event detection: L1 POD 0.474 to 0.125 and L2 POD 0.748 to 0.299. The
guardrail refused to save it. This shows that auxiliary-bin noise was not the
cause of the calibrator's fundamental severe-tail failure. Renamed the old
tracked binary to `rejected_pilot_calibrator.joblib` and changed the accepted
default path to `accepted_pooled_calibrator.joblib`; no accepted artifact
exists.

Next: implement a separate 24-hour/rolling-mean evaluation with coverage tests,
then freeze versioned per-city/per-lead/L1/L2 tables. Do not tune Component A on
the observed test regression; either predeclare a safety fallback or retain raw
Aurora.

## 2026-08-04 — Separate forward-24-hour headline evaluator

Implemented `src/eval/rolling24.py` from the already documented product
contract. Each forward 24-hour forecast uses trapezoidal integration of the
three 12-hour snapshots at `s`, `s+12`, and `s+24`. Observation targets use the
24 hourly values in `[start, end)`, require at least 12 reporting hours, and
exclude any window crossing the temporal cutoff. The actual CAMS forecast uses
the CAMS initialization field at lead zero, as specified. Five tests cover the
formula, CAMS lead-zero bridge, observation coverage, cutoff crossing, invalid
coverage, and pooled scope generation. The full suite passes 91/91 locally.

The evaluator generated 62,010 station windows; 51,566 meet observation
coverage. It reports per-city plus pooled temporal, train-city, L1, and L2
scopes without mixing them with the instantaneous sensitivity results.

Headline pooled-test results across all window starts: persistence MAE 21.59,
POD 0.466, FAR 0.371, CSI 0.365 (1,682 events); actual CAMS forecast MAE 31.85,
POD 0.154, FAR 0.911, CSI 0.060; raw Aurora MAE 28.22, POD 0.471, FAR 0.672,
CSI 0.239; Component A MAE 21.26, POD 0.582, FAR 0.441, CSI 0.399 (the latter
three methods share 1,704 events).

L1 improves from raw POD/CSI 0.400/0.262 to Component A 0.578/0.491, with every
window start improving POD. L2 improves MAE 30.22 to 21.31 and CSI 0.122 to
0.187, but POD falls from 0.798 to 0.755 across 94 events. That is enough to
keep Component A uncertified under the no-harm rule. Raw Aurora remains the
safe public fallback unless a new adaptation is evaluated under a newly
predeclared design; these test outcomes must not be used to tune Component A.

Next: freeze deterministic report artifacts and connect them to the reporting
package, then proceed with the immutable live-runner path and a fine-tuning
design that must clear the raw/Component A event-skill bar.

## 2026-08-11 — Documentation reconciliation after the completed rollout

No code, metric, or result changed in this session. The purpose was to remove
stale current-state claims that contradicted the verified repository.

Re-verified first, before editing anything:

- `python -m pytest -q` → 91 passed;
- `python -m src.eval.audit` → 39 checks, 36 passed, 2 expected legacy
  warnings, 1 FAILED (`pairs: pm1 <= pm2p5 <= pm10`);
- `results/metrics/indiaaqbench_24h.csv` and `indiaaqbench_24h_anchor.csv`
  exist; `results/models/` contains only `rejected_pilot_calibrator.joblib`.

Four documents asserted work that is in fact done:

- `README.md` claimed only hourly sensitivity metrics existed and listed
  "implement the 24-hour evaluation" as roadmap step 1;
- `docs/PRODUCT_SPEC.md` claimed no complete 56-date current-registry rollout
  existed and that neither CAMS method had a complete 56-date score;
- `docs/PROJECT_STATUS.md` listed implementing the 24-hour evaluation as the
  next scientific step, and still said 83 tests;
- `docs/PUBLICATION_READINESS.md` step 6 said "complete the 24-hour table".

Each was rewritten to the accurate remaining task, which is narrower: the
24-hour table is **generated but not frozen, versioned, or connected**.
`src/report/scorecard.py` still defaults to the hourly
`results/metrics/indiaaqbench.csv`, so the reporting package does not render
the 24-hour headline. That gap is now stated explicitly in `docs/HANDOFF.md`
rather than being described as unimplemented evaluation code.

Also corrected two stale test counts that were current-state claims:
`docs/WORKSTREAMS.md` (86 → 91) and `docs/EXECUTION_PLAN.md` (84 → 91, while
preserving the historical RunPod figure).

The PM-bin audit failure was deliberately left visible and was not waived,
downgraded, or reworded in any document. No scientific result, event metric, or
claim boundary was altered, and Component A remains uncertified with raw Aurora
as the public fallback.

Next: unchanged from the previous entry — freeze deterministic report artifacts
and connect them to the reporting package.

## 2026-08-11 — Diagnosis: why event skill is low, and what the real constraint is

Added `src/eval/diagnose_events.py` and `docs/EPISODE_SKILL_DIAGNOSIS.md`. All
method-performance numbers are train split, train_pool tier, out-of-fold by
init date. No test row was scored, so the held-out evidence is intact.

**The calibrator's documented failure explanation was incomplete.** "Trees
cannot extrapolate" is true but invites the wrong fix. The binding reason is
the loss, not the model family: a regressor minimizing MAE/MSE predicts near
the conditional mean, which for a heavy-tailed target sits below the upper
tail. So the MAE-optimal prediction falls below 121 even when exceedance is
likely. Improving MAE and destroying POD are the same act. Any concentration
regressor reproduces this, so no further concentration-regression calibrator
should be attempted.

Sweeping the decision threshold bounds what re-thresholding alone can win:
raw Aurora CSI 0.220 at 121 -> 0.284 at its best threshold; Component A 0.277
-> 0.355; persistence 0.251 -> 0.376. That best-CSI column is the ceiling for
any concentration post-processor.

**Aurora has a hard dynamic-range cap.** Across 20,008 train windows its
maximum is 196.1 ug/m3 while observations reach 571.8. It emits zero values
>=250 anywhere, against 281 observed in Delhi. In Lucknow and Mumbai it never
reaches 121 at all. POD in those categories is capped at zero by construction.

**The discrimination is largely between-city.** Pooled AUC 0.835 falls to 0.710
within-station. Per city: Delhi 0.767, Patna 0.640, Lucknow 0.722, Mumbai 0.422
(worse than chance). Ablation is worse news still: persistence + month + lead
gives AUC 0.908 / best CSI 0.480, and adding Aurora moves AUC to 0.919 while
lowering CSI to 0.469. On this benchmark Aurora does not clearly beat
yesterday's reading plus the month.

**The benchmark cannot answer the project's question.** 89.1% of all Very Poor+
windows are Delhi. The L2 held-out-city result is 92 Kolkata + 2 Kanpur + 0
Varanasi, so it is a Kolkata finding, not a Gangetic-city finding. Patna has 5
test events, Kanpur 2. Varanasi has zero events in 1,516 windows.

**Open data question, not a proven bug:** Varanasi's archive mean is 29.9
ug/m3, below Bangalore's 33.3, with a 4.3% exact-zero rate (~5x any other
city). The four stations are the genuine UPPCB sites at correct coordinates and
the hourly series is a coherent diurnal curve, so this is not the earlier class
of geo-matching failure. It must be settled against an independent CPCB source
before any Varanasi claim. Either way the benchmark has no Varanasi episodes.

**Direction that survives the diagnosis:** predict P(24h mean >= 121) directly
and publish an operating point. Out-of-fold ceiling estimate: AUC 0.927, best
CSI 0.476, versus raw Aurora 0.284 and Component A 0.355, with a usable
operating curve (POD 0.70 at FAR 0.40; POD 0.80 at FAR 0.49). This is a ceiling
estimate justifying a predeclared design, NOT a validated result, and it is
Delhi-dominated: per city it is Patna 0.159 and Lucknow 0.065.

Next: fix the evaluation before the model — re-freeze dates to oversample
Gangetic winter, settle the Varanasi level, and make per-target-city event
skill the headline. Fine-tuning remains the wrong next step; the limiting
factor is missing emissions/source information and station-scale
representativeness, which fine-tuning on 32 dates does not supply.
