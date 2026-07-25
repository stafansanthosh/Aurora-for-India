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
  * **Aurora value is the dominant feature**, kept alongside pm1/pm10, the
    near-surface met (2t, 10u/10v -> wind speed, msl), lead time, and cyclical
    season/hour encodings. The point is to correct level/timing, not relearn
    chemistry.
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
from ..eval import benchmark as bench
from ..splits import HELDOUT_CITIES, l1_is_holdout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = PROJECT_ROOT / "results" / "models"
DEFAULT_MODEL = MODEL_DIR / "pooled_calibrator.joblib"

# Raw model/met inputs the calibrator is allowed to see (all present in pairs).
RAW_FEATURES = ["aurora_pm2p5", "aurora_pm1", "aurora_pm10",
                "aurora_2t", "aurora_10u", "aurora_10v", "aurora_msl"]


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


def _test() -> None:
    frame = _synthetic_frame()
    parts = split_frame(frame)
    # L2 (held-out city rows) must never leak into the fit set.
    assert not parts["train"]["city"].isin(HELDOUT_CITIES).any()
    assert parts["l2_test"]["city"].isin(HELDOUT_CITIES).all()
    # L1 holdout is a stable, non-trivial partition of stations.
    assert 0 < frame["station_id"].map(l1_is_holdout).mean() < 0.5
    assert l1_is_holdout(7) == l1_is_holdout(7)  # deterministic

    cal = PooledCalibrator(max_iter=80).fit(parts["train"])
    held = parts["l1_test"].dropna(subset=["obs_pm25"])
    obs = held["obs_pm25"].to_numpy()
    mae_raw = np.mean(np.abs(held["aurora_pm2p5"].to_numpy() - obs))
    mae_cal = np.mean(np.abs(cal.predict(held) - obs))
    # Correcting a 2-4x multiplicative bias should cut error substantially.
    assert mae_cal < 0.6 * mae_raw, (mae_raw, mae_cal)
    print(f"OK  L1 MAE raw={mae_raw:.1f} -> calibrated={mae_cal:.1f} ug/m3")


def main() -> None:
    p = argparse.ArgumentParser(description="Fit + evaluate the pooled calibrator.")
    p.add_argument("--out", type=Path, default=DEFAULT_MODEL)
    p.add_argument("--selftest", action="store_true",
                   help="Run the synthetic smoke test and exit (no real data needed).")
    args = p.parse_args()

    if args.selftest:
        _test()
        return

    frame = bench.add_climatology(bench.build_frame())
    parts = split_frame(frame)
    print("Split rows -- " + ", ".join(f"{k}: {len(v):,}" for k, v in parts.items()))

    cal = PooledCalibrator().fit(parts["train"])
    # Running as `python -m src.model.calibrator` makes this class __main__.PooledCalibrator,
    # which can't be unpickled from another entry point (e.g. benchmark.py). Rebind to the
    # qualified module so the saved model loads anywhere.
    if cal.__class__.__module__ == "__main__":
        import importlib
        cal.__class__ = importlib.import_module("src.model.calibrator").PooledCalibrator
    path = cal.save(args.out)
    print(f"Fit on {len(parts['train']):,} train rows -> {path}")

    # Quick MAE read on each holdout (full metric suite lives in benchmark.py).
    for name in ("l1_test", "l2_test"):
        g = parts[name].dropna(subset=["obs_pm25"])
        g = g[g["lead_h"] > 0]
        if g.empty:
            print(f"{name}: no scorable rows yet.")
            continue
        raw = g["aurora_pm2p5"].to_numpy()
        cal_pred = cal.predict(g)
        obs = g["obs_pm25"].to_numpy()
        print(f"{name}: n={len(g):,}  MAE raw={np.mean(np.abs(raw-obs)):.1f} "
              f"-> calibrated={np.mean(np.abs(cal_pred-obs)):.1f} ug/m3")

    print("\nScore the full metric suite with:\n"
          f"  python -m src.eval.benchmark --calibrator {path}")


if __name__ == "__main__":
    main()
