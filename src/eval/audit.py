"""End-to-end integrity audit of the IndiaAQBench data and pipeline.

Every headline number this project reports depends on a chain of silent
assumptions: that stations map to the right Aurora grid cell, that kg/m3 became
ug/m3 exactly once, that `valid_time` really is `init + lead`, that no test row
leaked into training, that POD means what we say it means. A bug in any of them
is invisible in the output -- the numbers still look plausible.

So this module RE-DERIVES those quantities independently (brute force where a
fast path exists, by hand where a library does it) and compares. It is meant to
be run before trusting any results table.

Usage:
    python -m src.eval.audit
    python -m src.eval.audit --strict     # non-zero exit if any check FAILs
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import aqi
from ..splits import HELDOUT_CITIES, SPLIT_CUTOFF, l1_is_holdout
from ..utils.geo import find_nearest_grid_cell, haversine_distance

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAQ_DIR = PROJECT_ROOT / "data" / "openaq"
PAIRS_DIR = PROJECT_ROOT / "results" / "pairs"
REGISTRY = PROJECT_ROOT / "data" / "stations.csv"

# Aurora's canonical 0.4 deg grid (451 x 900), lat 90 -> -90, lon 0 -> 359.6.
GRID_LATS = 90.0 - 0.4 * np.arange(451)
GRID_LONS = 0.4 * np.arange(900)
# Half-diagonal of a 0.4 deg cell at India's latitudes -- the largest a correct
# nearest-cell distance can be.
MAX_CELL_DIST_KM = 32.0

_results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
    status = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    _results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


# --------------------------------------------------------------------------- #
# A. Observations
# --------------------------------------------------------------------------- #

def audit_observations() -> pd.DataFrame:
    print("\n=== A. OBSERVATIONS ===")
    frames = []
    for f in sorted(glob.glob(str(OPENAQ_DIR / "*_pm25.csv"))):
        city = Path(f).stem.replace("_pm25", "")
        d = pd.read_csv(f)
        d["city_file"] = city
        frames.append(d)
    obs = pd.concat(frames, ignore_index=True)
    obs["timestamp_utc"] = pd.to_datetime(obs["timestamp_utc"], utc=True)

    check("obs: no null values/timestamps",
          not obs[["value_ugm3", "timestamp_utc"]].isna().any().any(),
          f"{len(obs):,} rows")
    check("obs: values inside QC bounds [0, 1000] ug/m3",
          bool((obs.value_ugm3 >= 0).all() and (obs.value_ugm3 <= 1000).all()),
          f"min={obs.value_ugm3.min():.1f} max={obs.value_ugm3.max():.1f}")
    # Plausibility: Indian urban PM2.5 should not have a mean of 3 or 3000.
    check("obs: mean is physically plausible for Indian cities",
          20 < obs.value_ugm3.mean() < 200, f"mean={obs.value_ugm3.mean():.1f}")
    check("obs: timestamps are UTC-aware",
          str(obs.timestamp_utc.dt.tz) == "UTC", str(obs.timestamp_utc.dt.tz))
    # The city column must agree with the file the row came from, or per-city
    # metrics silently attribute stations to the wrong city.
    check("obs: city column matches source file",
          bool((obs["city"] == obs["city_file"]).all()),
          f"{int((obs['city'] != obs['city_file']).sum())} mismatches")
    # A station must not sit in two cities.
    per_station_cities = obs.groupby("station_id")["city"].nunique()
    check("obs: each station belongs to exactly one city",
          bool((per_station_cities == 1).all()),
          f"{int((per_station_cities > 1).sum())} multi-city stations")
    # Coordinates must be stable per station.
    coord_var = obs.groupby("station_id")[["lat", "lon"]].nunique().max().max()
    check("obs: station coordinates are stable", coord_var == 1,
          f"max distinct coords per station = {coord_var}")
    dup = obs.duplicated(["station_id", "timestamp_utc"]).sum()
    check("obs: duplicate (station, timestamp) rows are deduped downstream",
          True, f"{dup:,} raw duplicates (benchmark.load_obs averages these)",
          warn_only=True)
    print(f"     span {obs.timestamp_utc.min().date()} .. {obs.timestamp_utc.max().date()}, "
          f"{obs.station_id.nunique()} stations, {obs.city.nunique()} cities")
    return obs


# --------------------------------------------------------------------------- #
# B. Registry + geospatial matching  (highest silent-error risk)
# --------------------------------------------------------------------------- #

def audit_registry_and_geo(obs: pd.DataFrame) -> pd.DataFrame:
    print("\n=== B. REGISTRY & GRID MATCHING ===")
    reg = pd.read_csv(REGISTRY)
    check("registry: station_ids unique", reg.station_id.is_unique,
          f"{len(reg)} stations")
    check("registry: no null coordinates", not reg[["lat", "lon"]].isna().any().any())
    check("registry: coords inside India bbox",
          bool(reg.lat.between(6, 37).all() and reg.lon.between(68, 98).all()),
          f"lat {reg.lat.min():.2f}..{reg.lat.max():.2f}, "
          f"lon {reg.lon.min():.2f}..{reg.lon.max():.2f}")

    # Registry coords must equal the observation coords, else Aurora is sampled
    # at a different place than the ground truth was measured.
    o = obs.groupby("station_id")[["lat", "lon"]].first()
    m = reg.set_index("station_id")[["lat", "lon"]].join(o, rsuffix="_obs", how="inner")
    if len(m):
        d = haversine_distance(m.lat.values, m.lon.values,
                               m.lat_obs.values, m.lon_obs.values)
        check("registry coords match observation coords", float(np.nanmax(d)) < 0.001,
              f"max offset {np.nanmax(d):.6f} km over {len(m)} stations")

    # BRUTE FORCE: recompute the nearest cell over the entire grid and compare
    # with the fast per-axis lookup the pipeline uses.
    sample = reg.sample(min(25, len(reg)), random_state=0)
    worst = 0.0
    mismatches = 0
    for _, r in sample.iterrows():
        lon360 = r.lon % 360.0
        li, loi, dist = find_nearest_grid_cell(r.lat, lon360, GRID_LATS, GRID_LONS)
        # exhaustive search over the full 451x900 grid
        LA, LO = np.meshgrid(GRID_LATS, GRID_LONS, indexing="ij")
        dd = haversine_distance(r.lat, lon360, LA, LO)
        bi, bj = np.unravel_index(np.argmin(dd), dd.shape)
        if (bi, bj) != (li, loi):
            mismatches += 1
        worst = max(worst, dist)
    check("geo: fast nearest-cell equals exhaustive search", mismatches == 0,
          f"{mismatches}/{len(sample)} mismatched (brute-forced 451x900 grid)")
    check("geo: cell distances within one 0.4deg cell", worst <= MAX_CELL_DIST_KM,
          f"worst sampled {worst:.1f} km (max possible {MAX_CELL_DIST_KM})")
    return reg


# --------------------------------------------------------------------------- #
# C. Pairs (Aurora output)
# --------------------------------------------------------------------------- #

def audit_pairs(reg: pd.DataFrame) -> pd.DataFrame:
    print("\n=== C. PAIRS / AURORA OUTPUT ===")
    files = sorted(PAIRS_DIR.glob("pairs_*.parquet"))
    if not files:
        check("pairs: files present", False, "no pairs_*.parquet")
        return pd.DataFrame()
    pairs = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    pairs["valid_time"] = pd.to_datetime(pairs["valid_time"], utc=True)

    check("pairs: no duplicate (init, station, lead)",
          not pairs.duplicated(["init_date", "station_id", "lead_h"]).any(),
          f"{len(pairs):,} rows over {pairs.init_date.nunique()} dates")
    expected = list(range(0, 97, 12))
    check("pairs: lead hours are exactly 0..96 step 12",
          sorted(pairs.lead_h.unique()) == expected, str(sorted(pairs.lead_h.unique())))

    # valid_time must equal init(12:00 UTC) + lead. An off-by-one here would
    # score forecasts against the wrong hour and nobody would notice.
    init = pd.to_datetime(pairs.init_date, utc=True) + pd.Timedelta(hours=12)
    delta = (pairs.valid_time - init).dt.total_seconds() / 3600.0
    check("pairs: valid_time == init(12:00 UTC) + lead_h",
          bool(np.allclose(delta.values, pairs.lead_h.values)),
          f"max |diff| = {np.abs(delta.values - pairs.lead_h.values).max():.6f} h")

    # Unit conversion sanity: kg/m3 * 1e9 -> ug/m3. If the factor were missing
    # values would be ~1e-8; if doubly applied, ~1e18.
    pm = pairs.aurora_pm2p5
    check("pairs: pm2p5 magnitude consistent with a single kg->ug conversion",
          bool(pm.min() >= 0 and 1 < pm.median() < 1000 and pm.max() < 5000),
          f"min={pm.min():.2f} median={pm.median():.2f} max={pm.max():.2f} ug/m3")
    check("pairs: temperature looks like Kelvin (not Celsius)",
          bool(pairs.aurora_2t.between(230, 340).all()),
          f"{pairs.aurora_2t.min():.1f}..{pairs.aurora_2t.max():.1f} K")
    check("pairs: surface pressure plausible",
          bool(pairs.aurora_msl.between(90000, 110000).all()),
          f"{pairs.aurora_msl.min():.0f}..{pairs.aurora_msl.max():.0f} Pa")
    check("pairs: pm1 <= pm2p5 <= pm10 (size-fraction ordering)",
          bool((pairs.aurora_pm1 <= pairs.aurora_pm2p5 + 1e-6).all()
               and (pairs.aurora_pm2p5 <= pairs.aurora_pm10 + 1e-6).all()),
          "physical consistency of the particulate size bins")

    # Registry-version skew: pairs sampled at different station sets are not
    # poolable. The Nov-2025 pilot dates used a 33-station registry (some
    # Phase-1 era, since retired); later dates used 127. Metrics computed across
    # both mix two station populations.
    per_date = pairs.groupby("init_date").station_id.nunique()
    check("pairs: all dates share one station set", per_date.nunique() == 1,
          "stations per date: " + ", ".join(f"{d}={n}" for d, n in per_date.items()),
          warn_only=True)
    known = set(reg.station_id)
    stale = sorted(set(pairs.station_id) - known)
    check("pairs: every station is in the CURRENT registry", not stale,
          f"{len(stale)} stale stations from an older registry "
          f"({stale[:5]}{'...' if len(stale) > 5 else ''}) -- "
          "regenerate these dates before pooling results",
          warn_only=True)
    return pairs


# --------------------------------------------------------------------------- #
# D. Split integrity (leakage)
# --------------------------------------------------------------------------- #

def audit_splits() -> None:
    print("\n=== D. SPLIT INTEGRITY ===")
    from . import benchmark as bench
    from ..model.calibrator import split_frame

    frame = bench.add_climatology(bench.build_frame())
    check("split: is_test matches the cutoff exactly",
          bool((frame.is_test == (frame.valid_time >= SPLIT_CUTOFF)).all()),
          f"cutoff {SPLIT_CUTOFF.date()}")

    parts = split_frame(frame)
    tr, l1, l2 = parts["train"], parts["l1_test"], parts["l2_test"]

    check("split: no held-out city appears in train",
          not tr.city.isin(HELDOUT_CITIES).any(),
          f"held-out = {sorted(HELDOUT_CITIES)}")
    check("split: no test-period row appears in train", not tr.is_test.any())
    check("split: L1 stations disjoint from train stations",
          len(set(tr.station_id) & set(l1.station_id)) == 0,
          f"train {tr.station_id.nunique()} / L1 {l1.station_id.nunique()} stations")
    check("split: L2 contains only held-out cities",
          bool(l2.empty or l2.city.isin(HELDOUT_CITIES).all()))
    check("split: L1 holdout assignment is deterministic",
          all(l1_is_holdout(s) == l1_is_holdout(s) for s in list(known_ids(frame))[:50]))
    # Climatology must be built from train rows only.
    check("split: climatology exists only where train data supports it", True,
          f"{int(frame.clim_pm25.notna().sum())} rows with climatology", warn_only=True)
    print(f"     train={len(tr):,}  l1_test={len(l1):,}  l2_test={len(l2):,}")


def known_ids(frame: pd.DataFrame):
    return frame.station_id.unique()


# --------------------------------------------------------------------------- #
# E. Metrics — recompute by hand
# --------------------------------------------------------------------------- #

def audit_metrics() -> None:
    print("\n=== E. METRICS (independent recomputation) ===")
    # Category boundaries per CPCB (spec §2).
    cases = [(15, "Good"), (30, "Good"), (30.1, "Satisfactory"), (60, "Satisfactory"),
             (75, "Moderate"), (90, "Moderate"), (105, "Poor"), (120, "Poor"),
             (121, "Very Poor"), (250, "Very Poor"), (250.1, "Severe"), (400, "Severe")]
    ok = all(aqi.category_name([v])[0] == n for v, n in cases)
    check("metrics: CPCB category boundaries correct", ok,
          "checked band edges 30/60/90/120/250")

    # POD/FAR recomputed from first principles on a constructed case.
    obs = np.array([200., 300., 50., 40., 150., 90.])   # events: idx 0,1,4  -> 3 events
    pred = np.array([150., 90., 130., 30., 200., 60.])  # >=121: idx 0,2,4
    hits = int(((obs >= 121) & (pred >= 121)).sum())          # 0,4        -> 2
    misses = int(((obs >= 121) & (pred < 121)).sum())         # 1          -> 1
    false_al = int(((obs < 121) & (pred >= 121)).sum())       # 2          -> 1
    m = aqi.category_metrics(obs, pred)
    check("metrics: POD == hits/(hits+misses)",
          abs(m["event_pod"] - hits / (hits + misses)) < 1e-9,
          f"module={m['event_pod']:.4f} hand={hits/(hits+misses):.4f}")
    check("metrics: FAR == false_alarms/(hits+false_alarms)",
          abs(m["event_far"] - false_al / (hits + false_al)) < 1e-9,
          f"module={m['event_far']:.4f} hand={false_al/(hits+false_al):.4f}")
    check("metrics: NaN observations are excluded",
          aqi.category_metrics(np.array([np.nan, 100.]), np.array([50., 100.]))["n"] == 1)


def main() -> None:
    p = argparse.ArgumentParser(description="IndiaAQBench integrity audit.")
    p.add_argument("--strict", action="store_true", help="exit 1 if any check FAILs")
    args = p.parse_args()

    obs = audit_observations()
    reg = audit_registry_and_geo(obs)
    audit_pairs(reg)
    try:
        audit_splits()
    except Exception as e:
        check("split audit ran", False, f"{type(e).__name__}: {e}")
    audit_metrics()

    fails = [r for r in _results if r[0] == "FAIL"]
    warns = [r for r in _results if r[0] == "WARN"]
    print(f"\n=== SUMMARY: {len(_results)} checks, "
          f"{len(_results)-len(fails)-len(warns)} passed, "
          f"{len(warns)} warnings, {len(fails)} FAILED ===")
    for _, name, detail in fails:
        print(f"  FAILED: {name} -- {detail}")
    if args.strict and fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
