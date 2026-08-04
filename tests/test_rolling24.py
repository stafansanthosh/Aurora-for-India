from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.eval.rolling24 import build_windows, score_windows


def _frame(init: str = "2026-01-01") -> pd.DataFrame:
    init_time = pd.Timestamp(init, tz="UTC") + pd.Timedelta(hours=12)
    rows = []
    for lead in range(0, 97, 12):
        rows.append({
            "init_date": init,
            "init_time": init_time,
            "valid_time": init_time + pd.Timedelta(hours=lead),
            "station_id": 1,
            "city": "patna",
            "lead_h": lead,
            "aurora_pm2p5": float(lead),
            "persist_pm25": 20.0,
            "cams_pm25": 10.0,
            "cams_forecast_pm25": np.nan if lead == 0 else float(lead + 1),
        })
    return pd.DataFrame(rows)


def _obs(init: str = "2026-01-01", hours: int = 120) -> pd.DataFrame:
    start = pd.Timestamp(init, tz="UTC") + pd.Timedelta(hours=12)
    return pd.DataFrame({
        "station_id": 1,
        "timestamp_utc": pd.date_range(start, periods=hours, freq="h"),
        "obs_pm25": 100.0,
    })


def test_trapezoidal_forecast_and_cams_lead_zero_bridge() -> None:
    out = build_windows(_frame(), _obs())
    first = out[out.window_start_h == 0].iloc[0]
    assert first.aurora_pm2p5 == pytest.approx((0 + 2 * 12 + 24) / 4)
    assert first.cams_forecast_pm25 == pytest.approx((10 + 2 * 13 + 25) / 4)
    assert first.obs_pm25 == 100.0


def test_observation_coverage_is_required() -> None:
    obs = _obs(hours=11)
    out = build_windows(_frame(), obs, min_obs_hours=12)
    assert np.isnan(out.loc[out.window_start_h == 0, "obs_pm25"]).all()


def test_windows_crossing_cutoff_are_excluded() -> None:
    out = build_windows(_frame("2025-11-30"), _obs("2025-11-30"))
    assert 0 not in set(out.window_start_h)
    assert 12 in set(out.window_start_h)


def test_invalid_coverage_requirement_is_rejected() -> None:
    with pytest.raises(ValueError, match="between 1 and 24"):
        build_windows(_frame(), _obs(), min_obs_hours=0)


def test_scorecard_contains_pooled_and_l2_scopes() -> None:
    frame = _frame()
    windows = build_windows(frame, _obs())
    metrics = score_windows(windows)
    assert "pooled_test" in set(metrics.scope)
    # Patna is not held out, so this fixture contributes train-pool test rows.
    assert "train_city_test" in set(metrics.scope)
