"""Archival OpenAQ pull for the full IndiaAQBench period (all 9 cities).

Pulls the benchmark window once per city, saves the cleaned CSV to
data/openaq/{city}_pm25.csv AND an immutable copy under
data/openaq/archive/{city}_{from}_{to}.csv, and records every pull in
data/openaq/archive/pull_manifest.jsonl (query params, row/station counts,
timestamp). The archive + manifest are the reproducibility contract (spec §7):
OpenAQ India data are not "fully open", so we snapshot exactly what we used.

Usage:
    python -m src.data.archive_pull                       # all cities, full window
    python -m src.data.archive_pull --from 2024-10-01 --to 2026-07-22
    python -m src.data.archive_pull --cities delhi patna  # subset
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from .openaq_client import CITIES, OUTPUT_DIR, clean, fetch_city, save_city

load_dotenv()  # OPENAQ_API_KEY from .env (openaq_client only loads it in its own main)

ARCHIVE_DIR = OUTPUT_DIR / "archive"
MANIFEST = ARCHIVE_DIR / "pull_manifest.jsonl"

# Benchmark window (spec §6): post-monsoon 2024 through the present.
DEFAULT_FROM = "2024-10-01"
DEFAULT_TO = "2026-07-22"


def _log(rec: dict) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _quarters(date_from: str, date_to: str) -> list[tuple[str, str]]:
    """Split [from, to) into ~3-month windows (smaller, connection-safe pulls)."""
    edges = pd.date_range(date_from, date_to, freq="QS").tolist()
    bounds = [pd.Timestamp(date_from)] + edges + [pd.Timestamp(date_to)]
    bounds = sorted(set(b.normalize() for b in bounds))
    return [(a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d"))
            for a, b in zip(bounds[:-1], bounds[1:]) if a < b]


def pull_city(city: str, date_from: str, date_to: str) -> dict:
    # Pull quarter-by-quarter and concatenate; one flaky window can't lose the
    # whole city, and each response stays small enough to download intact.
    frames = []
    for a, b in _quarters(date_from, date_to):
        try:
            part = fetch_city(city, a, b)
            if not part.empty:
                frames.append(part)
            print(f"    {city} {a}..{b}: {len(part)} rows")
        except Exception as e:
            print(f"    {city} {a}..{b}: FAILED ({type(e).__name__}) - skipping window")
        time.sleep(1.0)  # pace between windows
    df = clean(pd.concat(frames, ignore_index=True)) if frames else pd.DataFrame()
    n_rows = len(df)
    n_stations = int(df["station_id"].nunique()) if n_rows else 0
    if n_rows:
        save_city(city, df)
        archive = ARCHIVE_DIR / f"{city}_{date_from}_{date_to}.csv"
        shutil.copyfile(OUTPUT_DIR / f"{city}_pm25.csv", archive)
        archive_name = archive.name
    else:
        archive_name = None
    rec = {
        "city": city, "date_from": date_from, "date_to": date_to,
        "rows": n_rows, "stations": n_stations, "archive": archive_name,
        "pulled_at": datetime.utcnow().isoformat(), "status": "ok",
    }
    _log(rec)
    print(f"[archive] {city}: {n_rows} rows, {n_stations} stations -> {archive_name}")
    return rec


def main() -> None:
    p = argparse.ArgumentParser(description="Archival OpenAQ pull for IndiaAQBench.")
    p.add_argument("--from", dest="date_from", default=DEFAULT_FROM)
    p.add_argument("--to", dest="date_to", default=DEFAULT_TO)
    p.add_argument("--cities", nargs="*", default=sorted(CITIES))
    args = p.parse_args()

    print(f"Archival pull: {args.cities}  {args.date_from} -> {args.date_to}")
    summary = []
    for city in args.cities:
        try:
            summary.append(pull_city(city, args.date_from, args.date_to))
        except Exception as e:
            _log({"city": city, "date_from": args.date_from, "date_to": args.date_to,
                  "status": "error", "error": repr(e),
                  "pulled_at": datetime.utcnow().isoformat()})
            traceback.print_exc()
            print(f"[archive] {city}: FAILED - logged, continuing.")

    total = sum(r.get("rows", 0) for r in summary)
    print(f"\nDone. {len(summary)} cities OK, {total} total rows archived under {ARCHIVE_DIR}")


if __name__ == "__main__":
    main()
