"""Retrieve and validate CAMS analysis inputs for AuroraAirPollution.

Aurora needs two complete global atmospheric states (00 and 12 UTC) for each
initialization date.  CAMS exposes those analyses as zero-hour forecasts in a
``netcdf_zip`` response containing surface and pressure-level NetCDF files.

The downloader is deliberately conservative because a truncated archive must
never be mistaken for a completed GPU input:

* deterministic request JSON is written before retrieval;
* downloads use ``.part`` and become final only after ZIP validation;
* raw ZIP size and SHA-256 are recorded in provenance;
* existing inputs are reused only when request, hash, and ZIP CRC all match;
* extraction is atomic and validates Aurora's required variables;
* offline mode fails closed instead of attempting network access.

Usage::

    python -m src.data.cams_composition --date 2025-02-19
    python -m src.data.cams_composition \
        --dates-file docs/benchmark_dates.csv --confirm-multiple --raw-only
    python -m src.data.cams_composition \
        --dates-file docs/benchmark_dates.csv --validate-only
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

import xarray as xr

ADS_URL = "https://ads.atmosphere.copernicus.eu/api"
DATASET = "cams-global-atmospheric-composition-forecasts"
DATASET_URL = (
    "https://ads.atmosphere.copernicus.eu/datasets/"
    "cams-global-atmospheric-composition-forecasts"
)
DOI = "10.24381/04a0b097"
LICENCE_URL = (
    "https://ads.atmosphere.copernicus.eu/licences/"
    "licence-to-use-copernicus-products"
)
REQUEST_SCHEMA_VERSION = "ads-cams-analysis-v2"

SURFACE_VARS = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_temperature",
    "mean_sea_level_pressure",
    "particulate_matter_1um",
    "particulate_matter_2.5um",
    "particulate_matter_10um",
    "total_column_carbon_monoxide",
    "total_column_nitrogen_monoxide",
    "total_column_nitrogen_dioxide",
    "total_column_ozone",
    "total_column_sulphur_dioxide",
]
MULTILEVEL_VARS = [
    "u_component_of_wind",
    "v_component_of_wind",
    "temperature",
    "geopotential",
    "specific_humidity",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "nitrogen_monoxide",
    "ozone",
    "sulphur_dioxide",
]
PRESSURE_LEVELS = [
    "50",
    "100",
    "150",
    "200",
    "250",
    "300",
    "400",
    "500",
    "600",
    "700",
    "850",
    "925",
    "1000",
]
TIMES = ["00:00", "12:00"]

# Short names produced by the CAMS NetCDF response and consumed by
# aurora_runner.assemble_inputs.
SURFACE_OUTPUT_VARS = {
    "u10",
    "v10",
    "t2m",
    "msl",
    "pm1",
    "pm2p5",
    "pm10",
    "tcco",
    "tc_no",
    "tcno2",
    "gtco3",
    "tcso2",
}
MULTILEVEL_OUTPUT_VARS = {
    "u",
    "v",
    "t",
    "z",
    "q",
    "co",
    "no2",
    "no",
    "go3",
    "so2",
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAMS_ANALYSIS_DIR = PROJECT_ROOT / "data" / "cams_analysis"
DEFAULT_DATES_FILE = PROJECT_ROOT / "docs" / "benchmark_dates.csv"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read valid JSON from {path}.") from exc


def _validate_date(date: str) -> str:
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid analysis date {date!r}; use YYYY-MM-DD.") from exc
    if parsed.strftime("%Y-%m-%d") != date:
        raise ValueError(f"Analysis date must be canonical YYYY-MM-DD: {date!r}.")
    return date


def request_payload(date: str) -> dict[str, Any]:
    """Return the pinned CAMS request consumed by Aurora."""
    return {
        "type": "forecast",
        "leadtime_hour": "0",
        "variable": SURFACE_VARS + MULTILEVEL_VARS,
        "pressure_level": PRESSURE_LEVELS,
        "date": _validate_date(date),
        "time": TIMES,
        "format": "netcdf_zip",
    }


def request_document(date: str) -> dict[str, Any]:
    return {
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "dataset": DATASET,
        "endpoint": ADS_URL,
        "payload": request_payload(date),
    }


def split_request_payload(date: str, role: str) -> dict[str, Any]:
    """Return a smaller surface or pressure-level request for queue fallback."""
    if role not in {"surface", "pressure_level"}:
        raise ValueError(f"Unknown CAMS split-request role: {role!r}")
    payload = {
        "type": "forecast",
        "leadtime_hour": "0",
        "variable": SURFACE_VARS if role == "surface" else MULTILEVEL_VARS,
        "date": _validate_date(date),
        "time": TIMES,
        "format": "netcdf_zip",
    }
    if role == "pressure_level":
        payload["pressure_level"] = PRESSURE_LEVELS
    return payload


@dataclass(frozen=True)
class AnalysisPaths:
    date: str
    zip_path: Path
    sfc_path: Path
    plev_path: Path
    request_path: Path
    provenance_path: Path


def analysis_paths(date: str, output_dir: Path | None = None) -> AnalysisPaths:
    date = _validate_date(date)
    directory = Path(output_dir or CAMS_ANALYSIS_DIR)
    return AnalysisPaths(
        date=date,
        zip_path=directory / f"{date}_cams.nc.zip",
        sfc_path=directory / f"{date}_sfc.nc",
        plev_path=directory / f"{date}_plev.nc",
        request_path=directory / f"{date}_request.json",
        provenance_path=directory / f"{date}_provenance.json",
    )


def _new_provenance(date: str) -> dict[str, Any]:
    return {
        "provenance_schema_version": 1,
        "status": "not_started",
        "source": "Copernicus Atmosphere Monitoring Service (CAMS)",
        "role": "Aurora atmospheric initialization",
        "dataset": DATASET,
        "dataset_url": DATASET_URL,
        "dataset_doi": DOI,
        "licence_url": LICENCE_URL,
        "access_method": "Copernicus ADS via cdsapi",
        "authentication": "user ADS credentials; credentials are never recorded",
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "request": request_payload(date),
        "date": date,
        "times_utc": TIMES,
        "attempts": [],
    }


def _read_or_new_provenance(path: Path, date: str) -> dict[str, Any]:
    if not path.exists():
        return _new_provenance(date)
    provenance = _load_json(path)
    if provenance.get("request") != request_payload(date):
        raise RuntimeError(f"Existing provenance request differs: {path}")
    provenance.setdefault("attempts", [])
    return provenance


def _safe_members(zip_path: Path) -> tuple[str, str]:
    """Validate CRC/path safety and return the surface/pressure member names."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            if not names:
                raise RuntimeError(f"CAMS archive is empty: {zip_path}")
            for name in names:
                member = PurePosixPath(name)
                if member.is_absolute() or ".." in member.parts:
                    raise RuntimeError(f"Unsafe member {name!r} in {zip_path}")
            bad = archive.testzip()
            if bad is not None:
                raise RuntimeError(f"ZIP CRC failure in member {bad!r}: {zip_path}")
            surface = [name for name in names if "sfc" in name.casefold()]
            pressure = [name for name in names if "plev" in name.casefold()]
            if len(surface) != 1 or len(pressure) != 1:
                raise RuntimeError(
                    f"Expected one sfc and one plev member in {zip_path}; found {names}."
                )
            if archive.getinfo(surface[0]).file_size <= 0:
                raise RuntimeError(f"Surface member is empty in {zip_path}.")
            if archive.getinfo(pressure[0]).file_size <= 0:
                raise RuntimeError(f"Pressure-level member is empty in {zip_path}.")
            return surface[0], pressure[0]
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"Invalid CAMS ZIP archive: {zip_path}") from exc


