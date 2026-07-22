"""Build/refresh the versioned station registry (data/stations.csv).

The registry is the ONLY station list benchmark code may use (BENCHMARK_SPEC
§7). It is derived from the archived OpenAQ pulls in data/openaq/*_pm25.csv and
is committed to git (small, and required for reproducibility).

Usage:
    python -m src.data.build_station_registry
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAQ_DIR = PROJECT_ROOT / "data" / "openaq"
REGISTRY = PROJECT_ROOT / "data" / "stations.csv"


def build() -> pd.DataFrame:
    frames = []
    for csv in sorted(OPENAQ_DIR.glob("*_pm25.csv")):
        city = csv.stem.replace("_pm25", "")
        df = pd.read_csv(csv, parse_dates=["timestamp_utc"])
        g = df.groupby("station_id").agg(
            station_name=("station_name", "first"),
            lat=("lat", "first"),
            lon=("lon", "first"),
            first_seen=("timestamp_utc", "min"),
            last_seen=("timestamp_utc", "max"),
            n_rows=("value_ugm3", "size"),
        ).reset_index()
        g.insert(1, "city", city)
        frames.append(g)
    if not frames:
        raise SystemExit(f"No *_pm25.csv files under {OPENAQ_DIR}")
    reg = pd.concat(frames, ignore_index=True)
    # A station may appear in multiple pulls; keep widest date range.
    reg = (reg.sort_values("n_rows", ascending=False)
              .groupby(["station_id", "city"], as_index=False).first()
              .sort_values(["city", "station_id"]))
    reg.to_csv(REGISTRY, index=False)
    print(f"Wrote {REGISTRY}  ({len(reg)} stations, "
          f"{reg['city'].nunique()} cities: {sorted(reg['city'].unique())})")
    return reg


if __name__ == "__main__":
    build()
