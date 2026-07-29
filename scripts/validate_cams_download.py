"""Validate the complete frozen-date CAMS forecast archive.

Run this before copying ``data/cams_forecast`` to GPU workers.  The archive is
local and ignored by Git; this script makes its completeness and provenance
checks reproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.cams_forecast import DEFAULT_LEADS, INDIA_AREA


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATES = PROJECT_ROOT / "docs" / "benchmark_dates.csv"
DEFAULT_ARCHIVE = PROJECT_ROOT / "data" / "cams_forecast"
EXPECTED_STATIONS = 159
MAX_CELL_DISTANCE_KM = 32.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fail(message: str) -> None:
    raise RuntimeError(message)


def validate_archive(dates_file: Path, archive: Path) -> dict[str, float | int]:
    schedule = pd.read_csv(dates_file)
    if "init_date" not in schedule.columns:
        _fail(f"{dates_file} has no init_date column")
    dates = schedule["init_date"].astype(str).tolist()
    if len(dates) != len(set(dates)):
        _fail("Frozen schedule contains duplicate dates")

    expected_dirs = {f"init={date}T12-00Z" for date in dates}
    actual_dirs = {path.name for path in archive.iterdir() if path.is_dir()}
    missing = sorted(expected_dirs - actual_dirs)
    extra = sorted(actual_dirs - expected_dirs)
    if missing or extra:
        _fail(f"CAMS archive directory mismatch: missing={missing}, extra={extra}")

    all_values: list[np.ndarray] = []
    max_distance = 0.0
    total_rows = 0
    for date in dates:
        directory = archive / f"init={date}T12-00Z"
        request_path = directory / "request.json"
        provenance_path = directory / "provenance.json"
        raw_path = directory / "pm25_leads_12_96.grib"
        samples_path = directory / "station_samples.csv"
        for path in (request_path, provenance_path, raw_path, samples_path):
            if not path.is_file() or path.stat().st_size == 0:
                _fail(f"{date}: required artifact missing or empty: {path.name}")

        request = json.loads(request_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        expected_area = [f"{value:g}" for value in INDIA_AREA]
        expected_leads = [str(lead) for lead in DEFAULT_LEADS]
        payload = request.get("payload", {})
        if payload.get("date") != date:
            _fail(f"{date}: request date mismatch")
        if payload.get("area") != expected_area:
            _fail(f"{date}: request area is not the pinned India area")
        if payload.get("leadtime_hour") != expected_leads:
            _fail(f"{date}: request lead set mismatch")
        if provenance.get("status") != "complete":
            _fail(f"{date}: retrieval status is not complete")
        if provenance.get("request") != payload:
            _fail(f"{date}: request/provenance payload mismatch")
        if provenance.get("raw_file", {}).get("sha256") != _sha256(raw_path):
            _fail(f"{date}: raw GRIB SHA-256 mismatch")

        samples = pd.read_csv(samples_path)
        expected_rows = EXPECTED_STATIONS * len(DEFAULT_LEADS)
        if len(samples) != expected_rows:
            _fail(f"{date}: {len(samples)} samples, expected {expected_rows}")
        if samples["station_id"].astype(str).nunique() != EXPECTED_STATIONS:
            _fail(f"{date}: station count is not {EXPECTED_STATIONS}")
        if sorted(samples["lead_h"].unique().tolist()) != list(DEFAULT_LEADS):
            _fail(f"{date}: extracted lead set mismatch")
        if samples.duplicated(["init_date", "station_id", "lead_h"]).any():
            _fail(f"{date}: duplicate station/lead keys")
        if set(samples["init_date"].astype(str)) != {date}:
            _fail(f"{date}: sample initialization date mismatch")

        values = pd.to_numeric(
            samples["cams_forecast_pm25"], errors="coerce"
        ).to_numpy(dtype=float)
        distances = pd.to_numeric(
            samples["cams_forecast_cell_dist_km"], errors="coerce"
        ).to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            _fail(f"{date}: non-finite or negative PM2.5 values")
        if not np.isfinite(distances).all() or (distances < 0).any():
            _fail(f"{date}: invalid station-cell distances")
        date_max_distance = float(distances.max())
        if date_max_distance > MAX_CELL_DISTANCE_KM:
            _fail(
                f"{date}: maximum station-cell distance {date_max_distance:.2f} km "
                f"exceeds {MAX_CELL_DISTANCE_KM:.2f} km"
            )

        extraction = provenance.get("extraction", {})
        output_file = extraction.get("output_file", {})
        if output_file.get("sha256") != _sha256(samples_path):
            _fail(f"{date}: station-sample SHA-256 mismatch")
        if extraction.get("rows") != expected_rows:
            _fail(f"{date}: provenance sample-row count mismatch")
        if extraction.get("stations") != EXPECTED_STATIONS:
            _fail(f"{date}: provenance station count mismatch")

        all_values.append(values)
        max_distance = max(max_distance, date_max_distance)
        total_rows += len(samples)

    combined = np.concatenate(all_values)
    return {
        "dates": len(dates),
        "stations_per_date": EXPECTED_STATIONS,
        "leads_per_station": len(DEFAULT_LEADS),
        "rows": total_rows,
        "pm25_min": float(combined.min()),
        "pm25_median": float(np.median(combined)),
        "pm25_max": float(combined.max()),
        "max_cell_distance_km": max_distance,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the frozen-date CAMS forecast archive."
    )
    parser.add_argument("--dates-file", type=Path, default=DEFAULT_DATES)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    summary = validate_archive(args.dates_file, args.archive)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
