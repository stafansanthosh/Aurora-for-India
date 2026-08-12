"""SILAM capture: the guarantees that keep a rolling-window archive trustworthy.

The archive is a rolling ~32-day window, so a cycle captured wrong cannot be
recaptured later. These tests pin the fail-closed behaviour rather than
performance: short upstream leads, unverified units, and the distinction
between a complete cycle and one with recorded gaps.
"""
import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.data import silam_forecast as silam


def _grid(hours: int, path, units: str = "ug/m3", day_offset: int = 0) -> None:
    """Write a small SILAM-shaped PM25 file with ``hours`` timesteps.

    ``day_offset`` mirrors the real layout: each lead day covers its own
    24-hour block, so d0..d4 never share a valid time.
    """
    start = pd.Timestamp("2026-08-11T01:00", tz="UTC") + pd.Timedelta(days=day_offset)
    times = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    lats = np.array([25.0, 25.2, 25.4])
    lons = np.array([82.8, 83.0, 83.2])
    values = np.arange(hours * 3 * 3, dtype="float32").reshape(hours, 3, 3)
    ds = xr.Dataset(
        {"PM25": (("time", "lat", "lon"), values, {"units": units})},
        coords={"time": times.tz_localize(None), "lat": lats, "lon": lons},
    )
    ds.to_netcdf(path)


def _cells() -> pd.DataFrame:
    return pd.DataFrame({"station_id": ["s1", "s2"], "city": ["varanasi", "varanasi"],
                         "lat_idx": [0, 1], "lon_idx": [1, 2], "cell_dist_km": [1.0, 2.0]})


def test_sample_file_derives_lead_hours_from_init(tmp_path):
    path = tmp_path / "pm25.nc"
    _grid(24, path)
    init = pd.Timestamp("2026-08-11T00:00:00Z")

    frame = silam._sample_file(path, _cells(), init)

    assert set(frame["station_id"]) == {"s1", "s2"}
    # First timestep is 01:00 against a 00:00 init.
    assert frame["lead_h"].min() == 1
    assert frame["lead_h"].max() == 24
    assert frame["valid_time"].nunique() == 24


def test_sample_file_rejects_unverified_units(tmp_path):
    path = tmp_path / "bad_units.nc"
    _grid(24, path, units="kg/m3")

    with pytest.raises(ValueError, match="unexpected units"):
        silam._sample_file(path, _cells(), pd.Timestamp("2026-08-11T00:00:00Z"))


def test_short_lead_fails_closed_by_default(tmp_path, monkeypatch):
    """Upstream really does serve short files -- 20260730 d2 had 20 hours.

    Silently accepting one produces 24-hour windows built from 20 hours of data
    that are indistinguishable from valid ones.
    """
    monkeypatch.setattr(silam, "load_registry", lambda *a, **k: pd.DataFrame(
        {"station_id": ["s1"], "city": ["varanasi"], "lat": [25.2], "lon": [83.0]}))

    def fake_download(url, destination):
        lead = int(url.rsplit("_d", 1)[1].split(".")[0])
        _grid(20 if lead == 2 else 24, destination, day_offset=lead)
        return "deadbeef", destination.stat().st_size

    monkeypatch.setattr(silam, "_download", fake_download)

    with pytest.raises(ValueError, match="expected 24 hours, got 20"):
        silam.capture_cycle("20260730", output_dir=tmp_path)


def test_allow_short_lead_records_the_gap_and_marks_the_cycle(tmp_path, monkeypatch):
    """The escape hatch must be explicit and must not masquerade as clean."""
    monkeypatch.setattr(silam, "load_registry", lambda *a, **k: pd.DataFrame(
        {"station_id": ["s1"], "city": ["varanasi"], "lat": [25.2], "lon": [83.0]}))

    def fake_download(url, destination):
        lead = int(url.rsplit("_d", 1)[1].split(".")[0])
        _grid(20 if lead == 2 else 24, destination, day_offset=lead)
        return "deadbeef", destination.stat().st_size

    monkeypatch.setattr(silam, "_download", fake_download)

    silam.capture_cycle("20260730", output_dir=tmp_path, allow_short_lead=True)
    provenance = json.loads((tmp_path / "20260730" / "provenance.json").read_text())

    assert provenance["status"] == "complete_with_gaps"
    assert provenance["short_leads"] == [{"lead": "d2", "hours": 20}]
    # A consumer filtering on == "complete" must not pick this cycle up.
    assert provenance["status"] != "complete"
    assert provenance["licence"] == "CC-BY-4.0"
    assert provenance["attribution"].startswith("SILAM")


def test_clean_cycle_is_marked_complete_with_no_gaps(tmp_path, monkeypatch):
    monkeypatch.setattr(silam, "load_registry", lambda *a, **k: pd.DataFrame(
        {"station_id": ["s1"], "city": ["varanasi"], "lat": [25.2], "lon": [83.0]}))
    def fake_download(url, destination):
        lead = int(url.rsplit("_d", 1)[1].split(".")[0])
        _grid(24, destination, day_offset=lead)
        return "deadbeef", destination.stat().st_size

    monkeypatch.setattr(silam, "_download", fake_download)

    silam.capture_cycle("20260811", output_dir=tmp_path)
    provenance = json.loads((tmp_path / "20260811" / "provenance.json").read_text())

    assert provenance["status"] == "complete"
    assert provenance["short_leads"] == []
    assert provenance["rows"] == 5 * 24          # 5 lead days x 24 hours x 1 station
    assert "retrieved_at_utc" in provenance["files"][0]
    assert provenance["files"][0]["sha256"] == "deadbeef"


def test_station_cells_pick_the_nearest_grid_point():
    reg = pd.DataFrame({"station_id": ["s1"], "city": ["varanasi"],
                        "lat": [25.19], "lon": [83.01]})
    cells = silam.station_cells(reg, np.array([25.0, 25.2, 25.4]),
                                np.array([82.8, 83.0, 83.2]))
    assert cells.loc[0, "lat_idx"] == 1        # 25.2 is nearest 25.19
    assert cells.loc[0, "lon_idx"] == 1        # 83.0 is nearest 83.01
    assert cells.loc[0, "cell_dist_km"] < 5.0
