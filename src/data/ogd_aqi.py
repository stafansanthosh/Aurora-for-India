r"""Tiny, provenance-first pilot for the official OGD India CPCB live feed.

This module deliberately supports only the Patna/Varanasi PM2.5 pilot defined
in ``docs/DATA_SOURCE_AUDIT.md``.  It does not scrape the CPCB dashboard, fetch
bulk history, alter the frozen OpenAQ benchmark, or claim that this delivery
route is independent truth.  It is a candidate live observation backup and
latency/completeness diagnostic that probably overlaps OpenAQ upstream.

The resource UUID below is the identifier exposed by the official resource
page's Data API control:

    https://www.data.gov.in/resource/
        real-time-air-quality-index-various-locations

Set up an API key through data.gov.in, then run one tiny (maximum ten-row)
probe from PowerShell:

    $env:DATA_GOV_IN_API_KEY = "<your data.gov.in API key>"
    .venv\Scripts\python.exe -m src.data.ogd_aqi `
      --output-dir "$env:TEMP\indiaaqbench-private\ogd-aqi"

The output directory intentionally defaults outside the repository.  Re-run at
the same local time on three days before deciding whether this source is useful.
Never commit a credential or an unreviewed raw snapshot.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen


RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
API_ENDPOINT = f"https://api.data.gov.in/resource/{RESOURCE_ID}"
RESOURCE_PAGE = (
    "https://www.data.gov.in/resource/"
    "real-time-air-quality-index-various-locations"
)
CATALOG_PAGE = "https://www.data.gov.in/catalog/real-time-air-quality-index"
GODL_PAGE = "https://up.data.gov.in/godl"
PRODUCT_NAME = "Real time Air Quality Index from various locations"
SOURCE_NAME = "OGD India / CPCB current AQI feed"
PILOT_CITIES = ("Patna", "Varanasi")
POLLUTANT = "PM2.5"
PILOT_LIMIT_PER_CITY = 5
VALUE_MIN_UGM3 = 0.0
VALUE_MAX_UGM3 = 1000.0
REQUEST_TIMEOUT_SECONDS = 30
PARSER_SCHEMA_VERSION = "ogd-aqi-pilot-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "stations.csv"

# The official resource says field-instrument data are displayed live without
# human intervention and may include abnormal values.  Keep those values and
# flag them; do not turn a high-pollution event into a silent deletion.
ROLE = (
    "candidate_live_ground_observation_backup_and_latency_diagnostic;"
    "not_verified_independent_truth"
)
ATTRIBUTION = (
    "Source: Ministry of Environment, Forest and Climate Change / "
    "Central Pollution Control Board, via the Open Government Data Platform "
    "India. Data may contain abnormal or erroneous live instrument values."
)

DEFAULT_OUTPUT_DIR = (
    Path(tempfile.gettempdir()) / "indiaaqbench-private" / "ogd-aqi"
)

HttpGet = Callable[..., Any]
Clock = Callable[[], datetime]


class _UrlResponse:
    """Small response adapter matching the injectable test-client contract."""

    def __init__(
        self,
        content: bytes,
        headers: Mapping[str, Any],
        status_code: int,
    ) -> None:
        self.content = content
        self.headers = headers
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(
                API_ENDPOINT,
                self.status_code,
                "OGD request failed",
                None,
                None,
            )


def _official_get(
    url: str,
    *,
    params: Mapping[str, Any],
    timeout: int,
) -> _UrlResponse:
    """Issue a plain GET to the documented OGD endpoint."""
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "IndiaAQBench/1"},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        return _UrlResponse(
            content=response.read(),
            headers=dict(response.headers.items()),
            status_code=int(response.status),
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("retrieval clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_city(city: str) -> str:
    """Return the canonical pilot city or reject scope expansion."""
    matches = [name for name in PILOT_CITIES if name.casefold() == city.strip().casefold()]
    if not matches:
        raise ValueError(
            f"City {city!r} is outside this tiny pilot; choose one of "
            f"{', '.join(PILOT_CITIES)}"
        )
    return matches[0]


def request_params(city: str, api_key: str, limit: int = PILOT_LIMIT_PER_CITY) -> dict[str, Any]:
    """Build the exact official Data API parameters for one tiny city probe."""
    canonical = canonical_city(city)
    if not api_key:
        raise ValueError("A non-empty data.gov.in API key is required")
    if not 1 <= limit <= PILOT_LIMIT_PER_CITY:
        raise ValueError(f"limit must be between 1 and {PILOT_LIMIT_PER_CITY}")
    return {
        "api-key": api_key,
        "format": "json",
        "offset": 0,
        "limit": limit,
        "filters[city]": canonical,
        "filters[pollutant_id]": POLLUTANT,
    }


def request_url_template(city: str, limit: int = PILOT_LIMIT_PER_CITY) -> str:
    """Return a publishable request template containing no credential."""
    params = request_params(city, "${DATA_GOV_IN_API_KEY}", limit)
    encoded = urlencode(params)
    # Keep the documented environment-variable placeholder human-readable.
    encoded = encoded.replace(
        "%24%7BDATA_GOV_IN_API_KEY%7D", "${DATA_GOV_IN_API_KEY}"
    )
    return f"{API_ENDPOINT}?{encoded}"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _repository_commit() -> str:
    """Return the checked-out commit when Git is available."""
    supplied = os.getenv("GIT_COMMIT", "").strip()
    if supplied:
        return supplied
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unrecorded"
    commit = completed.stdout.strip()
    if completed.returncode == 0 and len(commit) == 40:
        return commit
    return "unrecorded"


def _stable_record_hash(record: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in {"", "na", "n/a", "none", "null", "-"}


def _is_pm25_mass_unit(value: Any) -> bool:
    if _is_missing(value):
        return False
    token = str(value).strip().casefold()
    token = token.replace("μ", "u").replace("µ", "u").replace("³", "3")
    token = token.replace(" ", "").replace("^", "")
    return token in {"ug/m3", "ugm-3", "ugm3"}


def _pollutant_token(value: Any) -> str:
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def _explicit_timestamp_utc(value: Any) -> str | None:
    """Parse only timestamps that carry an explicit UTC offset.

    The OGD ``last_update`` field is commonly a naive local-looking string.
    The official resource text reviewed for this pilot does not define that
    timezone, so this module preserves it but refuses to guess an instant.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return _iso_utc(parsed)


