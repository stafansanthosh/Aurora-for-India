# Options review — decision support, not a decision

**Date:** 2026-08-11
**Purpose:** cross-check the external scope re-evaluation against verified repo
facts, lay out the options with honest pros and cons, and list what must be read
before choosing. **This document deliberately does not make a recommendation.**

Sources it reconciles:
- external analysis: `compass_artifact_wf-fef813df…` (user-supplied)
- `docs/EPISODE_SKILL_DIAGNOSIS.md` (train-split evidence from this repo)
- `docs/TARGET_REEVALUATION.md` (incumbent landscape)

---

## 1. Cross-check of the external analysis

### 1.1 Materially wrong

**Claim: "Each city has historically had a single CPCB CAAQMS (Patna: IGSC
Planetarium Complex; Varanasi: one station)."**

Verified from `data/stations.csv`:

| City | Stations in registry |
|---|---:|
| Patna | **7** |
| Lucknow | **6** |
| Varanasi | **4** |
| Kanpur | **3** |

Patna's are IGSC Planetarium, DRM Office Danapur, Rajbansi Nagar, Govt. High
School Shikarpur, Industrial Area Hajipur, Muradpur and Samanpura. The
"1–2 stations per city" premise is wrong by a factor of 3–7, and the document's
kill criterion built on it ("if the 1–2 stations per city have <60–80% valid
winter days") does not apply as written.

**But the conclusion partly survives for a different reason.** Verification is
thin — not in *stations* but in *events*:

| City | Very Poor+ 24h windows, train | test |
|---|---:|---:|
| Patna | 114 | **5** |
| Lucknow | 17 | 19 |
| Kanpur | 12 | **2** |
| Varanasi | **0** | **0** |

This matters because the two diagnoses imply different fixes. If the problem
were station count, nothing could fix it. Because the problem is event count and
season coverage, it is fixable by re-freezing dates onto Gangetic winter — and
by resolving the Varanasi data anomaly (§1.3).

### 1.2 Unresolved conflict — the most decision-relevant open question

**External analysis:** AQEWS covers ~8 cities (Delhi, Mumbai, Pune, Ahmedabad,
Kolkata, Hyderabad, Bengaluru, Jaipur); NCAP's ~131 non-attainment cities are
not served by forecasts.

**This repo's research (`TARGET_REEVALUATION.md`):** AQEWS provides forecasts
for "entire India" at 10 km with 10-day lead, explicitly naming Varanasi,
Lucknow, Patna and Kolkata among covered non-attainment cities.

Both may be true in different senses — a nationwide 10 km gridded field versus
dedicated city-level public products for eight cities. **The distinction decides
whether Patna/Varanasi are "unforecast" or "forecast badly", which is the whole
premise.** `ews.tropmet.res.in` refused connections from this machine, so
neither claim was confirmed at the source.

### 1.3 An open question the external analysis did not have

Varanasi's archive mean PM2.5 is **29.9 µg/m³ — below Bangalore's 33.3** — with
a 4.3% exact-zero rate (~5× any other city) and zero Very Poor+ windows in
1,516. The four stations are the genuine UPPCB sites at correct coordinates and
the diurnal curve is coherent, so this is not a geo-matching failure. It is
unresolved and it affects any Varanasi claim under any option.

### 1.4 Verified correct

- **MAUSAM** (Gupta, Sheshadri & Suri; arXiv:2509.01879; *JAMES* 2026) is real.
  The "15–45% larger errors against observations than against reanalysis"
  finding is quoted accurately, and its conclusion that reanalysis-centric
  benchmarks overstate skill is directly relevant. AIFS is reported most
  consistent, with GraphCast and GenCast strong; Aurora is **not** named in that
  top group. *The specific claim that Aurora showed "among the largest regional
  errors" could not be confirmed from the abstract — plausible, unverified.*
- **Aurora 1.5** is real: released July 2026, open source, +22 variables, native
  hourly resolution, ensemble with a CRPS objective, 0.25°. Boundary-layer
  height and 2 m dew-point are among the added variables.
- **CEEW's Delhi evaluation** (83/92 very-poor episodes in winter 2023-24;
  54/58 in 2024-25) matches independent sources.
- **0.4° ≈ 44 km, trained on CAMS analysis.** Consistent with this repo's own
  finding that Aurora's maximum output is 196 µg/m³ against observations
  reaching 572 — it inherited CAMS's compression of the severe tail.

