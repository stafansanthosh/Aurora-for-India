"""Why does Very Poor+ event skill stay low? Separate the causes.

A fixed-threshold POD/FAR/CSI number conflates two different failures:

  * **discrimination** -- can the forecast RANK episode windows above
    non-episode windows at all? Measured by AUC, threshold-free.
  * **calibration**    -- given a usable ranking, is the decision threshold in
    the right place? Measured by the gap between CSI at the nominal 121 ug/m3
    and the best CSI reachable by sweeping the threshold.

They have opposite fixes. If discrimination is the binding constraint, no
post-processor of any kind can help and the inputs must change. If calibration
is binding, the decision rule is the cheap fix.

SPLIT DISCIPLINE
----------------
Every method-performance number here is computed on the TRAIN split, train_pool
tier, out-of-fold by init_date. No test row is scored, so running this does not
consume the held-out evidence. The classifier section estimates a *ceiling* to
justify a predeclared design; it is not a validated result and its numbers must
be re-earned on test before any public claim.

Section L reports observed event COUNTS per city and split. Counts are sample
support -- the repo already publishes them -- not method performance.

Usage:
    python -m src.eval.diagnose_events
    python -m src.eval.diagnose_events --skip-classifier
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import aqi, benchmark as bench, rolling24

THRESH = aqi.VERY_POOR_THRESHOLD
PROJECT_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# Small metric helpers (kept local so this module never mutates scoring code)
# --------------------------------------------------------------------------- #

def contingency(obs_event: np.ndarray, pred_event: np.ndarray) -> tuple[float, float, float]:
    """POD, FAR, CSI from two boolean arrays."""
    hits = int((obs_event & pred_event).sum())
    misses = int((obs_event & ~pred_event).sum())
    false_alarms = int((~obs_event & pred_event).sum())
    pod = hits / (hits + misses) if (hits + misses) else np.nan
    far = false_alarms / (hits + false_alarms) if (hits + false_alarms) else np.nan
    csi = (hits / (hits + misses + false_alarms)
           if (hits + misses + false_alarms) else np.nan)
    return pod, far, csi


def auc(obs_event: np.ndarray, score: np.ndarray) -> float:
    """Rank-based AUC; no sklearn dependency, ties handled by average rank."""
    finite = np.isfinite(score)
    y, s = obs_event[finite], score[finite]
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return np.nan
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=float)
    ranks[order] = np.arange(1, len(s) + 1, dtype=float)
    s_sorted = s[order]
    start = 0
    for i in range(1, len(s) + 1):          # average ranks within tie groups
        if i == len(s) or s_sorted[i] != s_sorted[start]:
            if i - start > 1:
                ranks[order[start:i]] = ranks[order[start:i]].mean()
            start = i
    return float((ranks[y].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def best_threshold(obs_event: np.ndarray, score: np.ndarray) -> tuple[float, float, float, float]:
    """Sweep the decision threshold; return (best CSI, threshold, POD, FAR)."""
    finite = np.isfinite(score)
    y, s = obs_event[finite], score[finite]
    if y.sum() == 0 or s.size == 0:
        return (np.nan,) * 4
    best = (-1.0, np.nan, np.nan, np.nan)
    for t in np.unique(np.quantile(s, np.linspace(0.50, 0.999, 200))):
        pod, far, csi = contingency(y, s >= t)
        if np.isfinite(csi) and csi > best[0]:
            best = (csi, float(t), pod, far)
    return best


# --------------------------------------------------------------------------- #
# Frame construction
# --------------------------------------------------------------------------- #

def build() -> pd.DataFrame:
    """24-hour windows with Component A attached."""
    from ..model.anchor import anchor_frame

    frame = anchor_frame(bench.add_climatology(bench.build_frame()))
    return rolling24.build_windows(frame, bench.load_obs())


def train_pool(windows: pd.DataFrame) -> pd.DataFrame:
    """Train split, train_pool tier, scorable rows only."""
    part = windows[(~windows["is_test"]) & (windows["spatial_tier"] == "train_pool")]
    return part[np.isfinite(part["obs_pm25"])].copy()


METHODS = {
    "raw_aurora": "aurora_pm2p5",
    "anchored": "anchored_pm25",
    "persistence": "persist_pm25",
    "cams_forecast": "cams_forecast_pm25",
}


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #

def section_discrimination(train: pd.DataFrame) -> None:
    print("=" * 100)
    print("A. DISCRIMINATION vs CALIBRATION (train split, train_pool tier)")
    print("=" * 100)
    obs = train["obs_pm25"].to_numpy(float)
    event = obs >= THRESH
    print(f"n={len(train):,}  events={event.sum():,}  base rate={event.mean():.2%}\n")
    print(f"{'method':<16}{'AUC':>8}{'CSI@121':>10}{'POD@121':>10}{'FAR@121':>10}"
          f"{'best CSI':>10}{'@thresh':>10}")
    print("-" * 100)
    for name, col in METHODS.items():
        if col not in train.columns:
            continue
        v = train[col].to_numpy(float)
        finite = np.isfinite(v)
        pod, far, csi = contingency(event[finite], v[finite] >= THRESH)
        bcsi, bt, _, _ = best_threshold(event, v)
        print(f"{name:<16}{auc(event, v):>8.3f}{csi:>10.3f}{pod:>10.3f}{far:>10.3f}"
              f"{bcsi:>10.3f}{bt:>10.1f}")
    print("\nGap between CSI@121 and best CSI = what re-thresholding alone can win.")
    print("The best-CSI column is the CEILING for any concentration post-processor.")


def section_within_station(train: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("B. IS THE SKILL BETWEEN CITIES OR WITHIN A STATION?")
    print("=" * 100)
    print("Pooled AUC can be earned by ranking dirty cities above clean ones.")
    print("GRAP needs: which WINDOWS at THIS station spike?\n")
    event = (train["obs_pm25"] >= THRESH).to_numpy()
    print(f"{'method':<16}{'AUC pooled':>12}{'AUC within-station':>21}{'drop':>9}")
    print("-" * 100)
    for name, col in METHODS.items():
        if col not in train.columns:
            continue
        pooled = auc(event, train[col].to_numpy(float))
        anomaly = (train[col] - train.groupby("station_id")[col].transform("mean")).to_numpy(float)
        within = auc(event, anomaly)
        print(f"{name:<16}{pooled:>12.3f}{within:>21.3f}{within - pooled:>+9.3f}")


def section_ceiling(train: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("C. AURORA'S DYNAMIC RANGE — can it even emit an episode value?")
    print("=" * 100)
    print(f"{'city':<12}{'obs max':>10}{'aurora max':>12}{'obs>=121':>10}"
          f"{'aurora>=121':>13}{'obs>=250':>10}{'aurora>=250':>13}")
    print("-" * 100)
    for city, g in train.groupby("city"):
        o, a = g["obs_pm25"], g["aurora_pm2p5"]
        print(f"{str(city):<12}{o.max():>10.1f}{a.max():>12.1f}{(o >= 121).sum():>10,}"
              f"{(a >= 121).sum():>13,}{(o >= 250).sum():>10,}{(a >= 250).sum():>13,}")
    print("\nWhere Aurora's maximum sits below a category boundary, POD in that")
    print("category is capped at zero by construction -- no multiplier fixes it.")


def section_per_city(train: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("D. PER-CITY DISCRIMINATION — does it work where the project needs it?")
    print("=" * 100)
    print(f"{'city':<12}{'n':>8}{'events':>8}{'base':>8}{'AUC':>8}{'best CSI':>10}")
    print("-" * 100)
    for city, g in train.groupby("city"):
        event = (g["obs_pm25"] >= THRESH).to_numpy()
        if event.sum() < 10:
            print(f"{str(city):<12}{len(g):>8,}{event.sum():>8,}{event.mean():>8.2%}"
                  f"{'--':>8}{'--':>10}   too few events to score")
            continue
        v = g["aurora_pm2p5"].to_numpy(float)
        print(f"{str(city):<12}{len(g):>8,}{event.sum():>8,}{event.mean():>8.2%}"
              f"{auc(event, v):>8.3f}{best_threshold(event, v)[0]:>10.3f}")


def section_event_mass(windows: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("E. WHERE THE EVENTS ARE (counts only — no method scored on test here)")
    print("=" * 100)
    w = windows[np.isfinite(windows["obs_pm25"])].copy()
    w["event"] = w["obs_pm25"] >= THRESH
    total = int(w["event"].sum())
    print(f"{'city':<12}{'train ev':>10}{'train n':>9}{'test ev':>10}{'test n':>9}"
          f"{'% of all events':>18}")
    print("-" * 100)
    for city in sorted(w["city"].unique()):
        g = w[w["city"] == city]
        tr, te = g[~g["is_test"]], g[g["is_test"]]
        share = g["event"].sum() / total if total else np.nan
        print(f"{str(city):<12}{tr['event'].sum():>10,}{len(tr):>9,}"
              f"{te['event'].sum():>10,}{len(te):>9,}{share:>18.1%}")
    print("\nIf one non-target city holds most of the event mass, a pooled headline")
    print("describes that city, not the cities the project exists to serve.")


def section_classifier(train: pd.DataFrame) -> None:
    """Ceiling estimate for the exceedance-probability reframing."""
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.model_selection import GroupKFold
    except ImportError:
        print("\n[skip] scikit-learn unavailable; classifier section skipped.")
        return

    print("\n" + "=" * 100)
    print("F. CEILING ESTIMATE — predict P(exceedance) instead of concentration")
    print("=" * 100)
    print("Out-of-fold by init_date, TRAIN SPLIT ONLY. This is a ceiling estimate")
    print("to justify a predeclared design. It is NOT a validated result.\n")

    feats = ["aurora_pm2p5", "persist_pm25", "cams_forecast_pm25", "window_start_h"]
    feats = [c for c in feats if c in train.columns]
    part = train.dropna(subset=feats + ["obs_pm25"]).copy()
    part["month"] = pd.to_datetime(part["window_start"], utc=True).dt.month
    feats = feats + ["month"]

    X = part[feats].to_numpy(float)
    y = (part["obs_pm25"] >= THRESH).to_numpy()
    groups = part["init_date"].astype(str).to_numpy()
    if y.sum() < 50 or len(np.unique(groups)) < 5:
        print("[skip] insufficient train events or dates.")
        return

    oof = np.full(len(part), np.nan)
    for tr_idx, te_idx in GroupKFold(n_splits=5).split(X, y, groups):
        clf = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
            min_samples_leaf=40, l2_regularization=1.0, random_state=0)
        clf.fit(X[tr_idx], y[tr_idx])
        oof[te_idx] = clf.predict_proba(X[te_idx])[:, 1]

    print(f"{'approach':<40}{'AUC':>8}{'CSI@nominal':>14}{'best CSI':>10}")
    print("-" * 100)
    for label, score, nominal in [
            ("raw Aurora concentration", part["aurora_pm2p5"].to_numpy(float), THRESH),
            ("Component A concentration", part["anchored_pm25"].to_numpy(float), THRESH),
            ("P(event) classifier (out-of-fold)", oof, 0.5)]:
        finite = np.isfinite(score)
        _, _, csi = contingency(y[finite], score[finite] >= nominal)
        print(f"{label:<40}{auc(y, score):>8.3f}{csi:>14.3f}{best_threshold(y, score)[0]:>10.3f}")

    print("\nOperating curve — a probability lets the user CHOOSE the trade-off:")
    print(f"{'target POD':<14}{'threshold':>11}{'POD':>8}{'FAR':>8}{'CSI':>8}"
          f"{'alerts per 1000 windows':>26}")
    print("-" * 100)
    for target in (0.5, 0.6, 0.7, 0.8, 0.9):
        chosen = None
        for t in np.unique(np.quantile(oof, np.linspace(0.30, 0.999, 400))):
            pod, far, csi = contingency(y, oof >= t)
            if pod >= target and (chosen is None or far < chosen[2]):
                chosen = (float(t), pod, far, csi, float((oof >= t).mean() * 1000))
        if chosen:
            print(f"{target:<14.0%}{chosen[0]:>11.3f}{chosen[1]:>8.3f}{chosen[2]:>8.3f}"
                  f"{chosen[3]:>8.3f}{chosen[4]:>26.0f}")

    print("\nAblation — what does Aurora add over local observations + season?")
    print("-" * 100)
    for label, cols in [
            ("persistence + month + lead", ["persist_pm25", "month", "window_start_h"]),
            ("Aurora + month + lead", ["aurora_pm2p5", "month", "window_start_h"]),
            ("persistence + Aurora + month + lead",
             ["persist_pm25", "aurora_pm2p5", "month", "window_start_h"]),
            ("all features", feats)]:
        cols = [c for c in cols if c in part.columns]
        Xa = part[cols].to_numpy(float)
        o = np.full(len(part), np.nan)
        for tr_idx, te_idx in GroupKFold(n_splits=5).split(Xa, y, groups):
            c = HistGradientBoostingClassifier(
                max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                min_samples_leaf=40, l2_regularization=1.0,
                random_state=0).fit(Xa[tr_idx], y[tr_idx])
            o[te_idx] = c.predict_proba(Xa[te_idx])[:, 1]
        print(f"  {label:<40}AUC={auc(y, o):.3f}   best CSI={best_threshold(y, o)[0]:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--skip-classifier", action="store_true")
    args = parser.parse_args()

    windows = build()
    train = train_pool(windows)
    section_discrimination(train)
    section_within_station(train)
    section_ceiling(train)
    section_per_city(train)
    section_event_mass(windows)
    if not args.skip_classifier:
        section_classifier(train)


if __name__ == "__main__":
    main()
