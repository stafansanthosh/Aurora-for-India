# Codex brief — Option B: PM2.5 exceedance with boundary-layer meteorology

**Written:** 2026-08-11 by the Claude Code session that produced the diagnosis.
**Read first:** `docs/AGENT_BRIEF.md`, then this file, then `docs/HANDOFF.md`.
**Branch:** `master`. Do not create branches.
**You are cold-starting.** Everything needed is in this file or cited from it.

---

## 0. One-paragraph orientation

IndiaAQBench tests whether Microsoft Aurora plus cheap adaptation can produce
*useful* PM2.5 forecasts for Indian cities. "Useful" means **Very Poor+
(≥121 µg/m³) event skill — POD / FAR / CSI — not MAE**. A 56-date retrospective
rollout is complete and scored. A diagnosis then established why event skill is
low and what could fix it. The owner has chosen **Option B**: keep PM2.5 as the
target, but add the boundary-layer meteorology the current setup lacks. Your job
is to run the cheap kill-test for Option B before any GPU spend, and to build
out the pieces that survive it.

---

## 1. What was established, with evidence

All method-performance numbers below are **train split, train_pool tier,
out-of-fold by init date**. No test row was scored. Reproduce with
`python -m src.eval.diagnose_events`.

### 1.1 The calibrator failed for a structural reason

The documented reason ("trees cannot extrapolate") is incomplete and invites the
wrong fix. The real cause is the **loss**: an MAE/MSE-optimal regressor predicts
near the conditional mean, which for a heavy-tailed target sits below the upper
tail. It therefore falls below 121 µg/m³ even when exceedance is likely.
Improving MAE and destroying POD are the same act.

Evidence: L1 MAE 33.9 → 24.5 while POD 0.474 → 0.125; L2 MAE 34.2 → 20.2 while
POD 0.748 → 0.299.

**Do not build another concentration-regression calibrator.** Not with a neural
net, not with more features. The pipeline shape "predict µg/m³ → threshold at
121" is the defect.

### 1.2 Re-thresholding alone is capped

| Method | AUC | CSI @121 | best CSI | at threshold |
|---|---:|---:|---:|---:|
| raw Aurora | 0.835 | 0.220 | 0.284 | 105.2 |
| Component A | 0.878 | 0.277 | 0.355 | 105.2 |
| persistence | 0.884 | 0.251 | 0.376 | 83.8 |
| CAMS forecast | 0.716 | 0.037 | 0.194 | 49.8 |

`best CSI` is the ceiling for **any** concentration post-processor.

### 1.3 Aurora's dynamic range is a hard cap

Across 20,008 train windows Aurora's maximum output is **196.1 µg/m³**;
observations reach **571.8**. It emits **zero** values ≥250 anywhere, against
281 observed in Delhi. In Lucknow and Mumbai it never reaches 121 at all. This
is inherited from CAMS, which the 0.4° pollution checkpoint was fine-tuned to
reproduce.

### 1.4 The discrimination is largely between-city

| Method | AUC pooled | AUC within-station |
|---|---:|---:|
| raw Aurora | 0.835 | 0.710 |
| Component A | 0.878 | 0.785 |
| persistence | 0.884 | 0.808 |

Per city: Delhi 0.767, Patna **0.640**, Lucknow 0.722, Mumbai **0.422**
(worse than chance).

### 1.5 But Aurora DOES carry change information

This is the result that keeps Option B alive:

- Aurora-minus-persistence predicts a >25% deterioration at **AUC 0.764**
- Aurora's level alone: 0.656
- Aurora overtakes persistence at **+48 to +72 h** (winter +72 h: Aurora 0.923
  vs persistence 0.808)

The benchmark was scoring *level*, which persistence wins by construction. That
is a measurement-design fault, not an Aurora fault.

### 1.6 The exceedance reframing has real headroom

| Approach | AUC | CSI @ nominal | best CSI |
|---|---:|---:|---:|
| raw Aurora concentration | 0.837 | 0.220 | 0.284 |
| Component A concentration | 0.881 | 0.278 | 0.355 |
| **P(event) classifier, out-of-fold** | **0.927** | **0.438** | **0.476** |

