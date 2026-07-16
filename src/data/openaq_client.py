"""OpenAQ v3 API client — pull hourly PM2.5 ground truth for Indian cities.

Fetches PM2.5 measurements from OpenAQ stations near a target city and writes
them to ``data/openaq/{city}_pm25.csv`` following the project data contract.

Data contract (per COPILOT_CONTEXT.md section 4.1):
    timestamp_utc, timestamp_local, value_ugm3, lat, lon,
    station_id, station_name, city

API notes learned from the live v3 API (2026):
    * Auth via ``X-API-Key`` header.
    * Station discovery: GET /v3/locations?coordinates=lat,lon&radius=...
    * Each location embeds a ``sensors`` list; PM2.5 has ``parameter.id == 2``.
    * Hourly readings: GET /v3/sensors/{sensor_id}/hours (server-side hourly
      aggregates — cleaner than the raw /measurements 15-min stream).
      -- the date window params are ``datetime_from`` / ``datetime_to``
         (NOT ``date_from`` / ``date_to``, which the API silently ignores and
         then returns the sensor's entire history regardless of the window —
         verified against the live API, contradicts the published docs).
    * Measurement ``coordinates`` may be null; take station coords from the
      location metadata instead.

Usage:
    python -m src.data.openaq_client --city delhi \
        --date-from 2017-01-01 --date-to 2017-02-01
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

API_BASE = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2
PAGE_LIMIT = 1000  # OpenAQ v3 max page size
REQUEST_TIMEOUT = 60
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
MAX_RETRIES = 4

# City centres (lat, lon) — mirrors the target-city table in COPILOT_CONTEXT.md.
CITIES: dict[str, tuple[float, float]] = {
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bangalore": (12.9716, 77.5946),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
}

# Default search radius around a city centre, in metres (OpenAQ max is 25 km).
DEFAULT_RADIUS_M = 25_000

# Data-quality bounds (COPILOT_CONTEXT.md section 4.1).
VALUE_MIN = 0.0
VALUE_MAX = 1000.0
EXTREME_FLAG = 500.0
STUCK_HOURS = 24

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "openaq"


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #

class OpenAQClient:
    """Thin wrapper over the OpenAQ v3 REST API with retry + pagination."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.getenv("OPENAQ_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAQ_API_KEY not set. Add it to .env or pass api_key=..."
            )
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": key})

    # -- low-level -------------------------------------------------------- #

    def _get(self, path: str, params: dict | None = None) -> dict:
        """GET with simple exponential-backoff retry on transient errors."""
        url = f"{API_BASE}{path}"
        for attempt in range(MAX_RETRIES):
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code in RETRY_STATUS:
                wait = 2 ** attempt
                print(f"  HTTP {resp.status_code} on {path}; retry in {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()  # exhausted retries — surface the last error
        return {}  # unreachable, keeps type checkers happy

    # -- station discovery ------------------------------------------------ #

    def find_pm25_stations(
        self, city: str, radius_m: int = DEFAULT_RADIUS_M
    ) -> list[dict]:
        """Return PM2.5 stations near a city centre.

        Each entry: {station_id, station_name, lat, lon, sensor_id}.
        """
        if city not in CITIES:
            raise ValueError(f"Unknown city '{city}'. Known: {list(CITIES)}")
        lat, lon = CITIES[city]

        stations: list[dict] = []
        page = 1
        while True:
            payload = self._get(
                "/locations",
                params={
                    "coordinates": f"{lat},{lon}",
                    "radius": radius_m,
                    "parameters_id": PM25_PARAMETER_ID,
                    "limit": 100,
                    "page": page,
                },
            )
            results = payload.get("results", [])
            if not results:
                break
            for loc in results:
                coords = loc.get("coordinates") or {}
                pm25_sensor = next(
                    (
                        s
                        for s in loc.get("sensors", [])
                        if s.get("parameter", {}).get("id") == PM25_PARAMETER_ID
                    ),
                    None,
                )
                if pm25_sensor is None:
                    continue
                stations.append(
                    {
                        "station_id": loc.get("id"),
                        "station_name": loc.get("name"),
                        "lat": coords.get("latitude"),
                        "lon": coords.get("longitude"),
                        "sensor_id": pm25_sensor.get("id"),
                    }
                )
            if len(results) < 100:
                break
            page += 1
        return stations

    # -- measurements ----------------------------------------------------- #

    def fetch_hourly(
        self, sensor_id: int, datetime_from: str, datetime_to: str
    ) -> list[dict]:
        """Fetch hourly aggregates for one sensor in [datetime_from, datetime_to).

        ``datetime_from`` / ``datetime_to`` accept ``YYYY-MM-DD`` or full ISO
        8601; bare dates are normalised to UTC midnight. Returns the raw
        ``results`` records (unparsed).
        """
        dt_from = _to_iso_utc(datetime_from)
        dt_to = _to_iso_utc(datetime_to)
        records: list[dict] = []
        page = 1
        while True:
            payload = self._get(
                f"/sensors/{sensor_id}/hours",
                params={
                    "datetime_from": dt_from,
                    "datetime_to": dt_to,
                    "limit": PAGE_LIMIT,
                    "page": page,
                },
            )
            results = payload.get("results", [])
            records.extend(results)
            if len(results) < PAGE_LIMIT:
                break
            page += 1
            time.sleep(0.2)  # be polite to the API between pages
        return records


# --------------------------------------------------------------------------- #
# Parsing + cleaning
# --------------------------------------------------------------------------- #

def _to_iso_utc(value: str) -> str:
    """Normalise a ``YYYY-MM-DD`` or ISO string to ``YYYY-MM-DDTHH:MM:SSZ`` UTC."""
    ts = pd.Timestamp(value)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_records(records: list[dict], station: dict, city: str) -> pd.DataFrame:
    """Turn raw measurement JSON into contract-shaped rows."""
    rows: list[dict] = []
    for rec in records:
        period = rec.get("period", {})
        dt_from = period.get("datetimeFrom", {})
        rows.append(
            {
                "timestamp_utc": dt_from.get("utc"),
                "timestamp_local": dt_from.get("local"),
                "value_ugm3": rec.get("value"),
                "lat": station["lat"],
                "lon": station["lon"],
                "station_id": station["station_id"],
                "station_name": station["station_name"],
                "city": city,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["timestamp_local"] = pd.to_datetime(df["timestamp_local"])
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the project's data-quality rules (COPILOT_CONTEXT.md 4.1).

    * Drop values outside [0, 1000] (instrument errors).
    * Drop runs of >24 consecutive identical values (stuck sensor).
    * Flag (keep) values > 500 via an ``is_extreme`` column.
    """
    if df.empty:
        return df
    df = df.dropna(subset=["value_ugm3", "timestamp_utc"]).copy()

    # Range filter.
    df = df[(df["value_ugm3"] >= VALUE_MIN) & (df["value_ugm3"] <= VALUE_MAX)]

    # Stuck-sensor filter: per station, drop runs longer than STUCK_HOURS of
    # an identical value.
    keep_parts: list[pd.DataFrame] = []
    for _, grp in df.sort_values("timestamp_utc").groupby("station_id"):
        run_id = (grp["value_ugm3"] != grp["value_ugm3"].shift()).cumsum()
        run_len = grp.groupby(run_id)["value_ugm3"].transform("size")
        keep_parts.append(grp[run_len <= STUCK_HOURS])
    df = pd.concat(keep_parts) if keep_parts else df

    df["is_extreme"] = df["value_ugm3"] > EXTREME_FLAG
    return df.sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def fetch_city(
    city: str,
    date_from: str,
    date_to: str,
    client: OpenAQClient | None = None,
    radius_m: int = DEFAULT_RADIUS_M,
    max_stations: int | None = None,
) -> pd.DataFrame:
    """Fetch, parse, and clean PM2.5 for every station near ``city``."""
    client = client or OpenAQClient()
    stations = client.find_pm25_stations(city, radius_m=radius_m)
    print(f"Found {len(stations)} PM2.5 station(s) near {city}.")
    if max_stations is not None:
        stations = stations[:max_stations]
        print(f"  limiting to first {len(stations)} station(s).")

    frames: list[pd.DataFrame] = []
    for st in stations:
        print(
            f"  sensor {st['sensor_id']} ({st['station_name']}) "
            f"{date_from} -> {date_to} ...",
            end="",
            flush=True,
        )
        raw = client.fetch_hourly(st["sensor_id"], date_from, date_to)
        df = _parse_records(raw, st, city)
        print(f" {len(df)} rows")
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    return clean(combined)


def save_city(city: str, df: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{city}_pm25.csv"
    df.to_csv(out, index=False)
    return out


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pull OpenAQ PM2.5 for an Indian city.")
    p.add_argument("--city", required=True, choices=sorted(CITIES), help="Target city.")
    p.add_argument("--date-from", required=True, help="UTC start date, YYYY-MM-DD.")
    p.add_argument("--date-to", required=True, help="UTC end date (exclusive), YYYY-MM-DD.")
    p.add_argument(
        "--radius", type=int, default=DEFAULT_RADIUS_M, help="Search radius in metres."
    )
    p.add_argument(
        "--max-stations",
        type=int,
        default=None,
        help="Cap the number of stations fetched (useful for quick runs).",
    )
    return p.parse_args()


def main() -> None:
    load_dotenv()
    args = _parse_args()
    df = fetch_city(
        args.city,
        args.date_from,
        args.date_to,
        radius_m=args.radius,
        max_stations=args.max_stations,
    )
    if df.empty:
        print("No measurements returned — nothing written.")
        return
    out = save_city(args.city, df)
    n_extreme = int(df["is_extreme"].sum())
    print(
        f"Wrote {len(df)} rows ({df['station_id'].nunique()} stations, "
        f"{n_extreme} extreme) -> {out}"
    )


if __name__ == "__main__":
    main()
