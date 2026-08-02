"""Build four exact, credential-free CAMS input bundles for GPU workers."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from src.data import cams_composition, cams_forecast


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "gpu_inputs"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def partition_dates(dates: Sequence[str], workers: int) -> list[list[str]]:
    """Split dates into deterministic, balanced contiguous worker slices."""
    if workers < 1:
        raise ValueError("workers must be positive")
    if workers > len(dates):
        raise ValueError("workers cannot exceed the number of dates")
    quotient, remainder = divmod(len(dates), workers)
    result: list[list[str]] = []
    start = 0
    for index in range(workers):
        size = quotient + (1 if index < remainder else 0)
        result.append(list(dates[start : start + size]))
        start += size
    return result


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def _required_files(date: str) -> list[Path]:
    analysis = cams_composition.analysis_paths(date)
    forecast = cams_forecast.forecast_paths(cams_forecast.ForecastRequest(date))
    return [
        analysis.zip_path,
        analysis.request_path,
        analysis.provenance_path,
        forecast.raw_grib,
        forecast.request_json,
        forecast.provenance_json,
        forecast.station_samples_csv,
    ]


def build_bundles(
    dates: Sequence[str],
    output_dir: Path,
    *,
    workers: int = 4,
) -> list[Path]:
    """Validate inputs and build one uncompressed TAR per worker."""
    dates = list(dates)
    cams_composition.validate_archive(dates, deep=True)
    # The forecast validator checks exact frozen support and all retained hashes.
    from scripts.validate_cams_download import validate_archive as validate_forecast

    forecast_summary = validate_forecast(
        cams_forecast.DEFAULT_DATES_FILE, cams_forecast.DEFAULT_OUTPUT_DIR
    )
    if int(forecast_summary["dates"]) != len(dates):
        raise RuntimeError("CAMS forecast and analysis schedules differ.")

    output_dir.mkdir(parents=True, exist_ok=True)
    bundles: list[Path] = []
    commit = _git_commit()
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for index, worker_dates in enumerate(partition_dates(dates, workers)):
        bundle = output_dir / f"worker_{index:02d}_cams_inputs.tar"
        temporary = bundle.with_suffix(bundle.suffix + ".part")
        temporary.unlink(missing_ok=True)
        file_records: list[dict[str, str | int]] = []
        with tarfile.open(temporary, "w") as archive:
            slice_payload = ("\n".join(worker_dates) + "\n").encode("utf-8")
            _add_bytes(archive, f"slice_{index:02d}", slice_payload)
            for date in worker_dates:
                for path in _required_files(date):
                    if not path.is_file() or path.stat().st_size == 0:
                        raise FileNotFoundError(f"Missing GPU input: {path}")
                    relative = path.relative_to(PROJECT_ROOT).as_posix()
                    digest = _sha256(path)
                    archive.add(path, arcname=relative, recursive=False)
                    file_records.append(
                        {
                            "path": relative,
                            "bytes": path.stat().st_size,
                            "sha256": digest,
                        }
                    )
            manifest = {
                "schema_version": 1,
                "worker": index,
                "dates": worker_dates,
                "generated_at": generated_at,
                "source_commit": commit,
                "offline_required": True,
                "files": file_records,
            }
            _add_bytes(
                archive,
                "gpu_input_manifest.json",
                (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(
                    "utf-8"
                ),
            )
        os.replace(temporary, bundle)
        digest_path = bundle.with_suffix(bundle.suffix + ".sha256")
        digest_path.write_text(
            f"{_sha256(bundle)}  {bundle.name}\n", encoding="utf-8"
        )
        bundles.append(bundle)
    return bundles


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build exact offline CAMS bundles for GPU workers."
    )
    parser.add_argument(
        "--dates-file", type=Path, default=cams_composition.DEFAULT_DATES_FILE
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    dates = cams_composition.load_dates_file(args.dates_file)
    bundles = build_bundles(dates, args.output_dir, workers=args.workers)
    for bundle in bundles:
        print(
            f"{bundle}  {bundle.stat().st_size / (1024**3):.3f} GiB  "
            f"sha256={_sha256(bundle)}"
        )


if __name__ == "__main__":
    main()
