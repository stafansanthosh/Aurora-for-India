"""Phase 1 baseline evaluation: CAMS PM2.5 vs OpenAQ ground truth.

Loads ``data/processed/{city}_aligned.csv``, computes per-station error metrics
of the CAMS reanalysis PM2.5 against OpenAQ station readings, and writes a
summary to ``results/metrics/{city}_phase1.csv``. This answers the Phase-1
success criterion: one MAE number comparing a global model's PM2.5 to a real
Indian station (COPILOT_CONTEXT.md section 9).

Metrics are computed PER STATION because persistence (the reference baseline)
shifts within a single station's time series; pooling stations would both
break the shift and create non-unique timestamps.

Usage:
    python -m src.eval.run_phase1 --city delhi
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .metrics import compute_metrics

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
METRICS_DIR = PROJECT_ROOT / "results" / "metrics"


def evaluate_city(city: str, aligned_path: Path | None = None) -> pd.DataFrame:
    aligned_path = aligned_path or PROCESSED_DIR / f"{city}_aligned.csv"
    df = pd.read_csv(aligned_path, parse_dates=["timestamp_utc"])
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)

    if "cams_pm25" not in df.columns:
        raise SystemExit("Aligned file has no cams_pm25 column — nothing to score.")

    rows: list[dict] = []
    for sid, g in df.groupby("station_id"):
        g = g.dropna(subset=["openaq_pm25", "cams_pm25"]).sort_values("timestamp_utc")
        if g.empty:
            continue
        g = g.set_index("timestamp_utc")
        m = compute_metrics(g["openaq_pm25"], g["cams_pm25"], label="cams_vs_openaq")
        m["station_id"] = sid
        m["dist_km"] = round(float(g["distance_km"].iloc[0]), 2) if "distance_km" in g else None
        rows.append(m)

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    cols = ["station_id", "n", "MAE", "RMSE", "correlation",
            "skill_vs_persistence", "dist_km"]
    return result[[c for c in cols if c in result.columns]].sort_values(
        "MAE"
    ).reset_index(drop=True)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 1 CAMS-vs-OpenAQ evaluation.")
    p.add_argument("--city", required=True)
    p.add_argument("--aligned", type=Path, default=None, help="Aligned CSV override.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    res = evaluate_city(args.city, aligned_path=args.aligned)
    if res.empty:
        print("No station had overlapping OpenAQ + CAMS data — no metrics.")
        return

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    out = METRICS_DIR / f"{args.city}_phase1.csv"
    res.to_csv(out, index=False)

    # Pooled headline (weighted by station sample size) for the success metric.
    total_n = int(res["n"].sum())
    wmae = float((res["MAE"] * res["n"]).sum() / total_n)
    print(f"\n=== Phase 1: CAMS PM2.5 vs OpenAQ - {args.city} ===")
    print(res.to_string(index=False))
    print(f"\nStations scored: {len(res)}   Total matched hours: {total_n}")
    print(f"Sample-weighted mean MAE: {wmae:.1f} ug/m3")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