def _safe_single_member(zip_path: Path, token: str) -> str:
    """Validate a split provider ZIP and return its one expected member."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            for name in names:
                member = PurePosixPath(name)
                if member.is_absolute() or ".." in member.parts:
                    raise RuntimeError(f"Unsafe member {name!r} in {zip_path}")
            bad = archive.testzip()
            if bad is not None:
                raise RuntimeError(f"ZIP CRC failure in member {bad!r}: {zip_path}")
            matches = [name for name in names if token in name.casefold()]
            if len(matches) != 1 or archive.getinfo(matches[0]).file_size <= 0:
                raise RuntimeError(
                    f"Expected one non-empty {token} member in {zip_path}; found {names}."
                )
            return matches[0]
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"Invalid CAMS split ZIP archive: {zip_path}") from exc


def _combine_split_archives(surface_zip: Path, pressure_zip: Path, target: Path) -> None:
    """Build the canonical two-member archive without loading NetCDFs in RAM."""
    surface_member = _safe_single_member(surface_zip, "sfc")
    pressure_member = _safe_single_member(pressure_zip, "plev")
    target.unlink(missing_ok=True)
    try:
        with (
            zipfile.ZipFile(surface_zip) as surface_archive,
            zipfile.ZipFile(pressure_zip) as pressure_archive,
            zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as combined,
        ):
            for source_archive, member in (
                (surface_archive, surface_member),
                (pressure_archive, pressure_member),
            ):
                with source_archive.open(member) as source, combined.open(
                    PurePosixPath(member).name, "w"
                ) as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        _safe_members(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _verified_existing(paths: AnalysisPaths, provenance: Mapping[str, Any]) -> bool:
    if not paths.zip_path.is_file() or paths.zip_path.stat().st_size == 0:
        return False
    raw = provenance.get("raw_file", {})
    if provenance.get("status") != "complete":
        return False
    if raw.get("sha256") != _sha256(paths.zip_path):
        return False
    _safe_members(paths.zip_path)
    return True


def retrieve(
    date: str,
    output_dir: Path | None = None,
    *,
    client: Any | None = None,
    allow_retrieve: bool = True,
    now: Callable[[], datetime] = _utc_now,
) -> AnalysisPaths:
    """Retrieve one raw CAMS analysis archive with atomic provenance."""
    paths = analysis_paths(date, output_dir)
    paths.zip_path.parent.mkdir(parents=True, exist_ok=True)
    document = request_document(date)
    if paths.request_path.exists():
        if _load_json(paths.request_path) != document:
            raise RuntimeError(f"Existing request differs: {paths.request_path}")
    else:
        _atomic_json(paths.request_path, document)

    provenance = _read_or_new_provenance(paths.provenance_path, date)
    if _verified_existing(paths, provenance):
        return paths
    if paths.zip_path.exists():
        raise RuntimeError(
            f"Existing CAMS archive is not a verified complete retrieval: {paths.zip_path}. "
            "Preserve and investigate it; it will not be overwritten."
        )
    if not allow_retrieve:
        raise FileNotFoundError(
            f"Offline CAMS analysis is missing for {date}: {paths.zip_path}"
        )

    if client is None:
        import cdsapi

        client = cdsapi.Client(url=ADS_URL)

    started = now()
    # Reaching a new attempt with no verified raw file means any prior
    # ``running`` attempt was interrupted (process exit, reboot, or operator
    # cancellation). Preserve that fact rather than leaving stale "running"
    # provenance forever.
    if provenance.get("status") == "retrieving" and provenance["attempts"]:
        prior = provenance["attempts"][-1]
        if prior.get("status") == "running":
            prior.update(
                status="interrupted",
                completed_at=_iso_utc(started),
                error_type="InterruptedAttempt",
                error="A later retrieval attempt resumed without a completed raw file.",
            )
    attempt: dict[str, Any] = {
        "started_at": _iso_utc(started),
        "status": "running",
    }
    provenance["status"] = "retrieving"
    provenance["attempts"].append(attempt)
    _atomic_json(paths.provenance_path, provenance)

    partial = paths.zip_path.with_suffix(paths.zip_path.suffix + ".part")
    if partial.exists():
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        preserved = partial.with_name(f"{partial.name}.{stamp}")
        os.replace(partial, preserved)
        attempt["preserved_prior_partial"] = {
            "path": preserved.name,
            "bytes": preserved.stat().st_size,
            "sha256": _sha256(preserved),
        }
        _atomic_json(paths.provenance_path, provenance)

    try:
        result = client.retrieve(DATASET, request_payload(date), str(partial))
        if not partial.is_file() or partial.stat().st_size == 0:
            raise RuntimeError("ADS returned without a non-empty analysis ZIP.")
        _safe_members(partial)
        os.replace(partial, paths.zip_path)
        completed = now()
        attempt.update(
            status="complete",
            completed_at=_iso_utc(completed),
            elapsed_seconds=max(0.0, (completed - started).total_seconds()),
        )
        reply = getattr(result, "reply", None)
        if isinstance(reply, Mapping):
            attempt["provider"] = {
                key: reply[key]
                for key in ("request_id", "state", "content_length", "content_type")
                if key in reply and isinstance(reply[key], (str, int, float, bool))
            }
        provenance.update(
            status="complete",
            retrieved_at=_iso_utc(completed),
            raw_file={
                "path": paths.zip_path.name,
                "bytes": paths.zip_path.stat().st_size,
                "sha256": _sha256(paths.zip_path),
            },
        )
        _atomic_json(paths.provenance_path, provenance)
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
        _atomic_json(paths.provenance_path, provenance)
        raise


def retrieve_split(
    date: str,
    output_dir: Path | None = None,
    *,
    client: Any | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> AnalysisPaths:
    """Retrieve one date as two smaller requests, then make the canonical ZIP."""
    paths = analysis_paths(date, output_dir)
    paths.zip_path.parent.mkdir(parents=True, exist_ok=True)
    document = request_document(date)
    if paths.request_path.exists() and _load_json(paths.request_path) != document:
        raise RuntimeError(f"Existing request differs: {paths.request_path}")
    if not paths.request_path.exists():
        _atomic_json(paths.request_path, document)

    provenance = _read_or_new_provenance(paths.provenance_path, date)
    if _verified_existing(paths, provenance):
        return paths
    if paths.zip_path.exists():
        raise RuntimeError(
            f"Existing CAMS archive is not a verified complete retrieval: {paths.zip_path}."
        )
    if client is None:
        import cdsapi

        client = cdsapi.Client(url=ADS_URL)

    started = now()
    if provenance.get("status") == "retrieving" and provenance["attempts"]:
        prior = provenance["attempts"][-1]
        if prior.get("status") == "running":
            prior.update(
                status="interrupted",
                completed_at=_iso_utc(started),
                error_type="InterruptedAttempt",
                error="Split fallback replaced a stalled combined retrieval.",
            )
    attempt: dict[str, Any] = {
        "started_at": _iso_utc(started),
        "status": "running",
        "mode": "split_surface_pressure",
        "subrequests": {},
    }
    provenance["status"] = "retrieving"
    provenance["attempts"].append(attempt)
    _atomic_json(paths.provenance_path, provenance)

    surface_zip = paths.zip_path.with_name(f"{date}_surface.nc.zip.part")
    pressure_zip = paths.zip_path.with_name(f"{date}_pressure.nc.zip.part")
    combined = paths.zip_path.with_suffix(paths.zip_path.suffix + ".part")
    try:
        for role, target, token in (
            ("surface", surface_zip, "sfc"),
            ("pressure_level", pressure_zip, "plev"),
        ):
            target.unlink(missing_ok=True)
            result = client.retrieve(DATASET, split_request_payload(date, role), str(target))
            member = _safe_single_member(target, token)
            reply = getattr(result, "reply", None)
            attempt["subrequests"][role] = {
                "path": target.name,
                "bytes": target.stat().st_size,
                "sha256": _sha256(target),
                "member": member,
            }
            if isinstance(reply, Mapping):
                attempt["subrequests"][role]["provider"] = {
                    key: reply[key]
                    for key in ("request_id", "state", "content_length", "content_type")
                    if key in reply and isinstance(reply[key], (str, int, float, bool))
                }
            _atomic_json(paths.provenance_path, provenance)

        _combine_split_archives(surface_zip, pressure_zip, combined)
        os.replace(combined, paths.zip_path)
        completed = now()
        attempt.update(
            status="complete",
            completed_at=_iso_utc(completed),
            elapsed_seconds=max(0.0, (completed - started).total_seconds()),
        )
        provenance.update(
            status="complete",
            retrieved_at=_iso_utc(completed),
            raw_file={
                "path": paths.zip_path.name,
                "bytes": paths.zip_path.stat().st_size,
                "sha256": _sha256(paths.zip_path),
            },
        )
        _atomic_json(paths.provenance_path, provenance)
        return paths
    except Exception as exc:
        failed = now()
        attempt.update(
            status="failed",
            completed_at=_iso_utc(failed),
            elapsed_seconds=max(0.0, (failed - started).total_seconds()),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        provenance["status"] = "failed"
        _atomic_json(paths.provenance_path, provenance)
        raise
    finally:
        if provenance.get("status") == "complete":
            surface_zip.unlink(missing_ok=True)
            pressure_zip.unlink(missing_ok=True)
            combined.unlink(missing_ok=True)


def finalize_recovered_split(
    date: str,
    output_dir: Path | None = None,
    *,
    surface_request_id: str,
    pressure_request_id: str,
    now: Callable[[], datetime] = _utc_now,
) -> AnalysisPaths:
    """Finalize split results recovered from persistent provider-side jobs."""
    paths = analysis_paths(date, output_dir)
    provenance = _read_or_new_provenance(paths.provenance_path, date)
    if _verified_existing(paths, provenance):
        return paths

    surface_zip = paths.zip_path.with_name(f"{date}_surface.nc.zip.part")
    pressure_zip = paths.zip_path.with_name(f"{date}_pressure.nc.zip.part")
    for role, source, token in (
        ("surface", surface_zip, "sfc"),
        ("pressure_level", pressure_zip, "plev"),
    ):
        if not source.is_file():
            raise FileNotFoundError(f"Recovered {role} archive is missing: {source}")
        _safe_single_member(source, token)

    if not provenance.get("attempts") or provenance["attempts"][-1].get(
        "status"
    ) not in {"running", "failed"}:
        raise RuntimeError("No recoverable split attempt exists to finalize.")
    attempt = provenance["attempts"][-1]
    if attempt.get("mode") != "split_surface_pressure":
        raise RuntimeError("The running attempt is not a split retrieval.")

    combined = paths.zip_path.with_suffix(paths.zip_path.suffix + ".part")
    _combine_split_archives(surface_zip, pressure_zip, combined)
    os.replace(combined, paths.zip_path)
    completed = now()
    attempt.update(
        status="complete",
        completed_at=_iso_utc(completed),
        recovery="provider jobs outlived the original client process",
        subrequests={
            "surface": {
                "request_id": surface_request_id,
                "bytes": surface_zip.stat().st_size,
                "sha256": _sha256(surface_zip),
            },
            "pressure_level": {
                "request_id": pressure_request_id,
                "bytes": pressure_zip.stat().st_size,
                "sha256": _sha256(pressure_zip),
            },
        },
    )
    provenance.update(
        status="complete",
        retrieved_at=_iso_utc(completed),
        raw_file={
            "path": paths.zip_path.name,
            "bytes": paths.zip_path.stat().st_size,
            "sha256": _sha256(paths.zip_path),
        },
    )
    _atomic_json(paths.provenance_path, provenance)
    surface_zip.unlink()
    pressure_zip.unlink()
    return paths


def _extract_member(archive: zipfile.ZipFile, member: str, target: Path) -> None:
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with archive.open(member) as source, temporary.open("wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
        if temporary.stat().st_size == 0:
            raise RuntimeError(f"Extracted CAMS member {member!r} is empty.")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_netcdf(path: Path, required: set[str], role: str) -> dict[str, Any]:
    try:
        dataset = xr.open_dataset(path, engine="netcdf4", decode_timedelta=True)
    except Exception as exc:
        raise RuntimeError(f"Cannot open CAMS {role} NetCDF: {path}") from exc
    try:
        missing = sorted(required - set(dataset.data_vars))
        if missing:
            raise RuntimeError(f"CAMS {role} NetCDF is missing variables: {missing}")
        for coordinate in ("latitude", "longitude"):
            if coordinate not in dataset.coords or dataset[coordinate].size == 0:
                raise RuntimeError(f"CAMS {role} NetCDF lacks {coordinate} coordinates.")
        return {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "variables": sorted(dataset.data_vars),
            "dimensions": {name: int(size) for name, size in dataset.sizes.items()},
        }
    finally:
        dataset.close()


def extract(paths: AnalysisPaths) -> tuple[Path, Path]:
    """Atomically extract and validate Aurora's two NetCDF inputs."""
    provenance = _read_or_new_provenance(paths.provenance_path, paths.date)
    if not _verified_existing(paths, provenance):
        raise RuntimeError(f"Raw CAMS analysis is not verified: {paths.zip_path}")

    surface_member, pressure_member = _safe_members(paths.zip_path)
    with zipfile.ZipFile(paths.zip_path) as archive:
        _extract_member(archive, surface_member, paths.sfc_path)
        _extract_member(archive, pressure_member, paths.plev_path)

    surface = _validate_netcdf(paths.sfc_path, SURFACE_OUTPUT_VARS, "surface")
    pressure = _validate_netcdf(
        paths.plev_path, MULTILEVEL_OUTPUT_VARS, "pressure-level"
    )
    provenance["extraction"] = {
        "validated_at": _iso_utc(_utc_now()),
        "surface": surface,
        "pressure_level": pressure,
    }
    _atomic_json(paths.provenance_path, provenance)
    return paths.sfc_path, paths.plev_path


