"""Spatially + temporally align gridded ERA5/CAMS data to OpenAQ stations.

Produces ``data/processed/{city}_aligned.csv`` (COPILOT_CONTEXT.md section 6):
each row is one (station, hour) with the OpenAQ PM2.5 reading alongside the
CAMS PM2.5 and ERA5 surface fields sampled at the nearest grid cell.

The pipeline:
  1. Load cleaned OpenAQ hourly PM2.5 (``data/openaq/{city}_pm25.csv``).
  2. Open the ERA5 and CAMS NetCDF files (coordinate names auto-detected).
  3. For each distinct station, find the nearest grid cell in each dataset.
  4. Sample the grid time series at that cell, align on ``timestamp_utc``
     (CAMS is 3-hourly -> merged with a tolerance), and join to the station.

Usage:
    python -m src.data.align --city delhi \
        --era5 data/era5/delhi_era5_2018-02-01_2018-02-01.nc \
        --cams data/cams/delhi_cams_2018-02-01_2018-02-01.nc
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import xarray as xr

from ..utils.geo import find_nearest_grid_cell

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAQ_DIR = PROJECT_ROOT / "data" / "openaq"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Candidate coordinate names across ERA5/CAMS and old/new CDS API versions.
LAT_NAMES = ("latitude", "lat")
LON_NAMES = ("longitude", "lon")
TIME_NAMES = ("valid_time", "time", "forecast_reference_time")

# ERA5 surface variables we carry into the aligned frame -> output column names.
ERA5_VAR_MAP = {
    "u10": "era5_u10",
    "v10": "era5_v10",
    "t2m": "era5_t2m",
    "sp": "era5_sp",
    "msl": "era5_msl",
    "tcwv": "era5_tcwv",
}
# CAMS PM2.5 variable candidates -> single output column.
CAMS_PM25_NAMES = ("pm2p5", "pm2p5_conc", "particulate_matter_2.5um")

# CAMS EAC4 is 3-hourly; allow OpenAQ hours to match the nearest CAMS slot
# within this tolerance.
CAMS_MERGE_TOLERANCE = pd.Timedelta("90min")

# CAMS EAC4 PM2.5 is a mass concentration in kg m-3; OpenAQ is ug/m3.
KG_PER_M3_TO_UG_PER_M3 = 1e9


def _utc_ns(series: pd.Series) -> pd.Series:
    """Coerce a datetime series to tz-aware UTC at nanosecond resolution.

    pandas 3.0 parses CSV dates at microsecond resolution while xarray yields
    nanosecond times from NetCDF; merge_asof requires the two join keys to share
    the same resolution, so normalise everything to ns here.
    """
    s = pd.to_datetime(series, utc=True)
    return s.dt.as_unit("ns")


def _cams_unit_factor(ds: xr.Dataset) -> float:
    """Factor to convert the CAMS PM2.5 field to ug/m3, based on its units attr.

    EAC4 stores PM2.5 as a mass concentration in ``kg m-3``; OpenAQ is in
    ``ug/m3``. If the units already look like ug/m3 we leave the data alone; an
    unrecognised unit is left unscaled with a warning so the mismatch is visible
    rather than silently wrong.
    """
    for name in CAMS_PM25_NAMES:
        if name in ds.variables:
            units = str(ds[name].attrs.get("units", "")).lower().replace(" ", "")
            if units in ("kgm-3", "kgm**-3", "kg/m3", "kgm^-3"):
                return KG_PER_M3_TO_UG_PER_M3
            if units in ("ug/m3", "ugm-3", "µg/m3", "microgram/m3"):
                return 1.0
            print(f"  [align] warning: unrecognised CAMS PM2.5 units '{units}'; "
                  f"assuming kg/m3 -> ug/m3")
            return KG_PER_M3_TO_UG_PER_M3
    return 1.0


def _find_coord(ds: xr.Dataset, candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in ds.coords or name in ds.dims or name in ds.variables:
            return name
    raise KeyError(f"None of {candidates} found in dataset coords {list(ds.coords)}")


def _standardise(ds: xr.Dataset) -> tuple[xr.Dataset, str, str, str]:
    """Return dataset plus its (lat, lon, time) coordinate names."""
    lat = _find_coord(ds, LAT_NAMES)
    lon = _find_coord(ds, LON_NAMES)
    time = _find_coord(ds, TIME_NAMES)
    return ds, lat, lon, time


def _sample_grid_at_station(
    ds: xr.Dataset,
    lat_name: str,
    lon_name: str,
    time_name: str,
    station_lat: float,
    station_lon: float,
    var_map: dict[str, str],
) -> tuple[pd.DataFrame, float, float, float]:
    """Extract the nearest-cell time series for the requested variables.

    Returns (dataframe indexed by timestamp_utc, grid_lat, grid_lon, distance_km).
    """
    grid_lats = ds[lat_name].values
    grid_lons = ds[lon_name].values
    lat_idx, lon_idx, dist = find_nearest_grid_cell(
        station_lat, station_lon, grid_lats, grid_lons
    )
    cell = ds.isel({lat_name: lat_idx, lon_name: lon_idx})

    frame = {"timestamp_utc": _utc_ns(pd.Series(cell[time_name].values))}
    for src_name, out_name in var_map.items():
        if src_name in cell.variables:
            frame[out_name] = cell[src_name].values
    df = pd.DataFrame(frame)
    return df, float(grid_lats[lat_idx]), float(grid_lons[lon_idx]), dist


def align_city(
    city: str,
    era5_path: Path | None = None,
    cams_path: Path | None = None,
    openaq_path: Path | None = None,
) -> pd.DataFrame:
    """Align OpenAQ stations with ERA5 + CAMS grids for one city."""
    openaq_path = openaq_path or OPENAQ_DIR / f"{city}_pm25.csv"
    obs = pd.read_csv(openaq_path, parse_dates=["timestamp_utc"])
    # Snap observations to the top of the hour for a clean join key, then
    # normalise resolution so grid/obs merge keys are compatible.
    obs["timestamp_utc"] = _utc_ns(obs["timestamp_utc"]).dt.floor("h")
    obs = obs.rename(columns={"value_ugm3": "openaq_pm25"})
    # Some sensors report more than once per hour (e.g. labelled :00 and :30),
    # which collapse to duplicate station-hours after flooring. Average them so
    # each (station, hour) is unique before merging with the grids.
    obs = (
        obs.groupby(["station_id", "timestamp_utc"], as_index=False)
        .agg(openaq_pm25=("openaq_pm25", "mean"),
             lat=("lat", "first"), lon=("lon", "first"))
    )

    era5 = cams = None
    cams_to_ugm3 = 1.0
    if era5_path is not None:
        era5 = _standardise(xr.open_dataset(era5_path))
    if cams_path is not None:
        cams = _standardise(xr.open_dataset(cams_path))
        cams_to_ugm3 = _cams_unit_factor(cams[0])

    stations = obs[["station_id", "lat", "lon"]].drop_duplicates("station_id")
    out_rows: list[pd.DataFrame] = []

    for _, st in stations.iterrows():
        sid, slat, slon = st["station_id"], st["lat"], st["lon"]
        st_obs = obs[obs["station_id"] == sid][
            ["timestamp_utc", "openaq_pm25", "station_id"]
        ].copy()

        merged = st_obs.sort_values("timestamp_utc")

        if era5 is not None:
            ds, la, lo, ti = era5
            e_df, glat, glon, gdist = _sample_grid_at_station(
                ds, la, lo, ti, slat, slon, ERA5_VAR_MAP
            )
            merged = merged.merge(e_df, on="timestamp_utc", how="left")
            merged["grid_lat"] = glat
            merged["grid_lon"] = glon
            merged["distance_km"] = gdist

        if cams is not None:
            ds, la, lo, ti = cams
            c_df, _, _, _ = _sample_grid_at_station(
                ds, la, lo, ti, slat, slon, {n: "cams_pm25" for n in CAMS_PM25_NAMES}
            )
            c_df = c_df.dropna(axis=1, how="all").sort_values("timestamp_utc")
            if "cams_pm25" in c_df:
                c_df["cams_pm25"] = c_df["cams_pm25"] * cams_to_ugm3
            # 3-hourly CAMS -> nearest hourly obs within tolerance.
            merged = pd.merge_asof(
                merged.sort_values("timestamp_utc"),
                c_df,
                on="timestamp_utc",
                direction="nearest",
                tolerance=CAMS_MERGE_TOLERANCE,
            )

        out_rows.append(merged)

    result = pd.concat(out_rows, ignore_index=True)
    # Stable, contract-friendly column order (only those present).
    preferred = [
        "timestamp_utc", "openaq_pm25", "cams_pm25",
        *ERA5_VAR_MAP.values(),
        "station_id", "grid_lat", "grid_lon", "distance_km",
    ]
    cols = [c for c in preferred if c in result.columns]
    cols += [c for c in result.columns if c not in cols]
    return result[cols].sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Align ERA5/CAMS grids to OpenAQ stations.")
    p.add_argument("--city", required=True)
    p.add_argument("--era5", type=Path, default=None, help="ERA5 NetCDF path.")
    p.add_argument("--cams", type=Path, default=None, help="CAMS NetCDF path.")
    p.add_argument("--openaq", type=Path, default=None, help="OpenAQ CSV path override.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.era5 is None and args.cams is None:
        raise SystemExit("Provide at least one of --era5 / --cams.")
    df = align_city(args.city, era5_path=args.era5, cams_path=args.cams, openaq_path=args.openaq)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / f"{args.city}_aligned.csv"
    df.to_csv(out, index=False)
    matched = int(df["cams_pm25"].notna().sum()) if "cams_pm25" in df else 0
    print(f"Wrote {len(df)} rows -> {out}")
    if "cams_pm25" in df:
        print(f"  rows with CAMS PM2.5: {matched}")
    if "distance_km" in df:
        print(f"  mean station->grid distance: {df['distance_km'].mean():.2f} km")


if __name__ == "__main__":
    main()
