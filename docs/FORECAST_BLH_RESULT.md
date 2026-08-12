# Forecast-BLH gate result: free GFS is sufficient

**Date:** 2026-08-12
**Pre-declared contract:** `docs/FORECAST_BLH_CONTRACT.md`, committed as
`b78479b` before the multi-date GFS acquisition or score existed
**Reproduce acquisition:** `python -m src.data.gfs_boundary_layer`
**Reproduce score:** `python -m src.eval.forecast_blh_gate`
**Population:** frozen train dates only; the temporal test split remained sealed
**Verdict:** **FREE NWP SUFFICIENT - do not run Aurora 1.5**

---

## 1. What changed from the ceiling test

The earlier Option B result used ERA5 reanalysis valid at the target window.
That was perfect prognosis: an upper bound on the value of boundary-layer
information, not operational forecast skill.

This experiment replaces those analysed fields with an actual forecast issued
at initialization. It uses NOAA's free deterministic 0.25 degree GFS, exact 12Z
cycles matching the benchmark initialization, and exact three-hour forecast
times from +0 through +96 h. GFS and ERA5 are sampled at all 159 registry
stations. Their 24-hour BLH, ventilation, and dew-point-depression features use
the same eight three-hour valid times, so the comparison is like-for-like.

Every learned score remains train-only and out-of-fold by initialization date.
No test row was acquired for development or scored.

## 2. Data and integrity

| Check | Result |
|---|---:|
| Frozen train initializations | 32/32 |
| Stations | 159 |
| Forecast leads | 33 per date, +0..+96 h by 3 h |
| Station-lead rows | 167,904 |
| Duplicate `(init_date, station_id, lead_h)` keys | 0 |
| Missing dates | 0 |
| Non-finite required fields | 0 |
| Otherwise-eligible classifier-window coverage | 100% |
| Unresolved acquisition failures | 0 |

Each cycle has an immutable provenance record containing exact source and index
URLs, byte ranges, index and message hashes, retrieval time, GRIB initialization
and valid-time metadata, field identity, units, and the NOAA reuse terms. A
small number of transient NOAA read timeouts were retried against the same exact
cycle; no alternate initialization, date, or lead was substituted.

## 3. Raw GFS BLH degradation against ERA5

GFS is strongly high-biased relative to ERA5, especially in Delhi. That means
its absolute HPBL should not be described as interchangeable with ERA5 BLH.
However, correlation remains 0.71-0.75 pooled through +96 h, so the forecast
retains substantial ordering information for the classifier.

| Lead | n | GFS - ERA5 bias (m) | RMSE (m) | correlation |
|---:|---:|---:|---:|---:|
| +24 h | 5,088 | +515.5 | 1,029.2 | 0.707 |
| +48 h | 5,088 | +460.8 | 955.0 | 0.717 |
| +72 h | 5,088 | +485.9 | 954.2 | 0.753 |
| +96 h | 5,088 | +404.6 | 859.7 | 0.750 |

The full per-city and per-season physical table is versioned at
`results/forecast_blh/gfs_blh_degradation.csv`. City behaviour is heterogeneous:
for example, Delhi's bias is +793 to +1,096 m, while Mumbai is near unbiased
(-20 to +21 m). Raw pooled RMSE is therefore not a sufficient product gate.

## 4. Retained Very Poor+ episode skill

Same 18,934 train-pool windows, 2,167 Very Poor+ events, and 32 initialization
groups as the published ceiling experiment. Hyperparameters and folds remained
fixed.

| Feature set | AUC | best CSI | delta AUC vs current | delta CSI vs current |
|---|---:|---:|---:|---:|
| current (persistence + Aurora + CAMS + season/lead) | 0.927 | 0.476 | - | - |
| + ERA5 boundary layer, same 3 h grid | 0.971 | 0.676 | +0.044 | +0.200 |
| **+ GFS forecast boundary layer** | **0.961** | **0.638** | **+0.034** | **+0.162** |

GFS retains **75.8% of the ERA5-3h incremental AUC gain** and **80.9% of the
incremental CSI gain**. The ERA5-3h comparison is slightly below the separately
published hourly ceiling (0.973/0.682), as expected from the coarser sampling;
it is included only as the like-for-like retention denominator.

### Per city: current versus GFS

