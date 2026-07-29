"""IndiaAQBench data orchestrator: CAMS download -> Aurora rollout -> station samples.

For each init date (12:00 UTC):
  1. Download CAMS global analysis (skipped if already present).
  2. Assemble the Aurora Batch; record the raw CAMS pm2p5 at init per station
     (the "raw CAMS analysis" baseline, lead 0).
  3. Roll out +12h..+steps*12h. Per step, extract:
       - station-cell values for FEATURE_VARS (-> the pairs table), and
       - an India-region surface-PM2.5 subset (small NetCDF, kept).
     The 456 MB/day global inputs are deleted afterwards unless --no-cleanup.
  4. Append predictions to results/pairs/pairs.parquet and log a manifest row.

Resumable: dates already marked done in the manifest are skipped. The model is
loaded ONCE for the whole run. Observations are NOT joined here — that happens
at eval time against the archived OpenAQ pulls.

Usage:
    python -m src.pipeline.orchestrate --dates 2025-11-15 2025-11-20 --device cpu
    python -m src.pipeline.orchestrate --dates-file docs/benchmark_dates.csv
"""
from __future__ import annotations

import argparse
import json
import re
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from ..data import cams_composition
from ..model import aurora_runner
from ..utils.geo import find_nearest_grid_cell

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = PROJECT_ROOT / "data" / "stations.csv"
PAIRS_DIR = PROJECT_ROOT / "results" / "pairs"
INDIA_DIR = PROJECT_ROOT / "results" / "india_fields"
MANIFEST = PAIRS_DIR / "manifest.jsonl"

KG_TO_UG = 1e9
# Surface vars sampled at station cells (calibrator features + target).
FEATURE_VARS = ["pm2p5", "pm1", "pm10", "2t", "10u", "10v", "msl"]
INDIA = dict(lat=(6.0, 37.0), lon=(68.0, 98.0))


def _load_registry() -> pd.DataFrame:
    if not REGISTRY.exists():
        raise SystemExit(f"{REGISTRY} missing - run python -m src.data.build_station_registry")
    reg = pd.read_csv(REGISTRY)
    reg["lon360"] = reg["lon"] % 360.0
    return reg


def _registry_version(reg: pd.DataFrame) -> str:
    """Short fingerprint of the exact station set used for a run.

    Pairs produced against different registry versions are NOT comparable: the
    Nov-2025 pilot dates were sampled at 33 stations (some Phase-1 era, since
    retired) while later dates used 127, so a pooled metrics table would mix two
    different station populations. Stamping the version makes that detectable
    instead of silent -- audit compares these across dates.
    """
    import hashlib

    ids = ",".join(str(s) for s in sorted(reg["station_id"]))
    return f"{len(reg)}:{hashlib.sha1(ids.encode()).hexdigest()[:8]}"


def _station_cells(reg: pd.DataFrame, lats: np.ndarray, lons: np.ndarray) -> pd.DataFrame:
    rows = []
    for _, r in reg.iterrows():
        li, loi, dist = find_nearest_grid_cell(float(r["lat"]), float(r["lon360"]), lats, lons)
        rows.append({**r[["station_id", "city", "station_name", "lat", "lon"]].to_dict(),
                     "lat_idx": li, "lon_idx": loi, "cell_dist_km": round(dist, 1)})
    return pd.DataFrame(rows)


def _sample(pred_batch, cells: pd.DataFrame) -> pd.DataFrame:
    """Sample FEATURE_VARS at station cells from a prediction Batch (history -1)."""
    li = cells["lat_idx"].to_numpy()
    loi = cells["lon_idx"].to_numpy()
    out = cells[["station_id", "city", "cell_dist_km"]].copy()
    for v in FEATURE_VARS:
        arr = np.asarray(pred_batch.surf_vars[v][0, -1])
        vals = arr[li, loi].astype(float)
        if v in ("pm2p5", "pm1", "pm10"):
            vals = vals * KG_TO_UG
        out[f"aurora_{v}"] = np.round(vals, 3)
    return out


def _india_subset(pred_batch) -> xr.Dataset:
    """India-region grid for EVERY feature var, not just pm2p5.

    This is what makes the expensive Aurora rollout a one-time cost: with all
    calibrator features stored on the grid, a changed station registry (or a new
    feature set, or a different city list) can be re-derived offline instead of
    re-running the model. ~1.3 MB/date, so keeping everything is nearly free.
    """
    lats = np.asarray(pred_batch.metadata.lat)
    lons = np.asarray(pred_batch.metadata.lon)
    la = (lats >= INDIA["lat"][0]) & (lats <= INDIA["lat"][1])
    lo = (lons >= INDIA["lon"][0]) & (lons <= INDIA["lon"][1])
    data = {}
    for v in FEATURE_VARS:
        arr = np.asarray(pred_batch.surf_vars[v][0, -1])[np.ix_(la, lo)]
        if v in ("pm2p5", "pm1", "pm10"):
            arr = arr * KG_TO_UG
        name = f"{v}_ugm3" if v in ("pm2p5", "pm1", "pm10") else v
        data[name] = (("latitude", "longitude"), arr.astype(np.float32))
    return xr.Dataset(data, coords={"latitude": lats[la], "longitude": lons[lo]})