def download(
    date: str,
    output_dir: Path | None = None,
    *,
    allow_retrieve: bool = True,
) -> tuple[Path, Path]:
    """Return validated surface/pressure inputs, retrieving only when allowed."""
    paths = retrieve(date, output_dir, allow_retrieve=allow_retrieve)
    return extract(paths)


def load_dates_file(path: Path) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    if not lines:
        raise ValueError(f"Date file is empty: {path}")
    if "," in lines[0] or lines[0].strip() == "init_date":
        reader = csv.DictReader(lines)
        if reader.fieldnames is None or "init_date" not in reader.fieldnames:
            raise ValueError(f"CSV date file must contain init_date: {path}")
        dates = [row["init_date"].strip() for row in reader if row.get("init_date")]
    else:
        dates = [line.strip() for line in lines if line.strip()]
    result = [_validate_date(date) for date in dates]
    if not result or len(result) != len(set(result)):
        raise ValueError(f"Date file is empty or contains duplicates: {path}")
    return result


def validate_archive(
    dates: Sequence[str],
    output_dir: Path | None = None,
    *,
    deep: bool = False,
) -> dict[str, Any]:
    """Validate exact requested coverage, requests, hashes, and ZIP contents."""
    directory = Path(output_dir or CAMS_ANALYSIS_DIR)
    expected = {_validate_date(date) for date in dates}
    actual = {path.name[:10] for path in directory.glob("*_cams.nc.zip")}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise RuntimeError(
            f"CAMS analysis archive mismatch: missing={missing}, extra={extra}"
        )
    total_bytes = 0
    for date in sorted(expected):
        paths = retrieve(date, directory, allow_retrieve=False)
        total_bytes += paths.zip_path.stat().st_size
        if deep:
            try:
                extract(paths)
            finally:
                # The immutable ZIP is the portable source artifact. Extracted
                # NetCDFs are deterministic and would double local storage.
                paths.sfc_path.unlink(missing_ok=True)
                paths.plev_path.unlink(missing_ok=True)
    return {
        "dates": len(expected),
        "raw_zip_bytes": total_bytes,
        "raw_zip_gib": round(total_bytes / (1024**3), 3),
        "deep_netcdf_validation": deep,
        "missing": missing,
        "extra": extra,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve validated CAMS analysis inputs for Aurora."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--date")
    source.add_argument("--dates-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=CAMS_ANALYSIS_DIR)
    parser.add_argument("--confirm-multiple", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Concurrent provider requests for multi-date acquisition (1-4).",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Retain the validated raw ZIP without extracted NetCDF files.",
    )
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--split-request",
        action="store_true",
        help="Retrieve one date as separate surface and pressure-level requests.",
    )
    parser.add_argument(
        "--deep-validate",
        action="store_true",
        help="Extract every archive, validate Aurora variables, then remove duplicates.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    dates = [args.date] if args.date else load_dates_file(args.dates_file)
    dates = [_validate_date(date) for date in dates]
    if len(dates) > 1 and not (
        args.confirm_multiple or args.validate_only or args.dry_run
    ):
        raise SystemExit(
            f"{len(dates)} CAMS analysis requests selected. Review with --dry-run, "
            "then pass --confirm-multiple."
        )
    if not 1 <= args.workers <= 4:
        raise SystemExit("--workers must be between 1 and 4.")
    if args.split_request and len(dates) != 1:
        raise SystemExit("--split-request requires exactly one --date.")
    if args.dry_run:
        print(json.dumps([request_document(date) for date in dates], indent=2))
        return
    if args.validate_only:
        print(
            json.dumps(
                validate_archive(dates, args.output_dir, deep=args.deep_validate),
                indent=2,
            )
        )
        return

    def acquire(date: str) -> tuple[str, int]:
        print(f"[cams-analysis] starting {date}", flush=True)
        paths = (
            retrieve_split(date, args.output_dir)
            if args.split_request
            else retrieve(date, args.output_dir)
        )
        if not args.raw_only:
            extract(paths)
        return date, paths.zip_path.stat().st_size

    failures: list[tuple[str, BaseException]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(acquire, date): date for date in dates}
        completed = 0
        for future in as_completed(futures):
            date = futures[future]
            try:
                _, size = future.result()
                completed += 1
                print(
                    f"[cams-analysis] complete {completed}/{len(dates)} {date}: "
                    f"{size / (1024**2):.1f} MiB",
                    flush=True,
                )
            except BaseException as exc:
                failures.append((date, exc))
                print(
                    f"[cams-analysis] FAILED {date}: {type(exc).__name__}: {exc}",
                    flush=True,
                )
    if failures:
        names = ", ".join(date for date, _ in failures)
        raise SystemExit(f"{len(failures)} CAMS analysis date(s) failed: {names}")


if __name__ == "__main__":
    main()
