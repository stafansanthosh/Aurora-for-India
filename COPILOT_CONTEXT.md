# Aurora India AQI — Project Context for GitHub Copilot

> Feed this document to GitHub Copilot at the start of every session.
> It contains the full project objective, data contracts, model I/O specs, pipeline architecture, and coding conventions.

---

## 1. Project Objective

Evaluate whether **Microsoft Aurora** — a globally pretrained atmospheric foundation model — can produce useful, reliable air quality forecasts (specifically PM2.5) for Indian cities **without region-specific fine-tuning**.

### Core Research Question

> Can a globally trained Earth-system model produce meaningful PM2.5 predictions for India using only ERA5 reanalysis data as input, and does it outperform a naive persistence baseline?

### Why This Matters

- India has among the highest air pollution variability globally
- Existing AQI prediction systems are fragmented, hard to access, and often inaccurate at local level
- Aurora is trained on global atmospheric data — its performance on Indian conditions (monsoon dynamics, dust storms, crop burning events) is unknown
- If Aurora works out of the box, it could serve as a foundation for low-cost, high-coverage AQI forecasting across India
- If it fails, the failure patterns tell us exactly what region-specific adaptation is needed

---

## 2. Repository Structure

```
aurora-india-aqi/
│
├── data/
│   ├── openaq/                  # Ground truth PM2.5 from OpenAQ API
│   │   └── {city}_pm25.csv      # One file per city
│   ├── era5/                    # Atmospheric input for Aurora
│   │   └── {city}_{date}.nc     # NetCDF files, one per city per day
│   └── processed/               # Aligned, merged datasets ready for evaluation
│       └── {city}_aligned.csv   # ERA5 grid + OpenAQ station matched by nearest cell
│
├── notebooks/
│   ├── 01_openaq_exploration.ipynb
│   ├── 02_era5_exploration.ipynb
│   ├── 03_aurora_inference.ipynb
│   └── 04_evaluation.ipynb
│
├── src/
│   ├── data/
│   │   ├── openaq_client.py     # OpenAQ API wrapper
│   │   ├── era5_downloader.py   # CDS API download scripts
│   │   └── align.py             # Spatial alignment: ERA5 grid → OpenAQ station
│   ├── model/
│   │   ├── aurora_runner.py     # Aurora inference wrapper
│   │   └── batch_predict.py     # Run Aurora over multiple timesteps
│   ├── eval/
│   │   ├── metrics.py           # MAE, RMSE, correlation, skill score
│   │   └── baseline.py          # Persistence model
│   └── utils/
│       └── geo.py               # Haversine distance, nearest grid cell lookup
│
├── results/
│   ├── metrics/                 # JSON/CSV evaluation outputs
│   └── plots/                   # Visualisations
│
├── JOURNAL.md                   # Session-by-session progress log
├── COPILOT_CONTEXT.md           # This file
├── requirements.txt
└── README.md
```

---

## 3. Target Cities

| City | Lat | Lon | Reason |
|------|-----|-----|--------|
| Delhi | 28.6139 | 77.2090 | Worst pollution in India, most OpenAQ stations, best ground truth coverage |
| Mumbai | 19.0760 | 72.8777 | Coastal city, different pollution profile, good station density |
| Bangalore | 12.9716 | 77.5946 | Primary developer location, moderate pollution, cross-check feasibility |
| Chennai | 13.0827 | 80.2707 | South India anchor, different meteorological regime |
| Kolkata | 22.5726 | 88.3639 | Eastern India, industrial pollution, high variability |

Start with **Delhi** — best data coverage. Add cities once the single-city pipeline works end to end.

---

## 4. Data Sources

### 4.1 Ground Truth — OpenAQ

**API Base URL:** `https://api.openaq.org/v3`

**Authentication:** Bearer token in header: `X-API-Key: {OPENAQ_API_KEY}`

**Key Endpoints:**

```
GET /locations?coordinates=LAT,LON&radius=25000&parameters_id=2&limit=100
  → Stations within a radius of a point. PM2.5 has parameters_id=2.
    Each result embeds a `sensors` list; pick the sensor whose
    parameter.id == 2 for its PM2.5 sensor_id.

GET /sensors/{sensor_id}/hours?datetime_from=YYYY-MM-DDTHH:MM:SSZ&datetime_to=...&limit=1000
  → Server-side HOURLY aggregates for one sensor. This is the endpoint the
    client uses (cleaner than the raw /measurements 15-min stream).
```

