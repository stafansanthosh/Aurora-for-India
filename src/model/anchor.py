"""Component A — per-station trailing-ratio anchoring (online local adaptation).

Aurora can have substantial, location-dependent surface PM2.5 bias. The five
available pilot pair files were produced against superseded station registries,
so they cannot support a current numerical claim about that bias. This module
tests a deliberately simple response: correct each station using only its own
recently *verified* forecast errors.

Why multiplicative-from-history rather than a learned regressor
--------------------------------------------------------------
The v1 pooled calibrator (`src/model/calibrator.py`) predicted the observation
directly and collapsed the severe tail: Very Poor+ POD 0.00, 0 of 99 events
caught, because a tree ensemble cannot emit values beyond its training targets.
Component A has no training set and no target distribution, so it *cannot*
impose a ceiling: a bounded multiplier on a 339 ug/m3 Aurora spike still yields
a spike. It also tracks seasons in real time rather than assuming the training
season resembles the forecast season -- the exact gap that broke v1.

Multiplicative and sequential bias correction belong to an established family
of air-quality post-processing methods. This implementation is intentionally
small enough that its behavior and information boundary can be audited.

Honest labelling
----------------
This is **online local adaptation, not zero-shot transfer**. It consumes recent
observations at the very station it corrects, including in L1 and L2 holdouts.
That is legitimate here -- persistence uses past observations at inference time
too, and an operational system has yesterday's monitor readings -- but any claim
about held-out *cities* must say "adapted using local trailing observations",
never "generalized without local data".

Leakage protection
------------------
The single correctness requirement is that a correction for an init time ``t``
may use only pairs whose **verifying observation** landed strictly before ``t``.
``anchor_frame`` enforces this by walking init times in chronological order and
filtering history on ``valid_time < t`` (strict; an observation exactly at ``t``
is not yet available when the forecast is issued). Nothing is fit globally, so
there is no other channel through which the future could reach the past.

This proves the retrospective timestamp boundary only. The matched archive has
no trustworthy ``retrieved_at`` field, so this module must not be presented as
a live-safe adapter. The future live runner must additionally require that the
observation retrieval time is at or before initialization and must report
source age/fallback state.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Defaults. Chosen from the pair schema and the documented bias structure, NOT
# tuned against test dates (see module tests, which pin behaviour rather than
# performance).
# --------------------------------------------------------------------------- #

TRAILING_DAYS = 14.0
# The rollout is on a 12-hour grid (leads 0,12,...,96), so "short lead <= 24 h"
# means {12, 24}. Lead 0 is deliberately EXCLUDED: it is the CAMS analysis at
# init, i.e. the model input rather than a forecast, and the spec scores it as
# its own baseline. Anchoring on it would measure analysis bias, not forecast
# bias.
SHORT_LEADS = (12, 24)
PRIOR_STRENGTH = 3.0      # pseudo-observations pulling the ratio toward 1.0
MIN_MULTIPLIER = 1.0 / 3.0
MAX_MULTIPLIER = 3.0
EPSILON = 1e-6            # guards obs/0 when Aurora predicts ~0

RAW_COL = "aurora_pm2p5"
ANCHORED_COL = "anchored_pm25"
DIAG_COLS = ("anchor_multiplier", "anchor_n_samples",
             "anchor_obs_age_h", "anchor_fallback")


@dataclass(frozen=True)
class AnchorConfig:
    """Explicit, configurable knobs (nothing hidden in the algorithm)."""

    trailing_days: float = TRAILING_DAYS
    short_leads: tuple[int, ...] = field(default=SHORT_LEADS)
    prior_strength: float = PRIOR_STRENGTH
    min_multiplier: float = MIN_MULTIPLIER
    max_multiplier: float = MAX_MULTIPLIER
    epsilon: float = EPSILON


DEFAULT_CONFIG = AnchorConfig()


@dataclass(frozen=True)
class AnchorEstimate:
    """One station's correction, with the diagnostics the public feed needs."""

    multiplier: float
    n_samples: int
    obs_age_h: float          # hours from newest supporting obs to init; NaN if none
    fallback: bool            # True when no eligible history -> multiplier 1.0


NEUTRAL = AnchorEstimate(multiplier=1.0, n_samples=0, obs_age_h=np.nan,
                         fallback=True)


# --------------------------------------------------------------------------- #
# Core estimator
# --------------------------------------------------------------------------- #

