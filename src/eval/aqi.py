"""Indian AQI PM2.5 category utilities + event-detection metrics.

CPCB PM2.5 sub-index breakpoints (24 h averaging in the official AQI; we apply
them to whatever averaging window the caller provides and report the window):

    Good          0-30
    Satisfactory  31-60
    Moderate      61-90
    Poor          91-120
    Very Poor     121-250
    Severe        >250

The benchmark's headline event is "Very Poor or above" (>=121), the band where
GRAP-style forecast-triggered action begins and where global models fail.

Run tests: python -m src.eval.aqi
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Upper bounds of each band (last is open-ended).
BREAKPOINTS = [30.0, 60.0, 90.0, 120.0, 250.0, np.inf]
CATEGORIES = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]
VERY_POOR_THRESHOLD = 121.0  # obs >= this = "Very Poor or above" event
SEVERE_THRESHOLD = 251.0


def category_index(pm25) -> np.ndarray:
    """Map PM2.5 (ug/m3) to band index 0..5 (vectorised)."""
    x = np.asarray(pm25, dtype=float)
    return np.digitize(x, BREAKPOINTS[:-1], right=True)


def category_name(pm25) -> np.ndarray:
    return np.asarray(CATEGORIES)[category_index(pm25)]


def category_metrics(obs, pred) -> dict[str, float | int]:
    """Category + event-detection metrics for paired obs/pred PM2.5 arrays.

    Returns:
      n              sample count (NaN pairs dropped)
      cat_hit_rate   exact 6-band accuracy
      cat_adjacent   accuracy within +/-1 band
      event_*        Very Poor+ (>=121): contingency counts, pod, far,
                       miss_rate, csi, base_rate
    """
    obs = np.asarray(obs, dtype=float)
    pred = np.asarray(pred, dtype=float)
    m = np.isfinite(obs) & np.isfinite(pred)
    obs, pred = obs[m], pred[m]
    n = obs.size
    if n == 0:
        return {"n": 0}

    ci_o, ci_p = category_index(obs), category_index(pred)
    out = {
        "n": int(n),
        "cat_hit_rate": float((ci_o == ci_p).mean()),
        "cat_adjacent": float((np.abs(ci_o - ci_p) <= 1).mean()),
    }

    # Very Poor+ event detection (contingency table).
    eo = obs >= VERY_POOR_THRESHOLD
    ep = pred >= VERY_POOR_THRESHOLD
    hits = int((eo & ep).sum())
    misses = int((eo & ~ep).sum())
    false_alarms = int((~eo & ep).sum())
    out["event_hits"] = hits
    out["event_misses"] = misses
    out["event_false_alarms"] = false_alarms
    out["event_observed"] = hits + misses
    out["event_forecast"] = hits + false_alarms
    out["event_base_rate"] = float(eo.mean())
    out["event_pod"] = hits / (hits + misses) if (hits + misses) else np.nan
    out["event_far"] = false_alarms / (hits + false_alarms) if (hits + false_alarms) else np.nan
    out["event_miss_rate"] = misses / (hits + misses) if (hits + misses) else np.nan
    denom = hits + misses + false_alarms
    out["event_csi"] = hits / denom if denom else np.nan
    return out


def brier_score(event_obs, prob_pred) -> float:
    """Brier score for probabilistic Very Poor+ forecasts (lower is better)."""
    y = np.asarray(event_obs, dtype=float)
    p = np.asarray(prob_pred, dtype=float)
    m = np.isfinite(y) & np.isfinite(p)
    return float(np.mean((p[m] - y[m]) ** 2)) if m.any() else np.nan


def daily_mean(df: pd.DataFrame, value_col: str, time_col: str = "timestamp_utc",
               min_hours: int = 12) -> pd.DataFrame:
    """24h means per station-day (official AQI averaging), requiring coverage."""
    d = df.copy()
    d["date"] = pd.to_datetime(d[time_col], utc=True).dt.floor("D")
    g = d.groupby(["station_id", "date"])[value_col].agg(["mean", "count"]).reset_index()
    g = g[g["count"] >= min_hours].rename(columns={"mean": value_col})
    return g.drop(columns="count")


def _test() -> None:
    # Band edges land where CPCB says they should.
    assert list(category_name([15, 45, 75, 105, 200, 300])) == CATEGORIES
    assert category_name([30])[0] == "Good" and category_name([30.1])[0] == "Satisfactory"
    assert category_name([250])[0] == "Very Poor" and category_name([250.1])[0] == "Severe"

    # Perfect forecast: all hit, no misses/false alarms.
    obs = np.array([20, 80, 150, 300, 50.0])
    m = category_metrics(obs, obs)
    assert m["cat_hit_rate"] == 1.0 and m["event_pod"] == 1.0 and m["event_far"] == 0.0

    # The Phase-2 failure mode: predict 86 when obs is 290 -> missed Severe event.
    m = category_metrics([290.0], [86.0])
    assert m["event_pod"] == 0.0 and m["event_miss_rate"] == 1.0 and m["cat_hit_rate"] == 0.0

    # Adjacent-band credit: obs Poor (105) vs pred Moderate (85).
    m = category_metrics([105.0], [85.0])
    assert m["cat_hit_rate"] == 0.0 and m["cat_adjacent"] == 1.0

    # Brier: perfect confidence right/wrong.
    assert brier_score([1, 0], [1.0, 0.0]) == 0.0
    assert brier_score([1], [0.0]) == 1.0

    # NaNs dropped.
    assert category_metrics([np.nan, 100], [50, 100])["n"] == 1
    print("aqi.py: all tests passed")


if __name__ == "__main__":
    _test()
