"""Safety and provenance tests for CAMS analysis acquisition."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from src.data import cams_composition as cams


def _dataset(variables: set[str]) -> xr.Dataset:
    return xr.Dataset(
        {
            name: (
                ("valid_time", "latitude", "longitude"),
                np.ones((2, 2, 3), dtype=np.float32),
            )
            for name in variables
        },
        coords={
            "valid_time": np.array(
                ["2025-02-19T00:00", "2025-02-19T12:00"],
                dtype="datetime64[m]",
            ),
            "latitude": [30.0, 29.6],
            "longitude": [72.0, 72.4, 72.8],
        },
    )


def _analysis_zip(path: Path, *, omit_surface: str | None = None) -> Path:
    surface_vars = set(cams.SURFACE_OUTPUT_VARS)
    if omit_surface:
        surface_vars.remove(omit_surface)
    surface_path = path.parent / "source_sfc.nc"
    pressure_path = path.parent / "source_plev.nc"
    _dataset(surface_vars).to_netcdf(surface_path, engine="netcdf4")
    _dataset(set(cams.MULTILEVEL_OUTPUT_VARS)).to_netcdf(
        pressure_path, engine="netcdf4"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(surface_path, "data_sfc.nc")
        archive.write(pressure_path, "data_plev.nc")
    return path


def _split_zip(path: Path, role: str) -> Path:
    source = path.parent / f"source_{role}.nc"
    variables = (
        cams.SURFACE_OUTPUT_VARS
        if role == "sfc"
        else cams.MULTILEVEL_OUTPUT_VARS
    )
    _dataset(set(variables)).to_netcdf(source, engine="netcdf4")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(source, f"data_{role}.nc")
    return path


class _FakeClient:
    def __init__(self, source: Path) -> None:
        self.source = source
        self.calls: list[tuple[str, dict, str]] = []

    def retrieve(self, dataset: str, payload: dict, target: str) -> object:
        self.calls.append((dataset, payload, target))
        shutil.copyfile(self.source, target)
        return object()


class _SplitClient:
    def __init__(self, surface: Path, pressure: Path) -> None:
        self.surface = surface
        self.pressure = pressure
        self.calls: list[dict] = []

    def retrieve(self, dataset: str, payload: dict, target: str) -> object:
        self.calls.append(payload)
        source = self.pressure if "pressure_level" in payload else self.surface
        shutil.copyfile(source, target)
        return object()


def test_request_is_exact_and_global() -> None:
    payload = cams.request_payload("2025-02-19")

    assert payload["type"] == "forecast"
    assert payload["leadtime_hour"] == "0"
    assert payload["time"] == ["00:00", "12:00"]
    assert payload["pressure_level"] == cams.PRESSURE_LEVELS
    assert payload["variable"] == cams.SURFACE_VARS + cams.MULTILEVEL_VARS
    assert "area" not in payload


def test_split_retrieval_builds_the_same_verified_archive(tmp_path: Path) -> None:
    surface = _split_zip(tmp_path / "surface.zip", "sfc")
    pressure = _split_zip(tmp_path / "pressure.zip", "plev")
    client = _SplitClient(surface, pressure)

    paths = cams.retrieve_split("2025-02-19", tmp_path / "archive", client=client)
    provenance = json.loads(paths.provenance_path.read_text(encoding="utf-8"))

    assert len(client.calls) == 2
    assert "pressure_level" not in client.calls[0]
    assert client.calls[1]["pressure_level"] == cams.PRESSURE_LEVELS
    assert set(cams._safe_members(paths.zip_path)) == {"data_sfc.nc", "data_plev.nc"}
    assert provenance["status"] == "complete"
    assert provenance["attempts"][-1]["mode"] == "split_surface_pressure"
    assert not list((tmp_path / "archive").glob("*.part"))


def test_finalize_recovered_split_accepts_failed_client_attempt(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    paths = cams.analysis_paths("2025-02-19", archive)
    archive.mkdir()
    paths.request_path.write_text(
        json.dumps(cams.request_document("2025-02-19")), encoding="utf-8"
    )
    provenance = cams._new_provenance("2025-02-19")
    provenance["status"] = "failed"
    provenance["attempts"] = [
        {
            "mode": "split_surface_pressure",
            "status": "failed",
            "error_type": "PermissionError",
        }
    ]
    paths.provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    _split_zip(archive / "2025-02-19_surface.nc.zip.part", "sfc")
    _split_zip(archive / "2025-02-19_pressure.nc.zip.part", "plev")

    result = cams.finalize_recovered_split(
        "2025-02-19",
        archive,
        surface_request_id="surface-job",
        pressure_request_id="pressure-job",
    )
    recorded = json.loads(result.provenance_path.read_text(encoding="utf-8"))

    assert result.zip_path.exists()
    assert recorded["status"] == "complete"
    assert recorded["attempts"][-1]["status"] == "complete"
    assert recorded["attempts"][-1]["subrequests"]["surface"][
        "request_id"
    ] == "surface-job"


@pytest.mark.parametrize("date", ["2025-2-19", "2025-02-30", "init_date"])
def test_request_rejects_invalid_dates(date: str) -> None:
    with pytest.raises(ValueError):
        cams.request_payload(date)


def test_retrieve_is_atomic_hashed_and_reusable(tmp_path: Path) -> None:
    source = _analysis_zip(tmp_path / "provider.zip")
    client = _FakeClient(source)

    paths = cams.retrieve("2025-02-19", tmp_path / "archive", client=client)
    provenance = json.loads(paths.provenance_path.read_text(encoding="utf-8"))

    assert len(client.calls) == 1
    assert paths.zip_path.exists()
    assert not paths.zip_path.with_suffix(".zip.part").exists()
    assert provenance["status"] == "complete"
    assert provenance["raw_file"]["sha256"] == hashlib.sha256(
        paths.zip_path.read_bytes()
    ).hexdigest()

    cams.retrieve("2025-02-19", tmp_path / "archive", client=client)
    assert len(client.calls) == 1


def test_retry_marks_stale_running_attempt_interrupted(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    paths = cams.analysis_paths("2025-02-19", archive)
    paths.zip_path.parent.mkdir(parents=True, exist_ok=True)
    paths.request_path.write_text(
        json.dumps(cams.request_document("2025-02-19")), encoding="utf-8"
    )
    provenance = cams._new_provenance("2025-02-19")
    provenance["status"] = "retrieving"
    provenance["attempts"] = [
        {"started_at": "2026-08-02T00:00:00Z", "status": "running"}
    ]
    paths.provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    source = _analysis_zip(tmp_path / "provider.zip")

    cams.retrieve("2025-02-19", archive, client=_FakeClient(source))
    recorded = json.loads(paths.provenance_path.read_text(encoding="utf-8"))

    assert recorded["attempts"][0]["status"] == "interrupted"
    assert recorded["attempts"][1]["status"] == "complete"


def test_offline_mode_fails_closed_when_input_is_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Offline CAMS analysis is missing"):
        cams.retrieve("2025-02-19", tmp_path, allow_retrieve=False)


def test_unverified_existing_zip_is_not_silently_reused(tmp_path: Path) -> None:
    paths = cams.analysis_paths("2025-02-19", tmp_path)
    paths.zip_path.parent.mkdir(parents=True, exist_ok=True)
    paths.zip_path.write_bytes(b"not a zip")

    with pytest.raises(RuntimeError, match="not a verified complete retrieval"):
        cams.retrieve("2025-02-19", tmp_path, client=object())


def test_extract_validates_variables_and_records_hashes(tmp_path: Path) -> None:
    source = _analysis_zip(tmp_path / "provider.zip")
    paths = cams.retrieve(
        "2025-02-19", tmp_path / "archive", client=_FakeClient(source)
    )

    surface, pressure = cams.extract(paths)
    provenance = json.loads(paths.provenance_path.read_text(encoding="utf-8"))

    assert surface.exists() and pressure.exists()
    assert provenance["extraction"]["surface"]["sha256"] == hashlib.sha256(
        surface.read_bytes()
    ).hexdigest()
    assert set(provenance["extraction"]["surface"]["variables"]) >= (
        cams.SURFACE_OUTPUT_VARS
    )


def test_extract_rejects_missing_aurora_variable(tmp_path: Path) -> None:
    source = _analysis_zip(tmp_path / "provider.zip", omit_surface="pm2p5")
    paths = cams.retrieve(
        "2025-02-19", tmp_path / "archive", client=_FakeClient(source)
    )

    with pytest.raises(RuntimeError, match="missing variables.*pm2p5"):
        cams.extract(paths)


def test_archive_validation_requires_exact_dates(tmp_path: Path) -> None:
    source = _analysis_zip(tmp_path / "provider.zip")
    cams.retrieve("2025-02-19", tmp_path / "archive", client=_FakeClient(source))

    summary = cams.validate_archive(["2025-02-19"], tmp_path / "archive")
    assert summary["dates"] == 1

    deep = cams.validate_archive(
        ["2025-02-19"], tmp_path / "archive", deep=True
    )
    paths = cams.analysis_paths("2025-02-19", tmp_path / "archive")
    assert deep["deep_netcdf_validation"] is True
    assert not paths.sfc_path.exists()
    assert not paths.plev_path.exists()

    with pytest.raises(RuntimeError, match="missing=.*2025-02-20"):
        cams.validate_archive(
            ["2025-02-19", "2025-02-20"], tmp_path / "archive"
        )
