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

Next:
- Scale Phase 1 across the 5 cities + 4 seasons (Jan/Apr/Jul/Oct).
- Add ERA5-based columns to the analysis; plots into results/plots/.
- Phase 2: Aurora inference (needs A100 / Azure quota).
