"""Download gridded model input for the Aurora India AQI benchmark.

Two data stores, one ECMWF personal-access-token (in ~/.cdsapirc):

  * ERA5 single-levels  -> Climate Data Store   (cds.climate.copernicus.eu)
      Surface meteorology used both as Aurora input and for spatial alignment.
  * CAMS reanalysis EAC4 -> Atmosphere Data Store (ads.atmosphere.copernicus.eu)
      PM2.5 field ("particulate_matter_2.5um"). This is the Phase-1 "model"
      prediction we benchmark against OpenAQ ground truth.

The same personal-access-token authenticates against both stores, but each
store has its own URL and its own set of site policies / dataset licences that
must be accepted once via the website before downloads succeed. If a CAMS
download 403s with "user didn't accept all required site policies", log in at
ads.atmosphere.copernicus.eu, accept the data-protection policy, and accept the
CAMS EAC4 licence on the dataset page.

Coverage notes (plan the date window accordingly):
  * CAMS EAC4 reanalysis: 2003 -> 2025, 3-hourly, 0.75 deg.
  * ERA5: 1940 -> ~present (5-day lag), hourly, 0.25 deg.
  * OpenAQ Indian stations: old CPCB ~2016-2018; modern DPCC ~2025-present.
    Overlap windows for CAMS-vs-OpenAQ therefore sit in 2016-2018 and 2025.

Usage:
    python -m src.data.era5_downloader --dataset era5 --city delhi \
        --date-from 2018-02-01 --date-to 2018-02-02
    python -m src.data.era5_downloader --dataset cams --city delhi \
        --date-from 2018-02-01 --date-to 2018-02-02
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cdsapi

# --------------------------------------------------------------------------- #
# Stores + datasets
# --------------------------------------------------------------------------- #

CDS_URL = "https://cds.climate.copernicus.eu/api"
ADS_URL = "https://ads.atmosphere.copernicus.eu/api"

# ERA5 surface variables (COPILOT_CONTEXT.md section 4.2). Geopotential (z) and
# land-sea mask are static fields fetched separately when Aurora inference lands.
ERA5_VARIABLES = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_temperature",
    "surface_pressure",
    "mean_sea_level_pressure",
    "total_column_water_vapour",
]

# City bounding boxes, [North, West, South, East] (COPILOT_CONTEXT.md 4.2).
CITY_BBOX: dict[str, list[float]] = {
    "delhi": [29.1, 76.7, 28.1, 77.7],
    "mumbai": [19.6, 72.3, 18.6, 73.3],
    "bangalore": [13.5, 77.1, 12.5, 78.1],
    "chennai": [13.6, 79.8, 12.6, 80.8],
    "kolkata": [23.1, 87.8, 22.1, 88.8],
}

ALL_HOURS = [f"{h:02d}:00" for h in range(24)]        # ERA5 is hourly
EAC4_HOURS = [f"{h:02d}:00" for h in range(0, 24, 3)]  # CAMS EAC4 is 3-hourly

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ERA5_DIR = PROJECT_ROOT / "data" / "era5"
CAMS_DIR = PROJECT_ROOT / "data" / "cams"


# --------------------------------------------------------------------------- #
# Request construction
# --------------------------------------------------------------------------- #

def _daterange_str(date_from: str, date_to: str) -> str:
    """CDS/ADS accept an inclusive 'YYYY-MM-DD/YYYY-MM-DD' date range string."""
    return f"{date_from}/{date_to}"


def _era5_request(city: str, date_from: str, date_to: str) -> dict:
    return {
        "product_type": ["reanalysis"],
        "variable": ERA5_VARIABLES,
        "date": _daterange_str(date_from, date_to),
        "time": ALL_HOURS,
        "area": CITY_BBOX[city],
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def _cams_request(city: str, date_from: str, date_to: str) -> dict:
    return {
        "variable": ["particulate_matter_2.5um"],
        "date": _daterange_str(date_from, date_to),
        "time": EAC4_HOURS,
        "area": CITY_BBOX[city],
        "data_format": "netcdf",
    }


# dataset key -> (store url, CDS dataset id, request builder, output dir, tag)
DATASETS = {
    "era5": (CDS_URL, "reanalysis-era5-single-levels", _era5_request, ERA5_DIR, "era5"),
    "cams": (ADS_URL, "cams-global-reanalysis-eac4", _cams_request, CAMS_DIR, "cams"),
}


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #

def download(
    dataset: str,
    city: str,
    date_from: str,
    date_to: str,
    output_dir: Path | None = None,
) -> Path:
    """Retrieve one NetCDF file for a city + date window from the right store."""
    if dataset not in DATASETS:
        raise ValueError(f"Unknown dataset '{dataset}'. Known: {list(DATASETS)}")
    if city not in CITY_BBOX:
        raise ValueError(f"Unknown city '{city}'. Known: {list(CITY_BBOX)}")

    url, cds_name, build_request, default_dir, tag = DATASETS[dataset]
    out_dir = output_dir or default_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{city}_{tag}_{date_from}_{date_to}.nc"

    request = build_request(city, date_from, date_to)
    print(f"[{dataset}] store={url}")
    print(f"[{dataset}] dataset={cds_name}")
    print(f"[{dataset}] area(N,W,S,E)={CITY_BBOX[city]}  window={date_from}..{date_to}")
    print(f"[{dataset}] -> {target}")

    client = cdsapi.Client(url=url)  # key comes from ~/.cdsapirc
    client.retrieve(cds_name, request, str(target))
    print(f"[{dataset}] done: {target} ({target.stat().st_size/1e6:.2f} MB)")
    return target


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download ERA5 / CAMS grids for a city.")
    p.add_argument("--dataset", required=True, choices=sorted(DATASETS))
    p.add_argument("--city", required=True, choices=sorted(CITY_BBOX))
    p.add_argument("--date-from", required=True, help="Inclusive UTC start, YYYY-MM-DD.")
    p.add_argument("--date-to", required=True, help="Inclusive UTC end, YYYY-MM-DD.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    download(args.dataset, args.city, args.date_from, args.date_to)


if __name__ == "__main__":
    main()
