"""IndiaAQBench evaluation harness: score forecasts vs OpenAQ ground truth.

Joins the orchestrator's pairs (Aurora rollout sampled at station cells) to the
archived OpenAQ observations at each (station, valid_time), builds the mandatory
baselines, and computes the full metric suite per lead x city x method:

  methods   persistence | climatology | raw_cams | raw_aurora
  metrics   MAE, RMSE, bias, corr (secondary)  +  AQI category hit/adjacent,
            Very Poor+ POD/FAR/miss/CSI, Brier (headline)  +  the same on the
            extremes subset (obs >= 121 ug/m3)

Baselines (spec §5):
  persistence  obs at init time (the lead-0 valid_time) carried to every lead.
  climatology  per station x month x hour-of-day mean over the TRAIN period.
  raw_cams     the CAMS analysis pm2p5 sampled at init (pairs lead_h == 0),
               carried forward -- the "free global product" reference.
  raw_aurora   aurora_pm2p5 at each lead -- the foundation-model baseline.

Usage:
    python -m src.eval.benchmark                       # all pairs found
    python -m src.eval.benchmark --out results/metrics/indiaaqbench.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import aqi

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAIRS_DIR = PROJECT_ROOT / "results" / "pairs"
OPENAQ_DIR = PROJECT_ROOT / "data" / "openaq"
METRICS_DIR = PROJECT_ROOT / "results" / "metrics"

MATCH_TOL = pd.Timedelta("90min")   # obs-to-valid-time match tolerance
SPLIT_CUTOFF = pd.Timestamp("2025-07-01", tz="UTC")  # train < cutoff <= test
EXTREME = aqi.VERY_POOR_THRESHOLD


# --------------------------------------------------------------------------- #
# Loading + observation join
# --------------------------------------------------------------------------- #

def load_pairs() -> pd.DataFrame:
    files = sorted(PAIRS_DIR.glob("pairs_*.parquet"))
    if not files:
        raise SystemExit(f"No pairs_*.parquet under {PAIRS_DIR} - run the orchestrator.")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    df["valid_time"] = pd.to_datetime(df["valid_time"], utc=True)
    df["init_time"] = pd.to_datetime(df["init_date"], utc=True) + pd.Timedelta(hours=12)
    return df


def load_obs() -> pd.DataFrame:
    frames = []
    for csv in sorted(OPENAQ_DIR.glob("*_pm25.csv")):
        o = pd.read_csv(csv, usecols=["station_id", "timestamp_utc", "value_ugm3"])
        frames.append(o)
    obs = pd.concat(frames, ignore_index=True)
    obs["timestamp_utc"] = pd.to_datetime(obs["timestamp_utc"], utc=True)
    # Collapse to hourly per station (matches the sensor cadence; dedups half-hours).
    obs["hour"] = obs["timestamp_utc"].dt.floor("h")
    obs = (obs.groupby(["station_id", "hour"], as_index=False)["value_ugm3"].mean())
    return obs.rename(columns={"hour": "timestamp_utc", "value_ugm3": "obs_pm25"})


def _match_obs(times: pd.DataFrame, obs: pd.DataFrame, left_time: str,
               out_col: str) -> pd.Series:
    """merge_asof each (station, left_time) to nearest obs hour within MATCH_TOL."""
    left = times[["station_id", left_time]].dropna().sort_values(left_time)
    right = obs.sort_values("timestamp_utc")
    merged = pd.merge_asof(
        left, right, left_on=left_time, right_on="timestamp_utc",
        by="station_id", direction="nearest", tolerance=MATCH_TOL,
    )
    merged = merged.set_index(left.index)
    return merged["obs_pm25"].rename(out_col)


def build_frame() -> pd.DataFrame:
    """Assemble the scored frame: one row per (init, station, lead) with obs +
    every method's prediction."""
    pairs = load_pairs()
    obs = load_obs()

    # Ground truth at each forecast valid time.
    pairs["obs_pm25"] = _match_obs(pairs, obs, "valid_time", "obs_pm25")
    # Persistence: obs at the init time (same for all leads of an init).
    pairs["persist_pm25"] = _match_obs(pairs, obs, "init_time", "persist_pm25")

    # raw_cams: the lead-0 aurora_pm2p5 (== CAMS input) per (init, station),
    # carried to every lead.
    cams0 = (pairs[pairs["lead_h"] == 0]
             .set_index(["init_date", "station_id"])["aurora_pm2p5"]
             .rename("cams_pm25"))
    pairs = pairs.join(cams0, on=["init_date", "station_id"])

    pairs["is_test"] = pairs["valid_time"] >= SPLIT_CUTOFF
    return pairs


