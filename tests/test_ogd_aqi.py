"""Contract tests for the tiny official OGD India CPCB current-feed pilot."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from src.data.ogd_aqi import (
    API_ENDPOINT,
    PILOT_CITIES,
    RESOURCE_ID,
    attach_registry_matches,
    canonical_city,
    request_params,
    request_url_template,
    run_pilot,
    validate_records,
)


RETRIEVED = "2026-07-29T12:00:00Z"


def _row(
    *,
    city: str = "Patna",
    station: str = "IGSC Planetarium Complex, Patna - BSPCB",
    pollutant: str = "PM2.5",
    value: Any = "121",
    unit: Any = "ug/m3",
    latitude: Any = "25.5941",
    longitude: Any = "85.1376",
    observed: Any = "29-07-2026 17:00:00",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "country": "India",
        "state": "Bihar",
        "city": city,
        "station": station,
        "last_update": observed,
        "latitude": latitude,
        "longitude": longitude,
        "pollutant_id": pollutant,
        "pollutant_min": "100",
        "pollutant_max": "140",
        "pollutant_avg": value,
        "pollutant_unit": unit,
        "provider_extra_field": "preserve me",
        **extra,
    }


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.content = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        self.status_code = status_code
        self.headers = {
            "Content-Type": "application/json",
            "ETag": "tiny-fixture",
            "Set-Cookie": "must-not-be-preserved",
        }

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _payload(city: str) -> dict[str, Any]:
    state = "Bihar" if city == "Patna" else "Uttar Pradesh"
    station = (
        "IGSC Planetarium Complex, Patna - BSPCB"
        if city == "Patna"
        else "Ardhali Bazar, Varanasi - UPPCB"
    )
    latitude, longitude = (
        ("25.5941", "85.1376")
        if city == "Patna"
        else ("25.3505986", "82.9083074")
    )
    return {
        "index_name": RESOURCE_ID,
        "title": "Real time Air Quality Index from various locations",
        "total": 1,
        "count": 1,
        "limit": "5",
        "offset": "0",
        "records": [
            _row(
                city=city,
                station=station,
                state=state,
                latitude=latitude,
                longitude=longitude,
            )
        ],
    }


def test_scope_is_exactly_two_cities_and_pm25() -> None:
    assert PILOT_CITIES == ("Patna", "Varanasi")
    assert canonical_city(" patna ") == "Patna"
    params = request_params("VARANASI", "local-secret")
    assert params["filters[city]"] == "Varanasi"
    assert params["filters[pollutant_id]"] == "PM2.5"
    assert params["limit"] == 5
    with pytest.raises(ValueError, match="outside this tiny pilot"):
        canonical_city("Delhi")
    with pytest.raises(ValueError, match="between 1 and 5"):
        request_params("Patna", "key", limit=6)


def test_publishable_request_template_has_resource_id_and_no_real_key() -> None:
    template = request_url_template("Patna")
    assert template.startswith(API_ENDPOINT)
    assert "${DATA_GOV_IN_API_KEY}" in template
    assert "local-secret" not in template
    query = parse_qs(urlsplit(template).query)
    assert query["filters[city]"] == ["Patna"]
    assert query["filters[pollutant_id]"] == ["PM2.5"]
    assert query["limit"] == ["5"]


def test_validation_filters_scope_but_preserves_raw_fields_and_hash() -> None:
    kept = _row(document_id=123)
    rows, report = validate_records(
        [
            kept,
            _row(city="Delhi"),
            _row(pollutant="PM10"),
        ],
        "Patna",
        RETRIEVED,
    )
    assert report["rows_received"] == 3
    assert report["rows_retained"] == 1
    assert report["excluded_by_reason"] == {
        "different_city": 1,
        "different_pollutant": 1,
    }
    row = rows[0]
    assert row["raw"] == kept
    assert row["raw"]["provider_extra_field"] == "preserve me"
    assert row["resource_id"] == RESOURCE_ID
    expected_hash = hashlib.sha256(
        json.dumps(
            kept, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    assert row["raw_record_sha256"] == expected_hash
    assert row["retrieved_at_utc"] == RETRIEVED


def test_validation_keeps_severe_and_invalid_values_with_visible_flags() -> None:
    rows, report = validate_records(
        [
            _row(value="750"),
            _row(station="Broken", value="1001", latitude="999", unit=None),
            _row(station="Missing", value="NA", observed=None),
        ],
        "Patna",
        RETRIEVED,
    )
    assert len(rows) == 3
    assert rows[0]["value"] == 750.0
    assert "value_out_of_project_range" not in rows[0]["validation_flags"]
    assert {
        "value_out_of_project_range",
        "coordinates_out_of_range",
        "unit_missing",
    }.issubset(rows[1]["validation_flags"])
    assert {
        "value_missing_or_non_numeric",
        "observed_timestamp_missing",
    }.issubset(rows[2]["validation_flags"])
    assert report["validation_flag_counts"]["value_out_of_project_range"] == 1

    rows, _ = validate_records(
        [_row(unit="AQI")], "Patna", RETRIEVED
    )
    assert (
        "unit_not_recognized_as_pm25_mass_concentration"
        in rows[0]["validation_flags"]
    )


def test_naive_source_time_is_preserved_without_inventing_timezone() -> None:
    rows, _ = validate_records([_row()], "Patna", RETRIEVED)
    assert rows[0]["observed_at_source"] == "29-07-2026 17:00:00"
    assert rows[0]["observed_at_utc"] is None
    assert (
        "observed_timestamp_timezone_not_explicit"
        in rows[0]["validation_flags"]
    )

    rows, _ = validate_records(
        [_row(observed="2026-07-29T17:00:00+05:30")], "Patna", RETRIEVED
    )
    assert rows[0]["observed_at_utc"] == "2026-07-29T11:30:00Z"


def test_duplicates_are_retained_and_flagged_not_averaged() -> None:
    duplicate = _row()
    rows, report = validate_records(
        [duplicate, dict(duplicate)], "Patna", RETRIEVED
    )
    assert len(rows) == 2
    assert report["duplicate_rows"] == 2
    assert all(
        "duplicate_station_pollutant_time" in row["validation_flags"]
        for row in rows
    )


def test_registry_matching_requires_coordinates_not_a_name_only_guess() -> None:
    rows, _ = validate_records([_row()], "Patna", RETRIEVED)
    counts = attach_registry_matches(
        rows,
        [
            {
                "station_id": "5652",
                "city": "Patna",
                "station_name": "IGSC Planetarium Complex, Patna - BSPCB",
                "latitude": 25.5941,
                "longitude": 85.1376,
            }
        ],
    )
    assert counts == {"exact_name_and_near_coordinates": 1}
    assert rows[0]["registry_match"]["registry_station_id"] == "5652"

    name_only_rows, _ = validate_records(
        [_row(latitude=None, longitude=None)], "Patna", RETRIEVED
    )
    counts = attach_registry_matches(
        name_only_rows,
        [
            {
                "station_id": "5652",
                "city": "Patna",
                "station_name": "IGSC Planetarium Complex, Patna - BSPCB",
                "latitude": 25.5941,
                "longitude": 85.1376,
            }
        ],
    )
    assert counts == {"no_high_confidence_match": 1}
    assert name_only_rows[0]["registry_match"]["registry_station_id"] is None


def test_run_writes_immutable_snapshot_and_append_only_manifest_without_key(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, *, params: dict[str, Any], timeout: int) -> FakeResponse:
        calls.append({"url": url, "params": dict(params), "timeout": timeout})
        return FakeResponse(_payload(params["filters[city]"]))

    current = [datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)]

    def advancing_clock() -> datetime:
        result = current[0]
        current[0] += timedelta(seconds=1)
        return result

    registry_path = tmp_path / "stations.csv"
    registry_path.write_text(
        "station_id,city,station_name,lat,lon\n"
        '5652,patna,"IGSC Planetarium Complex, Patna - BSPCB",25.5941,85.1376\n'
        '5590,varanasi,"Ardhali Bazar, Varanasi - UPPCB",25.3505986,82.9083074\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "private-output"

    result = run_pilot(
        "super-secret-key",
        output_dir,
        http_get=fake_get,
        clock=advancing_clock,
        registry_path=registry_path,
    )
    assert len(calls) == 2
    assert {call["params"]["filters[city]"] for call in calls} == {
        "Patna",
        "Varanasi",
    }
    assert all(call["params"]["limit"] == 5 for call in calls)
    snapshot_path = result["snapshot_path"]
    manifest_path = result["manifest_path"]
    assert snapshot_path.exists()
    assert manifest_path.exists()

    snapshot_bytes = snapshot_path.read_bytes()
    manifest_lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == 1
    manifest = json.loads(manifest_lines[0])
    assert manifest["rows_received"] == 2
    assert manifest["rows_retained"] == 2
    assert manifest["snapshot_sha256"] == hashlib.sha256(
        snapshot_bytes
    ).hexdigest()
    assert manifest["role"].endswith("not_verified_independent_truth")
    assert "OpenAQ" in manifest["independence_status"]
    assert manifest["registry_actual_city_counts"] == {
        "Patna": 1,
        "Varanasi": 1,
    }
    assert manifest["registry_path"] == "stations.csv"
    assert manifest["registry_match_status_counts"] == {
        "exact_name_and_near_coordinates": 2
    }
    assert manifest["response_headers_by_city"]["Patna"] == {
        "content-type": "application/json",
        "etag": "tiny-fixture",
    }

    all_written = snapshot_bytes + manifest_path.read_bytes()
    assert b"super-secret-key" not in all_written
    assert b"${DATA_GOV_IN_API_KEY}" in all_written

    first_manifest_line = manifest_lines[0]
    second = run_pilot(
        "super-secret-key",
        output_dir,
        http_get=fake_get,
        clock=advancing_clock,
        registry_path=registry_path,
    )
    second_lines = second["manifest_path"].read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(second_lines) == 2
    assert second_lines[0] == first_manifest_line
    assert second["snapshot_path"] != snapshot_path


def test_run_rejects_missing_key_before_network_or_writes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="DATA_GOV_IN_API_KEY"):
        run_pilot("", tmp_path)
    assert list(tmp_path.iterdir()) == []
