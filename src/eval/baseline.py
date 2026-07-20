"""Naive baselines. Aurora/CAMS only add value if they beat these.

Persistence (COPILOT_CONTEXT.md section 7.1): predict t+1 = t.
"""
from __future__ import annotations

import pandas as pd


def persistence_forecast(pm25_series: pd.Series) -> pd.Series:
    """Predict each value as the previous timestep's value.

    The series should be time-ordered and hourly-regular for the shift to be
    meaningful. Returns a series aligned to the input index (first value NaN).
    """
    return pm25_series.shift(1)
