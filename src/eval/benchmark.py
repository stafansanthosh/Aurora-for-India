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
from ..splits import SPLIT_CUTOFF

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAIRS_DIR = PROJECT_ROOT / "results" / "pairs"
OPENAQ_DIR = PROJECT_ROOT / "data" / "openaq"
METRICS_DIR = PROJECT_ROOT / "results" / "metrics"
DATES_FILE = PROJECT_ROOT / "docs" / "benchmark_dates.csv"

MATCH_TOL = pd.Timedelta("90min")   # obs-to-valid-time match tolerance
EXTREME = aqi.VERY_POOR_THRESHOLD


# --------------------------------------------------------------------------- #
# Loading + observation join
# --------------------------------------------------------------------------- #

def _current_registry_version() -> str | None:
    """Fingerprint of the station registry as it stands right now."""
    reg_path = PROJECT_ROOT / "data" / "stations.csv"
    if not reg_path.exists():
        return None
    from ..pipeline.orchestrate import _registry_version

    return _registry_version(pd.read_csv(reg_path))


def _frozen_dates() -> set[str]:
    """Exact initialization dates admitted to an official benchmark table."""
    if not DATES_FILE.exists():
        raise SystemExit(f"Frozen date manifest missing: {DATES_FILE}")
    dates = pd.read_csv(DATES_FILE)
    if "init_date" not in dates.columns:
        raise SystemExit(f"{DATES_FILE} has no init_date column")
    out = set(dates["init_date"].astype(str))
    if len(out) != len(dates):
        raise SystemExit(f"{DATES_FILE} contains duplicate init_date rows")
    return out


def load_pairs(strict: bool = True) -> pd.DataFrame:
    """Load rollout pairs and enforce the official benchmark population.

    Strict mode admits only the current registry and exact frozen date
    manifest, then requires every date, station, and lead exactly once. Hazards
    this guards against are otherwise silent in the output:
      * pilot dates rolled out at 33 or 127 stations sitting alongside 159-station
        dates, so pooled metrics span different station populations;
      * dates no longer in the frozen list lingering on disk and contaminating
        the final table (2025-11-15 / 2025-11-20 are exactly this case).
    Pre-versioning files carry no stamp and are therefore treated as stale.
    """
    files = sorted(PAIRS_DIR.glob("pairs_*.parquet"))
    if not files:
        raise SystemExit(f"No pairs_*.parquet under {PAIRS_DIR} - run the orchestrator.")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if strict:
        current = _current_registry_version()
        stamped = df["registry_version"] if "registry_version" in df.columns else pd.Series(
            [None] * len(df), index=df.index)
        registry_keep = stamped.eq(current) if current else stamped.notna()
        frozen = _frozen_dates()
        date_keep = df["init_date"].astype(str).isin(frozen)
        if not registry_keep.all():
            dropped = sorted(df.loc[~registry_keep, "init_date"].astype(str).unique())
            print(f"[benchmark] excluding {len(dropped)} date(s) from a stale/unstamped "
                  f"registry (current={current}): {dropped}")
        current_extra = sorted(
            df.loc[registry_keep & ~date_keep, "init_date"].astype(str).unique())
        if current_extra:
            print(f"[benchmark] excluding {len(current_extra)} current-registry "
                  f"date(s) outside the frozen manifest: {current_extra}")
        df = df[registry_keep & date_keep].copy()
        if df.empty:
            raise SystemExit(
                f"No pairs match the current registry ({current}). Re-run the "
                "orchestrator, or pass strict=False to score legacy pairs.")

        present = set(df["init_date"].astype(str))
        missing = sorted(frozen - present)
        if missing:
            raise SystemExit(
                f"Current-registry rollout is incomplete: {len(present)}/"
                f"{len(frozen)} frozen dates present; missing {missing}.")

        registry = pd.read_csv(PROJECT_ROOT / "data" / "stations.csv")
        expected_rows = len(registry) * 9
        per_date_rows = df.groupby("init_date").size()
        bad_rows = per_date_rows[per_date_rows != expected_rows]
        if not bad_rows.empty:
            raise SystemExit(
                "Pair completeness failure; expected "
                f"{expected_rows:,} rows/date: {bad_rows.to_dict()}")
        keys = ["init_date", "station_id", "lead_h"]
        if df.duplicated(keys).any():
            raise SystemExit("Duplicate (init_date, station_id, lead_h) pair rows.")
        expected_leads = set(range(0, 97, 12))
        expected_stations = set(registry["station_id"].astype(str))
        for date, group in df.groupby("init_date"):
            if set(group["lead_h"]) != expected_leads:
                raise SystemExit(f"{date}: lead set is incomplete or unexpected.")
            if set(group["station_id"].astype(str)) != expected_stations:
                raise SystemExit(f"{date}: station set differs from current registry.")

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


def build_frame(strict: bool = True) -> pd.DataFrame:
    """Assemble the scored frame: one row per (init, station, lead) with obs +
    every method's prediction.

    ``strict`` drops pairs from a stale station registry (see load_pairs). Keep
    it on for scoring and for fitting any adaptation; the integrity audit passes
    False because inspecting stale pairs is precisely its job.
    """
    pairs = load_pairs(strict=strict)
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


