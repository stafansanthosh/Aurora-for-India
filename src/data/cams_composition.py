"""Download CAMS global atmospheric-composition ANALYSIS for AuroraAirPollution.

This is the single input dataset the air-pollution model needs: it supplies BOTH
the meteorological fields (2t/10u/10v/msl + t/u/v/q/z) AND the composition fields
(pm1/pm2.5/pm10, total columns, and co/no/no2/o3/so2 at pressure levels). No
separate ERA5 download is required; the static emission fields come from the
HuggingFace pickle (see aurora_runner.load_static_vars).

Dataset: cams-global-atmospheric-composition-forecasts (ADS). The *analysis*
product is obtained as the zero-hour forecast (``type=forecast, leadtime_hour=0``).
The response is a ``netcdf_zip`` containing two files:
  * data_sfc.nc  — surface-level variables
  * data_plev.nc — pressure-level variables
Global 0.4° grid (451x900), matching the model's static fields. No ``area`` key,
so the whole globe is fetched (the model runs globally; India is extracted from
the output).

Follows the official microsoft/aurora example_cams.ipynb recipe.

Usage:
    python -m src.data.cams_composition --date 2025-11-15
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import cdsapi

ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
DATASET = "cams-global-atmospheric-composition-forecasts"

SURFACE_VARS = [
    # meteorology
    "10m_u_component_of_wind", "10m_v_component_of_wind",
    "2m_temperature", "mean_sea_level_pressure",
    # pollution (surface concentrations + total columns)
    "particulate_matter_1um", "particulate_matter_2.5um", "particulate_matter_10um",
    "total_column_carbon_monoxide", "total_column_nitrogen_monoxide",
    "total_column_nitrogen_dioxide", "total_column_ozone",
    "total_column_sulphur_dioxide",
]
MULTILEVEL_VARS = [
    # meteorology
    "u_component_of_wind", "v_component_of_wind", "temperature",
    "geopotential", "specific_humidity",
    # pollution
    "carbon_monoxide", "nitrogen_dioxide", "nitrogen_monoxide",
    "ozone", "sulphur_dioxide",
]
PRESSURE_LEVELS = ["50", "100", "150", "200", "250", "300", "400",
                   "500", "600", "700", "850", "925", "1000"]
# Aurora needs two consecutive timesteps; the 0.4 air-pollution checkpoint uses
# a 12h step, so fetch UTC 00 and 12 and build the batch at UTC 12.
TIMES = ["00:00", "12:00"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAMS_ANALYSIS_DIR = PROJECT_ROOT / "data" / "cams_analysis"


def download(date: str, output_dir: Path | None = None) -> tuple[Path, Path]:
    """Download CAMS analysis for ``date`` (YYYY-MM-DD); return (sfc, plev) paths."""
    out_dir = output_dir or CAMS_ANALYSIS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{date}_cams.nc.zip"
    sfc_path = out_dir / f"{date}_sfc.nc"
    plev_path = out_dir / f"{date}_plev.nc"

    if not zip_path.exists():
        print(f"[cams-analysis] {DATASET}  date={date}  times={TIMES}  (global 0.4°)")
        client = cdsapi.Client(url=ADS_URL)  # key from ~/.cdsapirc
        client.retrieve(
            DATASET,
            {
                "type": "forecast",
                "leadtime_hour": "0",           # zero-hour forecast = analysis
                "variable": SURFACE_VARS + MULTILEVEL_VARS,
                "pressure_level": PRESSURE_LEVELS,
                "date": date,
                "time": TIMES,
                "format": "netcdf_zip",
            },
            str(zip_path),
        )
    else:
        print(f"[cams-analysis] {zip_path.name} already present, unpacking")

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        sfc_member = next(n for n in names if "sfc" in n)
        plev_member = next(n for n in names if "plev" in n)
        sfc_path.write_bytes(zf.read(sfc_member))
        plev_path.write_bytes(zf.read(plev_member))

    for p in (sfc_path, plev_path):
        print(f"[cams-analysis] -> {p}  ({p.stat().st_size/1e6:.1f} MB)")
    return sfc_path, plev_path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download CAMS analysis for AuroraAirPollution.")
    p.add_argument("--date", required=True, help="UTC date, YYYY-MM-DD.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    download(args.date)


if __name__ == "__main__":
    main()