def _source_timestamp_order(value: Any) -> datetime | None:
    """Parse a source timestamp for ordering only, without assigning a zone."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    candidates = (text[:-1] + "+00:00") if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(candidates).replace(tzinfo=None)
    except ValueError:
        pass
    for pattern in (
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _duplicate_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("city") or "").strip().casefold(),
        str(row.get("station") or "").strip().casefold(),
        _pollutant_token(row.get("pollutant_id")),
        str(row.get("observed_at_source") or "").strip(),
    )


def validate_records(
    records: Sequence[Mapping[str, Any]],
    requested_city: str,
    retrieved_at_utc: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter to the pilot contract and annotate, rather than hide, QC issues.

    Raw source records are embedded unchanged in every retained row.  A record
    outside the requested city or pollutant is excluded and counted.  Missing,
    duplicated, out-of-range, unit-ambiguous and coordinate-invalid records are
    retained with explicit validation flags.
    """
    city = canonical_city(requested_city)
    retained: list[dict[str, Any]] = []
    excluded = Counter()

    for source_record in records:
        raw = dict(source_record)
        if str(raw.get("city") or "").strip().casefold() != city.casefold():
            excluded["different_city"] += 1
            continue
        if _pollutant_token(raw.get("pollutant_id")) != "PM25":
            excluded["different_pollutant"] += 1
            continue

        value = _number(raw.get("pollutant_avg"))
        latitude = _number(raw.get("latitude"))
        longitude = _number(raw.get("longitude"))
        observed_source = raw.get("last_update")
        observed_utc = _explicit_timestamp_utc(observed_source)
        unit = raw.get("pollutant_unit")

        flags: list[str] = []
        if _is_missing(raw.get("station")):
            flags.append("station_missing")
        if value is None:
            flags.append("value_missing_or_non_numeric")
        elif not VALUE_MIN_UGM3 <= value <= VALUE_MAX_UGM3:
            flags.append("value_out_of_project_range")
        if latitude is None or longitude is None:
            flags.append("coordinates_missing_or_non_numeric")
        elif not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            flags.append("coordinates_out_of_range")
        if _is_missing(unit):
            flags.append("unit_missing")
        elif not _is_pm25_mass_unit(unit):
            flags.append("unit_not_recognized_as_pm25_mass_concentration")
        if _is_missing(observed_source):
            flags.append("observed_timestamp_missing")
        elif observed_utc is None:
            flags.append("observed_timestamp_timezone_not_explicit")

        retained.append(
            {
                "city": city,
                "station": raw.get("station"),
                "pollutant_id": raw.get("pollutant_id"),
                "value": value,
                "unit": unit,
                "latitude": latitude,
                "longitude": longitude,
                "observed_at_source": observed_source,
                "observed_at_utc": observed_utc,
                "retrieved_at_utc": retrieved_at_utc,
                "resource_id": RESOURCE_ID,
                "raw_record_sha256": _stable_record_hash(raw),
                "validation_flags": flags,
                "raw": raw,
            }
        )

    duplicate_counts = Counter(_duplicate_key(row) for row in retained)
    for row in retained:
        if duplicate_counts[_duplicate_key(row)] > 1:
            row["validation_flags"].append("duplicate_station_pollutant_time")

    flag_counts = Counter(
        flag for row in retained for flag in row["validation_flags"]
    )
    ordered_source_times = sorted(
        (
            (parsed, str(row["observed_at_source"]))
            for row in retained
            if (parsed := _source_timestamp_order(row["observed_at_source"]))
            is not None
        ),
        key=lambda pair: pair[0],
    )
    report = {
        "rows_received": len(records),
        "rows_retained": len(retained),
        "rows_excluded": sum(excluded.values()),
        "excluded_by_reason": dict(sorted(excluded.items())),
        "validation_flag_counts": dict(sorted(flag_counts.items())),
        "duplicate_rows": flag_counts["duplicate_station_pollutant_time"],
        "units_encountered": sorted(
            {
                str(row["unit"])
                for row in retained
                if not _is_missing(row["unit"])
            }
        ),
        "latest_observed_at_source": (
            ordered_source_times[-1][1] if ordered_source_times else None
        ),
    }
    return retained, report