def _manifest_done(registry_version: str | None = None) -> set[str]:
    """Dates already rolled out AT THE GIVEN REGISTRY VERSION.

    Resume must be registry-aware. The station registry grew 127 -> 159 after
    the OpenAQ re-pull, so dates completed under the old registry are NOT
    reusable: they sample Aurora at a different station set and pooling them
    with new dates would mix two populations. Ignoring the version here would
    have silently skipped three frozen dates at stale coverage -- invisible in
    the output, and only discoverable by counting rows.
    """
    if not MANIFEST.exists():
        return set()
    done = set()
    for line in MANIFEST.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("status") != "done":
            continue
        if registry_version is not None and rec.get("registry_version") != registry_version:
            continue  # rolled out at a different station set -> must redo
        done.add(rec["date"])
    return done


def _log(rec: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def process_date(date: str, model, reg: pd.DataFrame, steps: int, device: str,
                 cleanup: bool) -> int:
    """Run one init date end-to-end; returns number of pair rows written."""
    t0 = time.time()
    sfc_path, plev_path = cams_composition.download(date)

    batch = aurora_runner.assemble_inputs(sfc_path, plev_path)
    init_time = pd.Timestamp(batch.metadata.time[-1], tz="UTC")

    lats = np.asarray(batch.metadata.lat)
    lons = np.asarray(batch.metadata.lon)
    cells = _station_cells(reg, lats, lons)

    frames = []
    # Lead 0: the raw CAMS analysis input at init (baseline #3 in the spec).
    row0 = _sample(batch, cells)
    row0["lead_h"] = 0
    row0["valid_time"] = init_time
    frames.append(row0)

    india_steps = []
    for step, pred in aurora_runner.run_rollout(batch, steps=steps, device=device,
                                               model=model):
        s = _sample(pred, cells)
        s["lead_h"] = 12 * step
        s["valid_time"] = init_time + timedelta(hours=12 * step)
        frames.append(s)
        india_steps.append(_india_subset(pred).expand_dims(lead_h=[12 * step]))
        del pred
        print(f"  [{date}] step {step}/{steps} (+{12*step}h) done "
              f"({time.time()-t0:.0f}s elapsed)", flush=True)

    pairs = pd.concat(frames, ignore_index=True)
    pairs.insert(0, "init_date", date)
    # Self-describing provenance: the eval harness filters on this so pairs from
    # a different station set can never be pooled into one results table.
    pairs["registry_version"] = _registry_version(reg)

    PAIRS_DIR.mkdir(parents=True, exist_ok=True)
    out_parquet = PAIRS_DIR / f"pairs_{date}.parquet"
    pairs.to_parquet(out_parquet, index=False)

    INDIA_DIR.mkdir(parents=True, exist_ok=True)
    india = xr.concat(india_steps, dim="lead_h")
    india.attrs.update(init_date=date, init_time=str(init_time))
    india_path = INDIA_DIR / f"india_pm25_{date}.nc"
    india.to_netcdf(india_path)

    if cleanup:
        for p in (sfc_path, plev_path, sfc_path.parent / f"{date}_cams.nc.zip"):
            p.unlink(missing_ok=True)

    _log({"date": date, "status": "done", "rows": len(pairs),
          "stations": int(cells["station_id"].nunique()), "steps": steps,
          "registry_version": _registry_version(reg),
          "seconds": round(time.time() - t0), "pairs_file": out_parquet.name,
          "india_file": india_path.name, "written_at": datetime.utcnow().isoformat()})
    return len(pairs)


def main() -> None:
    p = argparse.ArgumentParser(description="IndiaAQBench orchestrator.")
    p.add_argument("--dates", nargs="*", default=[], help="Init dates YYYY-MM-DD.")
    p.add_argument("--dates-file", type=Path, help="File with one date per line (or CSV col 'date').")
    p.add_argument("--steps", type=int, default=8, help="Rollout steps (12h each).")
    p.add_argument("--device", default="cpu")
    p.add_argument("--no-cleanup", action="store_true",
                   help="Keep the global CAMS files after processing.")
    args = p.parse_args()

    dates = list(args.dates)
    if args.dates_file:
        txt = args.dates_file.read_text().splitlines()
        # Match YYYY-MM-DD rather than filtering header prefixes: the frozen
        # list's header is `init_date,...`, which does NOT start with "date",
        # so the old filter let the literal string "init_date" through as a
        # forecast date.
        dates += [tok for tok in (ln.strip().split(",")[0] for ln in txt)
                  if re.fullmatch(r"\d{4}-\d{2}-\d{2}", tok)]
    dates = list(dict.fromkeys(dates))  # de-dup, preserve order
    if not dates:
        raise SystemExit("No dates given.")

    reg = _load_registry()
    version = _registry_version(reg)
    done = _manifest_done(version)
    todo = [d for d in dates if d not in done]
    print(f"registry {version} ({len(reg)} stations) | {len(dates)} dates requested, "
          f"{len(dates)-len(todo)} already done at this registry, "
          f"{len(todo)} to run: {todo}", flush=True)
    if not todo:
        return

    print(f"Loading model on {args.device}...", flush=True)
    model = aurora_runner.load_model(args.device)

    for date in todo:
        try:
            n = process_date(date, model, reg, args.steps, args.device,
                             cleanup=not args.no_cleanup)
            print(f"[{date}] OK - {n} pair rows.", flush=True)
        except Exception as e:  # log + continue: one bad date must not kill a batch
            _log({"date": date, "status": "error", "error": repr(e),
                  "written_at": datetime.utcnow().isoformat()})
            traceback.print_exc()
            print(f"[{date}] FAILED - logged, continuing.", flush=True)


if __name__ == "__main__":
    main()
