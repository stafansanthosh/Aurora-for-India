"""Probe OpenAQ historical coverage — can we get post-monsoon TRAINING data?

Motivation: the coverage audit found ZERO usable post-monsoon train dates, which
left any trained calibrator blind to India's severe season (Diwali + stubble
burning) — the regime the benchmark exists to score. Before accepting that as a
permanent constraint we need to know *why* it is missing and whether more data
is reachable.

Two questions, answered cheaply (metadata only, ~1 request per city):
  1. How far back does each city's PM2.5 sensor set actually claim coverage
     (``datetimeFirst`` / ``datetimeLast`` from /locations)?
  2. How many stations per city cover each Oct-Nov (post-monsoon) window?

This does NOT pull measurements — it reads the sensor metadata OpenAQ already
publishes, so it is safe to run repeatedly while deciding scope.

Usage:
    python -m src.data.archive_probe
    python -m src.data.archive_probe --years 2022 2023 2024 2025
"""
from __future__ import annotations

import argparse

import pandas as pd
from dotenv import load_dotenv

from .openaq_client import CITIES, DEFAULT_RADIUS_M, PM25_PARAMETER_ID, OpenAQClient

load_dotenv()

POST_MONSOON = (10, 11)  # October-November: Diwali + stubble-burning season


def sensor_ranges(client: OpenAQClient, city: str) -> pd.DataFrame:
    """Per PM2.5 sensor near ``city``: claimed first/last measurement datetimes."""
    lat, lon = CITIES[city]
    rows: list[dict] = []
    page = 1
    while True:
        payload = client._get("/locations", params={
            "coordinates": f"{lat},{lon}", "radius": DEFAULT_RADIUS_M,
            "parameters_id": PM25_PARAMETER_ID, "limit": 100, "page": page,
        })
        results = payload.get("results", [])
        if not results:
            break
        for loc in results:
            for s in loc.get("sensors", []):
                if s.get("parameter", {}).get("id") != PM25_PARAMETER_ID:
                    continue
                # Coverage is published on the location, not the sensor.
                first = (loc.get("datetimeFirst") or {}).get("utc")
                last = (loc.get("datetimeLast") or {}).get("utc")
                rows.append({"city": city, "station_id": loc.get("id"),
                             "station_name": loc.get("name"),
                             "sensor_id": s.get("id"),
                             "first": pd.to_datetime(first, utc=True, errors="coerce"),
                             "last": pd.to_datetime(last, utc=True, errors="coerce")})
        if len(results) < 100:
            break
        page += 1
    return pd.DataFrame(rows)


def covers_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> int:
    """Number of distinct stations whose claimed range spans [start, end)."""
    if df.empty:
        return 0
    m = (df["first"] <= start) & (df["last"] >= end)
    return int(df.loc[m, "station_id"].nunique())


def main() -> None:
    p = argparse.ArgumentParser(description="Probe OpenAQ historical coverage.")
    p.add_argument("--years", nargs="*", type=int,
                   default=[2022, 2023, 2024, 2025],
                   help="Post-monsoon years to test for station coverage.")
    args = p.parse_args()

    client = OpenAQClient()
    frames = []
    print("Probing sensor metadata per city...\n")
    for city in sorted(CITIES):
        df = sensor_ranges(client, city)
        frames.append(df)
        if df.empty:
            print(f"{city:<10} no PM2.5 sensors found")
            continue
        print(f"{city:<10} {df['station_id'].nunique():>3} stations | "
              f"earliest claimed data: {df['first'].min()} | latest: {df['last'].max()}")

    allsens = pd.concat(frames, ignore_index=True)

    print(f"\n=== Stations covering the FULL Oct 1 - Nov 30 post-monsoon window ===")
    table = {}
    for year in args.years:
        start = pd.Timestamp(f"{year}-10-01", tz="UTC")
        end = pd.Timestamp(f"{year}-11-30", tz="UTC")
        table[year] = {c: covers_window(allsens[allsens.city == c], start, end)
                       for c in sorted(CITIES)}
    print(pd.DataFrame(table).to_string())

    print("\n=== Earliest claimed coverage per city (is backfill possible?) ===")
    earliest = (allsens.groupby("city")["first"].min().dt.date
                .rename("earliest_claimed").to_frame())
    earliest["stations_back_to_2023"] = [
        covers_window(allsens[allsens.city == c],
                      pd.Timestamp("2023-10-01", tz="UTC"),
                      pd.Timestamp("2023-11-30", tz="UTC"))
        for c in earliest.index]
    print(earliest.to_string())


if __name__ == "__main__":
    main()
