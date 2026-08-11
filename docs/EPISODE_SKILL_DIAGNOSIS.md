# Why event skill is low, and what would actually fix it

**Date:** 2026-08-11
**Reproduce:** `python -m src.eval.diagnose_events`
**Split discipline:** every method-performance number below is **train split,
train_pool tier, out-of-fold by init date**. No test row was scored. The
classifier section is a *ceiling estimate* used to justify a predeclared
design; it is **not a validated result** and must be re-earned on test.

Event counts per city and split (§4) are sample support, which the repository
already publishes, not method performance.

---

## Summary

1. The calibrator did not fail because of a bad model choice. It failed because
   **minimizing a concentration loss and detecting threshold exceedance are
   mathematically opposed.** Any concentration regressor will reproduce it.
2. Calibration is still right for **level**, and Component A does that job. It
   is the **wrong lever for event skill**, because the binding constraint is
   discrimination, not scale.
3. Aurora's discrimination is real but modest, is **largely between-city rather
   than within-station**, and **does not clearly beat persistence**.
4. The benchmark **cannot currently answer the project's question**: 89% of all
   Very Poor+ events are Delhi, and Varanasi has **zero** events in 1,516
   windows.
5. The promising direction is to **predict exceedance probability directly** and
   publish an operating point, not to predict µg/m³ and threshold it.

---

## 1. Why the calibrator failed — the real mechanism

The documented explanation was "trees cannot extrapolate beyond their training
targets." True, but incomplete, and the incomplete version invites the wrong
fix (swap the model family, add features).

The deeper reason is a property of the **loss**, not the model. A regressor
trained to minimize MAE or MSE predicts approximately the conditional
median/mean. For a heavy-tailed variable, the conditional mean sits far below
the upper tail. So the MAE-optimal prediction lands **below 121 µg/m³ even when
the probability of exceeding 121 is high**.

Improving MAE and destroying POD are therefore **the same act**, not a
trade-off that tuning can resolve. That is exactly the observed signature:

| Scope | MAE | POD |
|---|---|---|
| L1 raw → calibrated | 33.9 → 24.5 | 0.474 → 0.125 |
| L2 raw → calibrated | 34.2 → 20.2 | 0.748 → 0.299 |

**Consequence:** no concentration-regression calibrator should be attempted
again — not with a neural net, not with more features, not with quantile
targets bolted on afterwards. The pipeline shape "predict µg/m³ → compare to
121" is the defect.

### How much can re-thresholding alone win?

Sweeping the decision threshold over raw Aurora on train data:

| Method | AUC | CSI @121 | best CSI | at threshold |
|---|---:|---:|---:|---:|
| raw Aurora | 0.835 | 0.220 | 0.284 | 105.2 |
| Component A | 0.878 | 0.277 | 0.355 | 105.2 |
| persistence | 0.884 | 0.251 | 0.376 | 83.8 |
| CAMS forecast | 0.716 | 0.037 | 0.194 | 49.8 |

**`best CSI` is the ceiling for any concentration post-processor.** Even a
perfectly recalibrated Aurora tops out near CSI 0.28. That is the honest
ceiling of the current approach.

---

## 2. Aurora's dynamic range is a hard physical cap

Across 20,008 train windows:

| City | obs max | Aurora max | obs ≥121 | Aurora ≥121 | obs ≥250 | Aurora ≥250 |
|---|---:|---:|---:|---:|---:|---:|
| delhi | 376.0 | 196.1 | 1,998 | 959 | 281 | **0** |
| patna | 228.0 | 156.3 | 114 | 114 | 0 | 0 |
| lucknow | 197.4 | 107.6 | 16 | **0** | 0 | 0 |
| mumbai | 369.8 | 118.4 | 66 | **0** | 2 | 0 |
| chennai | 571.8 | 53.2 | 5 | 0 | 5 | 0 |

Aurora never emits a value ≥250 µg/m³ anywhere in the benchmark, while
observations do so 281 times in Delhi alone. In Lucknow and Mumbai it never
reaches 121 at all.

**Where Aurora's maximum sits below a category boundary, POD in that category
is capped at zero by construction.** A multiplier (Component A) lifts the level
and genuinely helps, but it cannot repair rank ordering — and rank ordering is
what the ceiling in §1 measures.

---

## 3. The skill is between cities, not within a station

Pooled AUC rewards a model for knowing "Delhi is dirty, Bangalore is clean."
GRAP needs the opposite: *for this station, will this window exceed?* Removing
each station's own mean level:

