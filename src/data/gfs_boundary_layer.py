"""Historical NOAA GFS boundary-layer fields for the forecast-BLH gate.

The binding design is ``docs/FORECAST_BLH_CONTRACT.md``.  This module reads
only frozen TRAIN initialisations, uses the exact 12Z GFS cycle, and samples
the 0.25-degree forecast every three hours through +96 h.  It range-reads the
five required GRIB messages rather than downloading multi-hundred-megabyte
global files.

Usage:
    python -m src.data.gfs_boundary_layer --plan
    python -m src.data.gfs_boundary_layer
    python -m src.data.gfs_boundary_layer --sample-only
    python -m src.data.gfs_boundary_layer --validate-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..splits import SPLIT_CUTOFF
from ..utils.geo import find_nearest_grid_cell

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATES_FILE = PROJECT_ROOT / "docs" / "benchmark_dates.csv"
REGISTRY = PROJECT_ROOT / "data" / "stations.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "gfs_blh"
BY_INIT_DIR = OUTPUT_DIR / "by_init"
PROVENANCE_DIR = OUTPUT_DIR / "provenance"
SAMPLES = OUTPUT_DIR / "gfs_blh_stations.csv"
FAILURES = OUTPUT_DIR / "failed_dates.json"

BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
CYCLE_HOUR = 12
FORECAST_HOURS = tuple(range(0, 97, 3))
SOURCE_LICENSE = (
    "NOAA data disseminated through NODD are open to the public and can be "
    "used as desired; attribution requested"
)

# Exact index identities in NOAA's official pgrb2 inventory.  ecCodes 2.47
# calls HPBL an unknown local parameter, so the authoritative identity is the
# byte range selected from the NOAA index, not the decoder's short name.
FIELD_SPECS: dict[str, tuple[str, str, str]] = {
    "gfs_blh": ("HPBL", "surface", "m"),
    "gfs_t2m": ("TMP", "2 m above ground", "K"),
    "gfs_d2m": ("DPT", "2 m above ground", "K"),
    "gfs_u10": ("UGRD", "10 m above ground", "m s-1"),
    "gfs_v10": ("VGRD", "10 m above ground", "m s-1"),
}

_thread_state = threading.local()
_eccodes_lock = threading.Lock()


def load_dates() -> list[pd.Timestamp]:
    dates = pd.read_csv(DATES_FILE)
    column = "init_date" if "init_date" in dates.columns else dates.columns[0]
    stamps = pd.to_datetime(dates[column], utc=True)
    return sorted(pd.Timestamp(s) for s in stamps[stamps < SPLIT_CUTOFF])


def source_urls(date: pd.Timestamp, lead_h: int) -> tuple[str, str]:
    ymd = pd.Timestamp(date).strftime("%Y%m%d")
    stem = (
        f"{BUCKET}/gfs.{ymd}/{CYCLE_HOUR:02d}/atmos/"
        f"gfs.t{CYCLE_HOUR:02d}z.pgrb2.0p25.f{lead_h:03d}"
    )
    return stem, f"{stem}.idx"


def parse_index(text: str) -> dict[str, dict[str, Any]]:
    """Return exact byte ranges for FIELD_SPECS from a NOAA ``.idx`` file."""
    parsed: list[dict[str, Any]] = []
    for raw in text.splitlines():
        parts = raw.rstrip().split(":")
        if len(parts) < 6:
            continue
        try:
            parsed.append({
                "record": int(parts[0]),
                "offset": int(parts[1]),
                "reference": parts[2],
                "parameter": parts[3],
                "level": parts[4],
                "step": parts[5],
                "index_line": raw.rstrip(),
            })
        except ValueError:
            continue

    wanted: dict[str, dict[str, Any]] = {}
    identities = {(param, level): out for out, (param, level, _) in FIELD_SPECS.items()}
    for i, record in enumerate(parsed):
        out = identities.get((record["parameter"], record["level"]))
        if out is None:
            continue
        if out in wanted:
            raise ValueError(f"duplicate index identity for {out}")
        if i + 1 >= len(parsed):
            raise ValueError(f"cannot determine end offset for final record {out}")
        end = int(parsed[i + 1]["offset"]) - 1
        wanted[out] = {**record, "end": end, "bytes": end - int(record["offset"]) + 1}

    missing = sorted(set(FIELD_SPECS) - set(wanted))
    if missing:
        raise ValueError(f"GFS index is missing required fields: {missing}")
    return wanted


def _session() -> requests.Session:
    session = getattr(_thread_state, "session", None)
    if session is None:
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        session = requests.Session()
        session.headers["User-Agent"] = "IndiaAQBench-forecast-BLH/1.0"
        session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=16,
                                                pool_maxsize=16))
        _thread_state.session = session
    return session


def _get_index(url: str) -> tuple[str, str]:
    response = _session().get(url, timeout=(15, 60))
    response.raise_for_status()
    content = response.content
    return content.decode("utf-8"), hashlib.sha256(content).hexdigest()


def _get_range(url: str, start: int, end: int) -> tuple[bytes, str]:
    response = _session().get(
        url, headers={"Range": f"bytes={start}-{end}"}, timeout=(15, 120)
    )
    response.raise_for_status()
    expected = end - start + 1
    if response.status_code != 206:
        raise RuntimeError(f"server ignored byte range for {url}: HTTP {response.status_code}")
    if len(response.content) != expected:
        raise RuntimeError(
            f"short byte range for {url}: expected {expected}, got {len(response.content)}"
        )
    if not response.content.startswith(b"GRIB") or not response.content.endswith(b"7777"):
        raise RuntimeError(f"range for {url} is not one complete GRIB message")
    return response.content, hashlib.sha256(response.content).hexdigest()


def station_cells(registry: pd.DataFrame) -> pd.DataFrame:
    lats = np.arange(90.0, -90.0001, -0.25)
    lons = np.arange(0.0, 360.0, 0.25)
    rows = []
    for row in registry.itertuples(index=False):
        lat_idx, lon_idx, distance = find_nearest_grid_cell(
            float(row.lat), float(row.lon), lats, lons
        )
        rows.append({
            "station_id": str(row.station_id).strip(),
            "city": str(row.city),
            "gfs_lat_idx": int(lat_idx),
            "gfs_lon_idx": int(lon_idx),
            "gfs_flat_idx": int(lat_idx) * len(lons) + int(lon_idx),
            "gfs_cell_dist_km": round(float(distance), 2),
        })
    return pd.DataFrame(rows)


def _decode_values(message: bytes, cells: pd.DataFrame) -> tuple[np.ndarray, dict[str, Any]]:
    from eccodes import (
        codes_get,
        codes_get_array,
        codes_get_long,
        codes_new_from_message,
        codes_release,
    )

    # ecCodes' definition loader is not thread-safe during concurrent first
    # use on Windows.  Network reads remain parallel; only this short decode is
    # serialized to prevent native ``no definitions found`` failures.
    with _eccodes_lock:
        handle = codes_new_from_message(message)
        try:
            ni = int(codes_get_long(handle, "Ni"))
            nj = int(codes_get_long(handle, "Nj"))
            if (nj, ni) != (721, 1440):
                raise ValueError(f"unexpected GFS grid: {(nj, ni)}")
            values = np.asarray(codes_get_array(handle, "values"), dtype=float)
            sampled = values[cells["gfs_flat_idx"].to_numpy(int)]
            metadata = {
                "data_date": int(codes_get_long(handle, "dataDate")),
                "data_time": int(codes_get_long(handle, "dataTime")),
                "forecast_time": int(codes_get_long(handle, "forecastTime")),
                "validity_date": int(codes_get_long(handle, "validityDate")),
                "validity_time": int(codes_get_long(handle, "validityTime")),
                "type_of_level": str(codes_get(handle, "typeOfLevel")),
                "decoder_short_name": str(codes_get(handle, "shortName")),
            }
            return sampled, metadata
        finally:
            codes_release(handle)


def retrieve_lead(date: pd.Timestamp, lead_h: int, cells: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    data_url, index_url = source_urls(date, lead_h)
    index_text, index_sha = _get_index(index_url)
    records = parse_index(index_text)
    init_time = pd.Timestamp(date).normalize() + pd.Timedelta(hours=CYCLE_HOUR)
    valid_time = init_time + pd.Timedelta(hours=lead_h)

    frame = cells[["station_id", "city", "gfs_cell_dist_km"]].copy()
    provenance_fields: dict[str, Any] = {}
    for output, (_, _, units) in FIELD_SPECS.items():
        record = records[output]
        message, message_sha = _get_range(data_url, record["offset"], record["end"])
        sampled, metadata = _decode_values(message, cells)
        if metadata["data_date"] != int(init_time.strftime("%Y%m%d")):
            raise ValueError(f"{output}: GRIB dataDate does not match init")
        if metadata["data_time"] != CYCLE_HOUR * 100:
            raise ValueError(f"{output}: GRIB dataTime does not match 12Z")
        if metadata["forecast_time"] != lead_h:
            raise ValueError(f"{output}: GRIB forecastTime does not match lead")
        expected_valid_date = int(valid_time.strftime("%Y%m%d"))
        expected_valid_time = int(valid_time.strftime("%H%M"))
        if (metadata["validity_date"], metadata["validity_time"]) != (
            expected_valid_date,
            expected_valid_time,
        ):
            raise ValueError(f"{output}: GRIB valid time does not match init + lead")
        if not np.isfinite(sampled).all():
            raise ValueError(f"{output}: non-finite station values")
        frame[output] = sampled
        provenance_fields[output] = {
            "parameter": record["parameter"],
            "level": record["level"],
            "units": units,
            "range": [int(record["offset"]), int(record["end"])],
            "bytes": int(record["bytes"]),
            "sha256": message_sha,
            "index_line": record["index_line"],
            "decoded": metadata,
        }

    frame.insert(0, "lead_h", int(lead_h))
    frame.insert(0, "valid_time", valid_time)
    frame.insert(0, "init_time", init_time)
    frame.insert(0, "init_date", pd.Timestamp(date).strftime("%Y-%m-%d"))
    frame["gfs_wind"] = np.hypot(frame["gfs_u10"], frame["gfs_v10"])
    frame["gfs_ventilation"] = frame["gfs_blh"] * frame["gfs_wind"]
    frame["gfs_dewpoint_depression"] = frame["gfs_t2m"] - frame["gfs_d2m"]

    provenance = {
        "init_date": pd.Timestamp(date).strftime("%Y-%m-%d"),
        "init_time": init_time.isoformat(),
        "valid_time": valid_time.isoformat(),
        "lead_h": int(lead_h),
        "data_url": data_url,
        "index_url": index_url,
        "index_sha256": index_sha,
        "fields": provenance_fields,
    }
    return frame, provenance


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _write_csv_atomic(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def _expected_init_path(date: pd.Timestamp) -> Path:
    return BY_INIT_DIR / f"gfs_blh_{pd.Timestamp(date).strftime('%Y%m%d')}.csv"


def _expected_provenance_path(date: pd.Timestamp) -> Path:
    return PROVENANCE_DIR / f"gfs_blh_{pd.Timestamp(date).strftime('%Y%m%d')}.json"


def validate_init(frame: pd.DataFrame, date: pd.Timestamp, stations: set[str]) -> None:
    frame = frame.copy()
    frame["station_id"] = frame["station_id"].astype(str)
    ymd = pd.Timestamp(date).strftime("%Y-%m-%d")
    if set(frame["init_date"].astype(str)) != {ymd}:
        raise ValueError(f"{ymd}: wrong init_date")
    if set(pd.to_numeric(frame["lead_h"]).astype(int)) != set(FORECAST_HOURS):
        raise ValueError(f"{ymd}: incomplete lead set")
    if set(frame["station_id"]) != stations:
        raise ValueError(f"{ymd}: station set differs from registry")
    expected = len(stations) * len(FORECAST_HOURS)
    if len(frame) != expected:
        raise ValueError(f"{ymd}: expected {expected:,} rows, found {len(frame):,}")
    keys = ["init_date", "station_id", "lead_h"]
    if frame.duplicated(keys).any():
        raise ValueError(f"{ymd}: duplicate keys")
    numeric = list(FIELD_SPECS) + [
        "gfs_wind", "gfs_ventilation", "gfs_dewpoint_depression"
    ]
    if not np.isfinite(frame[numeric].to_numpy(float)).all():
        raise ValueError(f"{ymd}: non-finite field values")
    init = pd.to_datetime(frame["init_time"], utc=True)
    valid = pd.to_datetime(frame["valid_time"], utc=True)
    expected_valid = init + pd.to_timedelta(pd.to_numeric(frame["lead_h"]), unit="h")
    if not valid.equals(expected_valid):
        raise ValueError(f"{ymd}: valid_time != init_time + lead_h")


def retrieve_date(date: pd.Timestamp, cells: pd.DataFrame, workers: int = 8) -> Path:
    path = _expected_init_path(date)
    provenance_path = _expected_provenance_path(date)
    stations = set(cells["station_id"].astype(str))
    if path.exists() and provenance_path.exists():
        cached = pd.read_csv(path)
        validate_init(cached, date, stations)
        print(f"[gfs-blh] {date:%Y-%m-%d}: cached")
        return path
    if path.exists() or provenance_path.exists():
        raise RuntimeError(
            f"{date:%Y-%m-%d}: incomplete cache pair; review before replacing {path.parent}"
        )

    parts: dict[int, pd.DataFrame] = {}
    provenance: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(retrieve_lead, date, lead, cells): lead
            for lead in FORECAST_HOURS
        }
        for future in as_completed(futures):
            lead = futures[future]
            frame, record = future.result()
            parts[lead] = frame
            provenance[lead] = record
            print(f"[gfs-blh] {date:%Y-%m-%d} +{lead:03d} h")

    combined = pd.concat([parts[lead] for lead in FORECAST_HOURS], ignore_index=True)
    combined = combined.sort_values(["station_id", "lead_h"]).reset_index(drop=True)
    validate_init(combined, date, stations)
    _write_csv_atomic(path, combined)
    _write_json_atomic(provenance_path, {
        "dataset": "NOAA GFS 0.25 degree pgrb2",
        "bucket": BUCKET,
        "cycle": "12Z",
        "forecast_hours": list(FORECAST_HOURS),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "licence": SOURCE_LICENSE,
        "purpose": "forecast-versus-analysis BLH gate; operational forecast",
        "records": [provenance[lead] for lead in FORECAST_HOURS],
    })
    print(f"[gfs-blh] {date:%Y-%m-%d}: wrote {len(combined):,} station rows")
    return path


def assemble() -> pd.DataFrame:
    registry = pd.read_csv(REGISTRY)
    stations = set(registry["station_id"].astype(str).str.strip())
    frames = []
    for date in load_dates():
        path = _expected_init_path(date)
        provenance_path = _expected_provenance_path(date)
        if not path.exists() or not provenance_path.exists():
            continue
        frame = pd.read_csv(path)
        validate_init(frame, date, stations)
        frames.append(frame)
    if not frames:
        raise SystemExit("no complete GFS initialization files to assemble")
    samples = pd.concat(frames, ignore_index=True)
    samples = samples.sort_values(["init_date", "station_id", "lead_h"]).reset_index(drop=True)
    _write_csv_atomic(SAMPLES, samples)
    print(f"[gfs-blh] assembled {len(samples):,} rows from {samples['init_date'].nunique()} dates")
    return samples


def validate_samples(frame: pd.DataFrame | None = None) -> dict[str, Any]:
    if frame is None:
        frame = pd.read_csv(SAMPLES)
    registry = pd.read_csv(REGISTRY)
    stations = set(registry["station_id"].astype(str).str.strip())
    expected_dates = load_dates()
    present = set(frame["init_date"].astype(str))
    expected = {d.strftime("%Y-%m-%d") for d in expected_dates}
    unexpected = sorted(present - expected)
    if unexpected:
        raise ValueError(f"unexpected GFS init dates: {unexpected}")
    for date in expected_dates:
        ymd = date.strftime("%Y-%m-%d")
        if ymd in present:
            validate_init(frame[frame["init_date"].astype(str) == ymd], date, stations)
    report = {
        "complete_dates": len(present),
        "expected_dates": len(expected),
        "missing_dates": sorted(expected - present),
        "stations": len(stations),
        "leads_per_date": len(FORECAST_HOURS),
        "rows": len(frame),
        "duplicates": int(frame.duplicated(["init_date", "station_id", "lead_h"]).sum()),
        "finite": bool(np.isfinite(frame[list(FIELD_SPECS)].to_numpy(float)).all()),
    }
    print(json.dumps(report, indent=2))
    return report


def reconcile_failures(failures: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep only failures whose exact date still lacks a validated cache pair."""
    unresolved = []
    registry = pd.read_csv(REGISTRY)
    stations = set(registry["station_id"].astype(str).str.strip())
    for failure in failures:
        date = pd.Timestamp(failure["date"], tz="UTC")
        path = _expected_init_path(date)
        provenance_path = _expected_provenance_path(date)
        if path.exists() and provenance_path.exists():
            validate_init(pd.read_csv(path), date, stations)
            continue
        unresolved.append(failure)
    return unresolved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--sample-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--date-retries", type=int, default=2,
                        help="whole-date retries after transport/decode failure")
    args = parser.parse_args()

    dates = load_dates()
    if args.plan:
        print(f"{len(dates)} train-only 12Z cycles")
        print(f"{len(FORECAST_HOURS)} forecast hours/date: 0..96 by 3 h")
        print(f"{len(dates) * len(FORECAST_HOURS):,} index objects")
        print(f"{len(dates) * len(FORECAST_HOURS) * len(FIELD_SPECS):,} GRIB ranges")
        print(f"output: {SAMPLES}")
        return
    if args.validate_only:
        validate_samples()
        return
    if not args.sample_only:
        registry = pd.read_csv(REGISTRY)
        cells = station_cells(registry)
        failures = []
        for date in dates:
            final_error: Exception | None = None
            for attempt in range(max(0, args.date_retries) + 1):
                try:
                    retrieve_date(date, cells, workers=max(1, args.workers))
                    final_error = None
                    break
                except Exception as exc:  # retry the exact same cycle; never substitute
                    final_error = exc
                    if attempt < max(0, args.date_retries):
                        print(
                            f"[gfs-blh] {date:%Y-%m-%d}: attempt {attempt + 1} "
                            f"failed ({exc}); retrying exact cycle"
                        )
            if final_error is not None:  # preserve missing-cycle policy and continue
                failures.append({
                    "date": date.strftime("%Y-%m-%d"), "error": repr(final_error)
                })
                print(f"[gfs-blh] {date:%Y-%m-%d}: FAILED: {final_error}")
        _write_json_atomic(FAILURES, reconcile_failures(failures))
    elif FAILURES.exists():
        existing_failures = json.loads(FAILURES.read_text(encoding="utf-8"))
        _write_json_atomic(FAILURES, reconcile_failures(existing_failures))
    samples = assemble()
    validate_samples(samples)


if __name__ == "__main__":
    main()