And it yields an operating curve the user can choose from: POD 0.70 at FAR 0.40;
POD 0.80 at FAR 0.49.

**Caveat that must travel with these numbers:** pooled and Delhi-dominated (91%
of train events). Per city: Patna best CSI 0.159, Lucknow 0.065.

### 1.7 The benchmark's event mass is Delhi

| City | train events | test events | share of all |
|---|---:|---:|---:|
| delhi | 2,436 | 1,554 | **89.1%** |
| kolkata | 109 | 92 | 4.5% |
| patna | 114 | **5** | 2.7% |
| lucknow | 17 | 19 | 0.8% |
| kanpur | 12 | **2** | 0.3% |
| varanasi | **0** | **0** | **0.0%** |

The L2 "held-out city" result is 92 Kolkata + 2 Kanpur + 0 Varanasi — a Kolkata
finding, not a Gangetic-city finding.

### 1.8 Open data question — Varanasi

Archive mean 29.9 µg/m³, **below Bangalore's 33.3**, with a 4.3% exact-zero rate
(~5× any other city). The four stations are the genuine UPPCB sites (Ardhali
Bazar, BHU, Bhelupur, Maldahiya) at correct coordinates, and the hourly series is
a coherent diurnal curve — so this is **not** a geo-matching failure. Unresolved.
A weak counter-signal: SILAM put Varanasi at 39.2 µg/m³ mean for cycle 20260811,
against archive means of 17.5/17.2 for Jul/Aug 2025.

---

## 2. What Option B is

Keep PM2.5 as the target. Replace the missing physics rather than the variable.

Gangetic winter episodes are **local emissions meeting a collapsed boundary
layer**. The 0.4° pollution checkpoint carries no boundary-layer information at
all, which is consistent with §1.3–1.4. Aurora 1.5 (released July 2026, open
source, +22 variables, hourly, ensemble, 0.25°) adds boundary-layer height,
2 m dew-point, cloud and 10/100 m winds.

Option B = an **exceedance-probability classifier** over:
- boundary-layer meteorology (BLH, dew-point depression, ventilation)
- local observations (persistence, Component A trailing ratio)
- season and lead
- satellite fire counts (FIRMS/VIIRS) — later
- optionally Aurora/CAMS PM2.5 as one input among several

---

## 3. YOUR PRIMARY TASK — the kill-test

**Do not start an Aurora 1.5 rollout.** First answer this, cheaply:

> If we had *perfect* knowledge of boundary-layer height at the target window,
> how much exceedance skill would that buy?

ERA5 is reanalysis: it assimilates observations and is valid *at* the target
window, so it is an **upper bound** on what any forecast of that field could
supply. If perfect-prognosis BLH does not materially improve Very Poor+
discrimination, Aurora 1.5's forecast BLH will improve it less, and **Option B
has no headroom**.

### 3.1 What is already built for you

`src/data/era5_boundary_layer.py` — written and started, may already be complete.

```bash
python -m src.data.era5_boundary_layer --plan          # 7 requests, 84 days
python -m src.data.era5_boundary_layer                 # download + sample
python -m src.data.era5_boundary_layer --sample-only   # re-sample existing files
```

Pulls ERA5 `boundary_layer_height`, `2m_dewpoint_temperature`, `2m_temperature`,
`10m_u/v` over India for **train-period days only**, samples at the 159 registry
stations, and derives `era5_wind`, `era5_ventilation` (BLH × wind) and
`era5_dewpoint_depression`. Output: `data/era5_blh/era5_blh_stations.csv`.

Check whether the download finished. If it failed, the likely cause is a CDS
licence not accepted — log in at `cds.climate.copernicus.eu`, accept the ERA5
single-levels licence, retry.

### 3.2 The experiment

1. Build 24-hour windows exactly as the headline path does:
   ```python
   from src.eval import benchmark as bench, rolling24
   from src.model.anchor import anchor_frame
   frame = anchor_frame(bench.add_climatology(bench.build_frame()))
   windows = rolling24.build_windows(frame, bench.load_obs())
   ```