> **API gotchas verified against the live v3 API (2026-07):**
> - The date-window params are **`datetime_from` / `datetime_to`**. The
>   `date_from` / `date_to` names shown in some OpenAQ docs are **silently
>   ignored** on `/hours` — the API returns the sensor's entire history
>   regardless of the window, which looks like a runaway/huge result set.
> - Sensor coverage varies wildly per station. Old CPCB sensors (e.g. DTU,
>   id 13864) cover ~2016–2018; modern DPCC sensors (e.g. R K Puram, id
>   12234787) cover ~2025–present. Query `/sensors/{id}` → `datetimeFirst` /
>   `datetimeLast` to see a sensor's window before requesting data.
> - Measurement-level `coordinates` may be null; take station lat/lon from the
>   `/locations` metadata instead.

**Response shape (measurements):**
```json
{
  "results": [
    {
      "value": 45.3,
      "parameter": {"name": "pm25", "units": "µg/m³"},
      "period": {
        "datetimeFrom": {"utc": "2024-01-01T00:00:00Z", "local": "2024-01-01T05:30:00+05:30"},
        "datetimeTo": {"utc": "2024-01-01T01:00:00Z"}
      },
      "coordinates": {"latitude": 28.6508, "longitude": 77.3152}
    }
  ]
}
```

**Data contract for stored CSVs (`data/openaq/{city}_pm25.csv`):**

| Column | Type | Description |
|--------|------|-------------|
| `timestamp_utc` | datetime | UTC timestamp of measurement |
| `timestamp_local` | datetime | IST (UTC+5:30) |
| `value_ugm3` | float | PM2.5 in µg/m³ |
| `lat` | float | Station latitude |
| `lon` | float | Station longitude |
| `station_id` | str | OpenAQ sensor ID |
| `station_name` | str | Human-readable station name |
| `city` | str | City name |

**Data quality rules:**
- Drop rows where `value_ugm3 < 0` or `value_ugm3 > 1000` (instrument errors)
- Drop rows where value is identical for more than 24 consecutive hours (stuck sensor)
- Flag but keep rows where `value_ugm3 > 500` (extreme pollution events — valid in Delhi)

---

### 4.2 Model Input — ERA5 via Copernicus CDS

**CDS API config file:** `~/.cdsapirc`
```
url: https://cds.climate.copernicus.eu/api
key: {PERSONAL_ACCESS_TOKEN}
```

> Note: the CDS API changed in 2024 — the old `v2` endpoint used a `{uid}:{key}` pair; the current API uses a single personal access token from your CDS profile page.

**Dataset:** `reanalysis-era5-single-levels`

**Variables required by Aurora:**

Aurora expects a specific set of atmospheric variables. The full Aurora model uses:

| ERA5 Variable Name | CDS Short Name | Description |
|-------------------|---------------|-------------|
| `10m_u_component_of_wind` | `u10` | Eastward wind at 10m (m/s) |
| `10m_v_component_of_wind` | `v10` | Northward wind at 10m (m/s) |
| `2m_temperature` | `t2m` | Air temperature at 2m (K) |
| `surface_pressure` | `sp` | Surface pressure (Pa) |
| `mean_sea_level_pressure` | `msl` | MSLP (Pa) |
| `total_column_water_vapour` | `tcwv` | Precipitable water (kg/m²) |
| `geopotential` | `z` | Surface geopotential (m²/s²) |

For AQI-related output, also request:
| ERA5 Variable Name | CDS Short Name | Description |
|-------------------|---------------|-------------|
| `total_column_pm2p5` | `pm2p5` | Column PM2.5 — from CAMS, not standard ERA5 |

> **Note:** Standard ERA5 does not contain PM2.5 directly. Use **CAMS reanalysis** (`cams-global-reanalysis-eac4`) for PM2.5 ground truth from the model side. Dataset: `particulate_matter_2.5um`.

**CDS download script pattern:**
```python
import cdsapi

c = cdsapi.Client()
c.retrieve(
    'reanalysis-era5-single-levels',
    {
        'product_type': 'reanalysis',
        'variable': ['10m_u_component_of_wind', '10m_v_component_of_wind',
                     '2m_temperature', 'surface_pressure', 'mean_sea_level_pressure',
                     'total_column_water_vapour'],
        'year': '2024',
        'month': '01',
        'day': ['01', '02', '03'],
        'time': [f'{h:02d}:00' for h in range(24)],
        'area': [35, 68, 6, 98],   # [North, West, South, East] — bounding box for India
        'format': 'netcdf',
    },
    'data/era5/india_jan2024.nc'
)
```

**Bounding boxes per city (0.5° buffer):**

