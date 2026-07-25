# IndiaAQBench — Specification v0.1

An openly reproducible benchmark for multi-day PM2.5 forecasting over Indian
cities, with foundation-model baselines. **Claim discipline:** we do not claim
"first benchmark ever"; we claim that *no widely adopted, openly reproducible
India AQ-forecasting benchmark with fixed public splits, shared code, and
standard baselines currently exists* — the literature is city-fragmented and
method-fragmented (reviews explicitly call for standardized evaluation).

Status: v0.1 (dates/splits provisional until the coverage audit; see §6).
Supersedes the May 2026 scaffold spec (see git history).

---

## 1. Landscape context (verified July 2026)

- India's operational forecasting layer: MoES/IITM **AQEWS** in Delhi
  (WRF-Chem, 400 m, assimilating; Performance Index 87 in Yadav 2025 JGR) and
  AQEWS-like deployments of **varying maturity and resolution** in 7 more
  cities (Mumbai's AIRWISE announced at 2 km; Jaipur described as 400 m).
  Nationally, IMD runs a **SILAM-based forecast driven by WRF meteorology**
  covering ~140 cities incl. Patna/Varanasi/Lucknow — public documents are
  inconsistent on grid spacing (3 km vs 5 km) and we could not verify AOD
  assimilation for the national SILAM product itself.
- In the Yadav 2025 seven-model Delhi eval: global tier PI = 47–60; SILAM 58,
  with "notable discrepancies during high-pollution events".
- Monitoring network (2026 parliamentary answer): **1,601 stations (566
  continuous + 1,035 manual) across 583 cities**; 28 NCAP cities still lack
  continuous stations.
- Aurora (Microsoft, Nature 2025): global air-pollution forecasts at orders of
  magnitude lower compute than operational systems; our Phase 2 confirmed the
  1.3B model runs on a 32 GB CPU (~12 min/step) and inherits CAMS's 2–4x
  underestimation of Delhi's extreme episodes.

**Positioning:** we benchmark the *public/global* tier and test whether cheap
adaptation lifts it into a practically useful band. Beating Delhi's flagship
AQEWS is an explicit non-goal; per-city transparency about where the national
tier is adequate is a goal.

## 2. Task definition

Forecast city-station PM2.5 at lead times **+12 h to +96 h** (12 h steps,
matching the AuroraAirPollution checkpoint), initialized from CAMS global
analysis at 12:00 UTC. Two evaluation targets:

1. **Concentration**: PM2.5 (µg/m³) at each station, at each lead.
2. **Category (headline)**: Indian AQI PM2.5 sub-index bands —
   Good ≤30 · Satisfactory 31–60 · Moderate 61–90 · Poor 91–120 ·
   **Very Poor 121–250** · **Severe >250** (24 h means; hourly comparisons
   reported separately as sensitivity). GRAP-style event = "Very Poor or
   above". Rationale: GRAP actions are invoked in advance on forecast AQI
   stages, so category skill is the actionable quantity.

## 3. Cities and holdout design

| Role | Cities |
|---|---|
| Train/val pool (station-level holdouts within) | Delhi, Mumbai, Chennai, Bangalore, Lucknow, Patna |
| **Held-out cities** (never seen in training) | **Kanpur, Varanasi** (IGP non-metros) + **Kolkata** (eastern metro) |

Two-level spatial validation (required for any adaptation method):
- **L1 — held-out stations** inside training cities (~20% of stations, frozen
  by hash). Tests within-city interpolation.
- **L2 — held-out cities** (all their stations). Tests regional transfer —
  the difference between "good interpolation" and a method.

Temporal validation: strict cutoff (§6); no sample after the cutoff may
influence training, including normalization statistics.

## 4. Metrics

**Headline (per lead time, per city):**
- Category hit rate (6-band accuracy) and adjacent-band accuracy
- Event detection for Very Poor+: POD (hit rate), FAR, missed-event rate,
  critical success index
- Exceedance-probability calibration (Brier score + reliability diagram)
  for probabilistic outputs

**Secondary:** MAE, RMSE, bias, Pearson r, skill vs persistence
(1 − MAE/MAE_persistence).

**Extremes reporting:** all metrics additionally on the obs ≥ 121 µg/m³
subset (the regime where global models fail).

## 5. Baselines (all mandatory in any results table)

1. **Persistence**: obs at init time carried to all leads.
2. **Hourly climatology**: per station × month × hour-of-day (train period only).
3. **Raw CAMS analysis**: the model input at init (the "free" global product).
4. **Raw AuroraAirPollution**: uncalibrated rollout — the foundation-model
   baseline this benchmark exists to measure.
5. (Adaptation ladder, evaluated identically: pooled calibrator; fine-tune.)

## 6. Benchmark period, dates, splits

> **SPLIT REVISION — 2026-07-24, disclosed.** The temporal cutoff moved
> **2025-07-01 → 2025-12-01**, exercising the contingency pre-registered below.
> This happened **once, before any adaptation model was trained on the new
> split**, and must be reported wherever results appear.
>
> *Trigger (pre-registered condition met):* OpenAQ serves essentially no Indian
> station data before ~Feb 2025 — 0–2 stations per city reporting in
> Oct 2024–Jan 2025, verified at sensor level (`src/data/archive_probe.py`;
> location metadata claiming coverage since 2016 is **not** served by the hours
> endpoint for any sensor, old or new). The original cutoff therefore left TRAIN
> as Feb–Jun 2025 only: the calm half of the year, p95 ≈ 142 µg/m³, containing
> **no severe season at all**.
>
> *Observed consequence:* a calibrator fit on that split collapsed the severe
> tail completely — Very Poor+ POD **0.00** at every lead vs raw Aurora's 0.64,
> catching 0 of 99 test events — because it had never seen an extreme value.
>
> *Effect of the revision:* post-monsoon 2025 (Diwali + stubble burning) moves
> into TRAIN; winter 2025-26 stays in TEST, so **both sides contain the severe
> regime**.
>
> | | train obs | train events ≥121 | train p95 | test events ≥121 |
> |---|---|---|---|---|
> | Original (07-01) | 245K | 13,844 | ~142 | 78,569 |
> | **Revised (12-01)** | **507K** | **40,538** | **~360** | **51,875** |
>
> The single source of truth for all split constants is `src/splits.py`.

### 6.1 Frozen dates (coverage audit 2026-07-23; re-run pending post-revision)

- **56 init dates** spanning 2025-02 .. 2026-06, frozen by the coverage audit
  (`src/eval/coverage_audit.py`) over the complete 9-city archive (941,803
  obs rows) and committed as `docs/benchmark_dates.csv`. Balanced 8 per
  (season × split) stratum; every chosen date has ≥5,000 train-pool
  station-hours in its +12..+96h validation window.
- Split rule (frozen before any adaptation training): temporal cutoff at
  **2025-07-01** — train/val strictly before, test strictly after. Test
  contains the full 2025-26 winter (incl. the already-validated 2025-11-15).
- **Documented coverage gap (post-monsoon is test-only).** OpenAQ Indian
  station density in Oct–Nov **2024** is below the usability threshold
  (≥2 stations, ≥40 station-hours in-window) for *every* city, so there are
  **zero post-monsoon train dates**; post-monsoon appears only in the 2025
  test split. This is consequential: post-monsoon (Diwali + stubble burning)
  is north India's peak-pollution season and the primary regime for the
  Very-Poor+ event thesis. We keep it test-only rather than backfill 2023
  (thin OpenAQ depth, larger pull): the adaptation methods must therefore
  **generalize into post-monsoon from other seasons**, making it a genuine
  out-of-distribution seasonal test rather than an interpolation. Reported as
  a headline caveat wherever post-monsoon numbers appear.
- Held-out-city validation is feasible: Kanpur/Varanasi/Kolkata each have
  340–380 usable test dates and 135–167 usable train-period dates (audited for
  feasibility only — they never drive date selection, per §3).

## 7. Data and reproducibility requirements

OpenAQ India data are public "although not in a fully open, transparent
manner" (OpenAQ South Asia landscape) — so reproducibility cannot be a
promise to "use the API". Requirements:

- **Archived raw pulls**: every OpenAQ response used is saved under
  `data/openaq/archive/` (CSV + pull manifest with query params, timestamp,
  row counts) and published with the benchmark (HF dataset).
- **Versioned station registry**: `data/stations.csv` (station_id, name, lat,
  lon, city, sensor ids, first/last seen) — the only station list any code
  may use.
- **Inputs**: CAMS analysis is redistributable per Copernicus licence; we
  publish extraction scripts + date manifests (not the 456 MB/day globals),
  plus the India-region extracts.
- **One-command reproduce** per results table; fixed seeds; environment
  pinned.
- QC (inherited from Phase 1 client): range filter, stuck-sensor detection,
  per-(station, hour) averaging. QC code is part of the benchmark.

## 8. Deployment/communication constraints

Any public forecast built on this is a **research system / transparent second
opinion** — explicitly not an official warning service (Aurora responsible-AI
guidance: not for operational decision-making without expert review).
Corrected maps are "model-derived local estimates with held-out-station
validation", never "field reconstruction". Public artifacts must show a
rolling scorecard vs persistence and the raw model.

## 9. Success criteria

- **S1 (benchmark)**: reproducible harness + all baselines across ~60 dates ×
  9 cities × 8 leads, with the per-city/season/extremes breakdown public.
- **S2 (adaptation)**: pooled calibrator beats persistence AND raw Aurora on
  Very Poor+ POD/FAR at 24–72 h on L1 *and* L2 holdouts.
- **S3 (compute equity)**: fine-tune vs calibrator answered with a cost
  ledger (engineering hours + $ + skill delta), either direction.
- **S4 (stretch)**: category skill at 24–72 h in the band of the published
  global-model tier (PI 47–60 class) at a small fraction of its
  infrastructure cost.
