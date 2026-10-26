# Field review: what an expert would do next

**Date:** 2026-10-26
**Status:** strategic review grounded in external literature and incumbent
documentation. Changes no scientific result and certifies nothing. External
claims are cited; where a source is secondary or a number could not be checked,
that is said explicitly.

---

## 1. The problem, restated

People in the Indo-Gangetic Plain (Delhi, Lucknow, Kanpur, Varanasi, Patna and
their neighbours) live through multi-day **Very Poor+ PM2.5 episodes** every
winter. The useful protective actions all need warning **one to three days
ahead, by category**:

- regulatory restrictions (GRAP in Delhi-NCR; on paper, an Emergency Response
  System or GRAP-like plan in every NCAP non-attainment city);
- school, hospital, and outdoor-work decisions;
- individual exposure reduction by vulnerable people.

The question this project can answer is **not** "who has no forecast". That
premise is falsified (`TARGET_REEVALUATION.md`). It is:

> Are the forecasts these cities receive good enough at *episodes* to act on,
> and can cheap local adaptation make them measurably better?

## 2. What the field already knows

### 2.1 Delhi is well served by its incumbent

CEEW's October 2025 evaluation of the Delhi AQEWS (400 m) reports that it
anticipated **83 of 92** "very poor and above" (AQI > 300) days in winter
2023-24 and **54 of 58** in winter 2024-25, with severe-day (AQI > 400) skill
improving roughly five-fold in 2024-25. The Delhi DSS also attributes the load
to Delhi, neighbouring districts, and Punjab/Haryana stubble fires.

That is a city-day POD of about 0.90-0.93. It is **not directly comparable**
with this repo's station-window PM2.5 >= 121 metric, and the false-alarm rate is
not given in the material reached. Even so, it shows that **beating the
incumbent in Delhi is neither likely nor useful**. Delhi stays a development
environment.

### 2.2 Outside Delhi, forecasts exist but their episode skill is unpublished

- AQEWS runs a 10 km national WRF-Chem domain with 72 h and 10-day products.
  IMD lists Lucknow, Varanasi and Patna (not Kanpur) among forecast cities.
- The IITM portal links PM2.5 verification pages for Lucknow and Patna. No
  episode-skill (POD/FAR/CSI) numbers for any non-Delhi city were found in the
  literature or secondary sources. The portal was unreachable from this
  session, as it was in August.
- The DSS paper itself attributes under-prediction of high concentrations to
  the 10 km grid. Independent IGP studies attribute low bias to under-estimated
  emissions and excessive night-time dispersion.
- UrbanEmissions publishes WRF-CAMx 0.25° forecasts for about 50 cities, also
  without public episode verification.

**Gap 1:** nobody independently publishes how well the forecasts used outside
Delhi warn of Very Poor+ days.

### 2.3 Forecast-triggered action is formalised only in NCR

CAQM's September 2024 revision lets GRAP Stages II-IV be invoked *on forecast*,
when IMD/IITM predict the higher category for about three days or more. Every
NCAP city was directed to prepare an emergency response plan, but no source
found shows forecast-based triggers or forecast verification operating in
Bihar or UP.

**Gap 2:** non-Delhi cities have the plans on paper and forecasts nearby, but no
trusted, verified forecast-to-action link.

### 2.4 Local post-processing is standard practice, and has a known weakness

Correcting a chemistry-transport model against local monitors is what national
services already do:

- the UK Met Office bias-corrects AQUM with AURN observations (SPPO, Neal et al.
  2014) before releasing site forecasts;
- NOAA tested analog and Kalman-filter correction of NAQFC PM2.5 (Djalalova et
  al. 2015). The best skill came from KF-AN, and its documented limitation is
  that it **reduces day-to-day variability and struggles with extreme events**;
- random forest or LightGBM correction of CAMS works on average error in China,
  the US and Hungary. A 2026 study from Japan warns that a fixed correction
  over-corrects when concentrations trend downward.

This repo independently found the same failure: an MAE-optimal calibrator that
caught 0 of 99 events. **The field has the method, and this project has
diagnosed its main weakness.** Modelling exceedance probability directly
(`EPISODE_SKILL_DIAGNOSIS.md` §5.1) is the right response. No operational
exceedance-probability post-processor for Indian cities was found.

### 2.5 AI weather models are not yet the answer for PM2.5 extremes

A 2024 wildfire-smoke study found Aurora underperforming physical forecasts for
PM2.5. It traced this to Aurora's 12-hourly output and its dependence on CAMS
for fire information. That agrees with this repo's findings (output capped at
196 µg/m³, discrimination mostly between cities).