### 1.5 A tension worth resolving before choosing

CEEW reports Delhi's AQEWS catching ~90% of very-poor episodes. That is the
**opposite** of "existing systems score poorly." If the 2025 paper motivating
this project shows weak incumbent performance, it is likely either (a) about
*global* models — Yadav et al. 2025 found IFS/GEOS-FP underperform on local
pollution events while WRF-Chem does well — or (b) about non-Delhi cities, where
no equivalent published evaluation was found. **Locating that paper precisely
matters: it is the evidentiary basis for the entire premise.**

---

## 2. The option the external analysis did not rank

It treats Aurora 1.5 as the reason to pivot *to fog*. But boundary-layer height
is exactly the variable `EPISODE_SKILL_DIAGNOSIS.md` §5.3 identified as missing
from the PM2.5 path — Gangetic winter episodes are emissions meeting a collapsed
boundary layer, and the 0.4° pollution checkpoint carries no BLH at all.

So there is a fourth option that is neither the criticised status quo nor a
pivot away from PM2.5: **use Aurora 1.5 meteorology as features in a PM2.5
exceedance classifier** — 0.25° instead of 0.4°, hourly instead of 12-hourly,
with BLH + dew-point + wind + cloud, combined with local observations and
satellite fire counts. This drops the CAMS-reproducing pollution checkpoint
(and its inherited low bias) while keeping the target variable.

---

## 3. Options, with pros and cons

### Option A — Winter fog / low-visibility, IGP tier-2 hubs

*The external analysis's #1.*

**Pros**
- Ground truth is genuinely excellent: hourly METAR visibility, free, objective,
  multi-year, at exactly the target airports (VILK, VEBN, VEPT, VIAR…).
- Aurora 1.5 outputs the right physical fields, and fog is meteorology-driven —
  matching this repo's finding that Aurora is a *transport/meteorology*
  instrument, not an emissions one.
- Plausibly a real gap: dedicated fog forecasting appears to be a Delhi-IGI
  product.
- Enormous real-world stakes (rail, road, aviation).
- Verification is not event-starved the way PM2.5 is here.

**Cons**
- **Discards nearly all existing work.** The registry, OpenAQ archive, CAMS
  archives, evaluator, event metrics, Component A, the 56-date rollout — almost
  none transfers to a visibility target.
- Aurora has **no visibility output**; a derived index is a modelling assumption
  that may simply not work. This is a research risk, not an engineering task.
- MAUSAM suggests Aurora's meteorology over India is weaker than peers — and
  fog depends entirely on that meteorology being right.
- IMD's Delhi fog product already reports POD 0.73–0.92 / CSI 0.54–0.68, so the
  bar at the one place with a published baseline is high.
- Fog is a shallow, sub-grid, radiation-and-microphysics phenomenon; 28 km may
  be as badly mismatched to fog as 44 km is to urban PM2.5. The document does
  not establish that it isn't.

### Option B — PM2.5 exceedance with Aurora 1.5 meteorology + local + fire

*Not ranked by the external analysis.*

**Pros**
- Keeps the target variable, the cities, and essentially all existing
  infrastructure.
- Directly attacks the diagnosed cause: adds BLH, the missing variable.
- Escapes the CAMS-reproducing pollution checkpoint and its low bias — you would
  use Aurora 1.5 as a *weather* model, which is what it is good at.
- The exceedance-probability reframing already shows a large train-split ceiling
  gain (AUC 0.927, best CSI 0.476 vs raw Aurora 0.284).
- 0.25° and hourly is strictly better resolved than the current 0.4°/12-hourly.

**Cons**
- Still 28 km against an incumbent at 10 km with chemistry, emissions and data
  assimilation.
- Requires re-running the entire rollout with a different checkpoint and
  different inputs (ERA5/HRES rather than CAMS analysis) — real GPU and download
  cost, contradicting "no more GPU compute needed".
- Does not fix the event-scarcity problem on its own; still needs a re-frozen
  winter-weighted date schedule.
- Unproven: no evidence yet that BLH closes the gap.

### Option C — PM2.5 bias correction / downscaling, framed as fixing CAMS

*The external analysis's #2.*

**Pros**
- Honest about the coarse grid; turns the CAMS low bias into the contribution
  rather than a fatal flaw.
