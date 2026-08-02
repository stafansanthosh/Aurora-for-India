"""Retrieve and sample the actual lead-dependent CAMS PM2.5 forecast.

This module is deliberately separate from :mod:`src.data.cams_composition`.
That module downloads the lead-zero fields used to initialise Aurora.  This
one downloads CAMS's own forecast at +12, ..., +96 hours so that the benchmark
can answer whether Aurora improves on the operational global forecast.

The acquisition contract is conservative:

* one initialization cycle and one variable per request;
* the exact request is written before submission;
* the original GRIB is retained unchanged;
* request attempts, retrieval times, byte count and SHA-256 are recorded;
* extraction accepts only the source unit kg m-3 and converts to ug m-3 once;
* all requested leads must be present before station samples are returned.

The ADS request schema can change.  ``REQUEST_SCHEMA_VERSION`` pins the schema
used here; compare a dry-run payload with the dataset form's "Show API request"
before the first paid/bulk run.

Examples
--------
Print the Pilot C request without downloading::

    python -m src.data.cams_forecast --date 2025-11-06 --area pilot --dry-run

Retrieve and sample one India-wide date (requires ADS credentials plus
cfgrib/ecCodes)::

    python -m src.data.cams_forecast --date 2025-11-06 \
        --stations data/stations.csv

Retrieve the frozen schedule only after deliberately acknowledging its size::

    python -m src.data.cams_forecast \
        --dates-file docs/benchmark_dates.csv --confirm-multiple
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import xarray as xr

from ..utils.geo import find_nearest_grid_cell

DATASET = "cams-global-atmospheric-composition-forecasts"
ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
DATASET_URL = (
    "https://ads.atmosphere.copernicus.eu/datasets/"
    "cams-global-atmospheric-composition-forecasts"
)
DOI = "10.24381/04a0b097"
LICENCE_URL = (
    "https://ads.atmosphere.copernicus.eu/licences/"
    "licence-to-use-copernicus-products"
)
VARIABLE = "particulate_matter_2.5um"
SOURCE_UNIT = "kg m-3"
OUTPUT_UNIT = "ug m-3"
KG_M3_TO_UG_M3 = 1_000_000_000.0
INIT_HOUR_UTC = 12
DEFAULT_LEADS = tuple(range(12, 97, 12))
INDIA_AREA = (30.0, 72.0, 8.0, 90.0)  # north, west, south, east
PILOT_AREA = (26.2, 82.4, 24.8, 85.6)
REQUEST_SCHEMA_VERSION = "ads-cams-forecast-v1"
PARSER_VERSION = "1"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "cams_forecast"
DEFAULT_STATIONS = PROJECT_ROOT / "data" / "stations.csv"
DEFAULT_DATES_FILE = PROJECT_ROOT / "docs" / "benchmark_dates.csv"

_PM25_NAMES = (VARIABLE, "pm2p5")
_LAT_NAMES = ("latitude", "lat")
_LON_NAMES = ("longitude", "lon")
_PROVENANCE_ATTRS = (
    "GRIB_centre",
    "GRIB_centreDescription",
    "GRIB_subCentre",
    "GRIB_edition",
    "GRIB_dataType",
    "GRIB_modelName",
    "GRIB_generatingProcessIdentifier",
    "GRIB_typeOfGeneratingProcess",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path) -> str:
    """Record a useful path without leaking a workstation home directory."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _repo_commit() -> str | None:
    override = os.environ.get("INDIAAQBENCH_COMMIT")
    if override:
        return override
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _validate_date(date: str) -> str:
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid initialization date {date!r}; use YYYY-MM-DD.") from exc
    canonical = parsed.strftime("%Y-%m-%d")
    if canonical != date:
        raise ValueError(f"Initialization date must be canonical YYYY-MM-DD, got {date!r}.")
    return canonical


