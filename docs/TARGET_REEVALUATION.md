# Re-evaluating the target: is Patna/Varanasi the right problem?

**Date:** 2026-08-11
**Status:** strategic review. Changes no scientific result and certifies nothing.
**Trigger:** `docs/EPISODE_SKILL_DIAGNOSIS.md` established what Aurora is and is
not good at. That makes the choice of target a decision to re-derive rather than
inherit.

---

## 0. The headline

**The founding premise is false.** Patna, Varanasi, Lucknow and Kanpur are not
unserved by public air-quality forecasting. India runs a nationwide
chemistry-transport forecast at **10 km with 10-day lead** that explicitly names
these cities, plus a 5 km/3-day alternative, plus a public multi-city bulletin.

IndiaAQBench runs Aurora at **0.4° ≈ 44 km with no chemistry and no emissions
inventory** — four times coarser than the incumbent, in the incumbent's own
cities. That is not a winnable framing, and it is not the framing that the
evidence supports.

**However**, the diagnosis also found a real and defensible gap, which is
different from the one the project assumed. It is set out in §3.

---

## 1. What was verified about the incumbent

| System | Operator | Resolution | Lead | Coverage |
|---|---|---|---:|---|
| AQEWS (WRF-Chem) | IITM/IMD/NCAR | **10 km** | **10 days** | **All India**, naming Varanasi, Lucknow, Patna, Kolkata among non-attainment cities |
| AQEWS Delhi nest | IITM | 400 m | 3 days | NCR-Delhi only |
| IMD-SILAM | IMD/FMI | 5 km | 3 days | Regional + Delhi street level |
| IMD city bulletin | IMD | — | — | ~140 Indian cities |
| SAFAR | IITM/IMD | — | 1–3 days | Delhi, Pune, Mumbai, Ahmedabad |

The project brief recorded "Delhi has AQEWS (WRF-Chem 400 m, PI 87)" and
concluded the rest of India was unserved. **The 400 m figure is the Delhi nest.
The national domain is 10 km and it covers the target cities.** That single
misreading is what made Patna/Varanasi look like a gap.

**Verification caveat:** `ews.tropmet.res.in` refused connections from this
machine, so the city list comes from IMD/IITM secondary documentation and search
results rather than the portal itself. Confirm directly before acting — but the
10 km national domain is stated consistently across independent sources.

---

## 2. What Aurora is actually good at

From `python -m src.eval.diagnose_events` and the threshold sweep, train split:

**Good at:**
- **Long lead.** Persistence dominates at 0–36 h, but Aurora overtakes it at
  +48–72 h. Winter +72 h: Aurora AUC 0.923 vs persistence 0.808.
- **Change, not level.** The Aurora-minus-persistence signal predicts a >25%
  deterioration with **AUC 0.764**. Aurora's *level* alone gives only 0.656.
  This is the single most encouraging result in the project and the benchmark
  was not measuring it.
- **Meteorology-driven regimes.** Pre-monsoon (transport/dust season) Aurora
  beats persistence at every lead ≥12 h.

**Bad at:**
- Absolute concentration at a station (dynamic range capped at 196 µg/m³ against
  observations reaching 572).
- Short lead — persistence wins outright.
- Monsoon — AUC collapses to 0.54–0.66.
- Emission-dominated urban winter inversion, which is exactly the
  Patna/Varanasi/Kanpur regime.

**Implication.** Aurora is a *meteorological transport* instrument. It should be
pointed at pollution that is transported, on multi-day timescales — not at
pollution that is locally emitted under a stagnant boundary layer.

---

## 3. The real gap is not "no forecast" — it is "only the global tier"

Essentially everywhere on earth now has *some* public forecast, because the
global tier (CAMS, SILAM, and the aggregators built on them) covers the planet.
So "this city has no forecast" is almost never literally true, including in
Africa and Central Asia.

But this repository already measured how good the global tier is at the thing
that matters, and the answer is: **poor.**

| Method (24-h headline, pooled test) | POD | FAR | CSI |
|---|---:|---:|---:|
| Actual CAMS forecast | 0.154 | 0.911 | 0.060 |
| Raw Aurora | 0.471 | 0.672 | 0.239 |
| Component A (trivial local anchoring) | 0.582 | 0.441 | 0.399 |

CAMS — the forecast that most of the world actually gets — detects **15% of
Very Poor+ episodes with a 91% false-alarm ratio**. A crude per-station
trailing-ratio anchor lifts that to POD 0.582 / CSI 0.399.

**That is the defensible thesis, and the project has already generated the
evidence for it:**

> Most of the world is served only by a global forecast that is close to useless
> for episode warning. Cheap local anchoring against a handful of public
> monitors makes it materially useful. This is demonstrable, low-compute, and
> deployable wherever a few monitors exist.

Note this thesis does not require Aurora to win. Aurora becomes an *upgrade to
test* rather than a prerequisite.

---

## 4. Where verification data actually exists

Probed live against OpenAQ v3 (active = reporting since 2026-06-01):