| City | North | West | South | East |
|------|-------|------|-------|------|
| Delhi | 29.1 | 76.7 | 28.1 | 77.7 |
| Mumbai | 19.6 | 72.3 | 18.6 | 73.3 |
| Bangalore | 13.5 | 77.1 | 12.5 | 78.1 |
| Chennai | 13.6 | 79.8 | 12.6 | 80.8 |
| Kolkata | 23.1 | 87.8 | 22.1 | 88.8 |

**NetCDF file structure (after download):**
```
Dimensions: latitude, longitude, time
Variables:
  u10(time, latitude, longitude)   - float32
  v10(time, latitude, longitude)   - float32
  t2m(time, latitude, longitude)   - float32
  sp(time, latitude, longitude)    - float32
  ...
Coordinates:
  latitude: array of floats, spacing 0.25°
  longitude: array of floats, spacing 0.25°
  time: array of int64 (hours since 1900-01-01)
```

**Loading ERA5 in Python:**
```python
import xarray as xr

ds = xr.open_dataset('data/era5/delhi_20240101.nc')
# Select nearest grid point to Delhi city centre
point = ds.sel(latitude=28.6139, longitude=77.2090, method='nearest')
# Extract u10 timeseries
u10 = point['u10'].values  # shape: (n_timesteps,)
```

---

## 5. Aurora Model

> **Phase 2 decision (July 2026): use `AuroraAirPollution`, not the weather model.**
> The installed `aurora` package ships `AuroraAirPollution` (checkpoint
> `aurora-0.4-air-pollution.ckpt`), which predicts **pm2p5 directly** (plus
> pm1/pm10 and CO/NO/NO2/O3/SO2) — the direct test of the research question.
> The weather models (`AuroraSmallPretrained`, etc.) do NOT output PM2.5, so the
> "small model on a cheap GPU" idea only yields meteorology. Key constraints:
> - Full size (~24 GB VRAM) → needs an **A100** (Azure NC24ads_A100_v4).
> - Must run on **CAMS *analysis*** data (ADS atmospheric-composition analysis),
>   NOT the EAC4 *reanalysis* used for the Phase-1 baseline.
> - Needs 2 history timesteps; inputs = surf (2t/10u/10v/msl + pm/gas columns),
>   static (lsm/z/slt + emission fields from a Microsoft pickle), atmos
>   (z/u/v/t/q + co/no/no2/go3/so2 at 13 levels).
> - Runner scaffold: `src/model/aurora_runner.py` (Batch construction validated
>   on CPU). GPU setup: `scripts/setup_a100.md`. The Phase-1 surface-only ERA5
>   download is NOT sufficient — pressure levels + static fields still needed.

### 5.1 Overview

Aurora is a 1.3B parameter transformer trained on 1+ million hours of diverse atmospheric data. It operates on a global grid and produces 6-hourly forecasts of atmospheric variables.

**GitHub:** https://github.com/microsoft/aurora
**Paper:** https://arxiv.org/abs/2405.13063

### 5.2 Installation

```bash
pip install microsoft-aurora
```

### 5.3 Model Variants

| Variant | VRAM Required | Notes |
|---------|--------------|-------|
| `AuroraSmallPretrained` | ~8GB | Smaller model, faster, good for development |
| `AuroraPretrained` | ~24GB (A100) | Full model, better accuracy |

**For this project:** Use `AuroraSmallPretrained` during development. Switch to `AuroraPretrained` once A100 quota is approved.

### 5.4 Input Format

Aurora requires a `Batch` object. The exact structure:

```python
from aurora import Batch, Metadata
import torch

batch = Batch(
    surf_vars={
        # Surface variables — shape: (batch=1, time=2, lat, lon)
        # time=2 means Aurora needs TWO consecutive timesteps as context
        "2t":  torch.tensor(...),   # 2m temperature (K)
        "10u": torch.tensor(...),   # 10m U-wind (m/s)
        "10v": torch.tensor(...),   # 10m V-wind (m/s)
        "msl": torch.tensor(...),   # Mean sea level pressure (Pa)
    },
    static_vars={
        # Static (time-invariant) — shape: (lat, lon)
        "z":   torch.tensor(...),   # Geopotential at surface
        "slt":  torch.tensor(...),  # Soil type
        "lsm":  torch.tensor(...),  # Land-sea mask
    },
    atmos_vars={
        # Pressure-level variables — shape: (batch=1, time=2, level, lat, lon)
        "t":  torch.tensor(...),    # Temperature at pressure levels
        "u":  torch.tensor(...),    # U-wind at pressure levels
        "v":  torch.tensor(...),    # V-wind at pressure levels
        "q":  torch.tensor(...),    # Specific humidity
        "z":  torch.tensor(...),    # Geopotential at pressure levels
    },
    metadata=Metadata(
        lat=torch.tensor([...]),    # 1D latitude array (degrees, descending)
        lon=torch.tensor([...]),    # 1D longitude array (degrees, 0–360)
        time=(datetime(...),),      # Tuple of datetime objects (one per batch item)
        atmos_levels=(50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000),  # hPa
    )
)
```

