"""Option B kill-test: does boundary-layer information buy exceedance skill?

PRE-DECLARED DESIGN: `docs/CODEX_BRIEF_OPTION_B.md` section 3.3, committed in
2ab1c50 BEFORE any result here existed.

    Proceed with Option B if adding ERA5 features lifts out-of-fold AUC by
    >= 0.02 AND best CSI by >= 0.03 over the `current` feature set, AND the gain
    holds in at least one non-Delhi city with >= 50 train events (only Patna
    qualifies, at 114).
    No headroom if perfect-prognosis ERA5 adds < 0.01 AUC.
    Anything between is reported as AMBIGUOUS, not rounded up.

WHAT THIS IS
------------
ERA5 is reanalysis: it assimilates observations and is valid *at* the target
window. It is therefore an UPPER BOUND on what any forecast of the same field
could supply. Every number here is **perfect-prognosis** and must never be
reported as achievable forecast skill.

SPLIT DISCIPLINE
----------------
Train split, train_pool tier, out-of-fold by init date. No test row is scored.

Usage:
    python -m src.eval.blh_ceiling_test
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from . import aqi, benchmark as bench, rolling24
from .diagnose_events import auc, best_threshold, contingency

THRESH = aqi.VERY_POOR_THRESHOLD
ERA5_SAMPLES = bench.PROJECT_ROOT / "data" / "era5_blh" / "era5_blh_stations.csv"

ERA5_VARS = ["era5_blh", "era5_ventilation", "era5_dewpoint_depression", "era5_wind"]

FEATURE_SETS = {
    "baseline (persistence + season + lead)": ["persist_pm25", "month", "window_start_h"],
    "current (+ Aurora + CAMS)": ["persist_pm25", "month", "window_start_h",
                                  "aurora_pm2p5", "cams_forecast_pm25"],
    "+ERA5 boundary layer": ["persist_pm25", "month", "window_start_h",
                             "aurora_pm2p5", "cams_forecast_pm25",
                             "blh_min", "blh_mean", "ventilation_mean",
                             "ventilation_min", "dewpoint_depression_mean"],
    "ERA5 only (+ season + lead)": ["month", "window_start_h", "blh_min", "blh_mean",
                                    "ventilation_mean", "ventilation_min",
                                    "dewpoint_depression_mean"],
}


def window_aggregates(era5: pd.DataFrame) -> pd.DataFrame:
    """Forward 24-hour aggregates of each ERA5 field, keyed by window start.

    Reindexes to a complete hourly axis first so that a window spanning a gap in
    the downloaded days yields NaN rather than a silently short average.
    """
    era5 = era5.copy()
    era5["valid_time"] = pd.to_datetime(era5["valid_time"], utc=True)
    out = []
    for var, aggs in [("era5_blh", ("min", "mean")),
                      ("era5_ventilation", ("min", "mean")),
                      ("era5_dewpoint_depression", ("mean",)),
                      ("era5_wind", ("mean",))]:
        wide = era5.pivot(index="valid_time", columns="station_id", values=var)
        full = pd.date_range(wide.index.min(), wide.index.max(), freq="h", tz="UTC")
        wide = wide.reindex(full)
        for agg in aggs:
            roll = getattr(wide.rolling(24, min_periods=24), agg)().shift(-23)
            name = f"{var.replace('era5_', '')}_{agg}"
            block = roll.stack(future_stack=True).rename(name).reset_index()
            block.columns = ["window_start", "station_id", name]
            out.append(block.set_index(["window_start", "station_id"]))
    return pd.concat(out, axis=1).reset_index()


def build() -> pd.DataFrame:
    from ..model.anchor import anchor_frame

    frame = anchor_frame(bench.add_climatology(bench.build_frame()))
    windows = rolling24.build_windows(frame, bench.load_obs())
    train = windows[(~windows["is_test"]) & (windows["spatial_tier"] == "train_pool")]
    train = train[np.isfinite(train["obs_pm25"])].copy()
    train["window_start"] = pd.to_datetime(train["window_start"], utc=True)
    train["station_id"] = train["station_id"].astype(str)
    train["month"] = train["window_start"].dt.month

    era5 = pd.read_csv(ERA5_SAMPLES)
    era5["station_id"] = era5["station_id"].astype(str)
    aggregates = window_aggregates(era5)
    aggregates["station_id"] = aggregates["station_id"].astype(str)

    merged = train.merge(aggregates, on=["window_start", "station_id"], how="left")
    covered = merged["blh_min"].notna().mean()
    print(f"ERA5 coverage of train windows: {covered:.1%} "
          f"({int(merged['blh_min'].notna().sum()):,} of {len(merged):,})")
    return merged


def out_of_fold(frame: pd.DataFrame, cols: list[str], y: np.ndarray,
                groups: np.ndarray) -> np.ndarray:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold

    X = frame[cols].to_numpy(float)
    oof = np.full(len(frame), np.nan)
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        clf = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
            min_samples_leaf=40, l2_regularization=1.0, random_state=0)
        clf.fit(X[tr], y[tr])
        oof[te] = clf.predict_proba(X[te])[:, 1]
    return oof


def main() -> None:
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()

    data = build()
    needed = sorted({c for cols in FEATURE_SETS.values() for c in cols})
    data = data.dropna(subset=needed + ["obs_pm25"]).copy()

    y = (data["obs_pm25"] >= THRESH).to_numpy()
    groups = data["init_date"].astype(str).to_numpy()
    print(f"\nn={len(data):,}  events={y.sum():,}  base={y.mean():.2%}  "
          f"dates={len(np.unique(groups))}")
    print("PERFECT-PROGNOSIS. ERA5 is valid at the target window; this is a "
          "CEILING, not achievable forecast skill.\n")

    print("=" * 92)
    print("POOLED (train split, out-of-fold by init date) -- 89% Delhi, read per-city below")
    print("=" * 92)
    print(f"{'feature set':<40}{'AUC':>9}{'best CSI':>11}{'dAUC':>9}{'dCSI':>9}")
    print("-" * 92)
    scores, preds = {}, {}
    for name, cols in FEATURE_SETS.items():
        oof = out_of_fold(data, cols, y, groups)
        a, c = auc(y, oof), best_threshold(y, oof)[0]
        scores[name] = (a, c)
        preds[name] = oof
        ref = scores.get("current (+ Aurora + CAMS)")
        da = f"{a - ref[0]:+9.3f}" if ref and name != "current (+ Aurora + CAMS)" else f"{'':>9}"
        dc = f"{c - ref[1]:+9.3f}" if ref and name != "current (+ Aurora + CAMS)" else f"{'':>9}"
        print(f"{name:<40}{a:>9.3f}{c:>11.3f}{da}{dc}")

    print("\n" + "=" * 92)
    print("PER CITY -- current vs +ERA5")
    print("=" * 92)
    print(f"{'city':<12}{'n':>8}{'events':>8}{'AUC cur':>10}{'AUC +ERA5':>11}"
          f"{'dAUC':>9}{'CSI cur':>10}{'CSI +ERA5':>11}{'dCSI':>9}")
    print("-" * 92)
    cur, new = preds["current (+ Aurora + CAMS)"], preds["+ERA5 boundary layer"]
    city_gains = {}
    for city, g in data.assign(_cur=cur, _new=new).groupby("city"):
        ev = (g["obs_pm25"] >= THRESH).to_numpy()
        if ev.sum() < 10:
            print(f"{str(city):<12}{len(g):>8,}{ev.sum():>8,}   too few events to score")
            continue
        a1, a2 = auc(ev, g["_cur"].to_numpy()), auc(ev, g["_new"].to_numpy())
        c1 = best_threshold(ev, g["_cur"].to_numpy())[0]
        c2 = best_threshold(ev, g["_new"].to_numpy())[0]
        city_gains[city] = (int(ev.sum()), a2 - a1, c2 - c1)
        print(f"{str(city):<12}{len(g):>8,}{ev.sum():>8,}{a1:>10.3f}{a2:>11.3f}"
              f"{a2-a1:>+9.3f}{c1:>10.3f}{c2:>11.3f}{c2-c1:>+9.3f}")

    # ------------------------------------------------------------------ #
    # Verdict against the PRE-DECLARED rule
    # ------------------------------------------------------------------ #
    ref_a, ref_c = scores["current (+ Aurora + CAMS)"]
    new_a, new_c = scores["+ERA5 boundary layer"]
    d_auc, d_csi = new_a - ref_a, new_c - ref_c
    qualifying = {c: v for c, v in city_gains.items() if v[0] >= 50 and c != "delhi"}
    holds = any(v[1] > 0 and v[2] > 0 for v in qualifying.values())

    print("\n" + "=" * 92)
    print("VERDICT against the pre-declared rule (docs/CODEX_BRIEF_OPTION_B.md 3.3)")
    print("=" * 92)
    print(f"  dAUC = {d_auc:+.3f}   (proceed needs >= +0.020; no-headroom below +0.010)")
    print(f"  dCSI = {d_csi:+.3f}   (proceed needs >= +0.030)")
    print(f"  non-Delhi cities with >=50 train events: "
          f"{ {c: v[0] for c, v in qualifying.items()} }")
    print(f"  gain holds in at least one of them: {holds}")

    if d_auc >= 0.02 and d_csi >= 0.03 and holds:
        verdict = "PROCEED — Option B has headroom"
    elif d_auc < 0.01:
        verdict = "NO HEADROOM — stop; do not spend GPU on Aurora 1.5 for this"
    else:
        verdict = "AMBIGUOUS — do not round up; report as ambiguous"
    print(f"\n  ==> {verdict}")
    print("\n  Reminder: ERA5 is perfect-prognosis. Aurora 1.5's FORECAST boundary")
    print("  layer at +48-96 h will do worse than this ceiling.")


if __name__ == "__main__":
    main()
