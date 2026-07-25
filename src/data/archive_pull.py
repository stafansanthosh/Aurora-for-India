"""Archival OpenAQ pull for the full IndiaAQBench period (all 9 cities).

Saves the cleaned per-city CSV to data/openaq/{city}_pm25.csv, an immutable copy
under data/openaq/archive/, and records every pull in the manifest. The archive +
manifest are the reproducibility contract (spec §7): OpenAQ India data are not
"fully open", so we snapshot exactly what we used.

CRASH/DISCONNECT SAFETY (this pull takes ~11 h over a flaky home connection):
  * The window is split into SMALL units (monthly by default) and each unit is
    written to its own part file under archive/parts/ the moment it lands.
  * Re-running skips any window whose part file already exists, so an
    interrupted pull resumes where it stopped instead of starting over.
  * Windows that legitimately hold no data get a `.empty` marker so they are
    not retried forever.
  * Per-window outcomes are recorded, and a city whose windows did not all
    succeed is logged status="partial" -- never a silent "ok" masking data loss.
  * --assemble-only rebuilds the city CSVs from existing parts with NO network,
    so an interrupted pull is always usable.

Usage:
    python -m src.data.archive_pull                       # all cities, resumable
    python -m src.data.archive_pull --cities patna varanasi
    python -m src.data.archive_pull --assemble-only       # offline, from parts
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

load_dotenv()  # OPENAQ_API_KEY from .env

ARCHIVE_DIR = OUTPUT_DIR / "archive"
PARTS_DIR = ARCHIVE_DIR / "parts"
MANIFEST = ARCHIVE_DIR / "pull_manifest.jsonl"

# Benchmark window (spec §6): post-monsoon 2024 through the present.
DEFAULT_FROM = "2024-10-01"
DEFAULT_TO = "2026-07-22"
# Monthly windows: small enough that one dropped connection costs minutes, not
# hours, and each response stays well under the size that broke mid-stream.
DEFAULT_FREQ = "MS"


def _log(rec: dict) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def _windows(date_from: str, date_to: str, freq: str = DEFAULT_FREQ) -> list[tuple[str, str]]:
    """Split [from, to) into small connection-safe windows."""
    edges = pd.date_range(date_from, date_to, freq=freq).tolist()
    bounds = [pd.Timestamp(date_from)] + edges + [pd.Timestamp(date_to)]
    bounds = sorted({b.normalize() for b in bounds})
    return [(a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d"))
            for a, b in zip(bounds[:-1], bounds[1:]) if a < b]


def _part_paths(city: str, a: str, b: str) -> tuple[Path, Path]:
    """(csv part, empty-marker) for one city-window."""
    stem = f"{city}__{a}__{b}"
    return PARTS_DIR / f"{stem}.csv", PARTS_DIR / f"{stem}.empty"


def pull_window(city: str, a: str, b: str) -> str:
    """Fetch one city-window into a part file.

    Returns 'cached' | 'ok' | 'empty' | 'failed'.
    """
    part, marker = _part_paths(city, a, b)
    if part.exists() or marker.exists():
        return "cached"
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        df = fetch_city(city, a, b)
    except Exception as e:
        print(f"    {city} {a}..{b}: FAILED ({type(e).__name__}) - retry on resume")
        return "failed"
    if df.empty:
        marker.write_text("")  # remember there is genuinely nothing here
        print(f"    {city} {a}..{b}: no data")
        return "empty"
    # Write atomically: an interrupt can never leave a half-written part behind.
    tmp = part.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(part)
    print(f"    {city} {a}..{b}: {len(df)} rows -> {part.name}")
    return "ok"


def assemble_city(city: str, date_from: str, date_to: str) -> dict:
    """Concatenate this city's part files, clean, and write the city CSV."""
    frames = []
    for p in sorted(PARTS_DIR.glob(f"{city}__*.csv")):
        try:
            frames.append(pd.read_csv(p))
        except Exception as e:  # a truncated part must not sink the whole city
            print(f"    skipping unreadable part {p.name} ({type(e).__name__})")
    if not frames:
        return {"rows": 0, "stations": 0, "archive": None}
    df = clean(pd.concat(frames, ignore_index=True))
    if df.empty:
        return {"rows": 0, "stations": 0, "archive": None}
    save_city(city, df)
    archive = ARCHIVE_DIR / f"{city}_{date_from}_{date_to}.csv"
    shutil.copyfile(OUTPUT_DIR / f"{city}_pm25.csv", archive)
    return {"rows": len(df), "stations": int(df["station_id"].nunique()),
            "archive": archive.name}


