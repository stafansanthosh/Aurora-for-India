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

Next:
- Spatial alignment (`src/data/align.py`): CAMS/ERA5 grid -> OpenAQ station.
- Phase 1 baseline metrics: CAMS PM2.5 vs OpenAQ, plus persistence baseline.
