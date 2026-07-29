"""Scorecard generator for IndiaAQBench evaluation results.

Loads benchmark metrics from results/metrics/indiaaqbench.csv, computes per-city
and per-lead scorecards emphasizing Very Poor+ event skill (POD, FAR, CSI) and
category hit rate over MAE, renders markdown reports, and generates figures into
docs/figures/.

Usage:
    python -m src.report.scorecard
    python -m src.report.scorecard --metrics results/metrics/indiaaqbench.csv --out-dir docs/figures/
    python -m src.report.scorecard --selftest
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from .plots import (
    plot_headline_events,
    plot_category_skill,
    plot_per_city_breakdown,
    plot_dashboard_summary,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METRICS_PATH = PROJECT_ROOT / "results" / "metrics" / "indiaaqbench.csv"
DEFAULT_EXTREMES_PATH = PROJECT_ROOT / "results" / "metrics" / "indiaaqbench_extremes.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "docs" / "figures"
DEFAULT_MD_PATH = DEFAULT_OUT_DIR / "scorecard.md"


def load_metrics(path: Path) -> pd.DataFrame:
    """Load metrics CSV, clean column names, and enforce numeric types.
    
    Drops rows where sample size n == 0 or missing.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Metrics file not found: {p}")
    
    df = pd.read_csv(p)
    df.columns = [c.strip().lower() for c in df.columns]

    numeric_cols = ["lead_h", "n", "mae", "rmse", "bias", "corr",
                    "cat_hit_rate", "event_pod", "event_far", "event_csi"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filter out rows with zero sample size
    if "n" in df.columns:
        df = df[df["n"].fillna(0) > 0].copy()

    return df


def build_scorecard_summary(df: pd.DataFrame, group_by: str = "lead_h") -> pd.DataFrame:
    """Aggregate metrics across cities by lead_h (or across leads by city) for each method."""
    if df.empty:
        return pd.DataFrame()

    valid = df.copy()
    metric_cols = [c for c in ["event_pod", "event_far", "event_csi", "cat_hit_rate", "mae", "rmse", "bias", "corr"] if c in valid.columns]
    
    grouped = (valid.groupby([group_by, "method"])[metric_cols]
               .mean()
               .reset_index())
    
    # Sort logically
    if group_by == "lead_h":
        grouped = grouped.sort_values(["lead_h", "method"])
    else:
        grouped = grouped.sort_values(["city", "method"])

    return grouped


def generate_markdown_report(
    df: pd.DataFrame,
    extremes_df: pd.DataFrame | None = None,
    out_path: Path | None = None
) -> str:
    """Generate a comprehensive Markdown scorecard report highlighting event skill over MAE."""
    lines = [
        "# IndiaAQBench Scorecard Report",
        "",
        "> **Note on Temporal Cutoff Revision:** Split cutoff revised once to **2025-12-01** (disclosed),",
        "> ensuring post-monsoon severe season data are present in training.",
        "",
        "## Headline Metric Focus",
        "GRAP emergency actions trigger on AQI categories. Success is evaluated on:",
        "1. **Very Poor+ Event Skill (≥121 µg/m³)**: POD (hit rate ↑), FAR (false alarm ratio ↓), CSI (critical success index ↑).",
        "2. **Category Hit Rate**: Exact 6-band AQI category accuracy ↑.",
        "3. **MAE**: Reported secondarily for continuous regression fidelity.",
        "",
        "---",
        "",
        "## 1. Pooled Headline Scorecard by Lead Time",
        "",
    ]

    by_lead = build_scorecard_summary(df, group_by="lead_h")
    if not by_lead.empty:
        # Format table per lead time
        pivot_pod = by_lead.pivot(index="lead_h", columns="method", values="event_pod")
        pivot_far = by_lead.pivot(index="lead_h", columns="method", values="event_far")
        pivot_csi = by_lead.pivot(index="lead_h", columns="method", values="event_csi")
        pivot_cat = by_lead.pivot(index="lead_h", columns="method", values="cat_hit_rate")
        pivot_mae = by_lead.pivot(index="lead_h", columns="method", values="mae")

        lines.append("### Very Poor+ Event POD (Probability of Detection) ↑")
        lines.append(pivot_pod.round(3).to_markdown())
        lines.append("")

        lines.append("### Very Poor+ Event FAR (False Alarm Ratio) ↓")
        lines.append(pivot_far.round(3).to_markdown())
        lines.append("")

        lines.append("### Very Poor+ Event CSI (Critical Success Index) ↑")
        lines.append(pivot_csi.round(3).to_markdown())
        lines.append("")

        lines.append("### AQI Category Hit Rate (6-Band Accuracy) ↑")
        lines.append(pivot_cat.round(3).to_markdown())
        lines.append("")

        lines.append("### Secondary Metric: MAE (µg/m³) ↓")
        lines.append(pivot_mae.round(2).to_markdown())
        lines.append("")

    lines.append("## 2. Per-City Scorecard Breakdown (+24h Lead)")
    lines.append("")
    by_city_24 = df[df["lead_h"] == 24] if "lead_h" in df.columns else df
    if not by_city_24.empty:
        city_summary = (by_city_24.groupby(["city", "method"])[["event_pod", "event_far", "event_csi", "cat_hit_rate", "mae"]]
                        .first()
                        .reset_index())
        pivot_city_pod = city_summary.pivot(index="city", columns="method", values="event_pod")
        lines.append("### Per-City Event POD (+24h) ↑")
        lines.append(pivot_city_pod.round(3).to_markdown())
        lines.append("")

    if extremes_df is not None and not extremes_df.empty:
        lines.append("## 3. Extremes Subset Scorecard (obs ≥ 121 µg/m³)")
        lines.append("")
        ext_lead = build_scorecard_summary(extremes_df, group_by="lead_h")
        if not ext_lead.empty:
            ext_pod = ext_lead.pivot(index="lead_h", columns="method", values="event_pod")
            ext_mae = ext_lead.pivot(index="lead_h", columns="method", values="mae")
            lines.append("### Extremes Event POD ↑")
            lines.append(ext_pod.round(3).to_markdown())
            lines.append("")
            lines.append("### Extremes MAE ↓")
            lines.append(ext_mae.round(2).to_markdown())
            lines.append("")

    report_text = "\n".join(lines)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")

    return report_text


def _test() -> None:
    """Self-test function validating load, scorecard calculations, markdown generation, and plots."""
    print("Running scorecard self-test...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        csv_file = tmp_path / "indiaaqbench.csv"
        ext_csv_file = tmp_path / "indiaaqbench_extremes.csv"

        # Create synthetic test dataset
        rows = []
        for lead in [12, 24, 48, 72]:
            for city in ["delhi", "kanpur", "kolkata"]:
                for method in [
                    "raw_aurora",
                    "calibrated",
                    "persistence",
                    "cams_forecast",
                    "cams_lead0_fixed",
                ]:
                    rows.append({
                        "lead_h": lead,
                        "city": city,
                        "method": method,
                        "n": 50,
                        "mae": np.random.uniform(20, 60),
                        "rmse": np.random.uniform(30, 80),
                        "bias": np.random.uniform(-10, 10),
                        "corr": np.random.uniform(0.3, 0.8),
                        "cat_hit_rate": np.random.uniform(0.3, 0.7),
                        "event_pod": np.random.uniform(0.2, 0.9),
                        "event_far": np.random.uniform(0.1, 0.5),
                        "event_csi": np.random.uniform(0.2, 0.8),
                    })
        pd.DataFrame(rows).to_csv(csv_file, index=False)
        pd.DataFrame(rows).to_csv(ext_csv_file, index=False)

        # 1. Test load_metrics
        df = load_metrics(csv_file)
        assert len(df) == len(rows), f"Expected {len(rows)} rows, got {len(df)}"

        # 2. Test build_scorecard_summary
        summary = build_scorecard_summary(df, group_by="lead_h")
        assert not summary.empty, "Summary should not be empty"

        # 3. Test generate_markdown_report
        md_out = tmp_path / "scorecard.md"
        report = generate_markdown_report(df, extremes_df=df, out_path=md_out)
        assert md_out.exists(), "Markdown file was not created"
        assert "# IndiaAQBench Scorecard Report" in report

        # 4. Test plot generation
        fig_dir = tmp_path / "figures"
        f1 = plot_headline_events(df, fig_dir / "headline_events.png")
        f2 = plot_category_skill(df, fig_dir / "category_skill.png")
        f3 = plot_per_city_breakdown(df, fig_dir / "per_city_breakdown.png", target_lead=24)
        f4 = plot_dashboard_summary(df, fig_dir / "dashboard_summary.png")

        for f in [f1, f2, f3, f4]:
            assert f.exists(), f"Figure file {f} was not created"

    print("Scorecard self-test passed successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(description="IndiaAQBench Scorecard & Dashboard Generator")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS_PATH,
                        help="Path to indiaaqbench.csv metrics file.")
    parser.add_argument("--extremes-metrics", type=Path, default=DEFAULT_EXTREMES_PATH,
                        help="Path to indiaaqbench_extremes.csv metrics file.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="Directory to save output figures.")
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_PATH,
                        help="Path to save markdown scorecard report.")
    parser.add_argument("--selftest", action="store_true",
                        help="Run self-test on synthetic data and exit.")
    args = parser.parse_args()

    if args.selftest:
        _test()
        sys.exit(0)

    print(f"Loading metrics from {args.metrics}...")
    df = load_metrics(args.metrics)

    extremes_df = None
    if args.extremes_metrics.is_file():
        print(f"Loading extremes metrics from {args.extremes_metrics}...")
        extremes_df = load_metrics(args.extremes_metrics)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Render figures to docs/figures/
    print("Generating scorecard dashboard figures...")
    f1 = plot_headline_events(df, args.out_dir / "scorecard_events.png")
    f2 = plot_category_skill(df, args.out_dir / "scorecard_category.png")
    f3 = plot_per_city_breakdown(df, args.out_dir / "scorecard_per_city.png", target_lead=24)
    f4 = plot_dashboard_summary(df, args.out_dir / "dashboard_summary.png")

    print(f"Wrote figures to {args.out_dir}:")
    print(f"  - {f1.name}")
    print(f"  - {f2.name}")
    print(f"  - {f3.name}")
    print(f"  - {f4.name}")

    # Generate Markdown Scorecard Report
    print(f"Generating markdown report at {args.md_out}...")
    generate_markdown_report(df, extremes_df=extremes_df, out_path=args.md_out)
    print(f"Wrote markdown report to {args.md_out}")


if __name__ == "__main__":
    main()