def pull_city(city: str, date_from: str, date_to: str, freq: str = DEFAULT_FREQ,
              assemble_only: bool = False) -> dict:
    wins = _windows(date_from, date_to, freq)
    counts = {"cached": 0, "ok": 0, "empty": 0, "failed": 0}
    if not assemble_only:
        for a, b in wins:
            counts[pull_window(city, a, b)] += 1
            time.sleep(0.5)  # pace between windows

    # NEVER let an incomplete pass overwrite a good existing CSV. A flaky
    # connection made 15 of Kolkata's 22 windows fail, and assembling from the
    # surviving 7 replaced a complete 93k-row file with 55k rows. Parts are
    # already safe on disk, so we simply defer assembly until the pull is whole
    # (or the caller explicitly asks via --assemble-only).
    if counts["failed"] and not assemble_only:
        res = {"rows": 0, "stations": 0, "archive": None}
        print(f"    {city}: {counts['failed']} window(s) failed - keeping the "
              f"existing CSV untouched; re-run to fill gaps.")
    else:
        res = assemble_city(city, date_from, date_to)
    status = "ok" if counts["failed"] == 0 else "partial"
    rec = {"city": city, "date_from": date_from, "date_to": date_to,
           "rows": res["rows"], "stations": res["stations"],
           "archive": res["archive"], "windows": counts,
           "windows_total": len(wins), "status": status,
           "pulled_at": datetime.utcnow().isoformat()}
    _log(rec)
    print(f"[archive] {city}: {res['rows']} rows, {res['stations']} stations, "
          f"windows {counts} -> {status}")
    return rec


def main() -> None:
    p = argparse.ArgumentParser(description="Archival OpenAQ pull for IndiaAQBench.")
    p.add_argument("--from", dest="date_from", default=DEFAULT_FROM)
    p.add_argument("--to", dest="date_to", default=DEFAULT_TO)
    p.add_argument("--cities", nargs="*", default=sorted(CITIES))
    p.add_argument("--freq", default=DEFAULT_FREQ,
                   help="Window size: MS=monthly (default), QS=quarterly, W=weekly.")
    p.add_argument("--assemble-only", action="store_true",
                   help="Rebuild city CSVs from existing parts; no network.")
    args = p.parse_args()

    print(f"Archival pull: {args.cities}  {args.date_from} -> {args.date_to} "
          f"(freq={args.freq}, resumable)")
    summary = []
    for city in args.cities:
        try:
            summary.append(pull_city(city, args.date_from, args.date_to,
                                     freq=args.freq,
                                     assemble_only=args.assemble_only))
        except Exception as e:
            _log({"city": city, "date_from": args.date_from, "date_to": args.date_to,
                  "status": "error", "error": repr(e),
                  "pulled_at": datetime.utcnow().isoformat()})
            traceback.print_exc()
            print(f"[archive] {city}: FAILED - logged, continuing.")

    total = sum(r.get("rows", 0) for r in summary)
    partial = [r["city"] for r in summary if r.get("status") == "partial"]
    print(f"\nDone. {len(summary)} cities, {total} total rows under {ARCHIVE_DIR}")
    if partial:
        print(f"PARTIAL (rerun the same command to fill gaps): {partial}")


if __name__ == "__main__":
    main()
