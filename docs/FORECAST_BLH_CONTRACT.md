# Forecast-versus-analysis boundary-layer gate

**Pre-declared:** 2026-08-12, before acquiring or scoring the multi-date GFS
comparison.
**Status:** binding experiment contract. Do not change thresholds after viewing
results.
**Population:** frozen train dates only. The temporal test split remains sealed.

## 1. Decision this experiment must make

The completed Option B experiment established a train-only, perfect-prognosis
ceiling: adding ERA5 boundary-layer meteorology raised pooled out-of-fold AUC
by 0.046 and best CSI by 0.206 over the current feature set. ERA5 is reanalysis
valid at the target time, not an operational forecast. Those numbers remain an
upper-bound analysis result and must never be described as forecast skill.

This gate asks whether a freely available operational weather forecast retains
enough of that information to make Aurora 1.5 GPU inference unnecessary. It
has two linked parts:

1. quantify forecast boundary-layer-height degradation against ERA5 analysis;
2. replace the perfect-prognosis boundary-layer features with forecast-time
   features and measure retained Very Poor+ episode discrimination.

The result must end with one of three recommendations in section 8. It does not
authorize GPU provisioning, inference, test-split scoring, Component A tuning,
or a new learned method.

## 2. Source selection and primary-source verification

### Selected free forecast: NOAA GFS

Use the NOAA Global Forecast System deterministic 0.25 degree GRIB2 product
from the public `noaa-gfs-bdp-pds` archive. NOAA documents four cycles per day,
public reuse, and anonymous access:

- https://registry.opendata.aws/noaa-gfs-bdp-pds/
- https://www.nco.ncep.noaa.gov/pmb/products/gfs/

The official 0.25 degree inventory identifies `HPBL` at the surface as
planetary boundary-layer height in metres and also exposes 2 m temperature,
2 m dew point, and 10 m U/V wind in the same product:

- https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f003.shtml

The archive was checked before this contract for the first required date at
+24 h and the last required date at +96 h; both index objects returned HTTP
200. One HPBL byte range was decoded only to validate the acquisition path. No
multi-date forecast-versus-analysis metric or episode result was viewed.

GFS is selected because it provides the required field, exact 12Z cycles,
leads through +96 h, the full frozen 2025 train period, a global 0.25 degree
grid, anonymous historical access, and terms compatible with reproducibility.
ERA5 is analysis truth for this diagnostic only; it is not an operational
input.

### Aurora 1.5 verification

Microsoft's released model documentation confirms that `AuroraV1p5` predicts
`blh` as one of seven output-only surface variables. It is a deterministic
0.25 degree weather model intended for IFS HRES T0 inputs, not an Aurora 1.5
air-pollution checkpoint. The documented optimal input contract includes 19
surface fields (with insolation computed by the package), five atmospheric
variables on 13 pressure levels, and 36 static variables. The separate Aurora
0.4 degree Air Pollution checkpoint remains the pollution model already used
by this repository and does not expose BLH.

Primary source:

- https://microsoft.github.io/aurora/models.html#aurora-1-5-0-25

Therefore Aurora 1.5 can technically supply forecast BLH, but doing so requires
a materially larger weather-input pipeline and GPU rollout. That spend is not
justified if GFS passes this gate.

## 3. Frozen population and matching

- Read initialization dates only from `docs/benchmark_dates.csv` and retain
  dates before `src.splits.SPLIT_CUTOFF`: 32 train initializations.
- Initialization is exactly 12:00 UTC, matching the existing Aurora rollout.
- Use the GFS 12Z cycle for the same calendar date. Never substitute 00Z, 06Z,
  18Z, a neighbouring date, or a different lead.
- Acquire forecast hours 0, 3, 6, ..., 96. This bounded three-hour grid is used
  for both GFS and ERA5 aggregates so temporal sampling is like-for-like.
- Every GFS row must carry `init_time`, `valid_time`, integer `lead_h`, station
  identity, source URL, byte range, retrieval time, and content hash through
  the source manifest.
- Sample GFS and ERA5 independently at each registry station's nearest native
  grid cell. Compare them by exact `(station_id, valid_time)` after verifying
  `valid_time == init_time + lead_h`.
- Raw degradation covers all 159 registry stations and is reported by city.
  Episode classification retains the ceiling test's train-only
  `spatial_tier == train_pool` population.
- Do not read, acquire for development, or score any test initialization.

## 4. Fields and 24-hour features

Acquire these instantaneous GFS fields and preserve their native units:

| GFS field | Level | Derived feature |
|---|---|---|
| `HPBL` | surface | BLH in m |
| `TMP` | 2 m above ground | dew-point depression with DPT |
| `DPT` | 2 m above ground | dew-point depression with TMP |
| `UGRD` | 10 m above ground | wind speed and ventilation |
| `VGRD` | 10 m above ground | wind speed and ventilation |

