"""Pooled calibrator: frozen Aurora features -> station PM2.5 (IndiaAQBench §5.5).

Raw Aurora inherits CAMS's 2-4x under-prediction of severe Indian pollution
(Phase 2). This is a lightweight *post-processor* that learns the correction
from (Aurora + meteorology at a station cell) -> observed PM2.5, WITHOUT
touching the 1.3B model. "Pooled" = one model across all stations and leads,
not a per-station fit -- so it can be applied to held-out cities it never saw.

Design choices that matter:
  * **Log space.** The bias is multiplicative and the target is heavy-tailed
    (Good ~15 to Severe >250), so we fit log1p(pm2.5) and expm1 back. This
    stops the severe tail from dominating the loss and keeps predictions
    positive.
  * **Aurora PM2.5 is the dominant feature**, kept alongside near-surface met
    (2t, 10u/10v -> wind speed, msl), lead time, and cyclical season/hour
    encodings. PM1/PM10 are deliberately excluded: Aurora predicts those
    channels independently and the full rollout contains small violations of
    nested size-bin ordering. The point is to correct PM2.5 level/timing, not
    learn from physically inconsistent auxiliary bins.
  * **Split discipline is enforced here, not assumed.** fit() must be handed
    train-only rows; the CLI builds L1 (held-out stations in train cities) and
    L2 (held-out cities) exactly as spec §3 requires, and never lets a test
    row -- or a held-out city -- touch the fit, including feature stats.

The calibrator is scored by the SAME harness as every other baseline
(src/eval/benchmark.py --calibrator ...), so "did it help?" is answered on the
category + Very Poor+ event metrics, not just MAE -- the whole point is to fix
the level while *preserving* Aurora's long-lead event skill.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

# Reuse the eval harness's join + split so predictions are scored identically.
from ..eval import aqi
from ..eval import benchmark as bench
from ..splits import HELDOUT_CITIES, l1_is_holdout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = PROJECT_ROOT / "results" / "models"
DEFAULT_MODEL = MODEL_DIR / "accepted_pooled_calibrator.joblib"

# Raw model/met inputs the calibrator is allowed to see (all present in pairs).
RAW_FEATURES = ["aurora_pm2p5", "aurora_2t", "aurora_10u", "aurora_10v",
                "aurora_msl"]


# --------------------------------------------------------------------------- #
# Feature engineering
# --------------------------------------------------------------------------- #

def make_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive the model matrix from a joined pairs+obs frame (bench.build_frame).

    Pure function of per-row Aurora/met fields + valid_time -- no station id,
    no city, nothing fit on data -- so it is identical for seen and held-out
    stations and carries zero leakage.
    """
    f = pd.DataFrame(index=frame.index)
    for c in RAW_FEATURES:
        f[c] = frame[c].astype(float)
    f["wind_speed"] = np.hypot(frame["aurora_10u"], frame["aurora_10v"])
    f["lead_h"] = frame["lead_h"].astype(float)
    vt = pd.to_datetime(frame["valid_time"], utc=True)
    hod = vt.dt.hour
    month = vt.dt.month
    f["hour_sin"] = np.sin(2 * np.pi * hod / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hod / 24)
    f["month_sin"] = np.sin(2 * np.pi * month / 12)
    f["month_cos"] = np.cos(2 * np.pi * month / 12)
    return f


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

class PooledCalibrator:
    """Log-space gradient-boosted corrector, pooled across stations and leads."""

    def __init__(self, **hgb_kwargs) -> None:
        params = dict(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                      min_samples_leaf=40, l2_regularization=1.0,
                      early_stopping=True, validation_fraction=0.15,
                      random_state=0)
        params.update(hgb_kwargs)
        self.model = HistGradientBoostingRegressor(**params)
        self.feature_names_: list[str] = []

    def fit(self, frame_train: pd.DataFrame) -> "PooledCalibrator":
        rows = frame_train.dropna(subset=["obs_pm25"] + RAW_FEATURES)
        if len(rows) < 50:
            raise ValueError(
                f"Only {len(rows)} usable train rows -- need the full "
                "orchestrator run before the calibrator can be fit for real.")
        X = make_features(rows)
        y = np.log1p(rows["obs_pm25"].to_numpy())
        self.feature_names_ = list(X.columns)
        self.model.fit(X.to_numpy(), y)
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        X = make_features(frame)[self.feature_names_].to_numpy()
        return np.expm1(self.model.predict(X)).clip(min=0.0)

    def save(self, path: Path = DEFAULT_MODEL) -> Path:
        import joblib
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path: Path = DEFAULT_MODEL) -> "PooledCalibrator":
        import joblib
        return joblib.load(path)