> **Critical:** Aurora expects longitudes in **0–360 range**, not -180 to 180. Convert ERA5 longitudes before feeding to the model.

> **Critical:** Aurora needs **two consecutive timesteps** (6 hours apart) as context to produce a forecast. You cannot run it on a single snapshot.

### 5.5 Running Inference

```python
from aurora import AuroraSmallPretrained

model = AuroraSmallPretrained()
model.load_checkpoint("microsoft/aurora", "aurora-0.25-small-pretrained.ckpt")
model.eval()

with torch.inference_mode():
    forecast = model.forward(batch)

# forecast is also a Batch object
# Access surface predictions:
pm25_proxy = forecast.surf_vars["2t"]   # shape: (1, 1, lat, lon)
```

### 5.6 Output Variables and PM2.5 Proxy

Aurora does **not** directly predict PM2.5 as an output variable in the pretrained checkpoint. The approach for this project:

1. **Primary approach:** Use CAMS reanalysis (`pm2p5` variable) as the "model prediction" — Aurora predicts the atmospheric state, CAMS provides the PM2.5 field for the same atmospheric conditions. Compare CAMS PM2.5 at the forecast timestep against OpenAQ ground truth.

2. **Secondary approach (experimental):** Use Aurora-predicted wind fields + boundary layer height as proxies for dispersion conditions, then apply a simple regression to estimate PM2.5. This is a research extension, not the initial goal.

3. **Simplest valid approach for Phase 1:** Download CAMS reanalysis PM2.5 for the target dates, align to OpenAQ stations, compute metrics. This tests the data pipeline without requiring Aurora to run at all, and gives a baseline for what a global model "already knows."

---

## 6. Spatial Alignment — ERA5 Grid to OpenAQ Station

ERA5 data is on a regular 0.25° grid. OpenAQ stations are point measurements. To compare them:

```python
import numpy as np

def haversine_distance(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two points."""
    R = 6371.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlambda/2)**2
    return 2 * R * np.arcsin(np.sqrt(a))

def find_nearest_grid_cell(station_lat, station_lon, era5_lats, era5_lons):
    """Return (lat_idx, lon_idx) of nearest ERA5 grid cell to a station."""
    lat_idx = np.argmin(np.abs(era5_lats - station_lat))
    lon_idx = np.argmin(np.abs(era5_lons - station_lon))
    return lat_idx, lon_idx
```

**Aligned dataset schema (`data/processed/{city}_aligned.csv`):**

| Column | Type | Description |
|--------|------|-------------|
| `timestamp_utc` | datetime | UTC timestamp (hourly) |
| `openaq_pm25` | float | Measured PM2.5 (µg/m³) |
| `cams_pm25` | float | CAMS reanalysis PM2.5 at nearest grid cell |
| `aurora_t2m` | float | Aurora predicted 2m temp (K) — for future use |
| `era5_u10` | float | ERA5 10m U-wind at nearest grid cell |
| `era5_v10` | float | ERA5 10m V-wind at nearest grid cell |
| `era5_sp` | float | ERA5 surface pressure (Pa) |
| `station_id` | str | OpenAQ station ID |
| `grid_lat` | float | Latitude of matched ERA5 grid cell |
| `grid_lon` | float | Longitude of matched ERA5 grid cell |
| `distance_km` | float | Haversine distance: station to grid cell |

---

## 7. Evaluation

### 7.1 Baseline — Persistence Model

```python
def persistence_forecast(pm25_series: pd.Series) -> pd.Series:
    """Predict t+1 = t (naive baseline)."""
    return pm25_series.shift(1)
```

Aurora only adds value if it beats this. Always compute persistence metrics first.

### 7.2 Metrics

```python
from sklearn.metrics import mean_absolute_error, mean_squared_error
import numpy as np

def compute_metrics(y_true, y_pred, label="model"):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    corr = np.corrcoef(y_true, y_pred)[0, 1]
    # Skill score vs persistence: positive means better than persistence
    persistence = y_true.shift(1).dropna()
    mae_persistence = mean_absolute_error(y_true[1:], persistence)
    skill = 1 - (mae / mae_persistence)
    return {"label": label, "MAE": mae, "RMSE": rmse, "correlation": corr, "skill_vs_persistence": skill}
```

