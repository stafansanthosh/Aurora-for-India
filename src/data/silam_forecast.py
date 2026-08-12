"""Prospective capture of the SILAM operational PM2.5 forecast (incumbent tier).

WHY THIS EXISTS
---------------
IndiaAQBench scores persistence, climatology, CAMS and Aurora. It does **not**
score any operational regional chemistry-transport model, so it cannot express
the claim the project actually wants to make -- "we improve on the forecast
these cities already receive". SILAM is the one incumbent-tier system whose
forecasts are publicly and openly redistributable, so it is the first real
incumbent this benchmark can hold.

WHAT IT IS, HONESTLY
--------------------
This is FMI's **global** SILAM v6.1 at 0.2 degrees, not IMD's India-specific
SILAM configuration and not IITM's AQEWS/AIRWISE WRF-Chem at 10 km. It is a
fair *regional-tier* comparator and a lower bound on what an operational
chemistry model achieves. Beating it is necessary, not sufficient, for a claim
about India's operational systems. Label it `silam_global`, never "the Indian
operational forecast".

Compared with the CAMS baseline already in the repo it is a better comparator
on three counts: hourly output (so the 24-hour headline is computed exactly
rather than trapezoidally approximated), native ug/m3 (no unit conversion), and
0.2 degrees rather than Aurora's 0.4.

THE ARCHIVE IS A ROLLING WINDOW
-------------------------------
The public bucket retains roughly the last 32 daily cycles. **Cycles not
captured are lost permanently.** This module therefore exists to be run on a
schedule from today onward; it cannot reconstruct the 56 frozen retrospective
dates, and no amount of later effort will recover them.

LIVE-SAFETY
-----------
Unlike the retrospective archive (see `src/model/anchor.py`, which notes the
absence of a trustworthy retrieval timestamp), every cycle captured here records
`retrieved_at_utc` alongside the source SHA-256. That is what a live-safe
adapter needs in order to prove it never consumed a value published after the
forecast it corrects.

DATA TERMS
----------
SILAM open data from the Finnish Meteorological Institute, CC BY 4.0. The
attribution string is written into every provenance record. Redistribution of
derived station samples is permitted with attribution; record it before any
publication.

Usage:
    python -m src.data.silam_forecast --list
    python -m src.data.silam_forecast                       # today's cycle
    python -m src.data.silam_forecast --cycle 20260811
    python -m src.data.silam_forecast --backfill            # every cycle still online
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import requests

from ..utils.geo import find_nearest_grid_cell

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = PROJECT_ROOT / "data" / "stations.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "silam"

BUCKET = "fmi-opendata-silam-surface-netcdf"
S3_BASE = f"https://{BUCKET}.s3.eu-west-1.amazonaws.com"
SPECIES = "PM25"
LEAD_DAYS = ("d0", "d1", "d2", "d3", "d4")
MODEL_TAG = "silam_glob_v6_1"
METHOD_NAME = "silam_global"
ATTRIBUTION = ("SILAM air quality forecast, Finnish Meteorological Institute, "
               "CC BY 4.0 (https://silam.fmi.fi/)")
PROVENANCE_SCHEMA_VERSION = 1

# A cycle is only trustworthy if every lead landed; a partial cycle would score
# some leads and silently drop others.
EXPECTED_HOURS_PER_LEAD = 24


# --------------------------------------------------------------------------- #
# Bucket discovery
# --------------------------------------------------------------------------- #

def _s3_list(prefix: str, delimiter: str | None = "/") -> tuple[list[str], list[str]]:
    """Return (common prefixes, keys) under ``prefix``."""
    params = {"list-type": "2", "prefix": prefix, "max-keys": "200"}
    if delimiter:
        params["delimiter"] = delimiter
    response = requests.get(S3_BASE, params=params, timeout=120)
    response.raise_for_status()
    root = ElementTree.fromstring(response.text)
    ns = {"s3": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

    def find_all(tag: str) -> list[str]:
        path = f".//s3:{tag}" if ns else f".//{tag}"
        return [e.text for e in root.findall(path, ns) if e.text]

    prefixes = [p for p in find_all("Prefix") if p and p != prefix]
    return prefixes, find_all("Key")


def available_cycles() -> list[str]:
    """Cycle dates (YYYYMMDD) still present in the rolling public window."""
    prefixes, _ = _s3_list("global/")
    return sorted(p.strip("/").split("/")[-1] for p in prefixes)


def _url(cycle: str, lead: str) -> str:
    return f"{S3_BASE}/global/{cycle}/{MODEL_TAG}_{cycle}_{SPECIES}_{lead}.nc"


# --------------------------------------------------------------------------- #
# Station geometry
# --------------------------------------------------------------------------- #

def load_registry(path: Path = REGISTRY) -> pd.DataFrame:
    reg = pd.read_csv(path)
    missing = {"station_id", "city", "lat", "lon"} - set(reg.columns)
    if missing:
        raise ValueError(f"registry missing columns: {sorted(missing)}")
    reg = reg.copy()
    reg["station_id"] = reg["station_id"].astype(str).str.strip()
    return reg


def station_cells(reg: pd.DataFrame, lats: np.ndarray, lons: np.ndarray) -> pd.DataFrame:
    """Nearest SILAM cell per station. SILAM lon is -180..180, as is the registry."""
    rows = []
    for record in reg.itertuples(index=False):
        lat_idx, lon_idx, dist = find_nearest_grid_cell(
            float(record.lat), float(record.lon), lats, lons)
        rows.append({"station_id": record.station_id, "city": record.city,
                     "lat_idx": lat_idx, "lon_idx": lon_idx,
                     "cell_dist_km": round(dist, 2)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> tuple[str, int]:
    with requests.get(url, stream=True, timeout=900) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(1 << 20):
                handle.write(chunk)
    return _sha256(destination), destination.stat().st_size


def _sample_file(path: Path, cells: pd.DataFrame, init: pd.Timestamp) -> pd.DataFrame:
    """Pointwise station extraction from one lead-day file."""
    import xarray as xr

    with xr.open_dataset(path) as ds:
        if SPECIES not in ds:
            raise ValueError(f"{path.name}: no {SPECIES} variable")
        lat_sel = xr.DataArray(cells["lat_idx"].to_numpy(), dims="station")
        lon_sel = xr.DataArray(cells["lon_idx"].to_numpy(), dims="station")
        values = ds[SPECIES].isel(lat=lat_sel, lon=lon_sel).to_numpy()  # (time, station)
        times = pd.to_datetime(ds["time"].to_numpy(), utc=True)
        units = str(ds[SPECIES].attrs.get("units", "")).lower()

    if "ug/m3" not in units.replace(" ", ""):
        raise ValueError(f"{path.name}: unexpected units {units!r}; refusing to "
                         "record values whose scale is not verified")

    frame = pd.DataFrame(values, index=times, columns=cells["station_id"].to_numpy())
    frame = frame.stack(future_stack=True).rename(METHOD_NAME).reset_index()
    frame.columns = ["valid_time", "station_id", "silam_pm25"]
    frame["lead_h"] = ((frame["valid_time"] - init).dt.total_seconds() // 3600).astype(int)
    return frame


def capture_cycle(cycle: str, output_dir: Path = OUTPUT_DIR,
                  keep_raw: bool = False, force: bool = False) -> Path:
    """Capture one SILAM cycle to an immutable, provenance-stamped CSV."""
    directory = output_dir / cycle
    directory.mkdir(parents=True, exist_ok=True)
    samples_path = directory / f"silam_{SPECIES.lower()}_stations.csv"
    provenance_path = directory / "provenance.json"

    if samples_path.exists() and provenance_path.exists() and not force:
        existing = json.loads(provenance_path.read_text())
        if existing.get("status") == "complete":
            print(f"[silam] {cycle}: already complete ({samples_path.name})")
            return samples_path

    reg = load_registry()
    init = pd.Timestamp(f"{cycle}T00:00:00Z")
    provenance: dict[str, Any] = {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "method": METHOD_NAME,
        "model": MODEL_TAG,
        "species": SPECIES,
        "cycle": cycle,
        "init_time_utc": init.isoformat(),
        "attribution": ATTRIBUTION,
        "licence": "CC-BY-4.0",
        "grid_note": "global 0.2 deg; nearest-cell sampling, distance recorded",
        "registry_stations": int(len(reg)),
        "status": "retrieving",
        "files": [],
    }

    parts, cells = [], None
    with tempfile.TemporaryDirectory() as tmp:
        for lead in LEAD_DAYS:
            url = _url(cycle, lead)
            target = (directory / Path(url).name) if keep_raw else Path(tmp) / Path(url).name
            retrieved_at = datetime.now(timezone.utc).isoformat()
            digest, size = _download(url, target)

            if cells is None:
                import xarray as xr
                with xr.open_dataset(target) as ds:
                    cells = station_cells(reg, ds["lat"].to_numpy(), ds["lon"].to_numpy())
                provenance["max_cell_distance_km"] = float(cells["cell_dist_km"].max())

            part = _sample_file(target, cells, init)
            hours = part["valid_time"].nunique()
            if hours != EXPECTED_HOURS_PER_LEAD:
                raise ValueError(
                    f"{cycle} {lead}: expected {EXPECTED_HOURS_PER_LEAD} hours, got {hours}")
            parts.append(part)
            provenance["files"].append({
                "lead": lead, "url": url, "sha256": digest, "bytes": size,
                "retrieved_at_utc": retrieved_at, "hours": int(hours)})
            print(f"[silam] {cycle} {lead}: {size/1e6:6.1f} MB, {hours} h, "
                  f"{part['station_id'].nunique()} stations")

    samples = pd.concat(parts, ignore_index=True)
    samples = samples.merge(cells[["station_id", "city", "cell_dist_km"]],
                            on="station_id", how="left")
    samples.insert(0, "cycle", cycle)
    samples.insert(1, "init_time", init.isoformat())
    samples = samples.sort_values(["station_id", "valid_time"]).reset_index(drop=True)

    if samples[["station_id", "valid_time"]].duplicated().any():
        raise ValueError(f"{cycle}: duplicate (station, valid_time) rows")

    samples.to_csv(samples_path, index=False)
    provenance["status"] = "complete"
    provenance["rows"] = int(len(samples))
    provenance["stations"] = int(samples["station_id"].nunique())
    provenance["lead_h_range"] = [int(samples["lead_h"].min()), int(samples["lead_h"].max())]
    provenance["samples_sha256"] = _sha256(samples_path)
    provenance_path.write_text(json.dumps(provenance, indent=2))
    print(f"[silam] {cycle}: wrote {len(samples):,} rows -> {samples_path}")
    return samples_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Capture SILAM PM2.5 forecasts.")
    parser.add_argument("--cycle", help="YYYYMMDD; default is today (UTC)")
    parser.add_argument("--list", action="store_true", help="show cycles still online")
    parser.add_argument("--backfill", action="store_true",
                        help="capture every cycle still in the rolling window")
    parser.add_argument("--keep-raw", action="store_true",
                        help="retain the ~190 MB/cycle NetCDF grids")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    cycles = available_cycles()
    if args.list:
        print(f"{len(cycles)} cycles online: {cycles[0]} .. {cycles[-1]}")
        for c in cycles:
            print(" ", c)
        return

    if args.backfill:
        targets = cycles
    elif args.cycle:
        targets = [args.cycle]
    else:
        targets = [datetime.now(timezone.utc).strftime("%Y%m%d")]

    failures = []
    for cycle in targets:
        if cycle not in cycles:
            print(f"[silam] {cycle}: NOT in the rolling window "
                  f"({cycles[0]}..{cycles[-1]}) -- permanently unavailable")
            failures.append(cycle)
            continue
        try:
            capture_cycle(cycle, args.output_dir, args.keep_raw, args.force)
        except Exception as exc:                                   # noqa: BLE001
            print(f"[silam] {cycle}: FAILED {exc}")
            failures.append(cycle)

    if failures:
        raise SystemExit(f"{len(failures)} cycle(s) failed: {failures}")


if __name__ == "__main__":
    main()