2. Restrict to `~is_test` and `spatial_tier == "train_pool"`.
3. Join ERA5 features by `(station_id, valid_time)`, **aggregated over the same
   24-hour window** as the target (mean BLH, min BLH, mean ventilation,
   mean dew-point depression). Minimum BLH over the window is likely the
   strongest single feature — episodes are made by the *worst* hour of mixing.
4. Fit `HistGradientBoostingClassifier` on `obs_pm25 >= 121`, out-of-fold by
   `init_date` with `GroupKFold(n_splits=5)`.
5. Compare feature sets, reporting AUC and best CSI:

   | Set | Features |
   |---|---|
   | baseline | persistence, month, lead |
   | current | + aurora_pm2p5, cams_forecast_pm25 |
   | **+ERA5** | + era5_blh_min, era5_blh_mean, era5_ventilation, era5_dewpoint_depression |

6. Report **per city**, not just pooled — the pooled number is 91% Delhi and
   will mislead you.

Helpers already exist in `src/eval/diagnose_events.py`: `auc()`,
`contingency()`, `best_threshold()`. Reuse them; do not rewrite metrics.

### 3.3 Decision rule — write this down BEFORE you look

State the threshold in `docs/` before running step 5, then honour it.

- **Proceed with Option B** if adding ERA5 features lifts out-of-fold AUC by
  **≥0.02** *and* best CSI by **≥0.03** over the `current` set, **and** the gain
  holds in at least one non-Delhi city with ≥50 train events (Patna qualifies at
  114; Lucknow and Kanpur do not).
- **Option B has no headroom** if perfect-prognosis ERA5 adds <0.01 AUC. Say so
  plainly and stop; that is a valuable negative result, not a failure.
- **Ambiguous in between** — report it as ambiguous. Do not round up.

### 3.4 Why this ordering matters

The gain measured here is a **ceiling**. Aurora 1.5's forecast BLH at +48–96 h
will be worse than ERA5's analysed BLH. If the ceiling is low, the achievable
value is lower still. Never present the perfect-prognosis number as achievable
skill; label it `perfect-prognosis` everywhere it appears.

---

## 4. SECONDARY TASKS, in priority order

### 4.1 Keep the SILAM capture alive (time-critical, do this daily)

`src/data/silam_forecast.py` captures the SILAM operational PM2.5 forecast —
the **first incumbent-tier comparator this benchmark has ever contained**.

```bash
python -m src.data.silam_forecast              # today's cycle
python -m src.data.silam_forecast --backfill   # everything still online
```

The public bucket keeps a **rolling ~32-day window**. Uncaptured cycles are lost
permanently. A backfill was started on 2026-08-11; verify it completed and keep
capturing daily.

Known issue to solve before any head-to-head: **SILAM initialises at 00Z, the
Aurora rollout at 12Z.** A naive comparison hands one side a 12-hour information
advantage. Either match init times or account for the offset explicitly.

Also note SILAM is not truth — it put Bangalore at 3.1 µg/m³ mean, which is
implausibly low.

### 4.2 Re-freeze the date schedule onto Gangetic winter

Nothing can be demonstrated in the target cities while they have 5 and 2 test
events (§1.7). Any re-freeze changes `src/splits.py` constants and **must** be
pre-declared and disclosed — the cutoff has already been revised once, and a
second undisclosed change would destroy the pre-registration discipline.

Do not do this silently. Write the design first.

### 4.3 Resolve the Varanasi anomaly (§1.8)

Cross-check against an independent CPCB source. `src/data/ogd_aqi.py` is the
intended instrument; no snapshots exist locally yet. Until resolved, Varanasi
must not appear in any claim.

### 4.4 Verify Aurora 1.5 before assuming it

Confirm from `microsoft.github.io/aurora` and the Aurora 1.5 paper:
- which of the 26 surface variables ship in the **open** checkpoint (BLH
  specifically);
- required inputs — ERA5 or HRES, which variables, what volume;
- whether an air-pollution variant of 1.5 exists, or only weather.

The whole option rests on BLH being in the released checkpoint. **Verify before
building.**