### 2.6 Fire counts are a weaker input than assumed

iFOREST (2025), using 15-minute geostationary data, reports that over 90% of
large Punjab farm fires in 2024-25 started after 15:00, after the polar-orbiting
overpasses that FIRMS-style counts rely on. CAQM has acknowledged that the
counts understate burning. **FIRMS counts are a biased and declining proxy.**
Any fire feature must come from geostationary data or be treated as weak. This
corrects the FIRMS suggestion made in chat on the same day.

### 2.7 Impact runs through institutions, not alerts alone

- **Burden:** a 2024 Lancet Planetary Health time-series study of ten Indian
  cities (2008-2019) attributes 7.2% of deaths to PM2.5 above the WHO guideline
  (Delhi 11.5%), about 33,000 deaths a year, with +1.42% daily deaths per
  +10 µg/m³ two-day average. Varanasi is one of the ten cities.
- **Alerts alone:** most studies find small or no behaviour change from alerts
  alone. Health benefits appear mainly where alerts are tied to enforcement or
  specific, credible advice.
- **Closest working analogue:** Ahmedabad's Heat Action Plan combined forecasts,
  public warnings, hospital preparedness and inter-department coordination.
  Its pilot evaluation estimates about 1,190 deaths a year avoided (95% CI
  162-2,218; before/after design).

**Implication:** a forecast helps people when a named institution acts on it
under pre-agreed thresholds. A better probability that nobody acts on has no
health impact.

## 3. Possible impact, honestly bounded

| Pathway | Who acts | Plausible effect | Evidence strength |
|---|---|---|---|
| Independent verification | PCBs, CAQM, media, IITM itself | Trust and accountability for the forecasts already used; pressure to fix weak cities | High feasibility; impact indirect |
| Calibrated probability warnings | City ERS or GRAP-like committees, health and education departments | Earlier and better-targeted restrictions and advisories | Only if adopted; the Ahmedabad model shows the shape |
| Public advisories | Residents, especially the vulnerable | Some exposure reduction | Weak on its own |
| Open method for global-tier-only regions | Lahore, Kathmandu, West Africa | Same as above where no incumbent exists | Untested |

The project should claim no mortality numbers for itself. The defensible claim
is decision-relevant: "forecast X caught N of M Very Poor+ days in city Y at
lead Z, with this false-alarm rate".

## 4. Options

### A. Independent episode verification of the incumbents (recommended first)

Score AQEWS, SILAM, CAMS and UrbanEmissions for Lucknow, Kanpur, Varanasi and
Patna through winter 2026-27. Score at **the unit decision-makers use**:
city-day CPCB AQI category, with POD/FAR/CSI per lead and event counts. This
fills Gap 1, needs no new model, reuses `src/eval/`, and stays useful whatever
the outcome.

*Requires:* daily archiving of each incumbent's forecasts starting now. The
SILAM capture lapsed on 2026-08-11, and lost cycles cannot be recovered. AQEWS
and UrbanEmissions are not archived at all.

### B. Post-process the best available incumbent into exceedance probabilities

Apply the anchoring and exceedance-classifier method to **SILAM (and AQEWS if
obtainable)** rather than to 0.4° CAMS or Aurora. This is what national services
do (§2.4), aimed at the weakness they document. Train on part of the season or
on the next one; never claim skill on the training period.

*Requires:* option A's archive. Realistically, this season gives the training
data and 2027-28 the test.

### C. Current path: own classifier on CAMS/Aurora + GFS + local readings

Keep it as the **comparison baseline and fallback** wherever no incumbent
exists. It passed train-only gates (`FORECAST_BLH_RESULT.md`) but has never been
scored against a 3-10 km incumbent.

### D. Fine-tune Aurora

Not now (`EPISODE_SKILL_DIAGNOSIS.md` §5.3, §2.5 above): no emissions input, no
fire information beyond CAMS, data too short, and Delhi-dominated.

### E. Same method where only the global tier exists

Lahore and Pakistani Punjab share the airshed and the season. OpenAQ shows
about 332 active Pakistani monitors, and the provincial AI smog forecast has no
independent evaluation in the sources found. Kathmandu and West Africa are
secondary. Options A and C transfer at CPU cost, but this dilutes the India
season if done now.

### F. Partner with users and data holders (do alongside A)

- BSPCB: 35 regulatory stations plus a 534-block low-cost network with IIT
  Kanpur, and a 50-sensor UNDP network in Patna since June 2024.