### 7.3 WHO and NAAQS Thresholds (for contextual reporting)

| Standard | 24h PM2.5 threshold |
|----------|-------------------|
| WHO (2021) | 15 µg/m³ |
| India NAAQS | 60 µg/m³ |
| India NAAQS (annual) | 40 µg/m³ |

---

## 8. Environment and Dependencies

**Python version:** 3.10+

**`requirements.txt`:**
```
microsoft-aurora
torch>=2.0.0
xarray
netcdf4
cdsapi
requests
pandas
numpy
scikit-learn
matplotlib
jupyter
tqdm
```

**Key imports used across the project:**
```python
import torch
import xarray as xr
import pandas as pd
import numpy as np
import cdsapi
import requests
from aurora import Aurora, AuroraSmallPretrained, Batch, Metadata
from datetime import datetime, timedelta
from pathlib import Path
```

**Environment variables required (store in `.env`, never commit):**
```
OPENAQ_API_KEY=your_key_here
CDS_API_KEY=your_personal_access_token   # mirrors ~/.cdsapirc
```

Load with:
```python
from dotenv import load_dotenv
import os
load_dotenv()
OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY")
```

---

## 9. Phase Plan

### Phase 1 — Data Pipeline (current)
- [ ] Pull OpenAQ PM2.5 for Delhi, Mumbai, Bangalore, Chennai, Kolkata
- [ ] Download CAMS reanalysis PM2.5 for same cities and dates
- [ ] Download ERA5 surface variables for same cities and dates
- [ ] Align CAMS/ERA5 grid to OpenAQ station coordinates
- [ ] Compute baseline metrics: CAMS PM2.5 vs OpenAQ
- [ ] Compute persistence baseline

**Success criterion:** One MAE number on screen comparing CAMS PM2.5 to a real OpenAQ station reading.

### Phase 2 — Aurora Inference (blocked on A100 quota)
- [ ] Load `AuroraSmallPretrained` on Azure NC24ads_A100_v4
- [ ] Construct valid `Batch` object from ERA5 for two consecutive 6h timesteps
- [ ] Run Aurora forward pass, extract output variables
- [ ] Compare Aurora output against Phase 1 CAMS baseline

**Success criterion:** Aurora runs end to end without error on real ERA5 data.

### Phase 3 — Evaluation at Scale
- [ ] Run evaluation across all 5 cities
- [ ] Evaluate across seasons (Jan, Apr, Jul, Oct — covers winter, pre-monsoon, monsoon, post-monsoon)
- [ ] Identify failure modes by city and season
- [ ] Document where and why Aurora underperforms

### Phase 4 — Adaptation (research extension)
- [ ] Try bias correction / calibration layer on Aurora output
- [ ] Try fine-tuning on India-specific data if resources allow
- [ ] Compare adapted vs unadapted Aurora

---

## 10. Coding Conventions for This Project

- All file I/O through `pathlib.Path`, never raw strings
- All timestamps stored and compared in UTC; display in IST only at output stage
- ERA5 longitude must be converted from -180/+180 to 0/360 before passing to Aurora
- NetCDF files opened with `xarray`, never `netCDF4` directly
- DataFrames must always have a `timestamp_utc` column as the time index
- Evaluation functions must accept `pd.Series`, not numpy arrays, so index alignment is automatic
- Never hardcode API keys; always load from environment variables
- Every script must have a `if __name__ == "__main__":` entry point with argparse for city and date range

---

## 11. Current Status (as of session start)

| Component | Status | Notes |
|-----------|--------|-------|
| Aurora installed | ✅ Done | `AuroraSmallPretrained` imports cleanly |
| OpenAQ API key | ✅ Done | In `.env`; verified against live API |
| OpenAQ data | ✅ Client done | `src/data/openaq_client.py`; verified Delhi 2018 + Jul 2026 |
| CDS API key | ✅ Done | `~/.cdsapirc` (new token format); verified via `src/check_cds.py` |
| ERA5 download | ⬜ Not started | Script not yet written |
| CAMS download | ⬜ Not started | Separate CDS dataset |
| Spatial alignment | ⬜ Not started | |
| Aurora inference | 🔴 Blocked | Waiting on Azure A100 quota (West India / South India, support request submitted) |
| Evaluation | ⬜ Not started | |

---

*Last updated: May 2026*