---

## 5. Hard rules — violating these wastes the project

1. **Never score on the test split** while developing. Everything in §3 is
   train-only, out-of-fold. The test set is the only honest evidence left.
2. **Any learned method needs a newly pre-declared validation design**, written
   and committed *before* it touches test data.
3. **Do not tune Component A** against already-viewed test outcomes.
4. **Split constants live only in `src/splits.py`.**
5. **Run `python -m src.eval.audit` before trusting any results table.** Expect
   39 checks: 36 pass, 2 legacy warnings, 1 PM-bin failure. **The PM-bin failure
   must stay visible** — never waive or downgrade it.
6. **Report per-city, always.** Pooled numbers are 89% Delhi.
7. **Verify before asserting.** Multiple confident beliefs in this project have
   been wrong: a "structural data gap" that was a sensor-selection bug; a
   calibrator that looked good on MAE while catching 0 of 99 events; and the
   founding premise that Patna/Varanasi had no forecast (see §7).
8. **Before stopping:** update `docs/HANDOFF.md`, append to `JOURNAL.md`, commit.
9. Do not push, publish, or provision infrastructure without the owner's
   explicit authorisation.

---

## 6. Repository map

| Need | File |
|---|---|
| Canonical brief | `docs/AGENT_BRIEF.md` |
| Current state | `docs/HANDOFF.md` |
| **Why event skill is low** | `docs/EPISODE_SKILL_DIAGNOSIS.md` |
| **Target re-derivation** | `docs/TARGET_REEVALUATION.md` |
| **Options and pros/cons** | `docs/OPTIONS_REVIEW.md` |
| Results | `docs/PRELIMINARY_RESULTS.md` |
| Split constants — only source | `src/splits.py` |
| Diagnostic harness | `src/eval/diagnose_events.py` |
| 24-hour headline evaluator | `src/eval/rolling24.py` |
| Component A anchor | `src/model/anchor.py` |
| Rejected calibrator (keep!) | `src/model/calibrator.py` |
| SILAM incumbent capture | `src/data/silam_forecast.py` |
| ERA5 BLH (kill-test) | `src/data/era5_boundary_layer.py` |
| Integrity audit | `src/eval/audit.py` |
| History and reasoning | `JOURNAL.md` |

Environment: Windows, `.venv/Scripts/python.exe`. Credentials in `.env`
(`OPENAQ_API_KEY`) and `~/.cdsapirc` (one ECMWF token; CDS for ERA5, ADS for
CAMS — different URLs, both already wired).

Verified state: 91/91 tests pass; audit 36 pass / 2 warn / 1 fail; 56-date
rollout complete at 80,136 rows.

---

## 7. Beliefs that turned out to be false — do not reinstate them

- "Patna and Varanasi have no public forecast." **False.** India runs AQEWS
  (WRF-Chem) nationwide at 10 km with 10-day lead, naming Varanasi, Lucknow and
  Patna. The brief's "AQEWS 400 m" is the *Delhi nest*, not the national domain.
  Unresolved conflict: one external source says AQEWS covers only ~8 cities.
  `ews.tropmet.res.in` refused connections; **confirm at the portal.**
- "Aurora adds nothing over persistence." **Too strong.** True for *level*,
  false for *change* (§1.5).
- "Varanasi is a clean city." Unresolved (§1.8) — treat as an open question.
- "The 121 µg/m³ threshold is the problem." **False.** AUC is flat (0.81–0.84)
  across every CPCB band, so discrimination — not the threshold — is binding.

---

## 8. Definition of done for this stint

1. The §3 kill-test is run, with the §3.3 decision rule written down first.
2. Result reported **per city**, labelled `perfect-prognosis`, with an explicit
   proceed / no-headroom / ambiguous verdict.
3. SILAM backfill verified complete and daily capture running.
4. Aurora 1.5's open checkpoint variables verified (§4.4).
5. `docs/HANDOFF.md` updated, `JOURNAL.md` appended, work committed on `master`.

If the kill-test says no headroom, **say so**. A clean negative result here saves
the GPU budget and is the most valuable thing you can produce.
