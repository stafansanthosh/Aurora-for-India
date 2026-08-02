"""Contract tests for the actual lead-dependent CAMS forecast baseline."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.data.cams_forecast import (
    DATASET,
    DEFAULT_LEADS,
    INDIA_AREA,
    KG_M3_TO_UG_M3,
    PILOT_AREA,
    ForecastRequest,
    attach_to_pairs,
    extract_and_record,
    extract_station_forecasts,
    forecast_paths,
    kg_m3_to_ug_m3,
    load_dates_file,
    request_document,
    retrieve_forecast,
)


def test_request_is_exact_deterministic_and_one_cycle():
    request = ForecastRequest("2025-11-06", area=PILOT_AREA)

    assert request.payload() == {
        "type": "forecast",
        "date": "2025-11-06",
        "time": "12:00",
        "leadtime_hour": ["12", "24", "36", "48", "60", "72", "84", "96"],
        "variable": "particulate_matter_2.5um",
        "area": ["26.2", "82.4", "24.8", "85.6"],
        "format": "grib",
    }
    assert request_document(request)["dataset"] == DATASET
    assert request.init_time == datetime(2025, 11, 6, 12, tzinfo=timezone.utc)
    assert tuple(
        int((valid - request.init_time).total_seconds() / 3600)
        for valid in request.valid_times
    ) == DEFAULT_LEADS


@pytest.mark.parametrize(
    "kwargs",
    [
        {"date": "2025-2-03"},
        {"date": "2025-02-30"},
        {"date": "2025-02-03", "time": "00:00"},
        {"date": "2025-02-03", "leads": (12, 12)},
        {"date": "2025-02-03", "leads": (24, 12)},
        {"date": "2025-02-03", "area": (8, 72, 30, 90)},
    ],
)
def test_request_rejects_ambiguous_or_wrong_acquisition(kwargs):
    with pytest.raises(ValueError):
        ForecastRequest(**kwargs)


def test_paths_keep_forecast_separate_from_aurora_inputs(tmp_path):
    paths = forecast_paths(ForecastRequest("2025-11-06"), tmp_path)

    assert paths.directory == tmp_path / "init=2025-11-06T12-00Z"
    assert paths.raw_grib.name == "pm25_leads_12_96.grib"
    assert paths.request_json.parent == paths.raw_grib.parent
    assert "cams_analysis" not in str(paths.raw_grib)


class _Result:
    reply = {
        "request_id": "safe-job-id",
        "state": "successful",
        "location": "https://signed.example/secret-token",
    }


class _FakeClient:
    def __init__(self, payload: bytes = b"synthetic-grib"):
        self.payload = payload
        self.calls = []

    def retrieve(self, dataset, request, target):
        self.calls.append((dataset, request, target))
        Path(target).write_bytes(self.payload)
        return _Result()


def test_retrieval_preserves_raw_request_hash_and_safe_provenance(tmp_path):
    request = ForecastRequest("2025-11-06", area=PILOT_AREA)
    client = _FakeClient()
    times = iter(
        [
            datetime(2025, 11, 7, 1, tzinfo=timezone.utc),
            datetime(2025, 11, 7, 1, 0, 2, tzinfo=timezone.utc),
        ]
    )

    paths = retrieve_forecast(request, tmp_path, client=client, now=lambda: next(times))

    assert paths.raw_grib.read_bytes() == b"synthetic-grib"
    assert json.loads(paths.request_json.read_text()) == request_document(request)
    provenance = json.loads(paths.provenance_json.read_text())
    assert provenance["status"] == "complete"
    assert provenance["raw_file"]["bytes"] == len(b"synthetic-grib")
    assert provenance["raw_file"]["sha256"] == hashlib.sha256(
        b"synthetic-grib"
    ).hexdigest()
    assert provenance["source_unit"] == "kg m-3"
    assert provenance["conversion_expression"] == "ug_m3 = kg_m3 * 1e9"
    assert provenance["attempts"][0]["provider"] == {
        "request_id": "safe-job-id",
        "state": "successful",
    }
    assert "secret-token" not in paths.provenance_json.read_text()
    assert client.calls[0][0] == DATASET
    assert not paths.raw_grib.with_suffix(".grib.part").exists()


def test_verified_existing_retrieval_is_resumable_without_network(tmp_path):
    request = ForecastRequest("2025-11-06")
    first_client = _FakeClient()
    first_times = iter(
        [
            datetime(2025, 11, 7, 1, tzinfo=timezone.utc),
            datetime(2025, 11, 7, 1, 0, 1, tzinfo=timezone.utc),
        ]
    )
    paths = retrieve_forecast(
        request, tmp_path, client=first_client, now=lambda: next(first_times)
    )
    second_client = _FakeClient(b"must-not-be-written")

    same = retrieve_forecast(request, tmp_path, client=second_client)

    assert same == paths
    assert second_client.calls == []
    assert paths.raw_grib.read_bytes() == b"synthetic-grib"


def test_offline_mode_fails_closed_when_forecast_is_missing(tmp_path):
    request = ForecastRequest("2025-11-06")

    with pytest.raises(FileNotFoundError, match="Offline CAMS forecast input"):
        retrieve_forecast(request, tmp_path, allow_retrieve=False)


def test_existing_raw_hash_mismatch_fails_instead_of_overwriting(tmp_path):
    request = ForecastRequest("2025-11-06")
    times = iter(
        [
            datetime(2025, 11, 7, 1, tzinfo=timezone.utc),
            datetime(2025, 11, 7, 1, 0, 1, tzinfo=timezone.utc),
        ]
    )
    paths = retrieve_forecast(
        request, tmp_path, client=_FakeClient(), now=lambda: next(times)
    )
    paths.raw_grib.write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="not a verified completed retrieval"):
        retrieve_forecast(request, tmp_path, client=_FakeClient())
    assert paths.raw_grib.read_bytes() == b"tampered"


def test_failed_attempt_is_visible_and_partial_is_preserved(tmp_path):
    class FailingClient:
        def retrieve(self, dataset, request, target):
            Path(target).write_bytes(b"partial")
            raise RuntimeError("provider unavailable")

    request = ForecastRequest("2025-11-06")
    times = iter(
        [
            datetime(2025, 11, 7, 1, tzinfo=timezone.utc),
            datetime(2025, 11, 7, 1, 0, 5, tzinfo=timezone.utc),
        ]
    )
    with pytest.raises(RuntimeError, match="provider unavailable"):
        retrieve_forecast(
            request, tmp_path, client=FailingClient(), now=lambda: next(times)
        )

    paths = forecast_paths(request, tmp_path)
    provenance = json.loads(paths.provenance_json.read_text())
    assert provenance["status"] == "failed"
    assert provenance["attempts"][-1]["partial_bytes"] == 7
    assert provenance["attempts"][-1]["partial_sha256"] == hashlib.sha256(
        b"partial"
    ).hexdigest()
    assert paths.raw_grib.with_suffix(".grib.part").read_bytes() == b"partial"


def _synthetic_dataset(
    request: ForecastRequest,
    *,
    units: str = "kg m**-3",
    leads: tuple[int, ...] = DEFAULT_LEADS,
) -> xr.Dataset:
    values = np.empty((len(leads), 2, 2), dtype=np.float64)
    for lead_index, _ in enumerate(leads):
        values[lead_index] = np.array(
            [[1.0, 2.0], [3.0, 4.0]], dtype=float
        ) * (lead_index + 1) * 1e-8
    data = xr.DataArray(
        values,
        dims=("step", "latitude", "longitude"),
        coords={
            "step": np.asarray(leads, dtype="timedelta64[h]"),
            "latitude": np.array([26.0, 25.0]),
            "longitude": np.array([82.5, 83.5]),
        },
        attrs={"units": units, "GRIB_modelName": "synthetic-cams"},
        name="pm2p5",
    )
    return xr.Dataset(
        {"pm2p5": data},
        coords={"time": np.datetime64(request.init_time.replace(tzinfo=None))},
    )


def test_station_extraction_has_all_leads_nearest_cells_and_one_conversion(tmp_path):
    request = ForecastRequest("2025-11-06", area=PILOT_AREA)
    stations = pd.DataFrame(
        [
            {
                "station_id": "patna-1",
                "city": "patna",
                "lat": 25.95,
                "lon": 82.55,
            },
            {
                "station_id": "varanasi-1",
                "city": "varanasi",
                "lat": 25.05,
                "lon": 83.45,
            },
        ]
    )

    samples, metadata = extract_station_forecasts(
        tmp_path / "not-read.grib",
        stations,
        request,
        registry_version="159:test",
        open_dataset=lambda _: _synthetic_dataset(request),
    )

    assert len(samples) == 2 * len(DEFAULT_LEADS)
    assert set(samples["lead_h"]) == set(DEFAULT_LEADS)
    assert not samples.duplicated(["init_date", "station_id", "lead_h"]).any()
    assert (samples["registry_version"] == "159:test").all()
    first = samples[
        (samples["station_id"] == "patna-1") & (samples["lead_h"] == 12)
    ].iloc[0]
    assert first["cams_forecast_pm25_kgm3"] == pytest.approx(1e-8)
    assert first["cams_forecast_pm25"] == pytest.approx(10.0)
    last = samples[
        (samples["station_id"] == "varanasi-1") & (samples["lead_h"] == 96)
    ].iloc[0]
    assert last["cams_forecast_pm25_kgm3"] == pytest.approx(32e-8)
    assert last["cams_forecast_pm25"] == pytest.approx(320.0)
    assert pd.Timestamp(last["valid_time"]) == pd.Timestamp(
        "2025-11-10 12:00:00+00:00"
    )
    assert metadata["rows"] == 16
    assert metadata["source_unit_encountered"] == "kg m**-3"
    assert metadata["grib_metadata"]["GRIB_modelName"] == "synthetic-cams"


@pytest.mark.parametrize("unit", ["ug m-3", "µg m**-3", "", "g m-3"])
def test_unit_guard_rejects_already_converted_or_unknown_units(unit):
    with pytest.raises(ValueError, match="possible second conversion"):
        kg_m3_to_ug_m3([1.0], unit)


def test_unit_conversion_is_exact_and_does_not_mutate_input():
    source = np.array([1e-9, 121e-9])
    converted = kg_m3_to_ug_m3(source, "kg m**-3")

    assert converted.tolist() == pytest.approx([1.0, 121.0])
    assert source.tolist() == pytest.approx([1e-9, 121e-9])
    assert KG_M3_TO_UG_M3 == 1e9


def test_extraction_rejects_missing_or_extra_leads(tmp_path):
    request = ForecastRequest("2025-11-06")
    stations = pd.DataFrame(
        [{"station_id": "s1", "lat": 25.0, "lon": 83.0}]
    )
    with pytest.raises(ValueError, match="lead set mismatch"):
        extract_station_forecasts(
            tmp_path / "not-read.grib",
            stations,
            request,
            open_dataset=lambda _: _synthetic_dataset(
                request, leads=DEFAULT_LEADS[:-1]
            ),
        )


def test_extraction_rejects_ug_dataset_before_sampling(tmp_path):
    request = ForecastRequest("2025-11-06")
    stations = pd.DataFrame(
        [{"station_id": "s1", "lat": 25.0, "lon": 83.0}]
    )
    with pytest.raises(ValueError, match="possible second conversion"):
        extract_station_forecasts(
            tmp_path / "not-read.grib",
            stations,
            request,
            open_dataset=lambda _: _synthetic_dataset(request, units="ug m-3"),
        )


def test_extract_and_record_hashes_registry_and_samples(tmp_path):
    request = ForecastRequest("2025-11-06")
    paths = forecast_paths(request, tmp_path / "output")
    paths.directory.mkdir(parents=True)
    paths.raw_grib.write_bytes(b"synthetic-grib")
    request_doc = request_document(request)
    paths.request_json.write_text(json.dumps(request_doc))
    paths.provenance_json.write_text(
        json.dumps(
            {
                "request": request.payload(),
                "status": "complete",
                "attempts": [],
                "raw_file": {
                    "sha256": hashlib.sha256(b"synthetic-grib").hexdigest()
                },
            }
        )
    )
    stations_path = tmp_path / "stations.csv"
    pd.DataFrame(
        [{"station_id": "s1", "city": "patna", "lat": 25.0, "lon": 83.0}]
    ).to_csv(stations_path, index=False)

    samples = extract_and_record(
        request,
        paths,
        stations_path,
        registry_version="159:test",
        open_dataset=lambda _: _synthetic_dataset(request),
    )

    assert len(samples) == len(DEFAULT_LEADS)
    provenance = json.loads(paths.provenance_json.read_text())
    extraction = provenance["extraction"]
    assert extraction["registry_version"] == "159:test"
    assert extraction["station_registry_sha256"] == hashlib.sha256(
        stations_path.read_bytes()
    ).hexdigest()
    assert extraction["output_file"]["sha256"] == hashlib.sha256(
        paths.station_samples_csv.read_bytes()
    ).hexdigest()


def test_attach_to_pairs_requires_identical_support_and_leaves_lead_zero_empty():
    pairs = pd.DataFrame(
        [
            {
                "init_date": "2025-11-06",
                "station_id": "s1",
                "lead_h": lead,
                "aurora_pm2p5": 10.0 + lead,
                "registry_version": "159:test",
            }
            for lead in (0, *DEFAULT_LEADS)
        ]
    )
    samples = pd.DataFrame(
        [
            {
                "init_date": "2025-11-06",
                "station_id": "s1",
                "lead_h": lead,
                "cams_forecast_pm25": 20.0 + lead,
                "cams_forecast_pm25_kgm3": (20.0 + lead) / 1e9,
                "registry_version": "159:test",
            }
            for lead in DEFAULT_LEADS
        ]
    )

    attached = attach_to_pairs(pairs, samples)

    assert len(attached) == len(pairs)
    assert pd.isna(attached.loc[attached["lead_h"] == 0, "cams_forecast_pm25"]).all()
    assert attached.loc[
        attached["lead_h"] > 0, "cams_forecast_pm25"
    ].notna().all()


def test_attach_to_pairs_rejects_incomplete_support_and_registry_mismatch():
    pairs = pd.DataFrame(
        [
            {
                "init_date": "2025-11-06",
                "station_id": "s1",
                "lead_h": lead,
                "registry_version": "159:current",
            }
            for lead in (0, *DEFAULT_LEADS)
        ]
    )
    incomplete = pd.DataFrame(
        [
            {
                "init_date": "2025-11-06",
                "station_id": "s1",
                "lead_h": lead,
                "cams_forecast_pm25": 10.0,
                "registry_version": "159:current",
            }
            for lead in DEFAULT_LEADS[:-1]
        ]
    )
    with pytest.raises(ValueError, match="support mismatch"):
        attach_to_pairs(pairs, incomplete)

    complete_wrong_version = pd.concat(
        [
            incomplete,
            pd.DataFrame(
                [
                    {
                        "init_date": "2025-11-06",
                        "station_id": "s1",
                        "lead_h": DEFAULT_LEADS[-1],
                        "cams_forecast_pm25": 10.0,
                        "registry_version": "159:stale",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    complete_wrong_version["registry_version"] = "159:stale"
    with pytest.raises(ValueError, match="different registry versions"):
        attach_to_pairs(pairs, complete_wrong_version)


def test_frozen_csv_loader_uses_only_init_date_column(tmp_path):
    dates_file = tmp_path / "dates.csv"
    dates_file.write_text(
        "init_date,season,test\n"
        "2025-02-19,winter,False\n"
        "2025-12-02,winter,True\n",
        encoding="utf-8",
    )

    assert load_dates_file(dates_file) == ["2025-02-19", "2025-12-02"]


def test_dates_file_rejects_duplicates(tmp_path):
    dates_file = tmp_path / "dates.txt"
    dates_file.write_text("2025-02-19\n2025-02-19\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        load_dates_file(dates_file)


def test_evaluator_keeps_operational_and_fixed_cams_baselines_distinct():
    from src.eval.benchmark import METHODS

    assert METHODS["cams_forecast"] == "cams_forecast_pm25"
    assert METHODS["cams_lead0_fixed"] == "cams_pm25"
    assert "raw_cams" not in METHODS
