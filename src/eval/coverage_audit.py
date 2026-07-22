"""Coverage audit: score OpenAQ density and propose the frozen benchmark dates.

An init date D (12:00 UTC) is usable if, across the +12h..+96h validation
window (D+0.5d .. D+4d), enough stations report enough hours -- that is the
window the Aurora rollout is scored against. We score every candidate init
date per city, stratify by season, and propose ~N dates balanced across
seasons while respecting the temporal split cutoff.

Held-out cities (Kanpur, Varanasi, Kolkata) are audited too but MUST NOT drive
date selection -- their coverage is a validation-feasibility check only.

Usage:
    python -m src.eval.coverage_audit --n 60 --out docs/benchmark_dates.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAQ_DIR = PROJECT_ROOT / "data" / "openaq"

HELDOUT_CITIES = {"kanpur", "varanasi", "kolkata"}
SPLIT_CUTOFF = pd.Timestamp("2025-07-01", tz="UTC")

# Validation window relative to init (12:00 UTC): +12h .. +96h.
LEAD_LO_H, LEAD_HI_H = 12, 96
# Usability thresholds for an init date, per city.
MIN_STATIONS = 2         # >= this many stations reporting in the window
MIN_STATION_HOURS = 40   # >= this many total station-hours in the window


def _season(month: int) -> str:
    return {10: "post-monsoon", 11: "post-monsoon",
            12: "winter", 1: "winter", 2: "winter",
            3: "pre-monsoon", 4: "pre-monsoon", 5: "pre-monsoon"}.get(month, "monsoon")


def _load_all() -> pd.DataFrame:
    frames = []
    for csv in sorted(OPENAQ_DIR.glob("*_pm25.csv")):
        city = csv.stem.replace("_pm25", "")
        df = pd.read_csv(csv, parse_dates=["timestamp_utc"])
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
        df["city"] = city
        frames.append(df[["city", "station_id", "timestamp_utc", "value_ugm3"]])
    if not frames:
        raise SystemExit(f"No *_pm25.csv under {OPENAQ_DIR}")
    return pd.concat(frames, ignore_index=True)


def score_dates(obs: pd.DataFrame) -> pd.DataFrame:
    """Per (city, init_date): stations + station-hours in the +12..+96h window."""
    obs = obs.assign(hour=obs["timestamp_utc"].dt.floor("h"))
    # Candidate init dates: every day spanned by the data.
    lo, hi = obs["timestamp_utc"].min().normalize(), obs["timestamp_utc"].max().normalize()
    init_days = pd.date_range(lo, hi, freq="D", tz="UTC")

    # Pre-index observations by city for speed.
    rows = []
    for city, g in obs.groupby("city"):
        ts = g["hour"].values
        sid = g["station_id"].values
        for d in init_days:
            win_lo = d + pd.Timedelta(hours=LEAD_LO_H)
            win_hi = d + pd.Timedelta(hours=LEAD_HI_H)
            m = (ts >= np.datetime64(win_lo)) & (ts <= np.datetime64(win_hi))
            if not m.any():
                continue
            station_hours = int(m.sum())
            n_stations = int(pd.unique(sid[m]).size)
            rows.append({"city": city, "init_date": d.strftime("%Y-%m-%d"),
                         "season": _season(d.month), "n_stations": n_stations,
                         "station_hours": station_hours,
                         "usable": n_stations >= MIN_STATIONS and station_hours >= MIN_STATION_HOURS,
                         "test": d >= SPLIT_CUTOFF})
    return pd.DataFrame(rows)


def density_table(scores: pd.DataFrame) -> pd.DataFrame:
    """Per city x season: usable-date count (train vs test)."""
    t = (scores[scores["usable"]]
         .groupby(["city", "season", "test"])["init_date"].nunique()
         .unstack("test", fill_value=0)
         .rename(columns={False: "train_dates", True: "test_dates"})
         .reset_index())
    return t.sort_values(["city", "season"])


def propose(scores: pd.DataFrame, n: int) -> pd.DataFrame:
    """Pick ~n init dates balanced across seasons, driven by TRAIN-POOL cities.

    An init date qualifies if any train-pool city finds it usable; we then
    balance the pick across seasons and across the train/test split.
    """
    pool = scores[~scores["city"].isin(HELDOUT_CITIES) & scores["usable"]]
    # A date is a candidate if >=1 train-pool city is usable on it.
    per_date = (pool.groupby("init_date")
                    .agg(season=("season", "first"), test=("test", "first"),
                         cities=("city", "nunique"),
                         station_hours=("station_hours", "sum"))
                    .reset_index())
    # Balance across the 4 season x {train,test} strata; prefer denser dates.
    per_date["stratum"] = per_date["season"] + ("/test" + per_date["test"].astype(str))
    strata = per_date["stratum"].unique()
    per_stratum = max(1, n // max(1, len(strata)))
    picks = []
    for s in strata:
        sub = per_date[per_date["stratum"] == s].sort_values(
            ["cities", "station_hours"], ascending=False)
        picks.append(sub.head(per_stratum))
    chosen = pd.concat(picks).sort_values("init_date").reset_index(drop=True)
    return chosen[["init_date", "season", "test", "cities", "station_hours"]]


def main() -> None:
    p = argparse.ArgumentParser(description="IndiaAQBench coverage audit.")
    p.add_argument("--n", type=int, default=60, help="Target number of init dates.")
    p.add_argument("--out", type=Path, default=PROJECT_ROOT / "docs" / "benchmark_dates.csv")
    args = p.parse_args()

    obs = _load_all()
    print(f"Loaded {len(obs):,} obs rows, {obs['city'].nunique()} cities, "
          f"{obs['timestamp_utc'].min().date()} .. {obs['timestamp_utc'].max().date()}")

    scores = score_dates(obs)
    dens = density_table(scores)
    print("\n=== Usable init dates per city x season (train | test) ===")
    print(dens.to_string(index=False))

    print("\n=== Held-out city validation feasibility (usable dates) ===")
    ho = (scores[scores["usable"] & scores["city"].isin(HELDOUT_CITIES)]
          .groupby(["city", "test"])["init_date"].nunique()
          .unstack("test", fill_value=0))
    print(ho.to_string())

    chosen = propose(scores, args.n)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    chosen.to_csv(args.out, index=False)
    print(f"\n=== Proposed {len(chosen)} benchmark dates "
          f"({int(chosen['test'].sum())} test / {int((~chosen['test']).sum())} train) ===")
    print(chosen.groupby(["season", "test"]).size().to_string())
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
