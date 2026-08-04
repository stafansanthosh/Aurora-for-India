"""Forward-24-hour PM2.5 headline evaluation.

Forecast windows follow ``docs/PRODUCT_SPEC.md``: for a window starting at
lead ``s``, integrate the three 12-hour snapshots with trapezoidal weights,
``(v_s + 2*v_s+12 + v_s+24) / 4``. Observation targets are hourly means over
``[start, end)`` and require at least 12 of 24 hours. Windows crossing the
temporal split cutoff are excluded.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import aqi, benchmark as bench
from ..splits import HELDOUT_CITIES, SPLIT_CUTOFF, l1_is_holdout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = PROJECT_ROOT / "results" / "metrics" / "indiaaqbench_24h.csv"
WINDOW_STARTS = tuple(range(0, 73, 12))
MIN_OBS_HOURS = 12


def _forecast_columns(frame: pd.DataFrame) -> dict[str, str]:
    return bench.active_methods(frame)


def build_windows(
    frame: pd.DataFrame,
    obs: pd.DataFrame,
    min_obs_hours: int = MIN_OBS_HOURS,
) -> pd.DataFrame:
    """Return one row per init/station/24-hour window with all methods."""
    if not 1 <= min_obs_hours <= 24:
        raise ValueError("min_obs_hours must be between 1 and 24")

    obs_values = {
        (str(r.station_id), pd.Timestamp(r.timestamp_utc)): float(r.obs_pm25)
        for r in obs.itertuples(index=False)
        if np.isfinite(r.obs_pm25)
    }
    methods = _forecast_columns(frame)
    keys = ["init_date", "station_id"]
    metadata = (frame.sort_values("lead_h").drop_duplicates(keys)
                .set_index(keys)[["city", "init_time"]])
    wide = {
        method: frame.pivot(index=keys, columns="lead_h", values=column)
        for method, column in methods.items()
    }
    cams0 = frame.pivot(index=keys, columns="lead_h", values="cams_pm25")[0]

    windows = []
    for start_h in WINDOW_STARTS:
        part = metadata.reset_index().copy()
        part["init_date"] = part["init_date"].astype(str)
        part["window_start_h"] = start_h
        part["lead_h"] = start_h
        part["window_start"] = pd.to_datetime(part["init_time"], utc=True) + pd.Timedelta(hours=start_h)
        part["window_end"] = part["window_start"] + pd.Timedelta(hours=24)
        crossing = (part["window_start"] < SPLIT_CUTOFF) & (SPLIT_CUTOFF < part["window_end"])
        part = part[~crossing].copy()
        part["is_test"] = part["window_start"] >= SPLIT_CUTOFF
        part["spatial_tier"] = np.where(
            part["city"].astype(str).str.lower().isin(HELDOUT_CITIES), "l2",
            np.where(part["station_id"].map(l1_is_holdout), "l1", "train_pool"),
        )

        index = pd.MultiIndex.from_frame(part[keys])
        for method, column in methods.items():
            source = wide[method]
            first = cams0 if method == "cams_forecast" and start_h == 0 else source[start_h]
            values = (
                first.reindex(index).to_numpy(float)
                + 2 * source[start_h + 12].reindex(index).to_numpy(float)
                + source[start_h + 24].reindex(index).to_numpy(float)
            ) / 4
            part[column] = values

        observed_means = []
        for station_id, start in zip(part["station_id"], part["window_start"]):
            observed = [
                obs_values.get((str(station_id), pd.Timestamp(hour)))
                for hour in pd.date_range(start, periods=24, freq="h")
            ]
            finite_obs = [v for v in observed if v is not None and np.isfinite(v)]
            observed_means.append(
                float(np.mean(finite_obs))
                if len(finite_obs) >= min_obs_hours else np.nan
            )
        part["obs_pm25"] = observed_means
        windows.append(part)
    return pd.concat(windows, ignore_index=True)


def score_windows(windows: pd.DataFrame) -> pd.DataFrame:
    """Per-city and pooled temporal/L1/L2 window metrics."""
    rows = []
    methods = _forecast_columns(windows)

    groups: list[tuple[str, str, str, pd.DataFrame]] = []
    for split, split_frame in windows.groupby("is_test"):
        split_name = "test" if split else "train"
        for city, group in split_frame.groupby("city"):
            groups.append((f"city:{city}", split_name, str(city), group))
    test = windows[windows["is_test"]]
    groups.extend([
        ("pooled_test", "test", "all", test),
        ("train_city_test", "test", "train_pool",
         test[test["spatial_tier"] == "train_pool"]),
        ("l1_test", "test", "l1", test[test["spatial_tier"] == "l1"]),
        ("l2_test", "test", "l2", test[test["spatial_tier"] == "l2"]),
    ])

    for scope, split, city, scoped in groups:
      for start_h, group in scoped.groupby("window_start_h"):
        obs_values = group["obs_pm25"].to_numpy(float)
        for method, column in methods.items():
            pred_values = group[column].to_numpy(float)
            keep = np.isfinite(obs_values) & np.isfinite(pred_values)
            obs_kept, pred_kept = obs_values[keep], pred_values[keep]
            rec = {"scope": scope, "split": split, "window_start_h": int(start_h),
                   "city": city, "method": method}
            rec.update(bench._regression(obs_kept, pred_kept))
            rec.update(aqi.category_metrics(obs_kept, pred_kept))
            rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="IndiaAQBench 24-hour headline evaluator")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--anchor", action="store_true")
    args = parser.parse_args()

    frame = bench.add_climatology(bench.build_frame())
    if args.anchor:
        from ..model.anchor import anchor_frame
        frame = anchor_frame(frame)
    windows = build_windows(frame, bench.load_obs())
    metrics = score_windows(windows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.out, index=False)
    matched = int(windows["obs_pm25"].notna().sum())
    print(f"Built {len(windows):,} forecast windows; {matched:,} have >=12 observation hours.")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