def _validate_leads(leads: Iterable[int]) -> tuple[int, ...]:
    result_list: list[int] = []
    try:
        for value in leads:
            if isinstance(value, bool) or int(value) != float(value):
                raise ValueError
            result_list.append(int(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Forecast leads must be integer hours.") from exc
    result = tuple(result_list)
    if not result:
        raise ValueError("At least one forecast lead is required.")
    if len(result) != len(set(result)):
        raise ValueError(f"Forecast leads contain duplicates: {result}.")
    if tuple(sorted(result)) != result:
        raise ValueError(f"Forecast leads must be strictly increasing: {result}.")
    invalid = [lead for lead in result if lead <= 0 or lead > 120]
    if invalid:
        raise ValueError(f"CAMS forecast leads must be integer hours in 1..120: {invalid}.")
    if result != DEFAULT_LEADS:
        raise ValueError(
            "IndiaAQBench pins the operational baseline to "
            f"+12..+96 h in 12 h steps; got {result}."
        )
    return result


def _validate_area(area: Sequence[float]) -> tuple[float, float, float, float]:
    if len(area) != 4:
        raise ValueError("Area must contain north, west, south, east.")
    north, west, south, east = (float(value) for value in area)
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError(
            "Invalid area; require -90 <= south < north <= 90 and "
            "-180 <= west < east <= 180."
        )
    return north, west, south, east


@dataclass(frozen=True)
class ForecastRequest:
    """A deterministic one-cycle CAMS forecast request."""

    date: str
    leads: tuple[int, ...] = DEFAULT_LEADS
    area: tuple[float, float, float, float] = INDIA_AREA
    time: str = "12:00"

    def __post_init__(self) -> None:
        object.__setattr__(self, "date", _validate_date(self.date))
        object.__setattr__(self, "leads", _validate_leads(self.leads))
        object.__setattr__(self, "area", _validate_area(self.area))
        if self.time != f"{INIT_HOUR_UTC:02d}:00":
            raise ValueError(
                f"IndiaAQBench pins CAMS and Aurora to {INIT_HOUR_UTC:02d}:00 UTC; "
                f"got {self.time!r}."
            )

    @property
    def init_time(self) -> datetime:
        return datetime.strptime(self.date, "%Y-%m-%d").replace(
            hour=INIT_HOUR_UTC, tzinfo=timezone.utc
        )

    @property
    def valid_times(self) -> tuple[datetime, ...]:
        return tuple(self.init_time + timedelta(hours=lead) for lead in self.leads)

    def payload(self) -> dict[str, Any]:
        # ECMWF advises using strings as ADS request values.  Keep this stable
        # so request.json is an exact, reviewable scientific artifact.
        return {
            "type": "forecast",
            "date": self.date,
            "time": self.time,
            "leadtime_hour": [str(lead) for lead in self.leads],
            "variable": VARIABLE,
            "area": [f"{value:g}" for value in self.area],
            "format": "grib",
        }


@dataclass(frozen=True)
class ForecastPaths:
    directory: Path
    raw_grib: Path
    request_json: Path
    provenance_json: Path
    station_samples_csv: Path


def forecast_paths(
    request: ForecastRequest, output_dir: Path = DEFAULT_OUTPUT_DIR
) -> ForecastPaths:
    stamp = request.init_time.strftime("%Y-%m-%dT%H-00Z")
    directory = Path(output_dir) / f"init={stamp}"
    return ForecastPaths(
        directory=directory,
        raw_grib=directory / "pm25_leads_12_96.grib",
        request_json=directory / "request.json",
        provenance_json=directory / "provenance.json",
        station_samples_csv=directory / "station_samples.csv",
    )


def request_document(request: ForecastRequest) -> dict[str, Any]:
    """Return the self-describing artifact written to ``request.json``."""
    return {
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "dataset": DATASET,
        "endpoint": ADS_URL,
        "payload": request.payload(),
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read valid JSON from {path}.") from exc


def _new_provenance(request: ForecastRequest) -> dict[str, Any]:
    return {
        "provenance_schema_version": 1,
        "status": "not_started",
        "source": "Copernicus Atmosphere Monitoring Service (CAMS)",
        "role": "forecast_baseline",
        "dataset": DATASET,
        "dataset_url": DATASET_URL,
        "dataset_doi": DOI,
        "licence_url": LICENCE_URL,
        "redistribution_decision": "unresolved",
        "access_method": "Copernicus ADS via cdsapi",
        "authentication": "user ADS credentials; credentials are never recorded",
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "request": request.payload(),
        "init_time": _iso_utc(request.init_time),
        "leads_h": list(request.leads),
        "valid_times": [_iso_utc(value) for value in request.valid_times],
        "variable": VARIABLE,
        "source_unit": SOURCE_UNIT,
        "output_unit": OUTPUT_UNIT,
        "conversion_expression": "ug_m3 = kg_m3 * 1e9",
        "area_north_west_south_east": list(request.area),
        "grid": "provider regular latitude/longitude grid (nominally 0.4 degree)",
        "format": "GRIB (raw retained unchanged)",
        "parser": f"{__name__}:{PARSER_VERSION}",
        "repository_commit": _repo_commit(),
        "library_versions": {
            "python": sys.version.split()[0],
            "cdsapi": _package_version("cdsapi"),
            "xarray": _package_version("xarray"),
            "cfgrib": _package_version("cfgrib"),
            "eccodes": _package_version("eccodes"),
            "numpy": _package_version("numpy"),
            "pandas": _package_version("pandas"),
        },
        "attempts": [],
    }


def _read_or_new_provenance(
    path: Path, request: ForecastRequest
) -> dict[str, Any]:
    if not path.exists():
        return _new_provenance(request)
    provenance = _load_json(path)
    if provenance.get("request") != request.payload():
        raise RuntimeError(
            f"Existing provenance request differs from the requested acquisition: {path}"
        )
    provenance.setdefault("attempts", [])
    return provenance


def _result_metadata(result: Any) -> dict[str, Any]:
    """Keep only non-sensitive provider job identifiers/status fields."""
    reply = getattr(result, "reply", None)
    if not isinstance(reply, Mapping):
        return {}
    allowlist = ("request_id", "state", "content_length", "content_type")
    safe: dict[str, Any] = {}
    for key in allowlist:
        if key not in reply:
            continue
        value = reply[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


def retrieve_forecast(
    request: ForecastRequest,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    client: Any | None = None,
    allow_retrieve: bool = True,
    now: Callable[[], datetime] = _utc_now,
) -> ForecastPaths:
    """Retrieve one forecast cycle, retaining raw data and complete provenance.

    ``client`` is injectable for tests.  A successful existing artifact is
    reused only when its request and SHA-256 still match provenance.
    """
    paths = forecast_paths(request, Path(output_dir))
    paths.directory.mkdir(parents=True, exist_ok=True)
    expected_document = request_document(request)
    if paths.request_json.exists():
        if _load_json(paths.request_json) != expected_document:
            raise RuntimeError(
                f"Refusing to reuse {paths.directory}: request.json differs."
            )
    else:
        _atomic_json(paths.request_json, expected_document)

    provenance = _read_or_new_provenance(paths.provenance_json, request)
    if paths.raw_grib.exists():
        actual_hash = _sha256(paths.raw_grib)
        recorded = provenance.get("raw_file", {}).get("sha256")
        if provenance.get("status") != "complete" or recorded != actual_hash:
            raise RuntimeError(
                f"Existing raw GRIB is not a verified completed retrieval: "
                f"{paths.raw_grib}. Preserve it and investigate; it will not be overwritten."
            )
        return paths

    if not allow_retrieve:
        raise FileNotFoundError(
            "Offline CAMS forecast input is missing: "
            f"{paths.raw_grib}"
        )

    if client is None:
        try:
            import cdsapi
        except ImportError as exc:
            raise RuntimeError(
                "cdsapi is required for retrieval. Install project dependencies "
                "and configure ~/.cdsapirc."
            ) from exc
        client = cdsapi.Client(url=ADS_URL)

    started = now()
    attempt: dict[str, Any] = {
        "started_at": _iso_utc(started),
        "status": "running",
    }
    provenance["status"] = "retrieving"
    provenance["attempts"].append(attempt)
    _atomic_json(paths.provenance_json, provenance)

    partial = paths.raw_grib.with_suffix(paths.raw_grib.suffix + ".part")
    if partial.exists():
        # A partial response is evidence from an interrupted attempt.  Preserve
        # it under a timestamped name rather than appending or overwriting it.
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        archived = partial.with_name(f"{partial.name}.{stamp}")
        counter = 1
        while archived.exists():
            archived = partial.with_name(f"{partial.name}.{stamp}.{counter}")
            counter += 1
        prior_bytes = partial.stat().st_size
        prior_hash = _sha256(partial)
        os.replace(partial, archived)
        attempt["preserved_prior_partial"] = {
            "path": archived.name,
            "bytes": prior_bytes,
            "sha256": prior_hash,
        }
        _atomic_json(paths.provenance_json, provenance)

    try:
        result = client.retrieve(DATASET, request.payload(), str(partial))
        if not partial.exists() or partial.stat().st_size == 0:
            raise RuntimeError("ADS retrieval returned without a non-empty GRIB file.")
        os.replace(partial, paths.raw_grib)
        completed = now()
        attempt.update(
            status="complete",
            completed_at=_iso_utc(completed),
            elapsed_seconds=max(0.0, (completed - started).total_seconds()),
            provider=_result_metadata(result),
        )
        provenance.update(
            status="complete",
            request_submitted_at=_iso_utc(started),
            retrieved_at=_iso_utc(completed),
            raw_file={
                "path": paths.raw_grib.name,
                "bytes": paths.raw_grib.stat().st_size,
                "sha256": _sha256(paths.raw_grib),
            },
        )
        _atomic_json(paths.provenance_json, provenance)
        return paths
    except Exception as exc:
        failed = now()
        attempt.update(
            status="failed",
            completed_at=_iso_utc(failed),
            elapsed_seconds=max(0.0, (failed - started).total_seconds()),
            error_type=type(exc).__name__,
            error=str(exc),
            partial_file=partial.name if partial.exists() else None,
            partial_bytes=partial.stat().st_size if partial.exists() else 0,
            partial_sha256=_sha256(partial) if partial.exists() else None,
        )
        provenance["status"] = "failed"
        _atomic_json(paths.provenance_json, provenance)
        raise


def _coordinate_name(dataset: xr.Dataset, candidates: Sequence[str], role: str) -> str:
    for name in candidates:
        if name in dataset.coords:
            return name
    raise ValueError(f"CAMS GRIB has no recognized {role} coordinate ({candidates}).")


def _pm25_variable(dataset: xr.Dataset) -> xr.DataArray:
    for name in _PM25_NAMES:
        if name in dataset.data_vars:
            return dataset[name]
    if len(dataset.data_vars) == 1:
        only = next(iter(dataset.data_vars))
        variable = dataset[only]
        long_name = str(variable.attrs.get("long_name", "")).casefold()
        if "particulate" in long_name and "2.5" in long_name:
            return variable
    raise ValueError(
        f"CAMS GRIB contains variables {list(dataset.data_vars)} but not PM2.5."
    )


def _canonical_unit(unit: str) -> str:
    return (
        str(unit)
        .strip()
        .casefold()
        .replace("µ", "u")
        .replace("μ", "u")
        .replace("**", "^")
        .replace(" ", "")
        .replace("(", "")
        .replace(")", "")
    )


def kg_m3_to_ug_m3(values: np.ndarray | Sequence[float], source_unit: str) -> np.ndarray:
    """Convert CAMS PM2.5 to ug m-3 exactly once.

    Accepting only kg m-3 is intentional.  If a caller passes an already
    converted array whose metadata says ug m-3, this function fails instead of
    silently multiplying it by 1e9 again.
    """
    canonical = _canonical_unit(source_unit)
    accepted = {"kgm^-3", "kgm-3", "kg/m^3", "kg/m3"}
    if canonical not in accepted:
        raise ValueError(
            f"Expected unconverted CAMS PM2.5 in kg m-3; got {source_unit!r}. "
            "Refusing a possible second conversion."
        )
    array = np.asarray(values, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError("CAMS PM2.5 contains non-finite source values.")
    if (array < 0).any():
        raise ValueError("CAMS PM2.5 contains negative source values.")
    return array * KG_M3_TO_UG_M3


def _lead_hours(dataset: xr.Dataset, variable: xr.DataArray) -> tuple[str, np.ndarray]:
    if "step" in variable.dims:
        step = dataset.coords["step"]
        values = np.asarray(step.values)
        if np.issubdtype(values.dtype, np.timedelta64):
            hours = values / np.timedelta64(1, "h")
        else:
            unit = str(step.attrs.get("units", "")).casefold()
            if unit not in {"h", "hour", "hours"}:
                raise ValueError(f"Cannot interpret numeric CAMS step unit {unit!r}.")
            hours = values.astype(float)
        if hours.ndim != 1 or not np.isfinite(hours).all():
            raise ValueError("CAMS forecast steps must be one finite 1-D coordinate.")
        rounded = np.rint(hours)
        if not np.allclose(hours, rounded, rtol=0.0, atol=1e-9):
            raise ValueError(f"CAMS forecast steps are not whole hours: {hours}.")
        return "step", rounded.astype(int)

    if "valid_time" in variable.dims and "time" in dataset.coords:
        init_values = np.atleast_1d(dataset.coords["time"].values)
        if init_values.size != 1:
            raise ValueError("CAMS file contains multiple forecast initializations.")
        valid = np.asarray(dataset.coords["valid_time"].values)
        hours = (valid - init_values[0]) / np.timedelta64(1, "h")
        return "valid_time", np.rint(hours).astype(int)

    raise ValueError("CAMS GRIB has no step/valid_time dimension for forecast leads.")


def _dataset_init_time(dataset: xr.Dataset) -> pd.Timestamp:
    if "time" not in dataset.coords:
        raise ValueError("CAMS GRIB has no forecast initialization coordinate 'time'.")
    values = np.atleast_1d(dataset.coords["time"].values)
    if values.size != 1:
        raise ValueError(
            f"CAMS GRIB must contain exactly one initialization; found {values.size}."
        )
    timestamp = pd.Timestamp(values[0])
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp


def _open_grib(path: Path) -> xr.Dataset:
    try:
        return xr.open_dataset(
            path,
            engine="cfgrib",
            backend_kwargs={"indexpath": ""},
        )
    except (ImportError, OSError, ValueError) as exc:
        raise RuntimeError(
            "Reading CAMS GRIB requires cfgrib and the ecCodes runtime. "
            "Install both, then retry; the raw GRIB remains unchanged."
        ) from exc


def _registry_file_version(path: Path) -> str:
    return f"sha256:{_sha256(path)[:16]}"


def extract_station_forecasts(
    raw_grib: Path,
    stations: pd.DataFrame,
    request: ForecastRequest,
    *,
    registry_version: str | None = None,
    open_dataset: Callable[[Path], xr.Dataset] = _open_grib,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Sample every requested CAMS lead at the nearest grid cell.

    Returns ``(samples, extraction_metadata)``.  ``samples`` is merge-ready for
    the benchmark on ``(init_date, station_id, lead_h)`` and contains both raw
    kg m-3 and converted ug m-3 values.
    """
    required = {"station_id", "lat", "lon"}
    missing = sorted(required - set(stations.columns))
    if missing:
        raise ValueError(f"Station registry missing required columns: {missing}.")
    if stations.empty:
        raise ValueError("Station registry is empty.")
    if stations["station_id"].astype(str).duplicated().any():
        raise ValueError("Station registry contains duplicate station_id values.")
    numeric = stations[["lat", "lon"]].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("Station registry contains invalid latitude/longitude values.")

    dataset = open_dataset(Path(raw_grib))
    try:
        variable = _pm25_variable(dataset)
        lat_name = _coordinate_name(dataset, _LAT_NAMES, "latitude")
        lon_name = _coordinate_name(dataset, _LON_NAMES, "longitude")
        grid_lats = np.asarray(dataset.coords[lat_name].values, dtype=float)
        grid_lons = np.asarray(dataset.coords[lon_name].values, dtype=float)
        if grid_lats.ndim != 1 or grid_lons.ndim != 1:
            raise ValueError("Only a regular 1-D latitude/longitude CAMS grid is supported.")
        if (
            not len(grid_lats)
            or not len(grid_lons)
            or not np.isfinite(grid_lats).all()
            or not np.isfinite(grid_lons).all()
        ):
            raise ValueError("CAMS latitude/longitude coordinates are empty or non-finite.")

        init_time = _dataset_init_time(dataset)
        expected_init = pd.Timestamp(request.init_time)
        if init_time != expected_init:
            raise ValueError(
                f"CAMS initialization {init_time} does not match request {expected_init}."
            )

        lead_dim, file_leads = _lead_hours(dataset, variable)
        if len(file_leads) != len(set(file_leads.tolist())):
            raise ValueError(f"CAMS GRIB contains duplicate forecast leads: {file_leads}.")
        requested = set(request.leads)
        actual = set(int(value) for value in file_leads)
        if actual != requested:
            raise ValueError(
                f"CAMS lead set mismatch; requested {sorted(requested)}, found {sorted(actual)}."
            )

        source_unit = str(variable.attrs.get("units", ""))
        # Validate once before walking the grid.  Conversion is then applied to
        # each scalar through the same guarded function below.
        kg_m3_to_ug_m3(np.array([0.0]), source_unit)

        cells: list[dict[str, Any]] = []
        lon_is_360 = bool(np.nanmax(grid_lons) > 180)
        carry = [
            name for name in ("station_id", "city", "station_name", "lat", "lon")
            if name in stations.columns
        ]
        for _, station in stations.iterrows():
            if not -90 <= float(station["lat"]) <= 90:
                raise ValueError(f"Invalid station latitude: {station['lat']!r}.")
            if not -180 <= float(station["lon"]) <= 180:
                raise ValueError(f"Invalid station longitude: {station['lon']!r}.")
            station_lon = float(station["lon"]) % 360.0 if lon_is_360 else float(station["lon"])
            lat_idx, lon_idx, distance = find_nearest_grid_cell(
                float(station["lat"]), station_lon, grid_lats, grid_lons
            )
            cells.append(
                {
                    **{name: station[name] for name in carry},
                    "lat_idx": lat_idx,
                    "lon_idx": lon_idx,
                    "cell_lat": float(grid_lats[lat_idx]),
                    "cell_lon": float(grid_lons[lon_idx]),
                    "cell_dist_km": float(distance),
                }
            )

        rows: list[dict[str, Any]] = []
        for lead in request.leads:
            lead_index = int(np.flatnonzero(file_leads == lead)[0])
            for cell in cells:
                value = variable.isel(
                    {
                        lead_dim: lead_index,
                        lat_name: cell["lat_idx"],
                        lon_name: cell["lon_idx"],
                    }
                )
                source_value = float(np.asarray(value.values).squeeze())
                converted = float(kg_m3_to_ug_m3([source_value], source_unit)[0])
                rows.append(
                    {
                        "init_date": request.date,
                        "init_time": expected_init,
                        "station_id": cell["station_id"],
                        "city": cell.get("city"),
                        "lead_h": lead,
                        "valid_time": expected_init + pd.Timedelta(hours=lead),
                        "cams_forecast_pm25_kgm3": source_value,
                        "cams_forecast_pm25": converted,
                        "cams_forecast_cell_lat": cell["cell_lat"],
                        "cams_forecast_cell_lon": cell["cell_lon"],
                        "cams_forecast_cell_dist_km": cell["cell_dist_km"],
                        "cams_forecast_source_unit": SOURCE_UNIT,
                        "cams_forecast_output_unit": OUTPUT_UNIT,
                        "registry_version": registry_version,
                    }
                )

        samples = pd.DataFrame(rows)
        expected_rows = len(stations) * len(request.leads)
        if len(samples) != expected_rows:
            raise RuntimeError(
                f"Station extraction produced {len(samples)} rows; expected {expected_rows}."
            )
        keys = ["init_date", "station_id", "lead_h"]
        if samples.duplicated(keys).any():
            raise RuntimeError(f"Station extraction produced duplicate keys {keys}.")

        attrs: dict[str, Any] = {}
        for name in _PROVENANCE_ATTRS:
            value = variable.attrs.get(name, dataset.attrs.get(name))
            if value is not None and isinstance(value, (str, int, float, bool)):
                attrs[name] = value
        metadata = {
            "extracted_at": _iso_utc(_utc_now()),
            "extraction_method": "nearest regular lat/lon grid cell",
            "parser": f"{__name__}:{PARSER_VERSION}",
            "registry_version": registry_version,
            "stations": int(stations["station_id"].nunique()),
            "rows": len(samples),
            "leads_h": list(request.leads),
            "first_valid_time": _iso_utc(request.valid_times[0]),
            "last_valid_time": _iso_utc(request.valid_times[-1]),
            "source_unit_encountered": source_unit,
            "output_unit": OUTPUT_UNIT,
            "conversion_expression": "ug_m3 = kg_m3 * 1e9",
            "grid_shape": [len(grid_lats), len(grid_lons)],
            "grid_latitude_range": [float(np.min(grid_lats)), float(np.max(grid_lats))],
            "grid_longitude_range": [float(np.min(grid_lons)), float(np.max(grid_lons))],
            "max_station_cell_distance_km": float(
                samples["cams_forecast_cell_dist_km"].max()
            ),
            "grib_metadata": attrs,
        }
        return samples, metadata
    finally:
        close = getattr(dataset, "close", None)
        if callable(close):
            close()


def extract_and_record(
    request: ForecastRequest,
    paths: ForecastPaths,
    stations_path: Path = DEFAULT_STATIONS,
    *,
    registry_version: str | None = None,
    open_dataset: Callable[[Path], xr.Dataset] = _open_grib,
) -> pd.DataFrame:
    """Extract station samples, write CSV, and append extraction provenance."""
    if not paths.raw_grib.exists():
        raise FileNotFoundError(f"Raw CAMS GRIB missing: {paths.raw_grib}")
    provenance = _read_or_new_provenance(paths.provenance_json, request)
    actual_raw_hash = _sha256(paths.raw_grib)
    recorded_raw_hash = provenance.get("raw_file", {}).get("sha256")
    if provenance.get("status") != "complete" or recorded_raw_hash != actual_raw_hash:
        raise RuntimeError(
            "Refusing to extract from a raw CAMS file that is not a "
            "hash-verified completed retrieval."
        )
    stations_path = Path(stations_path)
    stations = pd.read_csv(stations_path)
    version = registry_version or _registry_file_version(stations_path)
    samples, metadata = extract_station_forecasts(
        paths.raw_grib,
        stations,
        request,
        registry_version=version,
        open_dataset=open_dataset,
    )
    paths.station_samples_csv.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.station_samples_csv.with_name(f".{paths.station_samples_csv.name}.tmp")
    samples.to_csv(tmp, index=False, lineterminator="\n")
    os.replace(tmp, paths.station_samples_csv)

    provenance["extraction"] = {
        **metadata,
        "station_registry_path": _portable_path(stations_path),
        "station_registry_sha256": _sha256(stations_path),
        "output_file": {
            "path": paths.station_samples_csv.name,
            "bytes": paths.station_samples_csv.stat().st_size,
            "sha256": _sha256(paths.station_samples_csv),
        },
    }
    _atomic_json(paths.provenance_json, provenance)
    return samples


def attach_to_pairs(
    pairs: pd.DataFrame,
    samples: pd.DataFrame,
) -> pd.DataFrame:
    """Attach actual CAMS forecasts to an orchestrator pair frame.

    The join is intentionally strict: every positive-lead pair must have
    exactly one CAMS forecast and no CAMS sample may fall outside the pair
    population.  Lead zero remains missing because it is an analysis/input,
    not part of this forecast baseline.
    """
    keys = ["init_date", "station_id", "lead_h"]
    required_pairs = set(keys)
    required_samples = set(keys) | {"cams_forecast_pm25"}
    missing_pairs = sorted(required_pairs - set(pairs.columns))
    missing_samples = sorted(required_samples - set(samples.columns))
    if missing_pairs:
        raise ValueError(f"Pair frame missing CAMS join columns: {missing_pairs}.")
    if missing_samples:
        raise ValueError(f"CAMS samples missing required columns: {missing_samples}.")
    if pairs.duplicated(keys).any():
        raise ValueError(f"Pair frame contains duplicate keys {keys}.")
    if samples.duplicated(keys).any():
        raise ValueError(f"CAMS samples contain duplicate keys {keys}.")

    forecast_pairs = pairs[pairs["lead_h"] > 0]
    pair_keys = set(map(tuple, forecast_pairs[keys].itertuples(index=False, name=None)))
    sample_keys = set(map(tuple, samples[keys].itertuples(index=False, name=None)))
    missing = pair_keys - sample_keys
    extra = sample_keys - pair_keys
    if missing or extra:
        raise ValueError(
            "CAMS/pair support mismatch: "
            f"{len(missing)} forecast pair(s) missing CAMS and "
            f"{len(extra)} CAMS sample(s) outside the pair population."
        )

    if "registry_version" in pairs.columns and "registry_version" in samples.columns:
        pair_versions = set(
            pairs["registry_version"].dropna().astype(str).unique().tolist()
        )
        sample_versions = set(
            samples["registry_version"].dropna().astype(str).unique().tolist()
        )
        if pair_versions and sample_versions and pair_versions != sample_versions:
            raise ValueError(
                "CAMS samples and forecast pairs have different registry versions: "
                f"{sample_versions} != {pair_versions}."
            )

    value_columns = [
        column for column in samples.columns if column.startswith("cams_forecast_")
    ]
    overlapping = sorted(set(value_columns) & set(pairs.columns))
    if overlapping:
        raise ValueError(
            "Pair frame already contains CAMS forecast columns; refusing to "
            f"silently replace them: {overlapping}."
        )
    attached = pairs.merge(
        samples[keys + value_columns],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    positive = attached["lead_h"] > 0
    if attached.loc[positive, "cams_forecast_pm25"].isna().any():
        raise RuntimeError("CAMS attachment unexpectedly produced missing forecasts.")
    if attached.loc[~positive, "cams_forecast_pm25"].notna().any():
        raise RuntimeError("CAMS forecast values must not be attached at lead zero.")
    return attached


def load_dates_file(path: Path) -> list[str]:
    """Load a CSV ``init_date`` column or one-date-per-line text file."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines:
        raise ValueError(f"Date file is empty: {path}")

    dates: list[str]
    if "," in lines[0] or lines[0].strip() == "init_date":
        reader = csv.DictReader(lines)
        if reader.fieldnames is None or "init_date" not in reader.fieldnames:
            raise ValueError(f"CSV date file must contain an init_date column: {path}")
        dates = [row["init_date"].strip() for row in reader if row.get("init_date", "").strip()]
    else:
        dates = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]

    validated = [_validate_date(value) for value in dates]
    if not validated:
        raise ValueError(f"Date file contains no initialization dates: {path}")
    if len(validated) != len(set(validated)):
        raise ValueError(f"Date file contains duplicate initialization dates: {path}")
    return validated


def _parse_area(value: str) -> tuple[float, float, float, float]:
    if value == "india":
        return INDIA_AREA
    if value == "pilot":
        return PILOT_AREA
    try:
        return _validate_area(tuple(float(part) for part in value.split(",")))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Area must be 'india', 'pilot', or north,west,south,east."
        ) from exc


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve the actual +12..+96 h CAMS PM2.5 forecast baseline."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--date", help="One initialization date, YYYY-MM-DD.")
    source.add_argument(
        "--dates-file",
        type=Path,
        help="CSV with init_date or one date per line (for example the frozen schedule).",
    )
    parser.add_argument(
        "--area",
        type=_parse_area,
        default=INDIA_AREA,
        help="'india' (default), 'pilot', or north,west,south,east.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--stations",
        type=Path,
        default=None,
        help="After retrieval, sample this station registry (requires cfgrib/ecCodes).",
    )
    parser.add_argument(
        "--registry-version",
        help="Evaluator registry fingerprint to copy into station samples.",
    )
    parser.add_argument(
        "--confirm-multiple",
        action="store_true",
        help="Required before a dates file containing more than one request is retrieved.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print deterministic request documents without writing or retrieving.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    dates = [args.date] if args.date else load_dates_file(args.dates_file)
    dates = [_validate_date(date) for date in dates]
    if len(dates) > 1 and not (args.confirm_multiple or args.dry_run):
        raise SystemExit(
            f"{len(dates)} CAMS requests selected. Review them with --dry-run, "
            "then pass --confirm-multiple to retrieve."
        )

    requests = [ForecastRequest(date=date, area=args.area) for date in dates]
    if args.dry_run:
        documents = [request_document(request) for request in requests]
        print(
            json.dumps(
                documents[0] if len(documents) == 1 else documents,
                indent=2,
                sort_keys=True,
            )
        )
        return

    for request in requests:
        date = request.date
        paths = retrieve_forecast(request, args.output_dir)
        print(
            f"[cams-forecast] {date}: {paths.raw_grib} "
            f"({paths.raw_grib.stat().st_size:,} bytes, sha256={_sha256(paths.raw_grib)})"
        )
        if args.stations is not None:
            samples = extract_and_record(
                request,
                paths,
                args.stations,
                registry_version=args.registry_version,
            )
            print(
                f"[cams-forecast] {date}: sampled {samples['station_id'].nunique()} "
                f"stations x {samples['lead_h'].nunique()} leads -> "
                f"{paths.station_samples_csv}"
            )


if __name__ == "__main__":
    main()