def estimate_multiplier(history: pd.DataFrame, init_time: pd.Timestamp,
                        config: AnchorConfig = DEFAULT_CONFIG) -> AnchorEstimate:
    """Robust trailing obs/Aurora multiplier for ONE station at ``init_time``.

    ``history`` holds that station's rows only; the caller guarantees isolation.
    Eligibility: short lead, verifying observation strictly before ``init_time``
    and inside the trailing window, with finite non-negative Aurora and
    observation. If two forecast cycles verify against the same station
    observation, only the shorter-lead residual contributes to support.
    """
    if history.empty:
        return NEUTRAL

    init_time = pd.Timestamp(init_time)
    init_time = (init_time.tz_localize("UTC") if init_time.tzinfo is None
                 else init_time.tz_convert("UTC"))
    window_start = init_time - pd.Timedelta(days=config.trailing_days)
    valid_time = pd.to_datetime(history["valid_time"], utc=True)

    obs = pd.to_numeric(history["obs_pm25"], errors="coerce").to_numpy(dtype=float)
    raw = pd.to_numeric(history[RAW_COL], errors="coerce").to_numpy(dtype=float)

    eligible = (
        history["lead_h"].isin(config.short_leads).to_numpy()
        # STRICT `<`: an observation timestamped exactly at init is not yet
        # available to a forecast issued at init.
        & (valid_time < init_time).to_numpy()
        & (valid_time >= window_start).to_numpy()
        & np.isfinite(obs) & (obs >= 0)
        & np.isfinite(raw) & (raw >= 0)
    )
    if not eligible.any():
        return NEUTRAL

    eligible_history = history.loc[eligible, ["valid_time", "lead_h"]].copy()
    eligible_history["_valid_time"] = valid_time[eligible].to_numpy()
    eligible_history["_obs"] = obs[eligible]
    eligible_history["_raw"] = raw[eligible]
    eligible_history = (
        eligible_history
        .sort_values(["_valid_time", "lead_h"], kind="stable")
        .drop_duplicates("_valid_time", keep="first")
    )

    ratios = (
        eligible_history["_obs"].to_numpy(dtype=float)
        / np.maximum(eligible_history["_raw"].to_numpy(dtype=float), config.epsilon)
    )
    ratios = ratios[np.isfinite(ratios)]
    if ratios.size == 0:
        return NEUTRAL

    raw_ratio = float(np.median(ratios))  # robust to single bad readings

    # Shrink toward 1.0 when history is thin: weight = n / (n + prior_strength).
    # With prior_strength=3, one sample moves only 25% of the way to its ratio
    # while a fortnight of dense history moves >90%.
    weight = ratios.size / (ratios.size + config.prior_strength)
    shrunk = 1.0 + weight * (raw_ratio - 1.0)
    multiplier = float(np.clip(shrunk, config.min_multiplier, config.max_multiplier))

    newest = eligible_history["_valid_time"].max()
    obs_age_h = float((init_time - pd.Timestamp(newest)).total_seconds() / 3600.0)

    return AnchorEstimate(multiplier=multiplier, n_samples=int(ratios.size),
                          obs_age_h=obs_age_h, fallback=False)


# --------------------------------------------------------------------------- #
# Frame-level application
# --------------------------------------------------------------------------- #

def anchor_frame(frame: pd.DataFrame,
                 config: AnchorConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Add anchored predictions + diagnostics to a benchmark frame.

    Walks init times in chronological order; for each (init, station) the
    multiplier is estimated from that station's own earlier-verifying rows only.
    ``RAW_COL`` is never modified. Returns a copy.
    """
    out = frame.copy()
    for col in (ANCHORED_COL, "anchor_multiplier", "anchor_n_samples",
                "anchor_obs_age_h"):
        out[col] = np.nan
    out["anchor_fallback"] = True

    if out.empty:
        return out

    valid_time = pd.to_datetime(out["valid_time"], utc=True)
    out["valid_time"] = valid_time
    init_time = (pd.to_datetime(out["init_date"], utc=True)
                 + pd.Timedelta(hours=12)) if "init_time" not in out.columns \
        else pd.to_datetime(out["init_time"], utc=True)
    out["init_time"] = init_time

    # History is drawn from the whole frame, but only rows verifying before the
    # current init can ever qualify (enforced in estimate_multiplier).
    for t in sorted(out["init_time"].unique()):
        rows_now = out["init_time"] == t
        past = out.loc[out["valid_time"] < t]
        past_by_station = {sid: g for sid, g in past.groupby("station_id", sort=False)}

        for sid, idx in out.loc[rows_now].groupby("station_id", sort=False).groups.items():
            est = estimate_multiplier(
                past_by_station.get(sid, past.iloc[0:0]), pd.Timestamp(t), config)
            out.loc[idx, "anchor_multiplier"] = est.multiplier
            out.loc[idx, "anchor_n_samples"] = est.n_samples
            out.loc[idx, "anchor_obs_age_h"] = est.obs_age_h
            out.loc[idx, "anchor_fallback"] = est.fallback

    raw = pd.to_numeric(out[RAW_COL], errors="coerce")
    # clip(lower=0): a multiplier is never negative, but Aurora rows can be NaN,
    # and downstream scoring must never see a negative concentration.
    out[ANCHORED_COL] = (raw * out["anchor_multiplier"]).clip(lower=0.0)
    out["anchor_n_samples"] = out["anchor_n_samples"].fillna(0).astype(int)
    return out
