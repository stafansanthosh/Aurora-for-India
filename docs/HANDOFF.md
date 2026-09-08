# Handoff: IndiaAQBench current state

**Updated:** 2026-09-08
**Branch:** `master`
**Scientific state:** free GFS passed the forecast-BLH gate; do not run Aurora 1.5; one audit failure remains
**Product status:** illustrative preview only; no live feed
**Documentation state:** canonical/tool instructions and public/current-state
documents reconciled on 2026-08-12 with the event-skill diagnosis, target
re-evaluation, and chosen Option B direction. Historical plans carry explicit
supersession notes. No scientific result changed by that reconciliation.

## README readability follow-up (2026-09-08)

Read the full README again at the owner's request and rewrote it for first-time
readers. CAMS, Aurora, and the observation-based correction are explained before
the result table; Component A appears only as the code's name for that correction.
Replaced L1/L2 and unexplained modelling labels with descriptive language.
Added a planned-work section: version the retrospective reports, validate a
probability model using local readings/GFS, compare against existing SILAM
forecasts, then conditional private shadow testing and a possible public feed.
No model, metric, data, or experimental decision changed. The two boundary-layer
experiments remain explicitly train-only and the live interface illustrative.
The earlier README/lockfile commit 6af9a74 was pushed at the owner's request;
GitHub run 34216642114 passed Python and web jobs. This follow-up continues the
authorized public README work. Historical data-rights restrictions still apply.

## Public README and CI work (2026-09-08)

The README now leads with the negative raw-Aurora outcome and the verified
forward-24-hour temporal-test table: CAMS 0.154/0.911/0.060, raw Aurora
0.471/0.672/0.239, Component A 0.582/0.441/0.399, each across 1,704 observed
station-window events. Regenerating the existing anchored 24-hour artifact to
a temporary file reproduced every table value exactly. The hourly path remains
separate. This corrects the old README's implication that the entire temporal
test had never been scored: only the new boundary-layer classifier remains
train-only. Original Aurora primary sources describe global pollution work,
not a China-only paper. Personal motivation is grounded in the supplied
application excerpts without repeating the falsified unserved-city premise.

Local Python suite: 108 pass, one existing NumPy binary-size warning. Audit:
36 pass, two legacy warnings, one retained failure; independent count confirms
463 inconsistent PM-bin rows of 80,730. No accepted calibrator exists.

GitHub metadata and anonymous README access confirm PUBLIC, MIT, master, HTTP
200. `docs/PUBLICATION_READINESS.md` replaces the obsolete private/no-licence
checklist with the current audit and a concrete owner decision table. Gitleaks
8.30.1 scanned all 72 starting commits and 469.87 MB with no leaks. History has
16 blobs above 10 MiB; the largest ERA5 file is 84.22 MiB. OpenAQ/ERA5 historical
redistribution remains unresolved. Preserve 2ab1c50 → e0a3487 and b78479b →
bcef006 as pre-declaration/result evidence in any owner-approved restructuring.
No visibility change, history rewrite, deletion, mirror, or push was authorized
or performed. Six untracked SILAM cycles remain outside this commit.

The remote failure on d879a67 was solely nanoid <3.3.18. The fix changes only
three lockfile fields to 3.3.18; no dependency-range or workflow change is needed.
Local npm ci, production build, 2/2 web tests, and production audit passed (zero production vulnerabilities) under Node 22.14.0 x64. Development dependencies still report 19 audit issues outside this narrow fix. Remote CI on the new commit cannot be green until the owner authorizes a push.

## Immediate next action

Review `git show --stat HEAD` and the publication decision table. Do not push
without the owner's explicit request. Resolve rights confirmation versus a
reviewed rewrite versus a clean mirror before any publication restructuring.
After an authorized push, require green GitHub Actions on that exact commit.
The next scientific action remains freezing/versioning retrospective scorecards;
do not acquire or score temporal-test data for the boundary-layer classifier.

## Objective and claim boundary