Derive wind as `hypot(UGRD, VGRD)`, ventilation as `HPBL * wind`, and
dew-point depression as `TMP - DPT`, exactly paralleling the ERA5 ceiling
features.

For each existing 24-hour target window, use the eight exact three-hour samples
in `[window_start, window_end)`. Require all eight; a short window is missing,
not silently averaged. Compute BLH minimum/mean, ventilation minimum/mean, and
mean dew-point depression for both GFS and ERA5 on this same grid.

## 5. Missing-cycle and integrity policy

- Acquisition is resumable and may retry transport failures, but must never
  replace a missing cycle, lead, field, or valid time.
- A date is complete only with every lead 0..96 by 3 h, every required field,
  every station, unique keys, finite values, and matching source hashes.
- If any source object is genuinely unavailable after retry, exclude that
  entire initialization from *both* the GFS and ERA5 sides and list it. Never
  compare partial dates or allow different populations by feature set.
- The decision is valid only with at least 29 of 32 complete dates (90%), every
  represented train season still present, and at least 95% of otherwise
  eligible classifier windows. If not, report `INDETERMINATE - COVERAGE`; do not
  infer model inadequacy and do not authorize GPU work.
- Before scoring, verify exact key uniqueness, cycle/lead/valid-time arithmetic,
  finite values, units, source hashes, and population equality.

## 6. Raw BLH degradation metrics

At exact +24, +48, +72, and +96 h, report paired GFS-minus-ERA5:

- sample count and coverage;
- mean bias in metres;
- RMSE in metres;
- Pearson correlation.

Report each metric pooled and per city. Also report seasonal pooled rows as a
diagnostic. These physical metrics describe degradation but do not alone decide
product value; the event-skill gate in section 8 is primary.

## 7. Retained episode-skill experiment

Use the existing `HistGradientBoostingClassifier`, fixed hyperparameters,
five-fold `GroupKFold` by `init_date`, Very Poor+ threshold (121 ug/m3), and
metric helpers from `src.eval.diagnose_events`. Do not tune any model or
threshold against these results.

Compare the following on the identical complete-window population:

| Feature set | Features |
|---|---|
| current | persistence, month, window start lead, Aurora PM2.5, CAMS forecast PM2.5 |
| + ERA5 3-hour boundary layer | current + ERA5 BLH min/mean, ventilation min/mean, dew-point depression mean |
| + GFS forecast boundary layer | current + GFS analogues of the same five fields |

Report pooled AUC and best CSI, then current versus GFS per city with `n` and
event counts. Cities with fewer than 10 events are labelled too small to score.
Pooled results must be labelled Delhi-dominated.

Also report AUC and best CSI for the out-of-fold predictions in windows ending
at +24, +48, +72, and +96 h (window starts 0, 24, 48, and 72 h). Models remain
fit in the frozen pooled cross-validation; this is subgroup reporting, not
lead-specific refitting.

For context, report the signed retention ratios
`GFS incremental gain / ERA5-3h incremental gain` for AUC and CSI when the ERA5
denominator is positive. Do not substitute these ratios for the absolute gate
or compare them as if the three-hour experiment were identical to the published
hourly perfect-prognosis ceiling.

## 8. Pre-declared decision rule

Judge GFS against the same absolute hurdle that allowed Option B to proceed.

**FREE NWP SUFFICIENT - do not run Aurora 1.5** if all are true:

1. section 5 coverage is valid;
2. adding GFS forecast boundary-layer features lifts pooled out-of-fold AUC by
   at least 0.020 and best CSI by at least 0.030 over `current`;
3. both AUC and CSI gains are positive in at least one non-Delhi city with at
   least 50 train events.

**FREE NWP INSUFFICIENT - a bounded Aurora 1.5 BLH pilot is scientifically
justified, but not automatically authorized** if coverage is valid and pooled
GFS delta AUC is below 0.010. The recommendation must still state the observed
per-city and lead behaviour, Aurora 1.5's input burden, and that the released
checkpoint is weather-only.

**AMBIGUOUS - no GPU yet** for every valid-coverage result between those rules,
including a pooled pass that fails the non-Delhi condition. Do not round up.

`INDETERMINATE - COVERAGE` takes precedence over all three. The published ERA5
perfect-prognosis pass is not revoked by a weak GFS result; it means the
information exists, whereas this experiment tests whether an operational free
forecast retains enough of it.

## 9. Required artifacts and verification

The implementation must provide a plan mode, resumable acquisition, immutable
provenance, station sampling, a read-only validator, the scorer, focused tests,
and a result document. Before the final recommendation:

1. run focused acquisition/scoring tests;
2. run the full test suite;
3. run `python -m src.eval.audit` and preserve the two legacy warnings and the
   unresolved PM1/PM2.5/PM10 ordering failure visibly;
4. update `docs/HANDOFF.md` and append `JOURNAL.md`;
5. commit reviewed files on `master`; do not push.
