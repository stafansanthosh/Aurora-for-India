"""Phase 2 evaluation: Aurora-predicted PM2.5 vs OpenAQ ground truth.

Reads a saved AuroraAirPollution prediction (Batch.to_netcdf output), extracts
the predicted surface PM2.5 field, samples it at each OpenAQ station's nearest
0.4 deg grid cell, and compares against the station reading at the forecast's
valid time. Also reports the persistence baseline (the input PM2.5 at analysis
time) when available.

The 0.4 air-pollution checkpoint uses a 12h step: a batch built at UTC 12
predicts UTC 00 the next day. The prediction NetCDF's ``time`` coord carries the
valid time; we match OpenAQ to it.

Usage:
    python -m src.eval.run_phase2 --city delhi \
        --pred results/aurora_pred_2025-11-15.nc
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from ..data.openaq_client import CITIES
from ..utils.geo import find_nearest_grid_cell

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAQ_DIR = PROJECT_ROOT / "data" / "openaq"
METRICS_DIR = PROJECT_ROOT / "results" / "metrics"

KG_PER_M3_TO_UG_PER_M3 = 1e9
# Tolerance for matching an OpenAQ hour to the forecast valid time.
MATCH_TOLERANCE = pd.Timedelta("90min")


def _pm25_field(pred_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.Timestamp]:
    """Return (pm25_ugm3 [H,W], lats, lons, valid_time) from a prediction file."""
    ds = xr.open_dataset(pred_path)
    da = ds["surf_pm2p5"]
    # dims (batch, history, latitude, longitude) -> take batch 0, last history.
    arr = da.isel(batch=0, history=-1).values
    pm = np.asarray(arr, dtype=np.float32) * KG_PER_M3_TO_UG_PER_M3
    lats = ds["latitude"].values
    lons = ds["longitude"].values
    times = pd.to_datetime(np.atleast_1d(ds["time"].values))
    valid = pd.Timestamp(times[-1])
    if valid.tzinfo is None:
        valid = valid.tz_localize("UTC")
    return pm, lats, lons, valid


def evaluate(city: str, pred_path: Path, openaq_path: Path | None = None) -> pd.DataFrame:
    pm, lats, lons, valid = _pm25_field(pred_path)
    print(f"Prediction valid time: {valid}  (grid {pm.shape}, "
          f"pm2p5 {np.nanmin(pm):.1f}-{np.nanmax(pm):.1f} ug/m3)")

    openaq_path = openaq_path or OPENAQ_DIR / f"{city}_pm25.csv"
    obs = pd.read_csv(openaq_path, parse_dates=["timestamp_utc"])
    obs["timestamp_utc"] = pd.to_datetime(obs["timestamp_utc"], utc=True)

    # Aurora lon is 0-360; OpenAQ lon is -180..180 -> convert station lon.
    rows = []
    for sid, g in obs.groupby("station_id"):
        slat = float(g["lat"].iloc[0])
        slon = float(g["lon"].iloc[0]) % 360.0
        li, loi, dist = find_nearest_grid_cell(slat, slon, lats, lons)
        pred_val = float(pm[li, loi])

        # OpenAQ reading nearest the forecast valid time, within tolerance.
        g = g.assign(dt=(g["timestamp_utc"] - valid).abs()).sort_values("dt")
        nearest = g.iloc[0]
        if nearest["dt"] > MATCH_TOLERANCE:
            continue
        obs_val = float(nearest["value_ugm3"])
        rows.append({
            "station_id": sid,
            "station_name": g["station_name"].iloc[0],
            "aurora_pm25": round(pred_val, 1),
            "openaq_pm25": round(obs_val, 1),
            "abs_error": round(abs(pred_val - obs_val), 1),
            "dist_km": round(dist, 1),
        })

    res = pd.DataFrame(rows)
    return res.sort_values("abs_error").reset_index(drop=True) if not res.empty else res


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 2 Aurora-vs-OpenAQ evaluation.")
    p.add_argument("--city", required=True, choices=sorted(CITIES))
    p.add_argument("--pred", type=Path, required=True, help="Aurora prediction NetCDF.")
    p.add_argument("--openaq", type=Path, default=None)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    res = evaluate(args.city, args.pred, args.openaq)
    if res.empty:
        print("No OpenAQ station matched the forecast valid time within tolerance.")
        return
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    out = METRICS_DIR / f"{args.city}_phase2.csv"
    res.to_csv(out, index=False)
    mae = float(res["abs_error"].mean())
    print(f"\n=== Phase 2: Aurora PM2.5 vs OpenAQ - {args.city} ===")
    print(res.to_string(index=False))
    print(f"\nStations: {len(res)}   Mean absolute error: {mae:.1f} ug/m3")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
