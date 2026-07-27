"""Guardrail, split, OOD, and seasonal-transfer tests for the calibrator."""
from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.model.calibrator import (
    EventSkillRegressionError,
    PooledCalibrator,
    _calm_train_severe_test_frame,
    _synthetic_frame,
    _winter_train_monsoon_test_frame,
    compare_with_raw,
    event_skill_failures,
    save_if_event_safe,
    split_frame,
)
from src.splits import HELDOUT_CITIES, l1_is_holdout


class CalibratorTests(unittest.TestCase):
    def test_split_contract_and_same_regime_correction(self) -> None:
        frame = _synthetic_frame()
        parts = split_frame(frame)

        # Every assertion from the former inline _test() is retained here.
        self.assertFalse(parts["train"]["city"].isin(HELDOUT_CITIES).any())
        self.assertTrue(parts["l2_test"]["city"].isin(HELDOUT_CITIES).all())
        holdout_fraction = frame["station_id"].map(l1_is_holdout).mean()
        self.assertGreater(holdout_fraction, 0)
        self.assertLess(holdout_fraction, 0.5)
        self.assertEqual(l1_is_holdout(7), l1_is_holdout(7))

        cal = PooledCalibrator(max_iter=80).fit(parts["train"])
        held = parts["l1_test"].dropna(subset=["obs_pm25"])
        obs = held["obs_pm25"].to_numpy()
        mae_raw = np.mean(
            np.abs(held["aurora_pm2p5"].to_numpy() - obs))
        mae_cal = np.mean(np.abs(cal.predict(held) - obs))
        self.assertLess(mae_cal, 0.6 * mae_raw, (mae_raw, mae_cal))

    def test_calm_train_severe_test_trips_no_harm_gate(self) -> None:
        frame = _calm_train_severe_test_frame()
        train = frame[~frame["is_test"]]
        severe_test = frame[frame["is_test"]]
        cal = PooledCalibrator(max_iter=80).fit(train)
        result = compare_with_raw(severe_test, cal.predict(severe_test))

        self.assertEqual(result["raw_aurora"]["event_pod"], 1.0)
        self.assertEqual(result["calibrated"]["event_pod"], 0.0)
        self.assertTrue(event_skill_failures({"severe_test": result}))

        class MustNotSave:
            def save(self, path: Path) -> Path:
                raise AssertionError("harmful model reached save()")

        with self.assertRaises(EventSkillRegressionError):
            save_if_event_safe(
                MustNotSave(), Path("must-not-exist.joblib"),
                {"severe_test": result},
            )

    def test_winter_only_train_to_monsoon_only_test(self) -> None:
        frame = _winter_train_monsoon_test_frame()
        winter = frame[~frame["is_test"]]
        monsoon = frame[frame["is_test"]]

        self.assertTrue(set(winter["valid_time"].dt.month) <= {1, 2})
        self.assertTrue(set(monsoon["valid_time"].dt.month) <= {7, 8})
        cal = PooledCalibrator(max_iter=80).fit(winter)
        result = compare_with_raw(monsoon, cal.predict(monsoon))
        self.assertTrue(np.isfinite(result["calibrated"]["mae"]))
        self.assertEqual(result["calibrated"]["n"], len(monsoon))
        self.assertEqual(event_skill_failures({"monsoon_test": result}), [])

    def test_gate_allows_equal_pod(self) -> None:
        evaluations = {
            "l1_test": {
                "raw_aurora": {"event_pod": 0.5},
                "calibrated": {"event_pod": 0.5},
            }
        }
        self.assertEqual(event_skill_failures(evaluations), [])

        class SaveRecorder:
            def __init__(self) -> None:
                self.saved = False

            def save(self, path: Path) -> Path:
                self.saved = True
                return path

        recorder = SaveRecorder()
        path = Path("safe-model.joblib")
        self.assertEqual(save_if_event_safe(recorder, path, evaluations), path)
        self.assertTrue(recorder.saved)


if __name__ == "__main__":
    unittest.main()