| Method | AUC pooled | AUC within-station | drop |
|---|---:|---:|---:|
| raw Aurora | 0.835 | 0.710 | −0.125 |
| Component A | 0.878 | 0.785 | −0.093 |
| persistence | 0.884 | 0.808 | −0.075 |
| CAMS forecast | 0.716 | 0.434 | −0.281 |

Per city, on the cities that matter:

| City | n | events | base rate | AUC | best CSI |
|---|---:|---:|---:|---:|---:|
| delhi | 8,880 | 1,998 | 22.50% | 0.767 | 0.337 |
| patna | 1,469 | 114 | 7.76% | **0.640** | 0.115 |
| lucknow | 1,088 | 16 | 1.47% | 0.722 | 0.048 |
| mumbai | 5,391 | 66 | 1.22% | **0.422** | 0.036 |

In Patna — an actual target city — Aurora's AUC is 0.640. In Mumbai it is 0.422,
**worse than a coin flip**. The pooled 0.835 is substantially the Delhi/not-Delhi
contrast.

### Does Aurora beat persistence?

Out-of-fold ablation, train split:

| Feature set | AUC | best CSI |
|---|---:|---:|
| persistence + month + lead | 0.908 | **0.480** |
| Aurora + month + lead | 0.880 | 0.409 |
| persistence + Aurora + month + lead | 0.919 | 0.469 |
| all features | **0.927** | 0.476 |

Adding Aurora to persistence raises AUC by 0.011 and **lowers** best CSI.
Per lead, persistence-only equalled or beat persistence+Aurora at 5 of 7 window
starts; Aurora contributed positively only at +48 h and +60 h.

**On this benchmark, Aurora is not yet earning its place over "yesterday's
reading plus the month."** That is a negative result and it should be published
as one.

---

## 4. The benchmark cannot answer the project's question

Observed Very Poor+ 24-hour windows, counts only:

| City | train ev | train n | test ev | test n | share of all events |
|---|---:|---:|---:|---:|---:|
| delhi | 2,436 | 10,499 | 1,554 | 9,745 | **89.1%** |
| kolkata | 109 | 2,940 | 92 | 2,308 | 4.5% |
| patna | 114 | 1,469 | **5** | 1,183 | 2.7% |
| mumbai | 78 | 6,630 | 11 | 5,115 | 2.0% |
| lucknow | 17 | 1,304 | 19 | 1,008 | 0.8% |
| kanpur | 12 | 648 | **2** | 507 | 0.3% |
| varanasi | **0** | 848 | **0** | 668 | **0.0%** |

Three consequences:

1. **The pooled headline is a Delhi result.** Delhi is explicitly not the target.
2. **The L2 "held-out-city transfer" result is a Kolkata result.** Its 94 events
   are 92 Kolkata + 2 Kanpur + 0 Varanasi. Kolkata is a coastal megacity, not an
   underserved Gangetic city. The L2 POD 0.798 → 0.755 finding says nothing
   about Patna or Varanasi.
3. **Varanasi — the product's default landing city — has no episodes at all to
   evaluate against.**

### A data red flag that must be resolved before any Varanasi claim

Varanasi's archive mean PM2.5 is **29.9 µg/m³**, *below Bangalore's 33.3*, with
monthly means of 47.7 (Jan), 57.6 (Dec), 55.5 (Nov). It also has a **4.3%
exact-zero rate, roughly five times any other city**.

What has been checked: the four stations are the genuine UPPCB sites (Ardhali
Bazar, BHU, Bhelupur, Maldahiya) at correct coordinates, and the hourly series
is a coherent diurnal curve, not noise. So this is **not** an obvious
geo-matching or corruption failure of the kind previously found.

It is nonetheless not plausible on its face that Varanasi is cleaner than
Bangalore. This is an **open data question**, not a proven bug, and it must be
settled against an independent CPCB/UPPCB source before Varanasi appears in any
public claim. The bounded OGD pilot (`src/data/ogd_aqi.py`) is the intended
cross-check; no snapshots exist locally yet.

Either way the operational consequence is unchanged: **the benchmark contains
no Varanasi episodes, so it cannot support a Varanasi episode-forecasting
claim.**

---

## 5. What would actually work

### 5.1 Change the prediction target

Stop predicting µg/m³ and thresholding. Predict **P(24-hour mean ≥ 121)**
directly and publish a chosen operating point.

