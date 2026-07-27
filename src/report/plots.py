"""Visualization module for IndiaAQBench reporting and dashboard.

Generates publication-ready static matplotlib figures in docs/figures/ from benchmark metrics:
- Headline event skill: Very Poor+ (>=121 ug/m3) POD, FAR, CSI vs lead time.
- Headline category skill: AQI 6-band category hit rate vs lead time.
- Per-city breakdown: POD and Category Hit Rate per city.
- Executive dashboard summary figure.

Comments explain design choices and metrics focus (Very Poor+ event skill > MAE).
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # Headless execution
import matplotlib.pyplot as plt

# Consistent styling & colors across all benchmark figures
METHOD_COLORS = {
    "raw_aurora": "#1f77b4",   # Blue - Foundation model baseline
    "calibrated": "#ff7f0e",   # Orange - Calibrated model
    "persistence": "#2ca02c",  # Green - Naive persistence
    "raw_cams": "#9467bd",     # Purple - CAMS global analysis
    "climatology": "#7f7f7f",  # Grey - Historical station climatology
}

METHOD_LABELS = {
    "raw_aurora": "Raw Aurora",
    "calibrated": "Calibrated",
    "persistence": "Persistence",
    "raw_cams": "Raw CAMS",
    "climatology": "Climatology",
}

METHOD_STYLES = {
    "raw_aurora": {"ls": "-", "marker": "o", "lw": 2},
    "calibrated": {"ls": "-", "marker": "s", "lw": 2},
    "persistence": {"ls": "--", "marker": "^", "lw": 1.5},
    "raw_cams": {"ls": ":", "marker": "v", "lw": 1.5},
    "climatology": {"ls": "-.", "marker": "x", "lw": 1.5},
}


def _prepare_lead_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Filter out zero-sample rows and compute pooled average across cities per lead x method."""
    valid = df[df["n"] > 0].copy() if "n" in df.columns else df.copy()
    if valid.empty:
        return pd.DataFrame()
    
    # Group by lead_h and method to compute mean metric values across cities
    cols = [c for c in ["event_pod", "event_far", "event_csi", "cat_hit_rate", "mae", "rmse", "bias", "corr"] if c in valid.columns]
    summary = valid.groupby(["lead_h", "method"])[cols].mean().reset_index()
    return summary