| Country | active PM2.5 monitors | regime | national CTM forecast? |
|---|---:|---|---|
| India | 571 | urban inversion + transport | **yes — 10 km, 10 day** |
| Thailand | 381 | **biomass-burning haze** | partial |
| Pakistan | 332 | urban inversion + crop burning | monitoring yes; **no national multi-day model found** |
| Kazakhstan | 164 | winter coal/inversion | none found |
| South Africa | 117 | industrial/domestic | none found |
| Nepal | 77 | valley inversion + transport | none found (global tier only) |
| Ghana | 74 | **Harmattan dust** | none found |
| Philippines | 74 | urban | none found |
| Nigeria | 66 | **Harmattan dust** + urban | none found |
| Uganda | 45 | urban/biomass | none found |
| Senegal | 34 | **Saharan dust** | research-grade only (Dakar) |

The structural tension: **where forecasts are most absent, monitors are also
most absent.** Sub-Saharan Africa averages one ground monitor per 15.9 million
people. A benchmark needs verification data, so the frontier is the set of
places with *enough* monitors and *only* the global tier.

---

## 5. Candidate targets, ranked by fit to the evidence

Scored on: regime matches Aurora's strength (transport, multi-day) × verification
data exists × genuinely served only by the global tier.

### Tier 1 — strong fit

**(a) West African Harmattan dust — Ghana, Senegal, Nigeria, Burkina Faso.**
Dec–Feb Saharan dust transport is synoptic-scale, multi-day, and almost purely
meteorological — the one regime where a 0.4° global model is *not*
under-resolved, because the phenomenon itself is continental. Aurora's air
pollution head models dust directly. ~174 active monitors across the three
countries. No national forecast systems found; WMO's PREFIA programme exists
precisely because the capability is missing. **Highest strategic upside.**

**(b) Mainland SE Asia biomass-burning haze — northern Thailand, Laos, Myanmar
border.** Feb–April. Source is satellite-observable in near-real time (FIRMS /
VIIRS fire radiative power), transport is meteorological. Thailand has 381
active monitors — better verification data than the current Indian benchmark's
159 stations. This directly implements §5.3(a) of the diagnosis: give Aurora the
source term it lacks and let it do the transport.

### Tier 2 — good data, worse regime fit

**(c) Pakistan (Lahore/Punjab).** 332 active monitors, extreme severity, and no
national multi-day forecast model found — Punjab EPA publishes real-time AQI
across 41 stations but monitoring is not forecasting. **But the regime is winter
inversion plus crop burning — the same emission-dominated physics where §2 says
Aurora is weakest.** High need, poor tool match. Worth a cheap CAMS-anchoring
test (§6) before any Aurora work.

**(d) Nepal (Kathmandu valley).** 77 monitors, global tier only. Valley
topography at 0.4° is hopeless for Aurora, but the anchoring thesis (§3) does
not depend on resolution.

### Rejected

- **Continuing with Patna/Varanasi as an unserved-city claim.** Falsified by §1.
- **Central Asia winter coal.** Emission-dominated; same mismatch as (c) without
  the severity.
- **Anywhere with <30 active monitors.** Cannot verify, so cannot benchmark.

---

## 6. The next experiment does not need Aurora, or a GPU

The thesis in §3 is testable with **no new inference at all**, using code that
already exists (`src/data/cams_forecast.py`, `src/model/anchor.py`,
`src/eval/rolling24.py`, `src/eval/benchmark.py`):

1. Pull OpenAQ PM2.5 for one Tier-1 candidate region and its episode season.
2. Pull the matching **actual CAMS forecast** archive (already implemented).
3. Score CAMS event skill, then Component-A-anchored CAMS event skill.
4. If anchoring lifts CAMS the way it did in India (POD 0.154 → ~0.58), the
   product thesis holds **and is independent of Aurora**.
5. Only then ask whether Aurora beats anchored CAMS — a clean, well-posed
   question with a real incumbent to beat.

Cost: CAMS downloads and CPU. No GPU, no A100, no rollout.

This also inverts the project's risk. Today, everything depends on Aurora being
good. Under this plan the product works even if Aurora never does, and Aurora
gets a fair, falsifiable test against a baseline that matters.

---

## 7. What remains valuable from the work so far

Nothing here wastes the last several months. What transfers:

- the station registry, resumable archive puller, and QC path;
- the strict evaluator, event metrics, 24-hour headline path, and 39-check audit;
- Component A, which is the *method* the new thesis is built on;
- the rejected calibrator, which is now understood at the level of the loss
  function rather than the model family;
- **Delhi as a development environment.** It has 89% of the events and is where
  a method can actually be built and debugged. The brief always said Delhi was a
  diagnostic instrument; §4 says that is now its main job.

What does not transfer is the claim that this serves cities with no forecast.

---

## 8. Open questions before committing

1. Confirm the AQEWS city list directly at `ews.tropmet.res.in` (unreachable
   from this machine).
2. Settle the Varanasi data anomaly (`EPISODE_SKILL_DIAGNOSIS.md` §4) — it
   affects whether the existing archive can be trusted at all.
3. Check licensing and OpenAQ provider terms for any new country before pulling.
4. Decide whether the deliverable is a *public forecast* or an *independent
   verification of existing forecasts*. The second is cheaper, is not currently
   done for non-Delhi India, and the repository is already most of the way there.