IndiaAQBench tests whether global-tier atmospheric forecasts plus inexpensive,
observation-grounded adaptation can improve multi-day PM2.5 episode warning.
The original “underserved Patna/Varanasi” framing is retired. Delhi is a
development and diagnostic environment supplying most benchmark events, not
transferable target-city evidence. Success means Very Poor+ event skill
(POD/FAR/CSI and event counts), not MAE alone.

The historical hourly sensitivity results use hourly observation matching and hourly application of
CPCB thresholds. They are a sensitivity analysis, not the official 24-hour
headline and not evidence of year-round operational utility.

## Verified state

| Item | State |
|---|---|
| OpenAQ archive | 1,489,534 observations, 159 stations, 9 cities |
| Frozen schedule | 56 dates: 32 train, 24 test |
| Actual CAMS forecast archive | 56 dates, 71,232 positive-lead station rows |
| Aurora rollout | 56 dates, 80,136 rows, registry `159:4c0b55ad238f` |
| Canonical manifest | 56 records, 56 unique dates, zero errors, zero duplicates |
| Legacy pairs | 2025-11-15 and 2025-11-20 remain on disk and are strictly excluded |
| Tests | 108/108 pass locally (re-verified 2026-09-08) |
| Audit | 39 checks: 36 pass, 2 expected legacy warnings, 1 size-bin failure (re-verified 2026-08-12) |
| Raw/Component A scorecards | 24-hour headline and hourly sensitivity generated separately |
| Accepted calibrator | Absent; full-registry fit failed the POD no-harm gate |
| Public live forecast | Absent |
| ERA5 Option B acquisition | 7/7 planned months, 84 train-only days, 320,544 station-hours, 159 stations; hashes/coverage/duplicates/missing values validated 2026-08-12 |
| Option B kill-test | **PROCEED**: pooled ΔAUC +0.046, ΔCSI +0.206; Patna +0.183/+0.296; train-only perfect prognosis |
| GFS forecast-BLH gate | **FREE NWP SUFFICIENT**: pooled ΔAUC +0.0336, ΔCSI +0.1620; Patna +0.108/+0.101; 32/32 train cycles, no GPU |
| SILAM prospective capture | **32/32 rolling window captured**: 31 `complete`, 1 `complete_with_gaps` (20260730, upstream d2 has 20 distinct hours padded to 24 steps). 20260712 already aged out and survives only because it was captured in time |

The local `.venv` is healthy: Python 3.11.9. The earlier broken-environment
claim was caused by a restricted Codex sandbox, not the repository runtime.

## Outstanding audit failure and scoped decision

Aurora violates `PM1 <= PM2.5 <= PM10` on 463 of 80,730 stored rows (0.5735%).
The median excess is 0.265 µg/m³ and the maximum is 6.269 µg/m³. Violations
span 23 dates and every positive lead. The audit retains this as a failure.

Raw Aurora, persistence, CAMS, and Component A consume only PM2.5. PM1 and PM10
were removed from the calibrator and regression-tested as non-features. The
benchmark specification records this path-specific scoring decision. Do not
describe the full Aurora output as physically clean, and do not remove or
downgrade the audit check.

## First scorecard decision

On pooled temporal-test rows, Component A improves raw Aurora from POD 0.483,
FAR 0.721, CSI 0.215, and MAE 32.76 to POD 0.566, FAR 0.585, CSI 0.315, and MAE
26.52 across 2,113 observed Very Poor+ events.

In the 24-hour headline, Component A improves L1 at every window and improves
pooled CSI, but L2 POD falls from 0.798 to 0.755 across 94 events. The hourly
sensitivity also has an L1 +84-hour POD regression. Component A is promising
but **not certified for public selection**.

The direct-target calibrator again improved MAE while destroying event POD:

- L1: MAE 33.9 → 24.5, POD 0.474 → 0.125;
- L2: MAE 34.2 → 20.2, POD 0.748 → 0.299.

The guardrail refused to save an accepted model. The prior binary was renamed
`results/models/rejected_pilot_calibrator.joblib`; the accepted default path is
`results/models/accepted_pooled_calibrator.joblib` and does not exist.

## Diagnosis of the event-skill ceiling (2026-08-11)

