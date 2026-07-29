"""Unit tests moved from src.eval.aqi's inline smoke test."""
from __future__ import annotations

import unittest

import numpy as np

from src.eval.aqi import (
    CATEGORIES,
    brier_score,
    category_metrics,
    category_name,
)


class AqiTests(unittest.TestCase):
    def test_band_edges(self) -> None:
        self.assertEqual(
            list(category_name([15, 45, 75, 105, 200, 300])),
            CATEGORIES,
        )
        self.assertEqual(category_name([30])[0], "Good")
        self.assertEqual(category_name([30.1])[0], "Satisfactory")
        self.assertEqual(category_name([250])[0], "Very Poor")
        self.assertEqual(category_name([250.1])[0], "Severe")

    def test_perfect_forecast(self) -> None:
        obs = np.array([20, 80, 150, 300, 50.0])
        metrics = category_metrics(obs, obs)
        self.assertEqual(metrics["cat_hit_rate"], 1.0)
        self.assertEqual(metrics["event_pod"], 1.0)
        self.assertEqual(metrics["event_far"], 0.0)

    def test_phase_two_missed_severe_event(self) -> None:
        metrics = category_metrics([290.0], [86.0])
        self.assertEqual(metrics["event_pod"], 0.0)
        self.assertEqual(metrics["event_miss_rate"], 1.0)
        self.assertEqual(metrics["event_hits"], 0)
        self.assertEqual(metrics["event_misses"], 1)
        self.assertEqual(metrics["event_false_alarms"], 0)
        self.assertEqual(metrics["event_observed"], 1)
        self.assertEqual(metrics["event_forecast"], 0)
        self.assertEqual(metrics["cat_hit_rate"], 0.0)

    def test_adjacent_band_credit(self) -> None:
        metrics = category_metrics([105.0], [85.0])
        self.assertEqual(metrics["cat_hit_rate"], 0.0)
        self.assertEqual(metrics["cat_adjacent"], 1.0)

    def test_brier_score(self) -> None:
        self.assertEqual(brier_score([1, 0], [1.0, 0.0]), 0.0)
        self.assertEqual(brier_score([1], [0.0]), 1.0)

    def test_nans_are_dropped(self) -> None:
        self.assertEqual(
            category_metrics([np.nan, 100], [50, 100])["n"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
