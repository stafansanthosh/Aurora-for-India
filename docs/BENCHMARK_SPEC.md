# IndiaAQBench — Specification v0.1

An openly reproducible benchmark for multi-day PM2.5 forecasting over Indian
cities, with foundation-model baselines. **Claim discipline:** we do not claim
"first benchmark ever"; we claim that *no widely adopted, openly reproducible
India AQ-forecasting benchmark with fixed public splits, shared code, and
standard baselines currently exists* — the literature is city-fragmented and
method-fragmented (reviews explicitly call for standardized evaluation).

Status: v0.1 (dates and splits frozen; see §6).
Supersedes the May 2026 scaffold spec (see git history).

---

## 1. Landscape context (July 2026, amended 2026-08-12)

- India's operational forecasting layer includes the 400 m Delhi AQEWS nest,
  broader AQEWS/WRF-Chem products described as a 10 km national domain, and an
  IMD **SILAM-based forecast driven by WRF meteorology** associated with a
  roughly 140-city bulletin including Patna/Varanasi/Lucknow. Public documents
  conflict on exact city access, grid spacing, and product maturity; the AQEWS
  portal refused connections during the 2026-08-11 review. Do not convert these
  sources into either “nationwide city service is proven” or “these cities are
  unserved” without direct verification.
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
adaptation lifts its episode skill into a practically useful band. The frozen
nine-city benchmark does not establish an absence-of-service claim or a win
over an Indian incumbent. Beating Delhi's flagship AQEWS is an explicit
non-goal; initialization-aligned incumbent comparison and per-city evidence are
required before a product claim.

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

### 5.1 Particulate-channel integrity decision (2026-08-04)

The completed rollout contains 463 of 80,730 stored rows where Aurora's
independently predicted particulate channels violate nested size-bin ordering.
The integrity audit retains this as a failure. It is not silently repaired,
clipped, or waived.

The PM2.5 benchmark path is nevertheless separable and may be scored because
persistence, CAMS, raw Aurora, and Component A consume only PM2.5; source review
and regression tests verify that PM1 and PM10 cannot influence those methods.
PM1 and PM10 are excluded from the pooled calibrator. Results produced under
this carve-out must disclose the outstanding audit failure and must not imply
that all Aurora output channels passed physical-consistency checks.

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
> into TRAIN; winter 2025-26 stays in TEST, so both sides contain many
> Very-Poor+ observations. The completed archive changed the preliminary
> distribution estimates used when the split was revised:
>
> | Current pre-cutoff population | Rows | Events ≥121 | p95 | p99 |
> |---|---:|---:|---:|---:|
> | All nine-city archive | 824,615 | 68,519 | 163 | 334 |
> | Six-city train pool | 691,327 | 63,188 | 175 | 352 |
> | Calibrator spatial fit pool | 578,113 | 52,024 | 171 | 343 |
>
> The earlier provisional statement that revised-training p95 was about
> 360 µg/m³ was incorrect; that value is much closer to p99. The scientific
> conclusion remains unchanged—the revised fit period contains tens of
> thousands of severe observations—but publications must use the corrected
> percentile label. On the 32 selected training initialization dates, the
> exact scheduled station-time sample before tolerance matching is much
> smaller (about 22,913 rows, 2,513 events, p95 180), which is the relevant
> order of magnitude for fitted forecast pairs.
>
> The single source of truth for all split constants is `src/splits.py`.

### 6.1 Frozen dates (coverage audit completed 2026-07-28)

- **56 initialization dates** spanning 2025-02-19 through 2026-07-17 are frozen
  in `docs/benchmark_dates.csv`: 32 before the cutoff and 24 after it.
- The schedule contains eight dates in each available season × split stratum:
  winter, pre-monsoon, and monsoon on both sides, plus eight post-monsoon 2025
  dates in TRAIN.
- Split rule: train/validation timestamps are strictly before
  **2025-12-01**; test timestamps are on or after it. No later timestamp may
  influence learned parameters, normalization, climatology, or model
  selection.
- **Documented coverage gap: no independent post-monsoon test yet.** The
  post-cutoff archive currently ends in July 2026, before October–November
  2026 exists. Post-monsoon 2025 is therefore represented in fitting but not
  in independent testing. Current results can support winter, pre-monsoon,
  and monsoon test claims; they cannot establish post-monsoon prospective
  performance. A later untouched post-monsoon evaluation or an explicitly
  labeled retrospective seasonal-transfer stress test is required for that
  stronger claim.
- Date selection is driven only by the six-city train pool. Kanpur, Kolkata,
  and Varanasi remain fully held out from ordinary fitting and are scored
  independently; they do not influence which initialization dates are chosen.

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
