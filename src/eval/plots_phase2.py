"""Phase 2 visualisation: Aurora predicted PM2.5 over India vs OpenAQ stations.

Two figures:
  1. Aurora's predicted surface PM2.5 field over India (0.4 deg) with OpenAQ
     station readings overlaid as coloured dots on the same scale -- shows the
     model's smooth, low field against the high point observations.
  2. Per-station bar comparison: Aurora vs OpenAQ.

Usage:
    python -m src.eval.plots_phase2 --city delhi --pred results/aurora_pred_2025-11-15.nc
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

from ..utils.geo import find_nearest_grid_cell  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAQ_DIR = PROJECT_ROOT / "data" / "openaq"
PLOTS_DIR = PROJECT_ROOT / "results" / "plots"
KG_TO_UG = 1e9
INDIA = dict(lat=(6, 37), lon=(68, 98))


def _load(pred_path: Path, city: str):
    ds = xr.open_dataset(pred_path)
    pm = ds["surf_pm2p5"].isel(batch=0, history=-1).values * KG_TO_UG
    lats, lons = ds["latitude"].values, ds["longitude"].values
    valid = pd.Timestamp(pd.to_datetime(np.atleast_1d(ds["time"].values))[-1])
    obs = pd.read_csv(OPENAQ_DIR / f"{city}_pm25.csv", parse_dates=["timestamp_utc"])
    obs["timestamp_utc"] = pd.to_datetime(obs["timestamp_utc"], utc=True)
    if valid.tzinfo is None:
        valid = valid.tz_localize("UTC")
    return pm, lats, lons, valid, obs


def plot_india_map(pred_path: Path, city: str) -> Path:
    pm, lats, lons, valid, obs = _load(pred_path, city)
    la = (lats >= INDIA["lat"][0]) & (lats <= INDIA["lat"][1])
    lo = (lons >= INDIA["lon"][0]) & (lons <= INDIA["lon"][1])
    sub = pm[np.ix_(la, lo)]
    sub_lats, sub_lons = lats[la], lons[lo]

    # Station readings nearest the valid time.
    obs = obs.assign(dt=(obs["timestamp_utc"] - valid).abs())
    near = obs.sort_values("dt").groupby("station_id").first().reset_index()
    near = near[near["dt"] <= pd.Timedelta("90min")]

    vmax = float(max(np.nanmax(sub), near["value_ugm3"].max())) if not near.empty else np.nanmax(sub)
    fig, ax = plt.subplots(figsize=(8, 8))
    mesh = ax.pcolormesh(sub_lons, sub_lats, np.clip(sub, 0, vmax),
                         shading="auto", cmap="YlOrRd", vmin=0, vmax=vmax)
    if not near.empty:
        ax.scatter(near["lon"] % 360, near["lat"], c=near["value_ugm3"],
                   cmap="YlOrRd", vmin=0, vmax=vmax, s=120, edgecolors="black",
                   linewidths=1.2, zorder=5, label="OpenAQ stations")
    fig.colorbar(mesh, ax=ax, label="PM2.5 (ug/m3)", shrink=0.8)
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.set_title(f"Aurora predicted PM2.5 over India vs OpenAQ\n{valid:%Y-%m-%d %H:%M} UTC "
                 f"(dots = station readings, same colour scale)")
    ax.legend(loc="lower left")
    out = PLOTS_DIR / f"{city}_phase2_india_map.png"
    fig.tight_layout(); fig.savefig(out, dpi=130); plt.close(fig)
    return out


def plot_station_bars(pred_path: Path, city: str) -> Path:
    pm, lats, lons, valid, obs = _load(pred_path, city)
    obs = obs.assign(dt=(obs["timestamp_utc"] - valid).abs())
    near = obs.sort_values("dt").groupby("station_id").first().reset_index()
    near = near[near["dt"] <= pd.Timedelta("90min")]
    rows = []
    for _, r in near.iterrows():
        li, loi, _ = find_nearest_grid_cell(float(r["lat"]), float(r["lon"]) % 360, lats, lons)
        rows.append({"station": str(r["station_name"])[:22],
                     "Aurora": float(pm[li, loi]), "OpenAQ": float(r["value_ugm3"])})
    df = pd.DataFrame(rows).sort_values("OpenAQ")
    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(df))
    ax.barh(y - 0.2, df["OpenAQ"], height=0.4, label="OpenAQ (observed)", color="#c0504d")
    ax.barh(y + 0.2, df["Aurora"], height=0.4, label="Aurora (predicted)", color="#4f81bd")
    ax.set_yticks(y); ax.set_yticklabels(df["station"], fontsize=8)
    ax.set_xlabel("PM2.5 (ug/m3)")
    ax.set_title(f"Aurora vs OpenAQ PM2.5 - {city}, {valid:%Y-%m-%d %H:%M} UTC")
    ax.legend()
    out = PLOTS_DIR / f"{city}_phase2_bars.png"
    fig.tight_layout(); fig.savefig(out, dpi=130); plt.close(fig)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Phase 2 Aurora-vs-OpenAQ plots.")
    p.add_argument("--city", required=True)
    p.add_argument("--pred", type=Path, required=True)
    args = p.parse_args()
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    print("wrote", plot_india_map(args.pred, args.city))
    print("wrote", plot_station_bars(args.pred, args.city))


if __name__ == "__main__":
    main()
