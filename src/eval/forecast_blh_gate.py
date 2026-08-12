"""Score NOAA GFS boundary-layer degradation under the pre-declared gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import aqi, benchmark as bench, rolling24
from .blh_ceiling_test import out_of_fold
from .diagnose_events import auc, best_threshold
from ..data import gfs_boundary_layer as gfs

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ERA5_SAMPLES = PROJECT_ROOT / "data" / "era5_blh" / "era5_blh_stations.csv"
RESULT_DIR = PROJECT_ROOT / "results" / "forecast_blh"
RAW_OUT = RESULT_DIR / "gfs_blh_degradation.csv"
EPISODE_OUT = RESULT_DIR / "gfs_blh_episode_skill.csv"
VERDICT_OUT = RESULT_DIR / "gfs_blh_gate.json"
POINT_LEADS = (24, 48, 72, 96)
WINDOW_STARTS = rolling24.WINDOW_STARTS
THRESH = aqi.VERY_POOR_THRESHOLD

CURRENT_FEATURES = [
    "persist_pm25", "month", "window_start_h", "aurora_pm2p5", "cams_forecast_pm25"
]
SOURCE_FEATURES = [
    "blh_min", "blh_mean", "ventilation_min", "ventilation_mean",
    "dewpoint_depression_mean",
]


def _score_binary(y: np.ndarray, pred: np.ndarray) -> tuple[float, float]:
    return float(auc(y, pred)), float(best_threshold(y, pred)[0])


def _regression(obs: np.ndarray, pred: np.ndarray) -> dict[str, float | int]:
    keep = np.isfinite(obs) & np.isfinite(pred)
    o, p = obs[keep], pred[keep]
    if len(o) == 0:
        return {"n": 0, "bias_m": np.nan, "rmse_m": np.nan, "corr": np.nan}
    corr = float(np.corrcoef(o, p)[0, 1]) if len(o) > 1 and np.std(o) and np.std(p) else np.nan
    return {
        "n": int(len(o)),
        "bias_m": float(np.mean(p - o)),
        "rmse_m": float(np.sqrt(np.mean((p - o) ** 2))),
        "corr": corr,
    }


def load_matched() -> tuple[pd.DataFrame, dict[str, Any]]:
    forecast = pd.read_csv(gfs.SAMPLES)
    validation = gfs.validate_samples(forecast)
    forecast["station_id"] = forecast["station_id"].astype(str)
    forecast["valid_time"] = pd.to_datetime(forecast["valid_time"], utc=True)
    forecast["init_time"] = pd.to_datetime(forecast["init_time"], utc=True)

    analysis = pd.read_csv(ERA5_SAMPLES, usecols=[
        "station_id", "valid_time", "era5_blh", "era5_ventilation",
        "era5_dewpoint_depression",
    ])
    analysis["station_id"] = analysis["station_id"].astype(str)
    analysis["valid_time"] = pd.to_datetime(analysis["valid_time"], utc=True)
    if analysis.duplicated(["station_id", "valid_time"]).any():
        raise ValueError("ERA5 station samples contain duplicate exact-time keys")

    matched = forecast.merge(
        analysis, on=["station_id", "valid_time"], how="left", validate="many_to_one"
    )
    required = ["era5_blh", "era5_ventilation", "era5_dewpoint_depression"]
    if matched[required].isna().any().any():
        missing = int(matched[required].isna().any(axis=1).sum())
        raise ValueError(f"ERA5 exact-time match is missing for {missing:,} GFS rows")

    dates = pd.read_csv(gfs.DATES_FILE)
    dates["init_date"] = dates["init_date"].astype(str)
    matched = matched.merge(
        dates[["init_date", "season"]], on="init_date", how="left", validate="many_to_one"
    )
    if matched["season"].isna().any():
        raise ValueError("one or more GFS dates lack a frozen season label")
    return matched, validation


def raw_degradation(matched: pd.DataFrame) -> pd.DataFrame:
    point = matched[matched["lead_h"].isin(POINT_LEADS)].copy()
    rows = []
    groups: list[tuple[str, str, int, pd.DataFrame]] = []
    for lead, group in point.groupby("lead_h"):
        groups.append(("pooled", "all", int(lead), group))
    for (city, lead), group in point.groupby(["city", "lead_h"]):
        groups.append(("city", str(city), int(lead), group))
    for (season, lead), group in point.groupby(["season", "lead_h"]):
        groups.append(("season", str(season), int(lead), group))
    for scope, label, lead, group in groups:
        rec = {"scope": scope, "label": label, "lead_h": lead}
        rec.update(_regression(
            group["era5_blh"].to_numpy(float), group["gfs_blh"].to_numpy(float)
        ))
        rows.append(rec)
    return pd.DataFrame(rows)


def _window_aggregates(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Eight-sample, three-hour source aggregates for every target window."""
    source = frame.copy()
    rows = []
    for start in WINDOW_STARTS:
        subset = source[(source["lead_h"] >= start) & (source["lead_h"] < start + 24)]
        grouped = subset.groupby(["init_date", "station_id"], as_index=False).agg(
            sample_count=(f"{prefix}_blh", "count"),
            blh_min=(f"{prefix}_blh", "min"),
            blh_mean=(f"{prefix}_blh", "mean"),
            ventilation_min=(f"{prefix}_ventilation", "min"),
            ventilation_mean=(f"{prefix}_ventilation", "mean"),
            dewpoint_depression_mean=(f"{prefix}_dewpoint_depression", "mean"),
        )
        grouped = grouped[grouped["sample_count"] == 8].drop(columns="sample_count")
        grouped["window_start_h"] = int(start)
        grouped = grouped.rename(columns={
            name: f"{prefix}_{name}" for name in SOURCE_FEATURES
        })
        rows.append(grouped)
    return pd.concat(rows, ignore_index=True)