- Cheapest path — reuses everything and needs no new inference.
- This repo has already shown the effect is large: CAMS POD 0.154 → Component A
  0.582.
- Extends naturally to anywhere served only by the global tier.

**Cons**
- Least ambitious; reads as a post-processing paper rather than a forecasting
  system.
- Does not beat the Indian operational incumbent, and probably cannot.
- Value depends on how many places genuinely have only the global tier — an
  unresolved question (§1.2).

### Option D — Wet-bulb / humid-heat, interior tier-2 towns

*The external analysis's #3.*

**Pros**
- Aurora 1.5's 2 m T + dew-point are directly the required inputs — no derived
  index assumption.
- Health relevance is high and rising; humid-heat is a recognised gap.
- IMD station data provides verification.

**Cons**
- Weakest evidence base of the four; the document itself ranks it tertiary.
- IMD already issues heatwave warnings at 24–72 h.
- Discards all existing work, like Option A.
- Temperature is the variable AI models are *best* at, so the incumbent bar
  (plain NWP) is high and the headroom small.

---

## 4. What is common to every option

Two things must be settled regardless of choice:

1. **Validate against observations, not reanalysis.** MAUSAM's 15–45% finding
   says reanalysis-centric benchmarks overstate skill. This repo already does
   the right thing (OpenAQ verification) and should keep doing it.
2. **Event scarcity is a design problem, not a data problem.** Whatever the
   target, the frozen schedule must contain enough events in the target
   locations to score. The current one does not (89% of events are Delhi).

---

## 5. Reading list, ordered by how much it changes the decision

### Tier 1 — resolves the premise. Read before choosing.

1. **The 2025 paper showing incumbents scoring poorly** — locate it precisely
   (§1.5). If it is Delhi-only or about global models, the premise needs
   restating.
2. **CEEW, "How Well Can Delhi Predict Air Quality?" (1 Oct 2025)** —
   `ceew.in/publications/designing-effective-air-quality-decision-support-and-pollution-warning-alert-systems`.
   The strongest published incumbent-performance number; establishes the bar.
3. **`ews.tropmet.res.in` directly** — settle whether Patna/Varanasi receive a
   public AQEWS product or only sit inside a national grid (§1.2).
4. **Yadav et al. 2025**, *JGR Atmospheres*, `10.1029/2025JD043719` — regional
   vs global model comparison over Delhi; note it is Delhi-only.

### Tier 2 — establishes whether Aurora can do the job

5. **MAUSAM** — arXiv:2509.01879 / *JAMES* 2026,
   `10.1029/2025MS005568`. Read the Aurora-specific regional results; the
   headline claim about Aurora's ranking is unverified here.
6. **Aurora 1.5 paper** —
   `microsoft.com/en-us/research/wp-content/uploads/2026/07/Aurora_1_5_Paper.pdf`.
   Confirm which of the 26 surface variables are released in the open
   checkpoint, and the BLH verification scores specifically.
7. **Bodnar et al., *Nature* (2025)** — the original Aurora paper. Note that the
   air-pollution results are scored against **CAMS analysis, not observations**.

### Tier 3 — needed only for specific options

8. **IMD fog verification literature** (Delhi IGI POD/CSI/FAR) — only if
   Option A. Establishes the bar and whether tier-2 hubs are truly unserved.
9. **Kumar et al., *Sci. Rep.* 2020** (WRF-Chem IGP NMB 21–35%, Kanpur 59%) —
   quantifies the incumbent's own bias; relevant to B and C.
10. **ACAG/van Donkelaar V5.GL.04 and Dey et al. 1 km daily India** — only if
    Option C uses satellite AOD as a spatial covariate.
11. **Iowa State ASOS/METAR archive and OGIMET** — only if Option A; check
    winter missing-hour rates for VILK/VEBN/VEPT before committing.

---

## 6. Questions only you can answer

1. Is the deliverable a **research benchmark** or a **public service**? Option A
   is a stronger benchmark; Option C is a more shippable service.
2. How much of the existing infrastructure are you willing to write off? A and D
   discard most of it; B and C keep nearly all.
3. Is "underserved" defined by **absence** of a forecast or by **poor episode
   skill** of an existing one? Your last message says the latter — which argues
   against A and D, since both are justified partly by absence.
4. Is more GPU spend acceptable? B requires a full re-rollout on a different
   checkpoint.
