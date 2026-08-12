import numpy as np
import pandas as pd

from src.data import gfs_boundary_layer as gfs
from src.eval import forecast_blh_gate as gate


def test_parse_index_selects_exact_fields_and_ranges():
    text = "\n".join([
        "1:0:d=2025021912:PRMSL:mean sea level:24 hour fcst:",
        "2:100:d=2025021912:TMP:2 m above ground:24 hour fcst:",
        "3:250:d=2025021912:DPT:2 m above ground:24 hour fcst:",
        "4:400:d=2025021912:UGRD:10 m above ground:24 hour fcst:",
        "5:550:d=2025021912:VGRD:10 m above ground:24 hour fcst:",
        "6:700:d=2025021912:HPBL:surface:24 hour fcst:",
        "7:900:d=2025021912:RH:0.33-1 sigma layer:24 hour fcst:",
    ])
    parsed = gfs.parse_index(text)
    assert parsed["gfs_t2m"]["offset"] == 100
    assert parsed["gfs_t2m"]["end"] == 249
    assert parsed["gfs_blh"]["offset"] == 700
    assert parsed["gfs_blh"]["bytes"] == 200
    assert parsed["gfs_blh"]["index_line"].split(":")[3:5] == ["HPBL", "surface"]


def test_parse_index_rejects_missing_required_field():
    text = "\n".join([
        "1:0:d=2025021912:TMP:2 m above ground:24 hour fcst:",
        "2:100:d=2025021912:DPT:2 m above ground:24 hour fcst:",
        "3:200:d=2025021912:UGRD:10 m above ground:24 hour fcst:",
        "4:300:d=2025021912:VGRD:10 m above ground:24 hour fcst:",
        "5:400:d=2025021912:RH:surface:24 hour fcst:",
    ])
    try:
        gfs.parse_index(text)
    except ValueError as exc:
        assert "gfs_blh" in str(exc)
    else:
        raise AssertionError("missing HPBL should fail closed")


def _source_rows(station: str, count: int, prefix: str) -> pd.DataFrame:
    leads = np.arange(count) * 3
    return pd.DataFrame({
        "init_date": "2025-02-19",
        "station_id": station,
        "lead_h": leads,
        f"{prefix}_blh": 100 + leads,
        f"{prefix}_ventilation": 500 + leads,
        f"{prefix}_dewpoint_depression": 2 + leads / 100,
    })


def test_window_aggregates_require_all_eight_three_hour_samples():
    complete = _source_rows("complete", 9, "gfs")
    short = _source_rows("short", 7, "gfs")
    out = gate._window_aggregates(pd.concat([complete, short]), "gfs")
    first = out[out["window_start_h"] == 0]
    assert set(first["station_id"]) == {"complete"}
    row = first.iloc[0]
    assert row["gfs_blh_min"] == 100
    assert row["gfs_blh_mean"] == np.mean(np.arange(100, 124, 3))


def test_decision_rule_coverage_precedes_skill():
    gains = {"patna": {"events": 111, "delta_auc": 0.02, "delta_csi": 0.03}}
    assert gate.decide(False, 0.10, 0.20, gains) == "INDETERMINATE - COVERAGE"


def test_decision_rule_free_nwp_sufficient():
    gains = {"patna": {"events": 111, "delta_auc": 0.01, "delta_csi": 0.01}}
    assert gate.decide(True, 0.020, 0.030, gains).startswith("FREE NWP SUFFICIENT")


def test_decision_rule_insufficient_and_ambiguous():
    gains = {"patna": {"events": 111, "delta_auc": -0.01, "delta_csi": 0.01}}
    assert gate.decide(True, 0.009, 0.20, gains).startswith("FREE NWP INSUFFICIENT")
    assert gate.decide(True, 0.015, 0.20, gains) == "AMBIGUOUS - no GPU yet"


def test_source_coverage_denominator_excludes_current_feature_gaps(monkeypatch):
    base = pd.DataFrame({
        "init_date": ["2025-02-19"] * 2,
        "station_id": ["a", "b"],
        "window_start_h": [0, 0],
        "window_start": pd.to_datetime(["2025-02-19T12:00Z"] * 2),
        "is_test": [False, False],
        "spatial_tier": ["train_pool", "train_pool"],
        "obs_pm25": [130.0, 140.0],
        "persist_pm25": [100.0, 100.0],
        "aurora_pm2p5": [90.0, np.nan],
        "cams_forecast_pm25": [80.0, 80.0],
    })
    aggregates = pd.DataFrame({
        "init_date": ["2025-02-19"] * 2,
        "station_id": ["a", "b"],
        "window_start_h": [0, 0],
        **{name: [1.0, 1.0] for name in [
            "blh_min", "blh_mean", "ventilation_min", "ventilation_mean",
            "dewpoint_depression_mean",
        ]},
    })
    monkeypatch.setattr(gate, "_window_aggregates", lambda frame, prefix: aggregates.rename(
        columns={name: f"{prefix}_{name}" for name in gate.SOURCE_FEATURES}
    ))
    monkeypatch.setattr(gate.bench, "build_frame", lambda: pd.DataFrame())
    monkeypatch.setattr(gate.bench, "add_climatology", lambda frame: frame)
    monkeypatch.setattr(gate.bench, "load_obs", lambda: pd.DataFrame())
    monkeypatch.setattr(gate.rolling24, "build_windows", lambda frame, obs: base)
    import src.model.anchor as anchor
    monkeypatch.setattr(anchor, "anchor_frame", lambda frame: frame)

    data, coverage = gate.build_experiment(pd.DataFrame())
    assert len(data) == 1
    assert coverage == 1.0


def test_reconcile_failures_drops_dates_completed_on_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(gfs, "BY_INIT_DIR", tmp_path / "by_init")
    monkeypatch.setattr(gfs, "PROVENANCE_DIR", tmp_path / "provenance")
    monkeypatch.setattr(gfs, "REGISTRY", tmp_path / "stations.csv")
    pd.DataFrame({"station_id": ["a"]}).to_csv(gfs.REGISTRY, index=False)
    date = pd.Timestamp("2025-02-19", tz="UTC")
    path = gfs._expected_init_path(date)
    path.parent.mkdir(parents=True)
    pd.DataFrame({
        "init_date": ["2025-02-19"] * len(gfs.FORECAST_HOURS),
        "station_id": ["a"] * len(gfs.FORECAST_HOURS),
        "lead_h": gfs.FORECAST_HOURS,
        "init_time": ["2025-02-19T12:00:00Z"] * len(gfs.FORECAST_HOURS),
        "valid_time": pd.to_datetime("2025-02-19T12:00:00Z")
        + pd.to_timedelta(gfs.FORECAST_HOURS, unit="h"),
        **{name: np.ones(len(gfs.FORECAST_HOURS)) for name in [
            *gfs.FIELD_SPECS, "gfs_wind", "gfs_ventilation",
            "gfs_dewpoint_depression",
        ]},
    }).to_csv(path, index=False)
    provenance = gfs._expected_provenance_path(date)
    provenance.parent.mkdir(parents=True)
    provenance.write_text("{}")

    failures = [{"date": "2025-02-19", "error": "transient"}]
    assert gfs.reconcile_failures(failures) == []