def active_methods(frame: pd.DataFrame) -> dict[str, str]:
    """METHODS plus any adaptation columns present on the frame."""
    m = dict(METHODS)
    if "cal_pm25" in frame.columns:
        m["calibrated"] = "cal_pm25"
    if "anchored_pm25" in frame.columns:
        m["anchored"] = "anchored_pm25"
    return m


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

    methods = active_methods(df)
    rows = []
    for (lead, city), g in df.groupby(["lead_h", "city"]):
        obs = g["obs_pm25"].to_numpy()
        for method, col in methods.items():
            pred = g[col].to_numpy()
            mask = np.isfinite(obs)
            if extremes:
                mask &= obs >= EXTREME
            o, p = obs[mask], pred[mask]
            rec = {"lead_h": lead, "city": city, "method": method}
            rec.update(_regression(o, p))
            if extremes:
                rec["subset"] = "observed_very_poor_plus"
                rec["event_observed"] = int(rec["n"])
            else:
                rec.update({
                    k: v for k, v in aqi.category_metrics(o, p).items()
                    if k in (
                        "cat_hit_rate",
                        "event_pod",
                        "event_far",
                        "event_csi",
                        "event_hits",
                        "event_misses",
                        "event_false_alarms",
                        "event_observed",
                        "event_forecast",
                    )
                })
            rows.append(rec)
    return pd.DataFrame(rows)


def summary(frame: pd.DataFrame, split: str = "test") -> pd.DataFrame:
    """Pooled-over-cities headline per (lead, method) for a quick read."""
    df = frame[frame["lead_h"] > 0]
    df = df[df["is_test"]] if split == "test" else (df[~df["is_test"]] if split == "train" else df)
    methods = active_methods(df)
    rows = []
    for lead in sorted(df["lead_h"].unique()):
        g = df[df["lead_h"] == lead]
        obs = g["obs_pm25"].to_numpy()
        for method, col in methods.items():
            pred = g[col].to_numpy()
            rec = {"lead_h": int(lead), "method": method}
            rec.update(_regression(obs, pred))
            em = aqi.category_metrics(obs[np.isfinite(obs)], pred[np.isfinite(obs)])
            rec["event_pod"] = em.get("event_pod")
            rec["event_far"] = em.get("event_far")
            rec["event_csi"] = em.get("event_csi")
            rec["event_observed"] = em.get("event_observed")
            rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="IndiaAQBench evaluation harness.")
    p.add_argument("--out", type=Path, default=METRICS_DIR / "indiaaqbench.csv")
    p.add_argument("--split", default="all", choices=["all", "train", "test"])
    p.add_argument("--calibrator", type=Path, default=None,
                   help="Path to a saved PooledCalibrator; adds it as method #5.")
    p.add_argument("--anchor", action="store_true",
                   help="Add Component A (per-station trailing-ratio anchoring) "
                        "as a scored method. Online local adaptation: it uses "
                        "trailing observations at each station, including in the "
                        "L1/L2 holdouts, so it is NOT zero-shot transfer.")
    args = p.parse_args()

    frame = add_climatology(build_frame())
    if args.anchor:
        from ..model.anchor import anchor_frame
        frame = anchor_frame(frame)
        n_fb = int(frame["anchor_fallback"].sum())
        print(f"Applied Component A anchor -> 'anchored' method added "
              f"({n_fb:,}/{len(frame):,} rows fell back to multiplier 1.0).")
    if args.calibrator is not None:
        from ..model.calibrator import PooledCalibrator
        cal = PooledCalibrator.load(args.calibrator)
        frame["cal_pm25"] = cal.predict(frame)
        print(f"Applied calibrator {args.calibrator} -> 'calibrated' method added.")
    matched = int(frame[frame["lead_h"] > 0]["obs_pm25"].notna().sum())
    print(f"Loaded {len(frame):,} pred rows; "
          f"{matched:,} forecast rows matched to obs "
          f"({frame['city'].nunique()} cities, {frame['init_date'].nunique()} dates).")

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    full = score(frame, split=args.split)
    full.to_csv(args.out, index=False)
    ext = score(frame, split=args.split, extremes=True)
    ext.to_csv(args.out.with_name(args.out.stem + "_extremes.csv"), index=False)

    print(f"\n=== Pooled headline (split={args.split}) - MAE + Very Poor+ event skill ===")
    s = summary(frame, split=args.split)
    show = s.pivot(index="lead_h", columns="method", values="mae").round(1)
    print("MAE (ug/m3):"); print(show.to_string())
    pod = s.pivot(index="lead_h", columns="method", values="event_pod").round(2)
    print("\nVery Poor+ POD (hit rate):"); print(pod.to_string())
    far = s.pivot(index="lead_h", columns="method", values="event_far").round(2)
    print("\nVery Poor+ FAR (false-alarm ratio):"); print(far.to_string())
    csi = s.pivot(index="lead_h", columns="method", values="event_csi").round(2)
    print("\nVery Poor+ CSI:"); print(csi.to_string())
    events = s.pivot(index="lead_h", columns="method", values="event_observed")
    print("\nObserved Very Poor+ event count:"); print(events.to_string())
    print(f"\nWrote {args.out} (+_extremes)")


if __name__ == "__main__":
    main()