def load_pilot_registry(path: Path = DEFAULT_REGISTRY_PATH) -> list[dict[str, Any]]:
    """Read only the two pilot-city rows from the frozen station registry."""
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"station_id", "city", "station_name", "lat", "lon"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"Station registry {path} lacks required columns {sorted(required)}"
            )
        rows = []
        for raw in reader:
            city = str(raw.get("city") or "").strip().casefold()
            if city not in {name.casefold() for name in PILOT_CITIES}:
                continue
            rows.append(
                {
                    "station_id": raw["station_id"],
                    "city": canonical_city(city),
                    "station_name": raw["station_name"],
                    "latitude": _number(raw["lat"]),
                    "longitude": _number(raw["lon"]),
                }
            )
    return rows


def _name_token(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(haversine)))


def attach_registry_matches(
    rows: Sequence[dict[str, Any]],
    registry: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Attach only exact-name/coordinate or unique-coordinate candidates.

    No fuzzy name-only match is produced.  Ambiguous candidates remain
    unresolved for manual review.
    """
    status_counts = Counter()
    for row in rows:
        city_registry = [
            candidate
            for candidate in registry
            if str(candidate.get("city") or "").casefold()
            == str(row.get("city") or "").casefold()
        ]
        latitude = _number(row.get("latitude"))
        longitude = _number(row.get("longitude"))
        distances: list[tuple[float, Mapping[str, Any]]] = []
        if latitude is not None and longitude is not None:
            for candidate in city_registry:
                candidate_lat = _number(candidate.get("latitude"))
                candidate_lon = _number(candidate.get("longitude"))
                if candidate_lat is None or candidate_lon is None:
                    continue
                distances.append(
                    (
                        _distance_km(
                            latitude,
                            longitude,
                            candidate_lat,
                            candidate_lon,
                        ),
                        candidate,
                    )
                )

        exact_name = [
            (distance, candidate)
            for distance, candidate in distances
            if _name_token(candidate.get("station_name"))
            == _name_token(row.get("station"))
            and distance <= 2.0
        ]
        coordinate_only = [
            (distance, candidate)
            for distance, candidate in distances
            if distance <= 0.25
        ]
        if len(exact_name) == 1:
            distance, match = exact_name[0]
            status = "exact_name_and_near_coordinates"
        elif len(coordinate_only) == 1:
            distance, match = coordinate_only[0]
            status = "unique_coordinates_within_250m"
        elif len(exact_name) > 1 or len(coordinate_only) > 1:
            distance, match = min(
                exact_name or coordinate_only, key=lambda pair: pair[0]
            )
            status = "ambiguous_manual_review_required"
        else:
            distance, match = (None, None)
            status = "no_high_confidence_match"

        row["registry_match"] = {
            "status": status,
            "registry_station_id": (
                match.get("station_id") if match is not None else None
            ),
            "registry_station_name": (
                match.get("station_name") if match is not None else None
            ),
            "distance_km": round(distance, 4) if distance is not None else None,
            "method_note": (
                "No fuzzy name-only matching; unresolved/ambiguous rows require "
                "manual review."
            ),
        }
        status_counts[status] += 1
    return dict(sorted(status_counts.items()))


def _safe_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    """Preserve useful provider metadata without copying cookies or secrets."""
    allowed = {
        "content-type",
        "date",
        "etag",
        "last-modified",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "x-request-id",
    }
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() in allowed
    }


def fetch_city(
    city: str,
    api_key: str,
    *,
    http_get: HttpGet = _official_get,
    clock: Clock = _utc_now,
    limit: int = PILOT_LIMIT_PER_CITY,
) -> dict[str, Any]:
    """Fetch and validate at most five live PM2.5 rows for one pilot city."""
    canonical = canonical_city(city)
    params = request_params(canonical, api_key, limit)
    started = clock()
    monotonic_started = time.monotonic()
    response = http_get(
        API_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT_SECONDS
    )
    duration_seconds = time.monotonic() - monotonic_started
    response.raise_for_status()
    content = bytes(response.content)
    retrieved = clock()
    if api_key.encode("utf-8") in content:
        raise ValueError(
            "OGD response echoed the API credential; refusing to persist it"
        )
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"OGD response for {canonical} was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"OGD response for {canonical} was not a JSON object")

    payload_resource_id = payload.get("index_name")
    if payload_resource_id not in (None, RESOURCE_ID):
        raise ValueError(
            f"OGD response resource mismatch: expected {RESOURCE_ID}, "
            f"received {payload_resource_id!r}"
        )
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"OGD response for {canonical} has no records list")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f"OGD response for {canonical} contains a non-object record")
    if len(records) > limit:
        raise ValueError(
            f"OGD response for {canonical} exceeded the requested tiny limit "
            f"({len(records)} > {limit}); refusing to retain it"
        )

    retrieved_iso = _iso_utc(retrieved)
    normalized, validation = validate_records(records, canonical, retrieved_iso)
    return {
        "city": canonical,
        "request_started_at_utc": _iso_utc(started),
        "retrieved_at_utc": retrieved_iso,
        "response_time_seconds": round(duration_seconds, 6),
        "request_url_template": request_url_template(canonical, limit),
        "request_parameters": {
            key: ("${DATA_GOV_IN_API_KEY}" if key == "api-key" else value)
            for key, value in params.items()
        },
        "response_sha256": _sha256_bytes(content),
        "response_bytes": len(content),
        "response_headers": _safe_headers(getattr(response, "headers", {})),
        "response_metadata": {
            key: value for key, value in payload.items() if key != "records"
        },
        "records": normalized,
        "validation": validation,
    }


def _snapshot_bytes(snapshot: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")


def _publishable_path(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        # Do not leak a workstation username or private directory in a
        # potentially publishable manifest.
        return resolved.name


def _append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    """Append one complete JSON record without rewriting prior manifest lines."""
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def run_pilot(
    api_key: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    http_get: HttpGet = _official_get,
    clock: Clock = _utc_now,
    registry_path: Path | None = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    """Run both five-row probes and write one immutable snapshot + manifest row."""
    if not api_key:
        raise ValueError(
            "DATA_GOV_IN_API_KEY is not set. Create a key through data.gov.in "
            "and export it only in your local environment."
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_started = clock()
    responses: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for city in PILOT_CITIES:
        try:
            responses.append(
                fetch_city(city, api_key, http_get=http_get, clock=clock)
            )
        except (HTTPError, URLError, OSError, ValueError) as exc:
            safe_message = str(exc).replace(api_key, "${DATA_GOV_IN_API_KEY}")
            safe_message = safe_message.replace(
                quote_plus(api_key), "${DATA_GOV_IN_API_KEY}"
            )
            errors.append(
                {
                    "city": city,
                    "error_type": type(exc).__name__,
                    "message": safe_message,
                }
            )
    run_ended = clock()

    all_rows = [
        row
        for response in responses
        for row in response.get("records", [])
    ]
    registry_counts: dict[str, int] = {}
    match_counts: dict[str, int] = {}
    registry_error: str | None = None
    if registry_path is not None:
        try:
            registry = load_pilot_registry(registry_path)
            registry_counts = dict(
                sorted(Counter(row["city"] for row in registry).items())
            )
            match_counts = attach_registry_matches(all_rows, registry)
        except (OSError, ValueError) as exc:
            registry_error = f"{type(exc).__name__}: {exc}"

    snapshot = {
        "schema_version": PARSER_SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "product": PRODUCT_NAME,
        "role": ROLE,
        "warning": (
            "Unvalidated current instrument feed; probably overlaps OpenAQ and "
            "must not be described as independent truth."
        ),
        "resource_id": RESOURCE_ID,
        "official_resource_page": RESOURCE_PAGE,
        "official_catalog_page": CATALOG_PAGE,
        "api_endpoint": API_ENDPOINT,
        "run_started_at_utc": _iso_utc(run_started),
        "run_ended_at_utc": _iso_utc(run_ended),
        "responses": responses,
        "errors": errors,
        "registry_matching": {
            "registry_path": (
                _publishable_path(registry_path)
            ),
            "registry_city_counts": registry_counts,
            "match_status_counts": match_counts,
            "error": registry_error,
        },
    }
    content = _snapshot_bytes(snapshot)
    snapshot_hash = _sha256_bytes(content)
    timestamp_token = _iso_utc(run_ended).replace("-", "").replace(":", "")
    timestamp_token = timestamp_token.replace("T", "_").replace("Z", "Z")
    snapshot_path = output_dir / f"snapshot_{timestamp_token}_{snapshot_hash[:12]}.json"
    # Exclusive creation makes snapshots immutable and surfaces clock/hash
    # collisions rather than overwriting evidence.
    with snapshot_path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())

    all_flags = Counter(
        flag for row in all_rows for flag in row.get("validation_flags", [])
    )
    ordered_source_times = sorted(
        (
            (parsed, str(row["observed_at_source"]))
            for row in all_rows
            if (parsed := _source_timestamp_order(row.get("observed_at_source")))
            is not None
        ),
        key=lambda pair: pair[0],
    )
    explicit_observed_times = [
        str(row["observed_at_utc"])
        for row in all_rows
        if row.get("observed_at_utc") is not None
    ]
    manifest_record = {
        "schema_version": PARSER_SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "product": PRODUCT_NAME,
        "provider": (
            "Ministry of Environment, Forest and Climate Change / "
            "Central Pollution Control Board"
        ),
        "role": ROLE,
        "resource_id": RESOURCE_ID,
        "official_resource_page": RESOURCE_PAGE,
        "official_catalog_page": CATALOG_PAGE,
        "exact_endpoint": API_ENDPOINT,
        "access_method": "official Data API; API-key authentication",
        "authentication": "DATA_GOV_IN_API_KEY environment variable; not stored",
        "request_templates": [
            request_url_template(city) for city in PILOT_CITIES
        ],
        "geographical_bounds": list(PILOT_CITIES),
        "pollutant": POLLUTANT,
        "limit_per_city": PILOT_LIMIT_PER_CITY,
        "request_started_at_utc": _iso_utc(run_started),
        "request_ended_at_utc": _iso_utc(run_ended),
        "retrieved_at_utc": _iso_utc(run_ended),
        "snapshot_file": snapshot_path.name,
        "snapshot_bytes": len(content),
        "snapshot_sha256": snapshot_hash,
        "response_sha256_by_city": {
            response["city"]: response["response_sha256"]
            for response in responses
        },
        "response_headers_by_city": {
            response["city"]: response["response_headers"]
            for response in responses
        },
        "response_metadata_by_city": {
            response["city"]: response["response_metadata"]
            for response in responses
        },
        "provider_product_version": (
            "live resource; provider revision metadata retained per response"
        ),
        "parser_schema_version": PARSER_SCHEMA_VERSION,
        "repository_commit": _repository_commit(),
        "rows_received": sum(
            response["validation"]["rows_received"] for response in responses
        ),
        "rows_parsed": sum(
            response["validation"]["rows_received"] for response in responses
        ),
        "rows_retained": len(all_rows),
        "rows_excluded": sum(
            response["validation"]["rows_excluded"] for response in responses
        ),
        "excluded_by_reason": dict(
            sum(
                (
                    Counter(response["validation"]["excluded_by_reason"])
                    for response in responses
                ),
                Counter(),
            )
        ),
        "validation_flag_counts": dict(sorted(all_flags.items())),
        "distinct_provider_stations": len(
            {
                (row.get("city"), row.get("station"))
                for row in all_rows
                if row.get("station")
            }
        ),
        "provider_sensor_identifiers": (
            "not supplied by the reviewed OGD resource schema"
        ),
        "first_observed_at_source": (
            ordered_source_times[0][1] if ordered_source_times else None
        ),
        "last_observed_at_source": (
            ordered_source_times[-1][1] if ordered_source_times else None
        ),
        "first_observed_at_utc": min(explicit_observed_times, default=None),
        "last_observed_at_utc": max(explicit_observed_times, default=None),
        "units_encountered": sorted(
            {
                str(row["unit"])
                for row in all_rows
                if not _is_missing(row.get("unit"))
            }
        ),
        "error_history": errors,
        "registry_path": _publishable_path(registry_path),
        "registry_expected_city_counts": {"Patna": 7, "Varanasi": 4},
        "registry_actual_city_counts": registry_counts,
        "registry_match_status_counts": match_counts,
        "registry_error": registry_error,
        "terms_url": GODL_PAGE,
        "terms_reviewed_at": "2026-07-29",
        "terms_review_basis": (
            "Government Open Data License - India; re-review before public release"
        ),
        "redistribution_decision": "approved_raw_subject_to_GODL_attribution",
        "attribution": ATTRIBUTION,
        "independence_status": (
            "not established; likely shares CPCB/SPCB upstream measurements "
            "with OpenAQ"
        ),
    }
    manifest_path = output_dir / "manifest.jsonl"
    _append_jsonl(manifest_path, manifest_record)
    return {
        "snapshot_path": snapshot_path,
        "manifest_path": manifest_path,
        "snapshot": snapshot,
        "manifest_record": manifest_record,
        "errors": errors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch at most five current CPCB/OGD PM2.5 rows for each of Patna "
            "and Varanasi. This is a live-feed diagnostic, not independent truth."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Private local output directory (default: "
            f"{DEFAULT_OUTPUT_DIR}). Do not commit unreviewed snapshots."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_pilot(
        api_key=os.getenv("DATA_GOV_IN_API_KEY", ""),
        output_dir=args.output_dir,
    )
    manifest = result["manifest_record"]
    print(
        f"Wrote {manifest['rows_retained']} retained live rows to "
        f"{result['snapshot_path']}"
    )
    print(f"Appended provenance to {result['manifest_path']}")
    print("This feed is not verified independent truth and may overlap OpenAQ.")
    if result["errors"] or manifest["registry_error"]:
        raise SystemExit(
            "One or more city probes or registry checks failed; inspect the "
            "manifest before continuing."
        )


if __name__ == "__main__":
    main()