def add_climatology(frame: pd.DataFrame) -> pd.DataFrame:
    """Per station x month x hour-of-day mean obs over TRAIN rows only."""
    train = frame[~frame["is_test"]].dropna(subset=["obs_pm25"]).copy()
    if train.empty:
        frame["clim_pm25"] = np.nan
        return frame
    train["month"] = train["valid_time"].dt.month
    train["hod"] = train["valid_time"].dt.hour
    clim = (train.groupby(["station_id", "month", "hod"])["obs_pm25"]
                 .mean().rename("clim_pm25").reset_index())
    frame["month"] = frame["valid_time"].dt.month
    frame["hod"] = frame["valid_time"].dt.hour
    frame = frame.merge(clim, on=["station_id", "month", "hod"], how="left")
    return frame.drop(columns=["month", "hod"])


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

METHODS = {
    "persistence": "persist_pm25",
    "climatology": "clim_pm25",
    "raw_cams": "cams_pm25",
    "raw_aurora": "aurora_pm2p5",
}


def _regression(obs: np.ndarray, pred: np.ndarray) -> dict:
    m = np.isfinite(obs) & np.isfinite(pred)
    o, p = obs[m], pred[m]
    if o.size == 0:
        return {"n": 0, "mae": np.nan, "rmse": np.nan, "bias": np.nan, "corr": np.nan}
    return {
        "n": int(o.size),
        "mae": float(np.mean(np.abs(p - o))),
        "rmse": float(np.sqrt(np.mean((p - o) ** 2))),
        "bias": float(np.mean(p - o)),
        "corr": float(np.corrcoef(o, p)[0, 1]) if o.size > 1 and o.std() > 0 and p.std() > 0 else np.nan,
    }


def score(frame: pd.DataFrame, split: str = "all", extremes: bool = False) -> pd.DataFrame:
    """Metrics per (lead_h, city, method). split in {all,train,test}."""
    df = frame
    if split == "train":
        df = df[~df["is_test"]]
    elif split == "test":
        df = df[df["is_test"]]
    df = df[df["lead_h"] > 0]  # lead 0 is the analysis, not a forecast

    rows = []
    for (lead, city), g in df.groupby(["lead_h", "city"]):
        obs = g["obs_pm25"].to_numpy()
        for method, col in METHODS.items():
            pred = g[col].to_numpy()
            mask = np.isfinite(obs)
            if extremes:
                mask &= obs >= EXTREME
            o, p = obs[mask], pred[mask]
            rec = {"lead_h": lead, "city": city, "method": method}
            rec.update(_regression(o, p))
            rec.update({k: v for k, v in aqi.category_metrics(o, p).items()
                        if k in ("cat_hit_rate", "event_pod", "event_far", "event_csi")})
            rows.append(rec)
    return pd.DataFrame(rows)


def summary(frame: pd.DataFrame, split: str = "test") -> pd.DataFrame:
    """Pooled-over-cities headline per (lead, method) for a quick read."""
    df = frame[frame["lead_h"] > 0]
    df = df[df["is_test"]] if split == "test" else (df[~df["is_test"]] if split == "train" else df)
    rows = []
    for lead in sorted(df["lead_h"].unique()):
        g = df[df["lead_h"] == lead]
        obs = g["obs_pm25"].to_numpy()
        for method, col in METHODS.items():
            pred = g[col].to_numpy()
            rec = {"lead_h": int(lead), "method": method}
            rec.update(_regression(obs, pred))
            em = aqi.category_metrics(obs[np.isfinite(obs)], pred[np.isfinite(obs)])
            rec["event_pod"] = em.get("event_pod")
            rec["event_far"] = em.get("event_far")
            rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="IndiaAQBench evaluation harness.")
    p.add_argument("--out", type=Path, default=METRICS_DIR / "indiaaqbench.csv")
    p.add_argument("--split", default="all", choices=["all", "train", "test"])
    args = p.parse_args()

    frame = add_climatology(build_frame())
    matched = int(frame[frame["lead_h"] > 0]["obs_pm25"].notna().sum())
    print(f"Loaded {len(frame):,} pred rows; "
          f"{matched:,} forecast rows matched to obs "
          f"({frame['city'].nunique()} cities, {frame['init_date'].nunique()} dates).")

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    full = score(frame, split=args.split)
    full.to_csv(args.out, index=False)
    ext = score(frame, split=args.split, extremes=True)
    ext.to_csv(args.out.with_name(args.out.stem + "_extremes.csv"), index=False)

    print(f"\n=== Pooled headline (split={args.split}) - MAE + Very Poor+ POD by lead ===")
    s = summary(frame, split=args.split)
    show = s.pivot(index="lead_h", columns="method", values="mae").round(1)
    print("MAE (ug/m3):"); print(show.to_string())
    pod = s.pivot(index="lead_h", columns="method", values="event_pod").round(2)
    print("\nVery Poor+ POD (hit rate):"); print(pod.to_string())
    print(f"\nWrote {args.out} (+_extremes)")


if __name__ == "__main__":
    main()