`docs/EPISODE_SKILL_DIAGNOSIS.md` (reproduce with
`python -m src.eval.diagnose_events`) establishes, on train-split data only:

- the calibrator failed because **MAE-optimal regression and threshold
  exceedance are mathematically opposed**, not because of the model family — so
  no further concentration-regression calibrator should be attempted;
- **re-thresholding alone is capped**: raw Aurora best CSI 0.284, Component A
  0.355, persistence 0.376;
- **Aurora's dynamic range is capped** at 196.1 µg/m³ against observations
  reaching 571.8, emitting zero values ≥250 anywhere;
- Aurora's discrimination is **largely between-city** (pooled AUC 0.835 →
  within-station 0.710; Patna 0.640, Mumbai 0.422) and **does not clearly beat
  persistence** in ablation;
- **89.1% of all Very Poor+ windows are Delhi**; the L2 result is 92 Kolkata +
  2 Kanpur + 0 Varanasi; **Varanasi has zero events in 1,516 windows**;
- Varanasi's archive mean (29.9 µg/m³, below Bangalore's 33.3, 4.3% exact
  zeros) is an **open data question** requiring an independent CPCB cross-check
  before any Varanasi claim. The stations and coordinates are correct, so this
  is not the earlier geo-matching failure.

The direction that survives is **predicting P(exceedance) and publishing an
operating point**, not predicting µg/m³ and thresholding. The ceiling estimate
(AUC 0.927, best CSI 0.476) is train-only, Delhi-dominated, and **not a
validated result**.

## Target re-evaluation (2026-08-11) — the founding premise is falsified

`docs/TARGET_REEVALUATION.md`. **Patna and Varanasi are not unserved.** India
runs AQEWS (WRF-Chem) nationwide at **10 km with 10-day lead**, naming Varanasi,
Lucknow and Patna among covered cities, plus IMD-SILAM 5 km/3-day and a ~140-city
bulletin. The brief's "AQEWS 400 m" is the **Delhi nest**, not the national
domain — that misreading produced the target choice. Aurora at 0.4° (~44 km) is
four times coarser than the incumbent in the incumbent's own cities.

Confirm the city list at `ews.tropmet.res.in` directly; it refused connections
from this machine, so the finding rests on consistent secondary sources.

**The defensible gap is different, and this repo already measured it:** actual
CAMS — the forecast most of the world actually receives — scores POD 0.154,
FAR 0.911, CSI 0.060 at the 24-hour headline, while trivial local anchoring
reaches POD 0.582, CSI 0.399. The thesis "the global tier fails at episodes and
cheap local anchoring fixes it" does **not require Aurora to win**.

Ranked candidates: **Tier 1** West African Harmattan dust (Ghana/Senegal/Nigeria,
~174 active monitors, synoptic dust transport — the one regime 0.4° is not
under-resolved for) and **mainland SE Asia biomass haze** (Thailand, 381 active
monitors, FIRMS supplies the source term). **Tier 2** Pakistan (332 monitors, no
national multi-day model found, but emission-dominated regime) and Nepal.

Also: Aurora **does** carry change information — the Aurora-minus-persistence
signal predicts >25% deterioration at AUC 0.764, and Aurora overtakes persistence
at +48–72 h. The benchmark was scoring level, which persistence wins by
construction. This moderates the earlier "Aurora adds nothing" reading.

**The next decisive experiment needs no GPU and no Aurora:** score CAMS and
anchored-CAMS event skill in one Tier-1 region using existing code.

## Direction chosen (2026-08-11): Option B

The owner selected **Option B** from `docs/OPTIONS_REVIEW.md`: keep PM2.5 as the
target, add the boundary-layer meteorology the 0.4° pollution checkpoint lacks.

**`docs/CODEX_BRIEF_OPTION_B.md` is the self-contained working brief.** It holds
every diagnostic result, the kill-test design, the pre-declared decision rule,
and the hard rules. Any agent picking this up should read that file.

