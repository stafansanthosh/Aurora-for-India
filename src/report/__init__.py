"""IndiaAQBench reporting and dashboard package.

Provides per-city x per-lead scorecards and visualization tools for benchmark metrics:
- Very Poor+ (>=121 ug/m3) event skill (POD, FAR, CSI) - headline
- AQI category hit rate (6-band accuracy) - headline
- MAE, RMSE, Bias, Correlation - secondary
"""

from .scorecard import load_metrics, build_scorecard_summary, generate_markdown_report
from .plots import plot_headline_events, plot_category_skill, plot_per_city_breakdown, plot_dashboard_summary

__all__ = [
    "load_metrics",
    "build_scorecard_summary",
    "generate_markdown_report",
    "plot_headline_events",
    "plot_category_skill",
    "plot_per_city_breakdown",
    "plot_dashboard_summary",
]
