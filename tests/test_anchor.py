"""Tests for Component A (per-station trailing-ratio anchoring).

These pin *behaviour and safety*, deliberately not performance: no constant is
tuned against benchmark dates. The leakage tests are the important ones -- a
trailing correction that peeks at the future would look excellent and be
worthless.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.model.anchor import (
    ANCHORED_COL,
    RAW_COL,
    AnchorConfig,
    anchor_frame,
    estimate_multiplier,
)

T0 = pd.Timestamp("2025-11-15 12:00", tz="UTC")


def _row(station, valid_time, lead, raw, obs, init=None):
    init = init if init is not None else valid_time - pd.Timedelta(hours=lead)
    return {
        "init_date": init.strftime("%Y-%m-%d"),
        "init_time": init,
        "station_id": station,
        "city": "delhi",
        "lead_h": lead,
        RAW_COL: raw,
        "obs_pm25": obs,
        "valid_time": valid_time,
    }


def _hist(rows):
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Estimator
# --------------------------------------------------------------------------- #

def test_no_history_returns_neutral_multiplier():
    est = estimate_multiplier(pd.DataFrame(columns=["valid_time", "lead_h", RAW_COL,
                                                    "obs_pm25"]), T0)
    assert est.multiplier == 1.0
    assert est.n_samples == 0
    assert est.fallback is True
    assert np.isnan(est.obs_age_h)


def test_known_ratio_recovered_with_dense_history():
    # 20 samples all at obs/raw = 2.0; shrinkage weight 20/23 -> ~1.87.
    rows = [_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 50.0, 100.0)
            for i in range(20)]
    est = estimate_multiplier(_hist(rows), T0)
    assert est.n_samples == 20
    assert est.fallback is False
    expected = 1.0 + (20 / 23) * (2.0 - 1.0)
    assert est.multiplier == pytest.approx(expected)


def test_thin_history_shrinks_harder_than_dense_history():
    thin = _hist([_row(1, T0 - pd.Timedelta(hours=12), 12, 50.0, 100.0)])
    dense = _hist([_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 50.0, 100.0)
                   for i in range(20)])
    m_thin = estimate_multiplier(thin, T0).multiplier
    m_dense = estimate_multiplier(dense, T0).multiplier
    # Both point at ratio 2.0; the thin one must sit closer to the 1.0 prior.
    assert 1.0 < m_thin < m_dense < 2.0
    assert abs(m_thin - 1.0) < abs(m_dense - 1.0)


def test_multiplier_clipped_at_upper_bound():
    rows = [_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 1.0, 900.0)
            for i in range(30)]
    assert estimate_multiplier(_hist(rows), T0).multiplier == 3.0


def test_multiplier_clipped_at_lower_bound():
    rows = [_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 900.0, 1.0)
            for i in range(30)]
    assert estimate_multiplier(_hist(rows), T0).multiplier == pytest.approx(1.0 / 3.0)


# --------------------------------------------------------------------------- #
# Leakage
# --------------------------------------------------------------------------- #

def test_future_observations_never_influence_the_correction():
    future = [_row(1, T0 + pd.Timedelta(hours=12 * (i + 1)), 12, 50.0, 100.0)
              for i in range(20)]
    est = estimate_multiplier(_hist(future), T0)
    assert est.multiplier == 1.0 and est.fallback is True


def test_observation_exactly_at_init_is_excluded():
    # Not yet available when the forecast is issued -> strict `<`.
    est = estimate_multiplier(_hist([_row(1, T0, 12, 50.0, 100.0)]), T0)
    assert est.fallback is True and est.multiplier == 1.0


def test_history_older_than_window_is_ignored():
    old = [_row(1, T0 - pd.Timedelta(days=30 + i), 12, 50.0, 100.0) for i in range(10)]
    assert estimate_multiplier(_hist(old), T0).fallback is True


def test_only_short_leads_contribute():
    long_only = [_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 96, 50.0, 100.0)
                 for i in range(10)]
    assert estimate_multiplier(_hist(long_only), T0).fallback is True
    # lead 0 is the CAMS analysis (model input), not a forecast -> excluded too.
    lead0 = [_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 0, 50.0, 100.0)
             for i in range(10)]
    assert estimate_multiplier(_hist(lead0), T0).fallback is True


def test_station_histories_are_isolated():
    rows = [_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 50.0, 100.0)
            for i in range(20)]
    rows += [_row(2, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 50.0, 50.0)
             for i in range(20)]
    frame = _hist(rows + [_row(1, T0 + pd.Timedelta(hours=12), 12, 60.0, np.nan, init=T0),
                          _row(2, T0 + pd.Timedelta(hours=12), 12, 60.0, np.nan, init=T0)])
    out = anchor_frame(frame)
    now = out[out["init_time"] == T0].set_index("station_id")
    # Station 1 saw ratio 2.0, station 2 saw 1.0 -- neither may borrow.
    assert now.loc[1, "anchor_multiplier"] > 1.5
    assert now.loc[2, "anchor_multiplier"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Robustness
# --------------------------------------------------------------------------- #

def test_zero_nan_and_missing_values_are_handled_safely():
    rows = [
        _row(1, T0 - pd.Timedelta(hours=12), 12, 0.0, 100.0),      # zero Aurora
        _row(1, T0 - pd.Timedelta(hours=24), 12, np.nan, 100.0),   # NaN Aurora
        _row(1, T0 - pd.Timedelta(hours=36), 12, 50.0, np.nan),    # NaN obs
        _row(1, T0 - pd.Timedelta(hours=48), 12, -5.0, 100.0),     # negative Aurora
        _row(1, T0 - pd.Timedelta(hours=60), 12, 50.0, 100.0),     # the one good row
    ]
    est = estimate_multiplier(_hist(rows), T0)
    # A zero forecast is valid maximum-underprediction evidence; epsilon keeps
    # the ratio finite and the configured multiplier clip bounds the result.
    assert est.n_samples == 2
    assert np.isfinite(est.multiplier)
    assert est.multiplier == 3.0


def test_same_observation_from_two_cycles_counts_once():
    valid = T0 - pd.Timedelta(hours=12)
    rows = [
        _row(1, valid, 24, 20.0, 100.0),  # older cycle, ratio 5
        _row(1, valid, 12, 50.0, 100.0),  # newer cycle, ratio 2
    ]
    est = estimate_multiplier(_hist(rows), T0)
    assert est.n_samples == 1
    # The shorter-lead residual is retained, then one sample is shrunk by 1/4.
    assert est.multiplier == pytest.approx(1.25)


def test_raw_predictions_unchanged_and_anchored_non_negative():
    rows = [_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 50.0, 100.0)
            for i in range(5)]
    rows.append(_row(1, T0 + pd.Timedelta(hours=24), 24, 80.0, np.nan, init=T0))
    frame = _hist(rows)
    before = frame[RAW_COL].copy()
    out = anchor_frame(frame)
    pd.testing.assert_series_equal(out[RAW_COL], before, check_names=False)
    assert (out[ANCHORED_COL].dropna() >= 0).all()


def test_chronological_application_across_multiple_inits():
    """Each init may only use history verifying before it."""
    rows = []
    for i in range(6):  # six prior days of ratio-2 evidence
        vt = T0 - pd.Timedelta(days=6 - i)
        rows.append(_row(1, vt, 12, 50.0, 100.0))
    later = T0 + pd.Timedelta(days=1)
    rows.append(_row(1, T0 + pd.Timedelta(hours=12), 12, 70.0, 140.0, init=T0))
    rows.append(_row(1, later + pd.Timedelta(hours=12), 12, 70.0, np.nan, init=later))
    out = anchor_frame(_hist(rows))

    first = out[out["init_time"] == T0].iloc[0]
    second = out[out["init_time"] == later].iloc[0]
    # The later init sees strictly more evidence, so it is no less confident.
    assert second["anchor_n_samples"] > first["anchor_n_samples"]
    assert not bool(second["anchor_fallback"])


def test_diagnostics_counts_ages_and_fallback_status():
    rows = [_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 50.0, 100.0)
            for i in range(4)]
    rows.append(_row(1, T0 + pd.Timedelta(hours=12), 12, 60.0, np.nan, init=T0))
    out = anchor_frame(_hist(rows))
    now = out[out["init_time"] == T0].iloc[0]
    assert now["anchor_n_samples"] == 4
    assert now["anchor_obs_age_h"] == pytest.approx(12.0)  # newest supporting obs
    assert not bool(now["anchor_fallback"])

    # A station with no usable history reports the fallback honestly.
    lone = _hist([_row(9, T0 + pd.Timedelta(hours=12), 12, 60.0, np.nan, init=T0)])
    out2 = anchor_frame(lone)
    assert bool(out2.iloc[0]["anchor_fallback"])
    assert out2.iloc[0]["anchor_multiplier"] == 1.0
    assert out2.iloc[0]["anchor_n_samples"] == 0


def test_config_is_explicit_and_configurable():
    rows = [_row(1, T0 - pd.Timedelta(hours=12), 12, 50.0, 100.0)]
    weak = estimate_multiplier(_hist(rows), T0, AnchorConfig(prior_strength=0.0))
    strong = estimate_multiplier(_hist(rows), T0, AnchorConfig(prior_strength=50.0))
    assert weak.multiplier == pytest.approx(2.0)      # no shrinkage
    assert abs(strong.multiplier - 1.0) < 0.05        # heavy shrinkage
    tight = estimate_multiplier(
        _hist([_row(1, T0 - pd.Timedelta(hours=12 * (i + 1)), 12, 1.0, 900.0)
               for i in range(30)]), T0, AnchorConfig(max_multiplier=1.5))
    assert tight.multiplier == 1.5