# --------------------------------------------------------------------------- #
# Split construction (spec §3)
# --------------------------------------------------------------------------- #

def split_frame(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Partition into the train fit-set and the L1/L2 evaluation sets.

    train    : train-period rows, train-pool cities, NON-holdout stations.
    l1_test  : test-period rows, train-pool cities, held-out stations.
    l2_test  : test-period rows, held-out cities (any station).
    """
    heldout_city = frame["city"].isin(HELDOUT_CITIES)
    heldout_station = frame["station_id"].map(l1_is_holdout)
    is_test = frame["is_test"]
    train = frame[~is_test & ~heldout_city & ~heldout_station]
    l1_test = frame[is_test & ~heldout_city & heldout_station]
    l2_test = frame[is_test & heldout_city]
    return {"train": train, "l1_test": l1_test, "l2_test": l2_test}


# --------------------------------------------------------------------------- #
# Fit-time event guardrail
# --------------------------------------------------------------------------- #

class EventSkillRegressionError(RuntimeError):
    """Raised when calibration harms Very Poor+ probability of detection."""


def compare_with_raw(frame: pd.DataFrame, calibrated: np.ndarray) -> dict[str, dict]:
    """Return paired raw/calibrated MAE and Very Poor+ POD/FAR.

    Both methods are evaluated on exactly the same finite, positive-lead rows.
    This prevents missing calibrated predictions from making either side of the
    no-harm comparison look artificially better.
    """
    if len(frame) != len(calibrated):
        raise ValueError(
            f"Expected {len(frame)} calibrated predictions, got {len(calibrated)}.")

    obs = frame["obs_pm25"].to_numpy(dtype=float)
    raw = frame["aurora_pm2p5"].to_numpy(dtype=float)
    cal = np.asarray(calibrated, dtype=float)
    lead = frame["lead_h"].to_numpy(dtype=float)
    keep = (lead > 0) & np.isfinite(obs) & np.isfinite(raw) & np.isfinite(cal)
    obs, raw, cal = obs[keep], raw[keep], cal[keep]

    def metrics(pred: np.ndarray) -> dict:
        events = aqi.category_metrics(obs, pred)
        return {
            "n": int(obs.size),
            "mae": float(np.mean(np.abs(pred - obs))) if obs.size else np.nan,
            "event_pod": events.get("event_pod", np.nan),
            "event_far": events.get("event_far", np.nan),
        }

    return {"raw_aurora": metrics(raw), "calibrated": metrics(cal)}


def event_skill_failures(
        evaluations: dict[str, dict[str, dict]]) -> list[tuple[str, float, float]]:
    """List holdouts where calibrated Very Poor+ POD is below raw Aurora's.

    A holdout with no observed Very Poor+ events has undefined POD and cannot
    establish harm, so it is reported by the CLI but does not fail the gate.
    """
    failures = []
    for name, result in evaluations.items():
        raw_pod = float(result["raw_aurora"]["event_pod"])
        cal_pod = float(result["calibrated"]["event_pod"])
        if np.isfinite(raw_pod) and (not np.isfinite(cal_pod) or cal_pod < raw_pod):
            failures.append((name, raw_pod, cal_pod))
    return failures


def save_if_event_safe(
        calibrator: PooledCalibrator,
        path: Path,
        evaluations: dict[str, dict[str, dict]],
) -> Path:
    """Save only when calibrated POD does not regress on any scored holdout."""
    failures = event_skill_failures(evaluations)
    if failures:
        details = "; ".join(
            f"{name}: raw={raw:.3f}, calibrated={cal:.3f}"
            for name, raw, cal in failures
        )
        raise EventSkillRegressionError(
            "Very Poor+ POD is below raw Aurora; model was not saved. " + details)
    return calibrator.save(path)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _synthetic_frame(n: int = 4000, seed: int = 0) -> pd.DataFrame:
    """A joined-frame stand-in with a KNOWN multiplicative Aurora bias, so the
    calibrator's fit/predict/split path is testable before the full run lands."""
    rng = np.random.default_rng(seed)
    true_pm = rng.lognormal(mean=4.0, sigma=0.8, size=n)          # ~15..600
    aurora = true_pm / rng.uniform(2.0, 4.0, size=n)             # under-predicts 2-4x
    t0 = pd.Timestamp("2025-01-01", tz="UTC")
    vt = t0 + pd.to_timedelta(rng.integers(0, 240 * 24, n), unit="h")
    return pd.DataFrame({
        "station_id": rng.integers(1, 30, n),
        "city": rng.choice(["delhi", "patna", "kanpur"], n),
        "aurora_pm2p5": aurora, "aurora_pm1": aurora * 0.6,
        "aurora_pm10": aurora * 1.8, "aurora_2t": rng.normal(295, 6, n),
        "aurora_10u": rng.normal(0, 2, n), "aurora_10v": rng.normal(0, 2, n),
        "aurora_msl": rng.normal(101300, 400, n),
        "lead_h": rng.choice([12, 24, 48, 96], n),
        "valid_time": vt, "obs_pm25": true_pm,
        "is_test": rng.random(n) < 0.3,
    })


def _frame_from_regimes(
        train_obs: np.ndarray,
        test_obs: np.ndarray,
        train_start: str,
        test_start: str,
        seed: int,
        test_raw_fraction: float,
) -> pd.DataFrame:
    """Build deterministic train/test regimes for OOD and seasonal checks."""
    rng = np.random.default_rng(seed)
    n_train, n_test = len(train_obs), len(test_obs)
    n = n_train + n_test
    is_test = np.r_[np.zeros(n_train, dtype=bool), np.ones(n_test, dtype=bool)]
    obs = np.r_[train_obs, test_obs]

    # Calm training forecasts retain the historical 2-4x bias. The OOD test
    # fraction is caller-controlled so raw Aurora can retain event signal that
    # a target-predicting tree trained below the threshold will flatten.
    aurora_train = train_obs / rng.uniform(2.0, 4.0, n_train)
    aurora_test = test_obs * test_raw_fraction
    aurora = np.r_[aurora_train, aurora_test]
    train_times = pd.date_range(train_start, periods=n_train, freq="h", tz="UTC")
    test_times = pd.date_range(test_start, periods=n_test, freq="h", tz="UTC")
    valid_time = train_times.append(test_times)

    return pd.DataFrame({
        "station_id": rng.integers(1, 100, n),
        "city": rng.choice(["delhi", "patna"], n),
        "aurora_pm2p5": aurora,
        "aurora_pm1": aurora * 0.6,
        "aurora_pm10": aurora * 1.8,
        "aurora_2t": rng.normal(295, 6, n),
        "aurora_10u": rng.normal(0, 2, n),
        "aurora_10v": rng.normal(0, 2, n),
        "aurora_msl": rng.normal(101300, 400, n),
        "lead_h": rng.choice([12, 24, 48, 96], n),
        "valid_time": valid_time,
        "obs_pm25": obs,
        "is_test": is_test,
    })


def _calm_train_severe_test_frame(seed: int = 1) -> pd.DataFrame:
    """Calm train -> severe test: the distribution shift that sank calibrator v1."""
    rng = np.random.default_rng(seed)
    train_obs = rng.uniform(25.0, 90.0, 1600)
    test_obs = rng.uniform(180.0, 400.0, 800)
    return _frame_from_regimes(
        train_obs, test_obs, "2025-02-01", "2025-12-01", seed,
        test_raw_fraction=0.75,
    )


def _winter_train_monsoon_test_frame(seed: int = 2) -> pd.DataFrame:
    """Winter-only train -> monsoon-only test seasonal-transfer fixture."""
    rng = np.random.default_rng(seed)
    train_obs = rng.uniform(35.0, 240.0, 1200)
    test_obs = rng.uniform(35.0, 180.0, 800)
    return _frame_from_regimes(
        train_obs, test_obs, "2025-01-01", "2025-07-01", seed,
        test_raw_fraction=0.5,
    )


def _format_metric(value: float, digits: int) -> str:
    return f"{value:.{digits}f}" if np.isfinite(value) else "n/a"


def _print_comparison(name: str, result: dict[str, dict]) -> None:
    raw = result["raw_aurora"]
    cal = result["calibrated"]
    print(
        f"{name}: n={raw['n']:,}  "
        f"MAE raw={_format_metric(raw['mae'], 1)} -> "
        f"calibrated={_format_metric(cal['mae'], 1)} ug/m3  |  "
        f"Very Poor+ POD raw={_format_metric(raw['event_pod'], 3)} -> "
        f"calibrated={_format_metric(cal['event_pod'], 3)}  |  "
        f"FAR raw={_format_metric(raw['event_far'], 3)} -> "
        f"calibrated={_format_metric(cal['event_far'], 3)}"
    )


def run_selftest() -> None:
    """Exercise OOD failure detection and winter-to-monsoon transfer."""
    ood = _calm_train_severe_test_frame()
    cal = PooledCalibrator(max_iter=80).fit(ood[~ood["is_test"]])
    severe = ood[ood["is_test"]]
    ood_result = compare_with_raw(severe, cal.predict(severe))
    _print_comparison("calm_train -> severe_test", ood_result)
    if not event_skill_failures({"severe_test": ood_result}):
        raise AssertionError(
            "OOD selftest did not detect the known v1 event-skill collapse.")
    try:
        save_if_event_safe(cal, Path("selftest-must-not-save.joblib"),
                           {"severe_test": ood_result})
    except EventSkillRegressionError:
        pass
    else:
        raise AssertionError("No-harm-on-events gate accepted a harmful model.")

    seasonal = _winter_train_monsoon_test_frame()
    winter = seasonal[~seasonal["is_test"]]
    monsoon = seasonal[seasonal["is_test"]]
    if set(winter["valid_time"].dt.month) - {1, 2}:
        raise AssertionError("Seasonal fixture training rows are not winter-only.")
    if set(monsoon["valid_time"].dt.month) - {7, 8}:
        raise AssertionError("Seasonal fixture test rows are not monsoon-only.")
    seasonal_cal = PooledCalibrator(max_iter=80).fit(winter)
    seasonal_result = compare_with_raw(monsoon, seasonal_cal.predict(monsoon))
    _print_comparison("winter_train -> monsoon_test", seasonal_result)
    if not np.isfinite(seasonal_result["calibrated"]["mae"]):
        raise AssertionError("Seasonal-transfer predictions are not scorable.")
    if event_skill_failures({"monsoon_test": seasonal_result}):
        raise AssertionError(
            "Seasonal-transfer check regressed Very Poor+ event POD.")

    print("OK  OOD collapse was blocked; seasonal transfer is scorable.")


def main() -> None:
    p = argparse.ArgumentParser(description="Fit + evaluate the pooled calibrator.")
    p.add_argument("--out", type=Path, default=DEFAULT_MODEL)
    p.add_argument("--selftest", action="store_true",
                   help="Run the synthetic smoke test and exit (no real data needed).")
    args = p.parse_args()

    if args.selftest:
        run_selftest()
        return

    frame = bench.add_climatology(bench.build_frame())
    parts = split_frame(frame)
    print("Split rows -- " + ", ".join(f"{k}: {len(v):,}" for k, v in parts.items()))

    cal = PooledCalibrator().fit(parts["train"])
    evaluations = {}
    for name in ("l1_test", "l2_test"):
        g = parts[name]
        if g.empty:
            print(f"{name}: no scorable rows yet.")
            continue
        result = compare_with_raw(g, cal.predict(g))
        evaluations[name] = result
        _print_comparison(name, result)

    # Running as `python -m src.model.calibrator` makes this class
    # __main__.PooledCalibrator, which cannot be unpickled from another entry
    # point. Rebind only after evaluation, immediately before a permitted save.
    if cal.__class__.__module__ == "__main__":
        import importlib
        cal.__class__ = importlib.import_module(
            "src.model.calibrator").PooledCalibrator
    try:
        path = save_if_event_safe(cal, args.out, evaluations)
    except EventSkillRegressionError as exc:
        raise SystemExit(f"REFUSING TO SAVE: {exc}") from None
    print(f"Fit on {len(parts['train']):,} train rows -> {path}")

    print("\nScore the full metric suite with:\n"
          f"  python -m src.eval.benchmark --calibrator {path}")


if __name__ == "__main__":
    main()
