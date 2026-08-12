"""ERA5 boundary-layer fields for the Option B perfect-prognosis ceiling test.

WHY
---
`docs/EPISODE_SKILL_DIAGNOSIS.md` concluded that Gangetic winter episodes are
local emissions meeting a collapsed boundary layer, and that the 0.4 degree
Aurora air-pollution checkpoint carries no boundary-layer information at all.
Option B (`docs/OPTIONS_REVIEW.md` section 2) proposes fixing that with Aurora
1.5 meteorology.

Before spending any GPU budget on an Aurora 1.5 rollout, run the cheap version
of the question:

    If we had PERFECT knowledge of boundary-layer height and humidity at the
    target window, how much exceedance skill would that buy?

ERA5 is reanalysis -- it assimilates observations and is valid *at* the target
window, so it is an upper bound on what any forecast of the same field could
supply. If perfect-prognosis BLH does not materially improve Very Poor+
discrimination, then Aurora 1.5's forecast BLH will improve it less, and
Option B has no headroom. This is a kill-test, and it costs downloads and CPU
rather than GPU hours.

SPLIT DISCIPLINE
----------------
Only the TRAIN period is pulled by default (`--train-only`, the default).
The test must not consume held-out evidence.

HONEST LABELLING
----------------
Anything scored with these fields is **perfect-prognosis**, not a forecast.
It establishes a ceiling and must never be reported as achievable skill.

Usage:
    python -m src.data.era5_boundary_layer --plan
    python -m src.data.era5_boundary_layer
    python -m src.data.era5_boundary_layer --sample-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..splits import SPLIT_CUTOFF
from ..utils.geo import find_nearest_grid_cell

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATES_FILE = PROJECT_ROOT / "docs" / "benchmark_dates.csv"
REGISTRY = PROJECT_ROOT / "data" / "stations.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "era5_blh"
SAMPLES = OUTPUT_DIR / "era5_blh_stations.csv"

CDS_URL = "https://cds.climate.copernicus.eu/api"
DATASET = "reanalysis-era5-single-levels"

# Boundary-layer height is the variable the diagnosis says is missing.
# Dew-point gives humidity/fog-adjacent structure; 10 m wind gives ventilation.
VARIABLES = [
    "boundary_layer_height",
    "2m_dewpoint_temperature",
    "2m_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
]
SHORT_NAMES = {"blh": "era5_blh", "d2m": "era5_d2m", "t2m": "era5_t2m",
               "u10": "era5_u10", "v10": "era5_v10"}

# India domain, [North, West, South, East] -- matches orchestrate.INDIA.
AREA = [37.0, 68.0, 6.0, 98.0]

# Forecast windows run to +96 h, and a 24-hour window starting at +72 h ends at
# +96 h, so each initialisation needs its own day plus four more.
DAYS_PER_INIT = 5


def load_dates(train_only: bool = True) -> list[pd.Timestamp]:
    dates = pd.read_csv(DATES_FILE)
    column = "date" if "date" in dates.columns else dates.columns[0]
    stamps = pd.to_datetime(dates[column], utc=True)
    if train_only:
        stamps = stamps[stamps < SPLIT_CUTOFF]
    return sorted(pd.Timestamp(s) for s in stamps)


def required_days(dates: list[pd.Timestamp]) -> set[pd.Timestamp]:
    """Every calendar day any forecast window can touch."""
    days: set[pd.Timestamp] = set()
    for date in dates:
        for offset in range(DAYS_PER_INIT + 1):
            days.add(pd.Timestamp(date.date()) + pd.Timedelta(days=offset))
    return days


def month_plan(days: set[pd.Timestamp]) -> dict[tuple[int, int], list[int]]:
    """CDS is requested per month; group the needed days."""
    plan: dict[tuple[int, int], set[int]] = {}
    for day in days:
        plan.setdefault((day.year, day.month), set()).add(day.day)
    return {k: sorted(v) for k, v in sorted(plan.items())}


def _request(year: int, month: int, days: list[int]) -> dict:
    return {
        "product_type": ["reanalysis"],
        "variable": VARIABLES,
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": [f"{d:02d}" for d in days],
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": AREA,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(train_only: bool = True, output_dir: Path = OUTPUT_DIR) -> list[Path]:
    import cdsapi

    output_dir.mkdir(parents=True, exist_ok=True)
    plan = month_plan(required_days(load_dates(train_only)))
    client = cdsapi.Client(url=CDS_URL)
    written = []

    for (year, month), days in plan.items():
        target = output_dir / f"era5_blh_{year}{month:02d}.nc"
        provenance_path = output_dir / f"era5_blh_{year}{month:02d}_provenance.json"
        request = _request(year, month, days)

        if target.exists() and provenance_path.exists():
            existing = json.loads(provenance_path.read_text())
            if (existing.get("request") == request
                    and existing.get("sha256") == _sha256(target)):
                print(f"[era5] {year}-{month:02d}: cached ({len(days)} days)")
                written.append(target)
                continue

        print(f"[era5] {year}-{month:02d}: requesting {len(days)} days, "
              f"{len(VARIABLES)} variables ...")
        retrieved_at = datetime.now(timezone.utc).isoformat()
        client.retrieve(DATASET, request, str(target))
        provenance_path.write_text(json.dumps({
            "dataset": DATASET, "endpoint": CDS_URL, "request": request,
            "retrieved_at_utc": retrieved_at, "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "licence": "Copernicus ERA5; accept the licence in the CDS web UI",
            "purpose": "perfect-prognosis ceiling test; NOT a forecast input",
        }, indent=2))
        print(f"[era5] {year}-{month:02d}: {target.stat().st_size/1e6:.1f} MB")
        written.append(target)
    return written


def sample_stations(output_dir: Path = OUTPUT_DIR) -> Path:
    """Extract every ERA5 field at the registry station cells."""
    import xarray as xr

    files = sorted(output_dir.glob("era5_blh_*.nc"))
    if not files:
        raise SystemExit("no ERA5 files; run the download first")

    reg = pd.read_csv(REGISTRY)
    reg["station_id"] = reg["station_id"].astype(str).str.strip()
    parts, cells = [], None

    for path in files:
        with xr.open_dataset(path) as ds:
            lat_name = "latitude" if "latitude" in ds.coords else "lat"
            lon_name = "longitude" if "longitude" in ds.coords else "lon"
            time_name = "valid_time" if "valid_time" in ds.coords else "time"
            lats = ds[lat_name].to_numpy()
            lons = ds[lon_name].to_numpy()

            if cells is None:
                rows = []
                for record in reg.itertuples(index=False):
                    li, loi, dist = find_nearest_grid_cell(
                        float(record.lat), float(record.lon), lats, lons)
                    rows.append({"station_id": record.station_id, "city": record.city,
                                 "lat_idx": li, "lon_idx": loi,
                                 "era5_cell_dist_km": round(dist, 2)})
                cells = pd.DataFrame(rows)

            lat_sel = xr.DataArray(cells["lat_idx"].to_numpy(), dims="station")
            lon_sel = xr.DataArray(cells["lon_idx"].to_numpy(), dims="station")
            frame = None
            for short, out_name in SHORT_NAMES.items():
                if short not in ds:
                    continue
                values = ds[short].isel({lat_name: lat_sel, lon_name: lon_sel}).to_numpy()
                times = pd.to_datetime(ds[time_name].to_numpy(), utc=True)
                block = pd.DataFrame(values, index=times,
                                     columns=cells["station_id"].to_numpy())
                block = block.stack(future_stack=True).rename(out_name).reset_index()
                block.columns = ["valid_time", "station_id", out_name]
                frame = block if frame is None else frame.merge(
                    block, on=["valid_time", "station_id"], how="outer")
            if frame is not None:
                parts.append(frame)
        print(f"[era5] sampled {path.name}")

    samples = pd.concat(parts, ignore_index=True)
    samples = samples.drop_duplicates(["station_id", "valid_time"])
    samples = samples.merge(cells[["station_id", "city", "era5_cell_dist_km"]],
                            on="station_id", how="left")
    if "era5_u10" in samples and "era5_v10" in samples:
        samples["era5_wind"] = np.hypot(samples["era5_u10"], samples["era5_v10"])
    # Ventilation coefficient: the physical quantity that actually dilutes.
    if "era5_blh" in samples and "era5_wind" in samples:
        samples["era5_ventilation"] = samples["era5_blh"] * samples["era5_wind"]
    if "era5_t2m" in samples and "era5_d2m" in samples:
        samples["era5_dewpoint_depression"] = samples["era5_t2m"] - samples["era5_d2m"]

    samples = samples.sort_values(["station_id", "valid_time"]).reset_index(drop=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    samples.to_csv(SAMPLES, index=False)
    print(f"[era5] wrote {len(samples):,} rows -> {SAMPLES}")
    return SAMPLES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--plan", action="store_true", help="show the request plan and exit")
    parser.add_argument("--sample-only", action="store_true")
    parser.add_argument("--include-test", action="store_true",
                        help="also pull test-period days (NOT for the ceiling test)")
    args = parser.parse_args()

    train_only = not args.include_test
    if args.plan:
        plan = month_plan(required_days(load_dates(train_only)))
        total = sum(len(d) for d in plan.values())
        print(f"{len(plan)} monthly requests, {total} days, "
              f"{len(VARIABLES)} variables, area={AREA}")
        for (year, month), days in plan.items():
            print(f"  {year}-{month:02d}: {len(days)} days")
        return

    if not args.sample_only:
        download(train_only)
    sample_stations()


if __name__ == "__main__":
    main()