def build_experiment(matched: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    from ..model.anchor import anchor_frame

    gfs_agg = _window_aggregates(matched, "gfs")
    era5_agg = _window_aggregates(matched, "era5")

    frame = anchor_frame(bench.add_climatology(bench.build_frame()))
    windows = rolling24.build_windows(frame, bench.load_obs())
    base = windows[(~windows["is_test"]) & (windows["spatial_tier"] == "train_pool")]
    base = base[np.isfinite(base["obs_pm25"])].copy()
    base["init_date"] = base["init_date"].astype(str)
    base["station_id"] = base["station_id"].astype(str)
    base["month"] = pd.to_datetime(base["window_start"], utc=True).dt.month
    # "Otherwise eligible" in the contract means rows eligible for the
    # current comparator.  Do not charge GFS for Aurora/CAMS gaps that already
    # exclude a row from every feature-set comparison.
    base = base.dropna(subset=CURRENT_FEATURES + ["obs_pm25"]).reset_index(drop=True)
    eligible = len(base)

    data = base.merge(
        era5_agg, on=["init_date", "station_id", "window_start_h"], how="left",
        validate="one_to_one",
    ).merge(
        gfs_agg, on=["init_date", "station_id", "window_start_h"], how="left",
        validate="one_to_one",
    )
    required = CURRENT_FEATURES + [
        f"{source}_{feature}" for source in ("era5", "gfs") for feature in SOURCE_FEATURES
    ]
    data = data.dropna(subset=required + ["obs_pm25"]).reset_index(drop=True)
    return data, len(data) / eligible if eligible else 0.0


def decide(
    coverage_valid: bool,
    delta_auc: float,
    delta_csi: float,
    city_gains: dict[str, dict[str, float | int]],
) -> str:
    if not coverage_valid:
        return "INDETERMINATE - COVERAGE"
    holds = any(
        city.lower() != "delhi"
        and int(values["events"]) >= 50
        and float(values["delta_auc"]) > 0
        and float(values["delta_csi"]) > 0
        for city, values in city_gains.items()
    )
    if delta_auc >= 0.020 and delta_csi >= 0.030 and holds:
        return "FREE NWP SUFFICIENT - do not run Aurora 1.5"
    if delta_auc < 0.010:
        return (
            "FREE NWP INSUFFICIENT - bounded Aurora 1.5 BLH pilot scientifically "
            "justified, not automatically authorized"
        )
    return "AMBIGUOUS - no GPU yet"


def episode_skill(
    data: pd.DataFrame,
    validation: dict[str, Any],
    window_coverage: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    y = (data["obs_pm25"] >= THRESH).to_numpy()
    groups = data["init_date"].to_numpy()
    features = {
        "current": CURRENT_FEATURES,
        "+ERA5 3-hour boundary layer": CURRENT_FEATURES + [
            f"era5_{name}" for name in SOURCE_FEATURES
        ],
        "+GFS forecast boundary layer": CURRENT_FEATURES + [
            f"gfs_{name}" for name in SOURCE_FEATURES
        ],
    }
    predictions = {
        name: out_of_fold(data, columns, y, groups) for name, columns in features.items()
    }
    rows = []
    pooled: dict[str, tuple[float, float]] = {}
    for name, pred in predictions.items():
        a, c = _score_binary(y, pred)
        pooled[name] = (a, c)
        rows.append({
            "scope": "pooled", "label": "all", "window_end_h": "all",
            "feature_set": name, "n": len(data), "events": int(y.sum()),
            "auc": a, "best_csi": c,
        })

    city_gains: dict[str, dict[str, float | int]] = {}
    current_pred = predictions["current"]
    gfs_pred = predictions["+GFS forecast boundary layer"]
    for city, indexes in data.groupby("city").groups.items():
        idx = np.asarray(list(indexes), dtype=int)
        city_y = y[idx]
        if int(city_y.sum()) < 10 or int((~city_y).sum()) == 0:
            rows.append({
                "scope": "city", "label": str(city), "window_end_h": "all",
                "feature_set": "too few events", "n": len(idx),
                "events": int(city_y.sum()), "auc": np.nan, "best_csi": np.nan,
            })
            continue
        cur_a, cur_c = _score_binary(city_y, current_pred[idx])
        new_a, new_c = _score_binary(city_y, gfs_pred[idx])
        rows.extend([
            {"scope": "city", "label": str(city), "window_end_h": "all",
             "feature_set": "current", "n": len(idx), "events": int(city_y.sum()),
             "auc": cur_a, "best_csi": cur_c},
            {"scope": "city", "label": str(city), "window_end_h": "all",
             "feature_set": "+GFS forecast boundary layer", "n": len(idx),
             "events": int(city_y.sum()), "auc": new_a, "best_csi": new_c},
        ])
        city_gains[str(city)] = {
            "events": int(city_y.sum()), "delta_auc": new_a - cur_a,
            "delta_csi": new_c - cur_c,
        }

    for start, end in zip((0, 24, 48, 72), POINT_LEADS):
        idx = np.flatnonzero(data["window_start_h"].to_numpy(int) == start)
        lead_y = y[idx]
        if int(lead_y.sum()) == 0 or int((~lead_y).sum()) == 0:
            continue
        for name, pred in predictions.items():
            a, c = _score_binary(lead_y, pred[idx])
            rows.append({
                "scope": "window_end", "label": f"+{end}h", "window_end_h": end,
                "feature_set": name, "n": len(idx), "events": int(lead_y.sum()),
                "auc": a, "best_csi": c,
            })

    current = pooled["current"]
    era5 = pooled["+ERA5 3-hour boundary layer"]
    forecast = pooled["+GFS forecast boundary layer"]
    delta_auc = forecast[0] - current[0]
    delta_csi = forecast[1] - current[1]
    era5_delta_auc = era5[0] - current[0]
    era5_delta_csi = era5[1] - current[1]

    dates = pd.read_csv(gfs.DATES_FILE)
    train = dates[pd.to_datetime(dates["init_date"], utc=True) < gfs.SPLIT_CUTOFF]
    present_dates = set(data["init_date"].astype(str))
    present_seasons = set(train[train["init_date"].astype(str).isin(present_dates)]["season"])
    expected_seasons = set(train["season"])
    coverage_valid = (
        int(validation["complete_dates"]) >= 29
        and present_seasons == expected_seasons
        and window_coverage >= 0.95
    )
    verdict = decide(coverage_valid, delta_auc, delta_csi, city_gains)
    summary = {
        "contract": "docs/FORECAST_BLH_CONTRACT.md",
        "population": {
            "n": len(data), "events": int(y.sum()),
            "dates": len(present_dates), "window_coverage": window_coverage,
            "seasons": sorted(present_seasons), "coverage_valid": coverage_valid,
        },
        "scores": {
            name: {"auc": values[0], "best_csi": values[1]}
            for name, values in pooled.items()
        },
        "gfs_gain": {"delta_auc": delta_auc, "delta_csi": delta_csi},
        "era5_3h_gain": {"delta_auc": era5_delta_auc, "delta_csi": era5_delta_csi},
        "retention": {
            "auc": delta_auc / era5_delta_auc if era5_delta_auc > 0 else None,
            "csi": delta_csi / era5_delta_csi if era5_delta_csi > 0 else None,
        },
        "city_gains": city_gains,
        "verdict": verdict,
    }
    return pd.DataFrame(rows), summary


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    raise TypeError(type(value).__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-out", type=Path, default=RAW_OUT)
    parser.add_argument("--episode-out", type=Path, default=EPISODE_OUT)
    parser.add_argument("--verdict-out", type=Path, default=VERDICT_OUT)
    args = parser.parse_args()

    matched, validation = load_matched()
    raw = raw_degradation(matched)
    data, window_coverage = build_experiment(matched)
    episode, summary = episode_skill(data, validation, window_coverage)

    for path in (args.raw_out, args.episode_out, args.verdict_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(args.raw_out, index=False)
    episode.to_csv(args.episode_out, index=False)
    args.verdict_out.write_text(
        json.dumps(summary, indent=2, default=_json_default), encoding="utf-8"
    )

    print("\nRAW GFS BLH VS ERA5 (pooled)")
    print(raw[raw["scope"] == "pooled"].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nEPISODE SKILL (pooled; train-only OOF; Delhi-dominated)")
    print(episode[episode["scope"] == "pooled"].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nDECISION")
    print(json.dumps(summary, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
