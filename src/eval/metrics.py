"""Evaluation metrics: MAE, RMSE, correlation, and skill vs persistence.

All functions take pandas Series so index alignment is automatic
(COPILOT_CONTEXT.md section 7.2 + coding conventions).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .baseline import persistence_forecast


def _aligned_nonnull(y_true: pd.Series, y_pred: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Inner-align two series on their index and drop rows with any NaN."""
    df = pd.concat({"t": y_true, "p": y_pred}, axis=1, join="inner").dropna()
    return df["t"], df["p"]


def compute_metrics(
    y_true: pd.Series, y_pred: pd.Series, label: str = "model"
) -> dict:
    """MAE / RMSE / correlation for a prediction, plus skill vs persistence.

    Skill = 1 - MAE(model) / MAE(persistence), computed on the same rows the
    model is scored on. Positive skill means the model beats naive persistence.
    Returns NaNs (not an exception) when there are too few overlapping points.
    """
    t, p = _aligned_nonnull(y_true, y_pred)
    n = len(t)
    if n == 0:
        return {"label": label, "n": 0, "MAE": np.nan, "RMSE": np.nan,
                "correlation": np.nan, "skill_vs_persistence": np.nan}

    mae = mean_absolute_error(t, p)
    rmse = float(np.sqrt(mean_squared_error(t, p)))
    corr = float(np.corrcoef(t, p)[0, 1]) if n > 1 else np.nan

    # Persistence scored on the same index as the model prediction.
    persist = persistence_forecast(y_true)
    pt, pp = _aligned_nonnull(y_true.loc[t.index], persist.loc[t.index])
    if len(pt) > 0:
        mae_persist = mean_absolute_error(pt, pp)
        skill = 1 - (mae / mae_persist) if mae_persist > 0 else np.nan
    else:
        skill = np.nan

    return {
        "label": label,
        "n": n,
        "MAE": float(mae),
        "RMSE": rmse,
        "correlation": corr,
        "skill_vs_persistence": float(skill) if skill == skill else np.nan,
    }