| City | n | events | AUC current | AUC +GFS | delta AUC | CSI current | CSI +GFS | delta CSI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Delhi | 8,511 | 1,974 | 0.928 | 0.958 | +0.030 | 0.612 | 0.705 | +0.093 |
| **Patna** | 1,393 | 111 | 0.745 | **0.853** | **+0.108** | 0.159 | **0.260** | **+0.101** |
| Mumbai | 4,992 | 61 | 0.620 | 0.695 | +0.075 | 0.025 | 0.100 | +0.075 |
| Lucknow | 1,060 | 16 | 0.827 | 0.792 | -0.035 | 0.065 | 0.057 | -0.007 |

Patna and Mumbai both satisfy the contract's non-Delhi condition with at least
50 events. Lucknow regresses slightly but has only 16 events; it remains an
important warning against claiming universal city-level improvement. Bangalore
has zero events and Chennai has five, so neither is scored. The pooled result
is still Delhi-dominated and is not transferable evidence for every city.

### By target-window end

These are subgroup scores from the same pooled out-of-fold predictions, not
separately refit lead-specific models.

| Window end | Current AUC / CSI | +GFS AUC / CSI | AUC / CSI gain |
|---:|---:|---:|---:|
| +24 h | 0.904 / 0.473 | 0.949 / 0.600 | +0.045 / +0.127 |
| +48 h | 0.930 / 0.457 | 0.969 / 0.648 | +0.039 / +0.190 |
| +72 h | 0.944 / 0.553 | 0.960 / 0.642 | +0.016 / +0.089 |
| +96 h | 0.926 / 0.448 | 0.962 / 0.682 | +0.036 / +0.234 |

GFS improves both metrics at every reported window end. The +72 h AUC gain is
the smallest, but CSI still improves by 0.089.

## 5. Verdict against the pre-declared rule

| Criterion | Required | Actual | Met |
|---|---|---:|---|
| Valid coverage | at least 29/32 dates, all seasons, at least 95% eligible windows | 32/32, all seasons, 100% | yes |
| Pooled delta AUC | at least +0.020 | **+0.0336** | yes |
| Pooled delta CSI | at least +0.030 | **+0.1620** | yes |
| Positive AUC and CSI gains in a non-Delhi city with at least 50 events | at least one | Patna and Mumbai | yes |

**FREE NWP SUFFICIENT - do not run Aurora 1.5.**

This verdict is about the incremental value of forecast boundary-layer features
for this train-only classifier. It does not certify an operational product,
unlock the temporal test split, certify Component A, or establish skill in
cities without enough events.

## 6. Aurora 1.5 verification and spend decision

Microsoft's released documentation confirms that `AuroraV1p5` predicts `blh`
as an output-only surface variable. It is a 0.25 degree weather checkpoint for
IFS HRES T0 inputs, not an Aurora 1.5 air-pollution checkpoint. Its optimal
input contract requires 19 surface fields, five atmospheric variables on 13
pressure levels, and 36 static variables; insolation is computed by the package.
The existing 0.4 degree Aurora Air Pollution checkpoint is a separate model and
does not output BLH.

Primary source:

- https://microsoft.github.io/aurora/models.html#aurora-1-5-0-25

Aurora 1.5 is technically capable of this field, but GFS already clears the
same absolute episode-skill hurdle at every target window without a GPU or a new
HRES-input pipeline. There is no evidence-based reason to pay for an Aurora 1.5
rollout now. A future Aurora experiment would need a new pre-declared question
and a credible expected gain over GFS, not merely proof that the checkpoint
exists.

## 7. Claim boundary and next work

The honest conclusion is:

> The perfect-prognosis ERA5 ceiling passed, and a free operational GFS forecast
> retains enough of the boundary-layer episode signal to pass the pre-declared
> train-only gate. Use GFS as the forecast-time BLH source; do not spend on
> Aurora 1.5 inference for this purpose.

Do not shorten that to "GFS BLH is accurate"; the large model-dependent bias
contradicts that statement. Do not quote the ERA5 ceiling as achievable live
skill. Do not describe these train-only out-of-fold results as temporal-test or
operational validation.

The next scientific/reporting task is to freeze and wire the existing 24-hour
and hourly retrospective scorecards. Separately, the prospective SILAM archive
needs provenance review and an initialization-aligned incumbent comparison.
Neither task justifies Aurora 1.5 GPU inference.
