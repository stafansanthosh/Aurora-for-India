"""Phase 1 visualisation: CAMS PM2.5 vs OpenAQ ground truth.

Generates three figures into ``results/plots/`` from the aligned dataset:
  1. Scatter of CAMS vs OpenAQ with the 1:1 line (shows systematic bias).
  2. Time series overlay for the single station with the most matched hours.
  3. Per-station MAE bar chart.

Usage:
    python -m src.eval.plots --city delhi
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless / file output only
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .metrics import compute_metrics  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PLOTS_DIR = PROJECT_ROOT / "results" / "plots"


def _load(city: str, aligned_path: Path | None) -> pd.DataFrame:
    path = aligned_path or PROCESSED_DIR / f"{city}_aligned.csv"
    df = pd.read_csv(path, parse_dates=["timestamp_utc"])
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.dropna(subset=["openaq_pm25", "cams_pm25"])


def plot_scatter(df: pd.DataFrame, city: str) -> Path:
    fig, ax = plt.subplots(figsize=(6, 6))
    for sid, g in df.groupby("station_id"):
        ax.scatter(g["openaq_pm25"], g["cams_pm25"], s=14, alpha=0.6, label=str(sid))
    hi = max(df["openaq_pm25"].max(), df["cams_pm25"].max()) * 1.05
    ax.plot([0, hi], [0, hi], "k--", lw=1, label="1:1")
    ax.set_xlim(0, hi)
    ax.set_ylim(0, hi)
    ax.set_xlabel("OpenAQ PM2.5 (ug/m3)")
    ax.set_ylabel("CAMS PM2.5 (ug/m3)")
    ax.set_title(f"CAMS vs OpenAQ - {city} (Phase 1)")
    ax.legend(title="station", fontsize=7, ncol=2)
    out = PLOTS_DIR / f"{city}_scatter.png"
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_timeseries(df: pd.DataFrame, city: str) -> Path:
    # Station with the most matched hours = clearest overlay.
    sid = df.groupby("station_id").size().idxmax()
    g = df[df["station_id"] == sid].sort_values("timestamp_utc")
    m = compute_metrics(
        g.set_index("timestamp_utc")["openaq_pm25"],
        g.set_index("timestamp_utc")["cams_pm25"],
    )
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(g["timestamp_utc"], g["openaq_pm25"], "-o", ms=3, label="OpenAQ (obs)")
    ax.plot(g["timestamp_utc"], g["cams_pm25"], "-s", ms=3, label="CAMS (model)")
    ax.set_xlabel("time (UTC)")
    ax.set_ylabel("PM2.5 (ug/m3)")
    ax.set_title(
        f"{city} station {sid}: MAE={m['MAE']:.0f}  corr={m['correlation']:.2f}"
    )
    ax.legend()
    out = PLOTS_DIR / f"{city}_timeseries.png"
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def plot_station_mae(df: pd.DataFrame, city: str) -> Path:
    maes = {}
    for sid, g in df.groupby("station_id"):
        gg = g.set_index("timestamp_utc")
        maes[str(sid)] = compute_metrics(gg["openaq_pm25"], gg["cams_pm25"])["MAE"]
    s = pd.Series(maes).sort_values()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(s.index, s.values, color="#c0504d")
    ax.set_xlabel("MAE (ug/m3)")
    ax.set_ylabel("station")
    ax.set_title(f"CAMS-vs-OpenAQ MAE by station - {city}")
    out = PLOTS_DIR / f"{city}_station_mae.png"
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot Phase 1 CAMS-vs-OpenAQ results.")
    p.add_argument("--city", required=True)
    p.add_argument("--aligned", type=Path, default=None)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    df = _load(args.city, args.aligned)
    if df.empty:
        raise SystemExit("No matched OpenAQ+CAMS rows to plot.")
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    outs = [
        plot_scatter(df, args.city),
        plot_timeseries(df, args.city),
        plot_station_mae(df, args.city),
    ]
    for o in outs:
        print(f"wrote {o}")


if __name__ == "__main__":
    main()