def plot_headline_events(df: pd.DataFrame, out_path: Path) -> Path:
    """Plot Very Poor+ (>=121 ug/m3) event detection metrics (POD, FAR, CSI) vs lead time."""
    summary = _prepare_lead_summary(df)
    if summary.empty:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No valid data for event metrics", ha="center", va="center")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharex=True)
    leads = sorted(summary["lead_h"].unique())
    methods = [m for m in METHOD_COLORS.keys() if m in summary["method"].unique()]

    # 1. Very Poor+ POD (Hit Rate) - Higher is better
    ax_pod = axes[0]
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "event_pod" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax_pod.plot(sub["lead_h"], sub["event_pod"], label=METHOD_LABELS.get(m, m),
                        color=METHOD_COLORS.get(m, "black"), **st)
    ax_pod.set_title("Very Poor+ POD (Hit Rate) ↑\n[Higher = Better]", fontsize=11, fontweight="bold")
    ax_pod.set_ylabel("Probability of Detection")
    ax_pod.set_ylim(-0.05, 1.05)
    ax_pod.grid(True, linestyle="--", alpha=0.5)

    # 2. Very Poor+ FAR (False Alarm Ratio) - Lower is better
    ax_far = axes[1]
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "event_far" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax_far.plot(sub["lead_h"], sub["event_far"], label=METHOD_LABELS.get(m, m),
                        color=METHOD_COLORS.get(m, "black"), **st)
    ax_far.set_title("Very Poor+ FAR (False Alarm Ratio) ↓\n[Lower = Better]", fontsize=11, fontweight="bold")
    ax_far.set_ylabel("False Alarm Ratio")
    ax_far.set_ylim(-0.05, 1.05)
    ax_far.grid(True, linestyle="--", alpha=0.5)

    # 3. Very Poor+ CSI (Critical Success Index) - Higher is better
    ax_csi = axes[2]
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "event_csi" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax_csi.plot(sub["lead_h"], sub["event_csi"], label=METHOD_LABELS.get(m, m),
                        color=METHOD_COLORS.get(m, "black"), **st)
    ax_csi.set_title("Very Poor+ CSI (Critical Success Index) ↑\n[Higher = Better]", fontsize=11, fontweight="bold")
    ax_csi.set_ylabel("Critical Success Index")
    ax_csi.set_ylim(-0.05, 1.05)
    ax_csi.grid(True, linestyle="--", alpha=0.5)

    for ax in axes:
        ax.set_xlabel("Forecast Lead Time (hours)")
        ax.set_xticks(leads)

    axes[0].legend(loc="best", fontsize=9, framealpha=0.8)
    fig.suptitle("Headline Event Skill: Very Poor+ (≥121 µg/m³) Severe Pollution Episodes",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.tight_layout()
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_category_skill(df: pd.DataFrame, out_path: Path) -> Path:
    """Plot AQI 6-Band Category Hit Rate and secondary MAE vs lead time."""
    summary = _prepare_lead_summary(df)
    if summary.empty:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No valid data for category skill", ha="center", va="center")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    fig, (ax_cat, ax_mae) = plt.subplots(1, 2, figsize=(12, 4.5), sharex=True)
    leads = sorted(summary["lead_h"].unique())
    methods = [m for m in METHOD_COLORS.keys() if m in summary["method"].unique()]

    # Left: Category Hit Rate (Headline metric)
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "cat_hit_rate" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax_cat.plot(sub["lead_h"], sub["cat_hit_rate"], label=METHOD_LABELS.get(m, m),
                        color=METHOD_COLORS.get(m, "black"), **st)
    ax_cat.set_title("AQI Category Hit Rate (6-Band Accuracy) ↑\n[Headline Metric]", fontsize=11, fontweight="bold")
    ax_cat.set_xlabel("Forecast Lead Time (hours)")
    ax_cat.set_ylabel("Exact Band Accuracy")
    ax_cat.set_ylim(-0.05, 1.05)
    ax_cat.grid(True, linestyle="--", alpha=0.5)
    ax_cat.legend(loc="best", fontsize=9)

    # Right: MAE (Secondary metric)
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "mae" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax_mae.plot(sub["lead_h"], sub["mae"], label=METHOD_LABELS.get(m, m),
                        color=METHOD_COLORS.get(m, "black"), **st)
    ax_mae.set_title("Mean Absolute Error (µg/m³) ↓\n[Secondary Metric]", fontsize=11, fontweight="bold")
    ax_mae.set_xlabel("Forecast Lead Time (hours)")
    ax_mae.set_ylabel("MAE (µg/m³)")
    ax_mae.grid(True, linestyle="--", alpha=0.5)

    for ax in (ax_cat, ax_mae):
        ax.set_xticks(leads)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_per_city_breakdown(df: pd.DataFrame, out_path: Path, target_lead: int = 24) -> Path:
    """Plot per-city breakdown of Very Poor+ POD and Category Hit Rate for target lead time."""
    valid = df[(df["n"] > 0) & (df["lead_h"] == target_lead)].copy() if "n" in df.columns else df[df["lead_h"] == target_lead].copy()
    
    if valid.empty:
        # Fallback to any lead if target lead is empty
        valid = df[df["n"] > 0].copy() if "n" in df.columns else df.copy()
        if not valid.empty:
            target_lead = int(valid["lead_h"].iloc[0])
            valid = valid[valid["lead_h"] == target_lead]

    if valid.empty:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No valid data for per-city breakdown", ha="center", va="center")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    cities = sorted(valid["city"].unique())
    methods = [m for m in ["raw_aurora", "calibrated", "persistence", "raw_cams"] if m in valid["method"].unique()]

    fig, (ax_pod, ax_cat) = plt.subplots(1, 2, figsize=(14, 5))
    x = np.arange(len(cities))
    width = 0.8 / max(len(methods), 1)

    for i, m in enumerate(methods):
        sub = valid[valid["method"] == m].set_index("city")
        pod_vals = [sub.loc[c, "event_pod"] if c in sub.index and "event_pod" in sub.columns and pd.notna(sub.loc[c, "event_pod"]) else 0 for c in cities]
        cat_vals = [sub.loc[c, "cat_hit_rate"] if c in sub.index and "cat_hit_rate" in sub.columns and pd.notna(sub.loc[c, "cat_hit_rate"]) else 0 for c in cities]

        offset = x + (i - len(methods)/2 + 0.5) * width
        ax_pod.bar(offset, pod_vals, width, label=METHOD_LABELS.get(m, m), color=METHOD_COLORS.get(m, "grey"), alpha=0.85)
        ax_cat.bar(offset, cat_vals, width, label=METHOD_LABELS.get(m, m), color=METHOD_COLORS.get(m, "grey"), alpha=0.85)

    ax_pod.set_title(f"Very Poor+ Event POD by City (+{target_lead}h Lead) ↑", fontsize=11, fontweight="bold")
    ax_pod.set_ylabel("POD (Hit Rate)")
    ax_pod.set_xticks(x)
    ax_pod.set_xticklabels([c.capitalize() for c in cities], rotation=30, ha="right")
    ax_pod.set_ylim(0, 1.05)
    ax_pod.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax_pod.legend(loc="best", fontsize=8)

    ax_cat.set_title(f"AQI Category Hit Rate by City (+{target_lead}h Lead) ↑", fontsize=11, fontweight="bold")
    ax_cat.set_ylabel("Category Accuracy")
    ax_cat.set_xticks(x)
    ax_cat.set_xticklabels([c.capitalize() for c in cities], rotation=30, ha="right")
    ax_cat.set_ylim(0, 1.05)
    ax_cat.grid(True, linestyle="--", alpha=0.4, axis="y")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_dashboard_summary(df: pd.DataFrame, out_path: Path) -> Path:
    """Consolidated 2x2 executive scorecard dashboard summarizing benchmark metrics."""
    summary = _prepare_lead_summary(df)
    if summary.empty:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No valid data for dashboard summary", ha="center", va="center")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        return out_path

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    leads = sorted(summary["lead_h"].unique())
    methods = [m for m in METHOD_COLORS.keys() if m in summary["method"].unique()]

    # Top-Left: Event POD (Headline)
    ax = axes[0, 0]
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "event_pod" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax.plot(sub["lead_h"], sub["event_pod"], label=METHOD_LABELS.get(m, m),
                    color=METHOD_COLORS.get(m, "black"), **st)
    ax.set_title("A. Very Poor+ Event POD (Hit Rate) ↑", fontsize=11, fontweight="bold")
    ax.set_ylabel("Probability of Detection")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="best", fontsize=8)

    # Top-Right: Event CSI (Headline)
    ax = axes[0, 1]
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "event_csi" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax.plot(sub["lead_h"], sub["event_csi"], label=METHOD_LABELS.get(m, m),
                    color=METHOD_COLORS.get(m, "black"), **st)
    ax.set_title("B. Critical Success Index (CSI) ↑", fontsize=11, fontweight="bold")
    ax.set_ylabel("Critical Success Index")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, linestyle="--", alpha=0.5)

    # Bottom-Left: AQI Category Hit Rate (Headline)
    ax = axes[1, 0]
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "cat_hit_rate" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax.plot(sub["lead_h"], sub["cat_hit_rate"], label=METHOD_LABELS.get(m, m),
                    color=METHOD_COLORS.get(m, "black"), **st)
    ax.set_title("C. AQI Category Hit Rate (6-Band) ↑", fontsize=11, fontweight="bold")
    ax.set_ylabel("Category Accuracy")
    ax.set_xlabel("Forecast Lead Time (hours)")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, linestyle="--", alpha=0.5)

    # Bottom-Right: MAE (Secondary)
    ax = axes[1, 1]
    for m in methods:
        sub = summary[summary["method"] == m].sort_values("lead_h")
        if not sub.empty and "mae" in sub.columns:
            st = METHOD_STYLES.get(m, {})
            ax.plot(sub["lead_h"], sub["mae"], label=METHOD_LABELS.get(m, m),
                    color=METHOD_COLORS.get(m, "black"), **st)
    ax.set_title("D. Mean Absolute Error (Secondary Metric) ↓", fontsize=11, fontweight="bold")
    ax.set_ylabel("MAE (µg/m³)")
    ax.set_xlabel("Forecast Lead Time (hours)")
    ax.grid(True, linestyle="--", alpha=0.5)

    for a in axes.flat:
        a.set_xticks(leads)

    fig.suptitle("IndiaAQBench Executive Scorecard Dashboard", fontsize=14, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path