Ceiling estimate, out-of-fold on train:

| Approach | AUC | CSI at nominal | best CSI |
|---|---:|---:|---:|
| raw Aurora concentration | 0.837 | 0.220 | 0.284 |
| Component A concentration | 0.881 | 0.278 | 0.355 |
| **P(event) classifier** | **0.927** | **0.438** | **0.476** |

This sidesteps the §1 failure completely: there is no magnitude to shrink and no
training-distribution ceiling. The decision threshold becomes an explicit policy
choice rather than an artifact of a loss function:

| If you want POD ≥ | POD | FAR | CSI | alerts per 1,000 windows |
|---|---:|---:|---:|---:|
| 50% | 0.503 | 0.294 | 0.416 | 82 |
| 60% | 0.606 | 0.336 | 0.464 | 104 |
| 70% | 0.701 | 0.402 | 0.476 | 134 |
| 80% | 0.803 | 0.489 | 0.454 | 180 |
| 90% | 0.900 | 0.622 | 0.363 | 273 |

A public-health user can pick "catch 80% of episodes, accept one false alarm in
two." A fixed 121 µg/m³ cut offers no such control.

**Caveat that must travel with these numbers:** they are pooled and therefore
dominated by Delhi (91% of train events). Per city they are far weaker — Patna
best CSI 0.159, Lucknow 0.065. They justify a design; they do not justify a
claim.

### 5.2 Fix the evaluation before fixing the model

No method can be shown to work where it matters while target-city episodes are
absent. Required before further modelling:

1. Re-freeze the date schedule to **oversample Gangetic winter (Nov–Jan)** for
   Patna, Kanpur, Lucknow, Varanasi. December currently contributes 535 windows
   in total across all nine cities.
2. Settle the Varanasi level question against an independent source.
3. Report **per-target-city** event skill as the headline. Retire the pooled
   number, or label it explicitly as a Delhi diagnostic.
4. Re-examine whether Kolkata should carry the L2 conclusion alone.

### 5.3 Reconsider what Aurora is for

Aurora is a **meteorological** foundation model. Gangetic winter episodes are
driven by local and regional **emissions** — crop-residue burning, biomass
combustion, traffic, brick kilns — interacting with boundary-layer collapse.
At 0.4° with no emissions inputs, Aurora can see the ventilation half of that
and essentially none of the source half. §3 is consistent with that: it tracks
seasonal and city-scale contrasts, and struggles with the station-level,
day-to-day anomaly.

Three honest options:

- **(a) Give Aurora what it lacks.** Add fire radiative power (FIRMS/VIIRS),
  boundary-layer height, and ventilation coefficient as classifier features.
  Cheap, testable, no GPU.
- **(b) Demote Aurora to one input among several** in an exceedance classifier
  that leans on local observations, and require it to earn inclusion by
  ablation. Current evidence supports this.
- **(c) Accept that the shippable product is a statistical 24–72 h exceedance
  nowcast** built on local monitors + met + season, with Aurora optional.

Fine-tuning Aurora remains the **wrong next step**: it is expensive, and §2–§3
say the limiting factor is missing source information and station-scale
representativeness, neither of which fine-tuning on 32 dates supplies.

### 5.4 What can honestly be shipped

The target cities are **monitored but unforecast** — Patna 7 stations,
Lucknow 6, Varanasi 4, Kanpur 3. "Underserved" here means no forecast, not no
data. Local observations are therefore available operationally, which makes a
persistence-anchored exceedance classifier deployable today and makes
"zero-shot transfer to unmonitored cities" a separate, harder tier that current
evidence does not support.

A defensible first release:

> An experimental 24–72 hour **probability** of Very Poor+ PM2.5 for monitored
> Indian cities without a public forecast, published with its operating point,
> its verified hit/miss record, and the explicit statement that skill is
> currently demonstrated mainly in Delhi.

That is shippable, honest, and useful. Claiming Patna or Varanasi skill is not
supported by anything currently in this repository.

---

## 6. What this does not establish

- No test-split evidence was generated. Every number here is train-split.
- The classifier ceiling is pooled and Delhi-dominated; per-target-city skill
  remains poor and unproven.
- The Varanasi level question is open, not settled.
- Nothing here certifies Component A, which remains uncertified with raw Aurora
  as the public fallback.
- Any learned method built on §5.1 requires a **newly predeclared validation
  design** written before it is scored on test.