The **kill-test is complete and passed**. Train-only, out-of-fold addition of
perfect-prognosis ERA5 raised pooled AUC from 0.927 to 0.973 and best CSI from
0.476 to 0.682. Patna rose from AUC/CSI 0.745/0.159 to 0.928/0.455. This says
boundary-layer information has headroom; it does not say an operational BLH
forecast will retain it. Full caveats are in `docs/BLH_CEILING_RESULT.md`.

ERA5 acquisition completed and passed a read-only validation on 2026-08-12:
seven request-matching monthly files, 84 required train-only days, 320,544
station-hours, 159 stations, 2,016 timestamps, zero duplicate
`(station_id, valid_time)` keys, zero missing feature cells, and matching file
hashes. The validated inputs and ceiling-test implementation are committed in
`e0a3487`.

The **forecast-BLH gate is also complete and passed** under the contract
committed in `b78479b` before acquisition. NOAA GFS 0.25 degree 12Z forecasts
were acquired for all 32 frozen train initializations, every three hours through
+96 h: 167,904 rows, 159 stations, zero missing dates, duplicates, unresolved
failures, or non-finite fields. Exact source/index URLs, byte ranges, hashes,
retrieval times, GRIB cycle/lead metadata, units, and terms are retained per
cycle. The temporal test split remained sealed.

On the same 18,934 out-of-fold train windows and 2,167 events, adding GFS
forecast boundary-layer features raised pooled AUC from 0.927 to 0.961 and best
CSI from 0.476 to 0.638 (ΔAUC +0.0336, ΔCSI +0.1620). It retained 75.8% of the
like-for-like ERA5-3h AUC gain and 80.9% of the CSI gain. Patna improved by
+0.108 AUC/+0.101 CSI across 111 events; Mumbai also improved across 61 events.
GFS cleared the pre-declared rule, so **do not run Aurora 1.5 for BLH**. Raw GFS
HPBL is strongly high-biased against ERA5 (+405 to +516 m pooled), so the claim
is retained classifier signal, not interchangeable physical BLH. Full results:
`docs/FORECAST_BLH_RESULT.md`.

Primary documentation separately confirmed that Aurora 1.5's released weather
checkpoint outputs `blh`, but requires a much larger IFS HRES T0 weather-input
contract. It is not an Aurora 1.5 air-pollution checkpoint. Technical
availability no longer justifies a rollout because free GFS already passes.

The SILAM capture continued independently during this work. Untracked
directories now exist for 20260713, 20260714, and 20260715; they remain outside
this gate and were not provenance-reviewed, staged, deleted, or overwritten.
Cycle 20260811 and the previously documented capture remain in place. Review
each untracked cycle separately before trusting or committing it.

## Exact next scientific action

1. Freeze/version the generated 24-hour and hourly retrospective tables and
   connect the forward-24-hour headline to `src/report/` without pooling the two
   scoring paths.
2. Preserve train-only development and per-city event counts. ERA5 remains
   perfect-prognosis analysis; GFS is forecast-time input but this gate is not
   temporal-test or operational validation.
3. Do not start Aurora 1.5 inference or provision a GPU for BLH. Any future
   Aurora experiment requires a new pre-declared incremental-value question
   over the now-qualified GFS source.
4. Review the prospective SILAM capture without deleting or overwriting cycles;
   an eventual head-to-head must align its 00Z initialization with the
   comparison forecast.
5. Resolve the Varanasi observation anomaly and verify incumbent coverage before
   making city-specific product claims.

No Aurora 1.5 GPU compute is warranted for BLH: the cheapest adequate source is
GFS and it passed. Fine-tuning remains deferred.

## Publication boundary

The repository is already public and MIT-licensed. Historical OpenAQ/ERA5
redistribution remains unresolved. Read `docs/PUBLICATION_READINESS.md` for the
verified audit and rights/rewrite/mirror comparison before proposing any action.
No visibility change, history rewrite, mirror, data deletion, or push is
authorized. Scientific posts must disclose the cutoff revision, missing
post-monsoon test, hourly-versus-24-hour distinction, audit failure, rejected
calibrator, Delhi-dominated support, target re-evaluation, and train-only
perfect-prognosis/forecast-input distinction for the boundary-layer experiments.