- UPPCB, CEEW (who already verify the Delhi forecasts), UrbanEmissions, and the
  IITM/IMD verification team.

Ask which decisions they take, at what lead, and how many false alarms they
tolerate. That fixes the operating point and the scoring unit before results
exist.

## 5. What an expert would do

1. **This week:** restart SILAM capture and begin archiving AQEWS and
   UrbanEmissions city forecasts daily. Without this, options A and B are lost
   for the season.
2. **Before 1 December:** pre-register the verification contract: cities,
   city-day CPCB AQI unit, leads, metrics, and handling of missing days. Commit
   it before results, as was done for the GFS gate.
3. **Resolve the Varanasi observation anomaly** against CPCB data
   (`src/data/ogd_aqi.py`) before scoring Varanasi.
4. **Contact BSPCB/UPPCB and CEEW** to agree the decision unit and operating
   point.
5. **Weekly through February:** score incumbents (A) and the in-repo baseline
   (C). Publish nothing until the season contract is complete.
6. **March 2027:** publish the non-Delhi episode-verification report, which no
   one has. Decide on B for winter 2027-28 from evidence.
7. **Defer** fine-tuning, new regions, and any public feed.

## 6. What this review does not establish

- Non-Delhi incumbent skill is **unknown**, not known to be poor. Option A
  exists to find out.
- CEEW's Delhi numbers are city-day AQI > 300 counts and were read via search
  summaries; the PDF and the IITM portal were unreachable from this session.
- Pakistan forecast claims come from government statements and press only.

## Sources

- CEEW, *How well can Delhi predict air quality?* (2025): https://www.ceew.in/sites/default/files/ceew-how-well-can-delhi-predict-air-quality.pdf
- Kumar et al., DSS v1.0 for Delhi, GMD (2024): https://gmd.copernicus.org/articles/17/2617/2024/
- AIRWISE, BAMS (2024): https://doi.org/10.1175/BAMS-D-23-0181.1
- IMD air quality SOP: https://mausam.imd.gov.in/imd_latest/contents/pdf/emrc_sop.pdf
- IITM SILAM / other-city verification pages: https://ews.tropmet.res.in/silam.php, https://ews.tropmet.res.in/otherCities.php
- SILAM pre-operational validation: https://www.longdom.org/open-access/preoperational-validation-of-air-quality-forecasting-model-silam-for-india-92111.html
- UrbanEmissions India forecasts: https://urbanemissions.info/india-air-quality-forecasts/
- CAQM GRAP revision press release (Sept 2024): https://caqm.nic.in/WriteReadData/LINKS/CAQM%20PR%2018092024-100abe518ff-0fbf-4c60-ad8a-a91ebba8d1b7.pdf
- Neal et al. 2014 / Met Office SPPO (via EGU26-5574): https://meetingorganizer.copernicus.org/EGU26/EGU26-5574.html
- NOAA NAQFC bias correction (Wilczak & Djalalova): https://www.weather.gov/media/sti/aq/presentations/20140909/Bias%20Correction%20for%20Air%20Quality%20Predictions/Wilczak&Djalalova%20AQ_Webinar_09092014_rev2.pdf
- CAMS calibration, China/US: https://doi.org/10.3390/rs12223813; Hungary: https://iopscience.iop.org/article/10.1088/2515-7620/ad6239; Japan (2026): https://link.springer.com/article/10.1186/s40645-026-00830-x
- Aurora vs physical forecasts for smoke PM2.5: https://arxiv.org/pdf/2409.05866
- Satellite fire undercounting: https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report, https://www.ceew.in/blogs/how-does-satellite-technology-detect-punjab-stubble-burning-fires
- Lancet Planetary Health ten-city mortality (2024): https://scholars.mssm.edu/en/publications/ambient-air-pollution-and-daily-mortality-in-ten-cities-of-india-
- Alert effectiveness: https://research.birmingham.ac.uk/en/publications/alerts-work-air-quality-warnings-and-cycling/, https://blogs.iadb.org/ideas-matter/en/?p=8894
- Ahmedabad Heat Action Plan evaluation: https://pmc.ncbi.nlm.nih.gov/articles/PMC6236972/
- Bihar sensor networks: https://patnapress.com/bihar-takes-leap-in-air-quality-management-all-534-blocks-now-equipped-with-low-cost-pollution-sensors/, https://patnapress.com/enhanced-air-quality-monitoring-in-patna-with-50-low-cost-sensors/
- Punjab (Pakistan) AI smog forecasting: https://www.zameen.com/news/punjab-deploys-ai-fight-smog-improve-air-quality.html
