# IndiaAQBench data-expansion plan

**Status:** implementation-ready research plan; no new source has been approved,
downloaded, matched, or licensed by this document.

**Purpose:** identify additional data that can materially improve the experimental
forecast feed, severe-event skill, and year-round validation without weakening
the benchmark's provenance or introducing leakage.

**Primary success criterion:** Very Poor+ (`PM2.5 >= 121 ug/m3`) event skill
measured with POD, FAR, and CSI. Additional data are not justified by row count or
MAE alone.

**Existing benchmark contract remains authoritative:** split constants come only
from `src/splits.py`; the current 159-station registry in `data/stations.csv`
remains the v0.1 registry until a separately reviewed migration is approved.

---

## 1. Decision this plan supports

IndiaAQBench currently has a complete scoped OpenAQ archive of 1,489,534
station-hours across 159 stations and nine cities. The archive starts around
February 2025 in practice. It therefore contains only one observed
post-monsoon period, October-November 2025, and that period influenced the
current training design.

Additional data can create value in four different ways:

1. **More observation truth:** more independent station measurements for
   training, external testing, or live verification.
2. **A stronger forecast baseline:** actual CAMS forecasts at each lead, rather
   than carrying the CAMS initialization value forward.
3. **Predictive features:** information known at forecast initialization that a
   cheap adapter can learn from.
4. **Explanatory context:** fire, smoke, dust, weather, or satellite layers that
   help a user understand a forecast but are not yet used to change it.

These roles must never be blurred. In particular:

- OpenAQ, CPCB, and state-board measurements are observations. They become a
  forecast baseline only through a defined method such as persistence or
  climatology.
- A satellite aerosol index is not surface PM2.5 truth.
- A reanalysis produced after the forecast valid time is not a live-forecast
  feature.
- A layer shown in the UI is not evidence of improved forecast skill.

### Recommendation in one sentence

Add actual CAMS forecast leads first; run a small direct-ground-data pilot in
Patna and Varanasi in parallel; add fire and satellite data initially as
explanatory layers; promote any source into model fitting only after a
same-support ablation shows better held-out event skill.

---

## 2. Source roles and priority

### 2.1 Definitions

| Role | Definition | Examples | May use data after initialization? |
|---|---|---|---|
| Observation truth | A measurement against which a previously saved forecast is verified | OpenAQ, direct CPCB/state-board station PM2.5 | Yes, but only as the later outcome |
| Forecast baseline | A forecast available at the same initialization time as Aurora | CAMS forecast at +12 to +96 hours | No |
| Predictive feature | An input available by initialization and passed to an adapter | recent station bias, forecast wind, boundary-layer height | No |
| Explanatory UI layer | Context displayed to users without changing the prediction | nearby fire detections, satellite aerosol plume | No, if it describes that forecast |
| Retrospective diagnostic | Information used to explain a past error but not claim live skill | final ERA5 reanalysis, science-quality fire archive | It must not be represented as live input |

Every field entering a forecast must carry both an **observation/valid time** and
an **availability time**. The latter answers: “Could the live system actually
have known this when it issued the forecast?”

### 2.2 Source-evaluation table

“Access status” below means only what is visible from the official public page
or current repository. It is not a conclusion about automated access,
redistribution, or fitness for this project.

| Source class | Intended role | Expected ROI | Why it may help | Official starting point | Access/licensing questions that remain |
|---|---|---:|---|---|---|
| Direct CPCB CAAQMS and state-board feeds | Observation truth; recent-observation feature when available before init | **High if it adds history, stations, or lower latency; otherwise low because it may duplicate OpenAQ** | Could provide earlier post-monsoon coverage, reduce live observation delay, or recover stations missing from OpenAQ | [CPCB air-quality data links](https://cpcb.nic.in/rules-7/), [CPCB National AQI portal](https://airquality.cpcb.gov.in/AQI_India/), [CPCB CCR portal](https://app.cpcbccr.com/) | No stable machine interface, historical depth, rate limit, terms, attribution, and raw redistribution permission have been verified. State-board routes must be inventoried separately. |
| Actual CAMS global forecast leads | Mandatory forecast baseline; fallback; possible adapter feature | **Very high** | Makes the comparison operationally fair and supplies lead-dependent meteorology and composition | [CAMS global atmospheric-composition forecasts](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=overview) | Current code and credentials fetch lead zero only. Required lead availability, version metadata, request size, latency, and licence obligations for published extracts must be tested and recorded. |
| Earlier independent station archives or research datasets | Observation truth for added training or an external seasonal test | **Potentially transformational, but uncertain** | An untouched 2023 or 2024 post-monsoon period could strengthen year-round evidence and add severe events | Begin with CPCB/state-board archives and published metro-project data custodians; no specific research archive is approved yet | Physical station identity, averaging period, QC history, publication rights, and whether data are genuinely independent of CPCB/OpenAQ must be established before use. |
| NASA FIRMS VIIRS/MODIS active fires | Predictive feature after timing audit; explanatory UI layer immediately | **Moderate for post-monsoon explanation; uncertain for forecast gain** | Locates recent fire activity and supports an understandable smoke-context layer | [NASA FIRMS active-fire data](https://firms.modaps.eosdis.nasa.gov/active_fire/) | Earthdata/API requirements, citation, NRT versus later science-quality replacement, availability lag, and redistribution/display terms must be recorded. |
| CAMS GFAS fire emissions | Predictive feature or episode diagnostic | **Low-to-moderate incremental ROI** | Provides gridded fire emissions and plume information, but related information already drives CAMS | [CAMS GFAS fire emissions](https://ads.atmosphere.copernicus.eu/datasets/cams-global-fire-emissions-gfas?tab=overview) | Avoid double counting information already present in CAMS/Aurora. Confirm which version was available at each initialization and the terms for extracts. |
| Sentinel-5P Level-2 Aerosol Index | Explanatory UI layer first; later feature candidate | **Mostly contextual initially** | Can show absorbing aerosol plumes associated with smoke or dust | [Sentinel-5P documentation](https://documentation.dataspace.copernicus.eu/Data/SentinelMissions/Sentinel5P.html) | Aerosol Index is unitless and is not surface PM2.5. Cloud, overpass, QA, NRT/NTC latency, API quota, and display/redistribution requirements must be handled. |
| Other satellite aerosol products, such as MAIAC AOD | Retrospective feature candidate or explanatory layer | **Moderate research value; low launch priority** | Aerosol optical depth may add plume context at finer spatial resolution | [NASA MAIAC product documentation](https://www.earthdata.nasa.gov/s3fs-public/2025-04/MCD19_User_Guide_V6.pdf) | AOD is a column quantity, not surface PM2.5. Cloud gaps, retrieval QA, overpass timing, and live latency make it unsuitable as truth. Confirm the current product/version page before implementation. |
| CAMS/ECMWF meteorology | Predictive features | **High because much is already in the Aurora input** | Wind, precipitation, humidity, and mixing conditions can explain surface bias and transport | Use the CAMS forecast source above; [ERA5 hourly single levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview) is a retrospective comparator | Prefer fields available in the same live CAMS cycle. ERA5 is delayed/revised and must not be presented as a live input without an explicit availability simulation. |
| CAMS emissions inventories | Static/slow feature; explanatory context | **Mostly contextual at first** | Sectoral emissions may help characterize city regimes and support later research | [CAMS global emission inventories](https://ads.atmosphere.copernicus.eu/datasets/cams-global-emission-inventories?tab=overview) | Inventories can lag real emissions, may already inform CAMS, and do not describe unexpected same-day activity. Version, sector, year, and terms must be pinned. |

### 2.3 Priority order

#### P0 — actual CAMS forecast leads

This is the clearest high-ROI addition because it fixes an evaluation weakness
without requiring a learned method. The current downloader in
`src/data/cams_composition.py` requests `leadtime_hour=0`, which is the analysis
used to initialize Aurora. The present “raw CAMS” baseline therefore asks
whether Aurora beats holding that starting field constant. It does not ask
whether Aurora beats the lead-dependent CAMS forecast that was actually
available.

The first expansion should request the matching CAMS forecast cycle and
lead-dependent PM2.5 for +12 through +96 hours. The initial implementation
should be a baseline and fallback, not silently introduced as a calibrator
feature.

Value delivered even if model skill does not improve:

- a fairer public comparison;
- a fallback forecast when Aurora inference fails;
- a lead-dependent diagnostic of whether errors originate in CAMS or Aurora;
- weather/composition features already synchronized with the forecast cycle.

#### P1 — direct ground-data discovery

Direct CPCB and state-board data are high ROI only if they add at least one of:

- earlier independent history;
- new physical stations;
- lower live latency;
- fewer missing station-hours;
- clearer sensor/provider provenance.

OpenAQ station names already identify BSPCB as the provider for Patna and UPPCB
for Varanasi. The direct source may therefore be the same upstream measurement.
The default assumption must be **overlap until proven otherwise**, not “more
rows means more data.”

#### P2 — earlier independent station archives

This has the highest scientific upside because it could supply an independent
post-monsoon period. It also has the highest discovery and governance cost.

An earlier archive can support:

- additional fit data, if assigned to training before outcomes are inspected;
- an external retrospective test, if the method is frozen before the archive's
  outcome values are examined;
- seasonal stress tests.

It cannot reproduce the operational reliability evidence of a genuinely live
forecast. Results must be labelled “retrospective external validation,” not
“prospective.”

#### P3 — fires and satellite aerosol context

FIRMS is useful for an understandable public interface and for diagnosing
post-monsoon episodes. Sentinel-5P aerosol imagery can make regional smoke or
dust visible. Neither should delay the first forecast feed.

Initially:

- show them as dated context layers;
- display their acquisition/overpass time;
- do not alter the forecast;
- do not call them PM2.5 truth;
- do not claim causal source attribution.

Only after the feed is stable should they enter a correction model, one source
at a time.

#### P4 — emissions inventories and additional retrospective meteorology

Use existing CAMS-cycle meteorology before adding another weather source.
Static emissions can eventually help a regional adapter or underserved-city
typology, but they are unlikely to fix abrupt events by themselves.

---

## 3. Canonical station and sensor identity

### 3.1 Current limitation

`data/stations.csv` currently contains:

```text
station_id, city, station_name, lat, lon, first_seen, last_seen, n_rows
```

Its `station_id` is an OpenAQ location identifier. The hourly archive no longer
retains the individual OpenAQ sensor identifier after multiple PM2.5 sensors at
one location are combined. This is sufficient for the frozen v0.1 benchmark but
not for reconciling multiple providers.

A physical monitoring site, a provider's station record, and an instrument
sensor are different entities. They need separate identifiers.

### 3.2 Proposed identity tables

#### `physical_stations`

One row per real-world monitoring location:

| Field | Meaning |
|---|---|
| `physical_station_id` | Stable project-generated identifier; never a provider ID |
| `canonical_name` | Human-reviewed display name |
| `city`, `state`, `country` | Canonical geography |
| `lat`, `lon`, `elevation_m` | Best-supported coordinates and optional elevation |
| `location_type` | Traffic, residential, industrial, background, unknown |
| `valid_from`, `valid_to` | Period during which this physical site existed |
| `coordinate_source` | Provider or document supporting the canonical coordinates |
| `registry_version` | Version in which this identity was approved |

#### `provider_stations`

One row per provider representation of a physical site:

| Field | Meaning |
|---|---|
| `provider` | `openaq`, `cpcb_ccr`, `bspcb`, `uppcb`, etc. |
| `provider_station_id` | Identifier exactly as supplied by that provider |
| `physical_station_id` | Approved link to the physical site |
| `provider_name`, `provider_city` | Unmodified provider labels |
| `provider_lat`, `provider_lon` | Unmodified provider coordinates |
| `operator` | Agency operating the station, where supplied |
| `first_seen`, `last_seen` | Provider-record validity |
| `match_method` | Exact crosswalk, coordinate/name, or manual |
| `match_confidence` | Numeric confidence plus categorical band |
| `review_status`, `reviewer`, `reviewed_at` | Audit fields |

#### `sensors`

One row per provider instrument/measurement stream:

| Field | Meaning |
|---|---|
| `provider_sensor_id` | Identifier exactly as supplied |
| `provider_station_id` | Owning provider-station record |
| `pollutant` | Canonical pollutant, initially `pm25` |
| `reported_unit` | Unit in the raw payload |
| `averaging_period` | Instantaneous, hourly, 24-hour, unknown |
| `instrument_model` | If supplied |
| `valid_from`, `valid_to` | Sensor deployment/replacement interval |
| `is_reference_grade` | `true`, `false`, or `unknown`; never inferred from provider name |

#### `observations`

Processed rows should retain:

- `physical_station_id`;
- provider and provider station/sensor IDs;
- raw observation start and end times;
- canonical UTC interval start and end;
- original and converted value/unit;
- retrieval time;
- provider QC flags and project QC flags;
- raw-file hash and parser version;
- whether the row is eligible as truth, a live feature, or both;
- all contributing sensor IDs when an aggregate is produced.

### 3.3 No silent migration of v0.1

The first implementation must build a proposed crosswalk beside the existing
registry. It must not rewrite `data/stations.csv`, change frozen L1 assignments,
or resample existing pair files.

If a future benchmark version adopts `physical_station_id`, it requires:

1. an explicit registry-version bump;
2. a deterministic mapping from every old OpenAQ `station_id`;
3. a regenerated spatial split from the approved canonical ID according to a
   documented migration rule;
4. fresh pair/evaluation artifacts;
5. disclosure that results are not directly row-for-row comparable with v0.1.

---

## 4. Matching protocol

Matching produces candidates first and approved links second. Outcome PM2.5
values must not influence identity matching.

### Stage 0 — normalize identity fields

- Preserve every raw name.
- Create a comparison-only normalized name: lowercase; Unicode normalization;
  punctuation and agency suffix handling; whitespace collapse.
- Normalize coordinates to WGS84 decimal degrees while retaining original
  values and coordinate system claims.
- Normalize city/state aliases separately from station names.
- Extract provider IDs and explicit cross-references where present.

### Stage 1 — exact identifiers

Accept automatically only when an authoritative provider crosswalk explicitly
links the records, or when the same provider's stable station ID is present in
both sources.

Do not treat identical station names as exact identifiers.

Suggested confidence: `1.00`, method `exact_provider_crosswalk`.

### Stage 2 — tight geospatial plus compatible name

Generate a high-confidence candidate when:

- coordinates are within 100 m; and
- normalized names are strongly compatible, or the operator and locality
  unambiguously agree.

Suggested confidence band: `high`, but retain the component scores and distance.
Dense monitoring compounds may require manual review even inside 100 m.

### Stage 3 — wider geospatial/name candidates

Generate manual-review candidates when:

- coordinates are within 1 km with a strong name match; or
- coordinates are within 250 m with a weak/missing name match.

These are not approved automatically. Provider coordinates can be city
centroids, rounded values, or moved station metadata.

### Stage 4 — manual review

The review report must display:

- both names and operators;
- coordinates on a map and distance;
- provider URLs/metadata snapshots;
- active dates;
- sensor/pollutant details;
- competing candidate stations;
- proposed action and reason.

Allowed decisions:

- `same_physical_station`;
- `different_physical_station`;
- `possible_relocation`;
- `insufficient_evidence`.

Unresolved candidates remain separate. A false merge is more damaging than a
temporary duplicate.

### Stage 5 — temporal plausibility audit

After identity approval, compare active periods. Overlapping records with
systematically different coordinates or mutually incompatible instruments
trigger review. Observation values may be used here to audit an already
proposed link, never to create it.

### Confidence requirements

- Public/benchmark integration target: at least 95% of retained pilot rows map
  through exact or reviewed-high-confidence links.
- All ambiguous matches affecting Very Poor+ events receive manual review.
- Low-confidence matches are excluded from fitting and headline scoring but
  retained in the match report.

---

## 5. Time, units, and averaging harmonization

### 5.1 Time

- Store canonical timestamps in UTC.
- Display India times in `Asia/Kolkata` (IST, UTC+05:30).
- Preserve the provider's original timestamp string, timezone, and meaning.
- Represent measurements as intervals: `period_start_utc` and
  `period_end_utc`, not just an ambiguous point time.
- Store `retrieved_at_utc` and, where available, `published_at_utc`.
- Never infer UTC versus IST from the numerical hour alone.
- Daylight-saving conversion is not an India issue, but upstream UTC products
  still require explicit timezone-aware parsing.

The existing OpenAQ rows commonly occur at `:30` UTC because the local hourly
period begins on an IST hour. Flooring them to UTC `:00` would change their
meaning. Harmonization must align interval centers or ends according to the
provider's declared period, not by cosmetic timestamp flooring.

### 5.2 Units

Canonical surface PM2.5 concentration is `ug/m3`.

- Preserve `raw_value` and `raw_unit`.
- Convert only through an explicit, tested unit rule.
- Record the conversion factor and parser version.
- Do not convert column aerosol or mass-mixing-ratio products into surface
  `ug/m3` without the physical variables and documented calculation required.
- Treat unknown units as invalid for training/scoring until resolved.

### 5.3 Hourly versus rolling 24-hour

These are separate evaluation targets:

- **Hourly/instantaneous sensitivity:** matched hourly station concentration.
- **Headline category evaluation:** trailing or forecast-window 24-hour mean,
  because the project specification associates CPCB PM2.5 category thresholds
  with 24-hour means.

Proposed rolling-24-hour contract:

1. Align to an IST hourly grid.
2. Average duplicate readings within each physical station-hour only after
   sensor/provider deduplication.
3. Require at least 18 valid hourly values in a 24-hour window for a reported
   mean.
4. Record `hours_present` and do not interpolate the missing hours for headline
   scoring.
5. Run a stricter 24-of-24 completeness sensitivity analysis.
6. Keep local-calendar-day and trailing-24-hour products separately named.

If a source supplies only an official 24-hour aggregate, retain it as such. Do
not expand it into 24 invented hourly values.

---

## 6. Quality control and duplicate rules

### 6.1 Preserve raw data

Raw responses are immutable. Cleaning creates derived data with explicit flags;
it never edits the raw snapshot. Every dropped or excluded row must be
countable by reason.

### 6.2 Base QC

Apply the current project rules where appropriate:

- numeric and timestamp parseability;
- PM2.5 range `[0, 1000] ug/m3`;
- missing-coordinate and unknown-unit flags;
- stuck-value runs longer than 24 consecutive hours;
- duplicate station-hour detection;
- extreme values over `500 ug/m3` retained and flagged, not deleted.

Add source-aware checks:

- provider QC flag and calibration/maintenance status;
- impossible interval ordering;
- timestamp cadence changes;
- coordinate/name changes;
- abrupt sensor replacement;
- extended zero runs;
- excessive missingness;
- revisions between retrievals.

QC must not preferentially remove severe events. Report exclusion rates
separately below and above `121 ug/m3`.

### 6.3 Duplicate hierarchy

1. **Identical raw payload:** deduplicate by source record ID or payload hash.
2. **Same provider sensor and interval:** keep the latest declared revision,
   but retain both raw versions and revision timestamps.
3. **Replacement sensors with non-overlapping validity:** concatenate under one
   physical station while retaining sensor IDs.
4. **Overlapping sensors at one physical station:** keep separate through QC.
   Select a primary stream using a pre-registered completeness/QC rule, or
   compute a robust aggregate only after overlap analysis validates that rule.
5. **OpenAQ versus direct CPCB/state-board record:** assume a shared upstream
   observation when physical station, interval, and value lineage agree. Choose
   one canonical row by source precedence; never average the same measurement
   simply because it arrived through two APIs.
6. **Nearby but distinct physical stations:** never combine them into a city
   average at ingestion.

Every aggregate must list the contributing provider sensor IDs.

### 6.4 Disagreement audit

For overlapping candidate rows at the same physical station and interval,
report:

- count and coverage;
- mean and median bias;
- MAE;
- correlation;
- fraction with absolute difference greater than
  `max(20 ug/m3, 25% of the pair mean)`;
- disagreement rate separately for Very Poor+ observations;
- timestamp shifts at `-2` through `+2` hours to detect period-label errors.

Do not resolve disagreement by averaging until timing, units, and revision
semantics have been checked.

---

## 7. Provenance contract

Each source acquisition writes an append-only manifest record containing:

- source and product name;
- provider/product version;
- official landing page and exact endpoint;
- access method and authentication class, never credentials;
- request parameters and geographical/temporal bounds;
- request start/end and retrieval time in UTC;
- raw response filename, byte size, and SHA-256;
- response headers or provider revision markers when available;
- parser module version and repository commit;
- rows received, parsed, retained, and excluded by QC reason;
- distinct provider stations and sensors;
- first/last observation or valid time;
- source unit and averaging-period values encountered;
- error/retry history;
- applicable terms/licence URL and the date reviewed;
- redistribution decision: `approved_raw`, `approved_derived_only`,
  `scripts_only`, or `unresolved`;
- attribution/citation text required by the provider.

Provider web terms and API behavior can change. Save a dated terms/metadata
snapshot or hash where legally permitted, and re-review before each public data
release.

### Publication rule

If raw redistribution is unresolved or prohibited:

- do not commit or publish the raw payload;
- publish acquisition code if permitted;
- publish request manifests, hashes, schemas, and row-count reports;
- publish only derived aggregates if the applicable terms explicitly allow it;
- document the user's own credential/terms-acceptance step.

The repository specification currently describes CAMS analysis as
redistributable. This workstream must still record the current Copernicus terms
and confirm that the intended forecast extracts and public delivery comply.

---

## 8. Two-city pilot: Patna and Varanasi

### 8.1 Why these cities

- **Patna:** target non-metro in the training-city pool, currently 7 OpenAQ
  stations with station names identifying BSPCB.
- **Varanasi:** target non-metro in the L2 held-out-city set, currently 4
  OpenAQ stations with station names identifying UPPCB.

Together they test whether a source adds value in both ordinary fitting and a
city that must remain excluded from ordinary model training.

### 8.2 Pilot scope

No national bulk pull occurs before this pilot passes.

#### Phase A — source and rights dossier

For the CPCB CCR route and each relevant BSPCB/UPPCB route:

1. Record the official owner, portal, and public documentation.
2. Determine whether an official download or documented API exists.
3. Record authentication, captcha, rate limit, and query constraints.
4. Request or locate written terms for research use, attribution, and
   redistribution.
5. Stop any route that would require bypassing access controls or violating
   terms.

#### Phase B — three small temporal probes

For each city and candidate ground source:

1. **Overlap window:** 2025-10-15 through 2025-11-15. This is already covered by
   OpenAQ and includes a high-value post-monsoon comparison period.
2. **Earlier-history probes:** request no more than seven days in October 2023
   and seven days in October 2024 to establish whether measurements are
   genuinely retrievable, rather than relying on metadata claims.
3. **Live-latency probe:** for seven consecutive days, record what is available
   at fixed retrieval times without using those readings to change a public
   forecast yet.

If the interface cannot query these small windows reproducibly, do not scale it.

#### Phase C — identity matching

1. Create provider-station and sensor rows.
2. Generate exact and geospatial/name candidates.
3. Manually review every ambiguous pair.
4. Produce a map and crosswalk report.
5. Leave unresolved records separate.

#### Phase D — overlap/QC report

For each physical station:

- source availability by day;
- station-hours from each source;
- same-upstream duplicate rate;
- unique station-hours after deduplication;
- unit/timestamp agreement;
- disagreement statistics;
- Very Poor+ counts before and after QC;
- retrieval latency;
- data revision behavior.

#### Phase E — value report and decision

Report results for Patna and Varanasi separately. Varanasi observations remain
excluded from ordinary adaptation fitting under the L2 contract.

### 8.3 Continuation gates

Full ground-source integration requires all safety gates and at least one
material-value gate.

#### Safety gates — all required

- Official source ownership and allowed access path documented.
- Publication/redistribution status explicitly resolved or safely limited to
  scripts/manifests.
- PM2.5 units and averaging-period semantics verified.
- At least 95% of retained rows mapped through exact or reviewed
  high-confidence station links.
- No unresolved systematic timestamp shift.
- No unresolved disagreement rate above 10% using the threshold in section
  6.4.
- Missingness and QC exclusions reported, including separate severe-event
  exclusions.
- Acquisition is rerunnable and creates byte hashes plus a provenance manifest.

An exceeded disagreement threshold triggers investigation; it does not justify
silently choosing the more convenient source.

#### Material-value gates — at least one required

After physical-station/provider deduplication, the candidate must achieve one
of:

1. Add at least 30 consecutive usable days outside the present OpenAQ archive
   in each pilot city, including a meaningful post-monsoon or winter interval.
2. Add at least 5% and at least 2,000 usable unique station-hours in each pilot
   city over the tested historical horizon.
3. Add at least 50 unique Very Poor+ station-hours across the two pilot cities,
   including at least 10 in Varanasi, or add at least 10 unique Very Poor+
   rolling-24-hour station-days across them.
4. Reduce median live observation availability lag by at least 60 minutes
   without increasing disagreement, or improve completed station-hours by at
   least 10% during the seven-day live probe.
5. Add a physical station not represented in OpenAQ with at least 75% hourly
   completeness over 30 days.

These are project continuation thresholds, not universal quality standards.
The pilot report must show the raw values even if it fails every gate.

### 8.4 Stop conditions

Stop after the pilot rather than expanding nationally when:

- the candidate is almost entirely a second delivery route for the same
  observations and adds neither history, latency, nor reliability;
- access depends on fragile UI scraping, captcha bypass, or undocumented
  behavior that cannot be responsibly automated;
- identity, units, or averaging periods cannot be resolved;
- redistribution or publication obligations are incompatible with the public
  project;
- severe-event rows are disproportionately missing or removed by provider QC.

---

## 9. Leakage prevention

### 9.1 Immutable forecast-time cutoff

For a forecast initialized at time `T`, a feature is eligible only if:

```text
availability_time <= T
```

Observation time alone is insufficient. A 12:00 observation published at 14:00
was not available to a 12:00 forecast.

### 9.2 Source-specific rules

- **Ground observations:** Component A may use only rows actually available
  before initialization. Later observations are truth only.
- **CAMS:** use the forecast cycle and product version available at
  initialization. Do not use a later analysis valid at the forecast target
  time.
- **FIRMS:** use only detections delivered before initialization; later
  science-quality replacements are retrospective diagnostics.
- **GFAS:** pin issue/availability time, not just fire date.
- **Sentinel-5P:** enforce product publication time and QA. An overpass before
  initialization whose product arrived afterward is not a live feature.
- **ERA5:** use as retrospective meteorology unless the experiment simulates
  its real publication delay. It is not a live forecast input.
- **Emissions inventories:** pin the version that existed at initialization for
  prospective claims.

### 9.3 Split protection

- Import `SPLIT_CUTOFF`, held-out cities, and L1 rules from `src/splits.py`.
- Fit all normalization, imputation, matching thresholds that depend on
  observations, and model parameters on the authorized fit pool only.
- Varanasi, Kanpur, and Kolkata remain absent from ordinary learned fitting.
- Identity matching may use metadata across time because it does not use PM2.5
  outcomes; any value-based identity audit must not tune a predictive method.
- An external historical test archive is sealed before outcome inspection:
  record file hashes, freeze the method version, then score.
- Do not choose sources or hyperparameters based on headline test improvement
  and report the same test as untouched.

### 9.4 Live ledger

Every experimental-feed forecast records:

- initialization and publication time;
- model/adaptor versions;
- feature-source versions and latest allowed timestamps;
- raw Aurora, CAMS, and adapted predictions;
- missing/stale flags.

The prediction is immutable. Later observation matching appends verification; it
does not overwrite the prediction.

---

## 10. Ablation experiment ladder

An ablation changes one data source at a time. All comparisons use identical
splits, dates, stations, seeds, methods, and event definitions.

### 10.1 Fixed evaluation views

Report both:

1. **Common support:** exactly the station-times available to every compared
   method/source. This isolates model change.
2. **Expanded support:** all additional station-times enabled by the new
   source. This measures coverage but must not be compared as if it were the
   same test population.

Always report per-city, pooled train-city, L1, and L2 results with Very Poor+
event counts.

### 10.2 Ladder

| Step | Change from previous step | Question |
|---|---|---|
| A0 | Persistence, climatology, current fixed CAMS lead-zero, raw Aurora | Existing benchmark reference |
| A1 | Add actual CAMS forecast at every lead as a separate baseline | Does Aurora add value over the available operational global forecast? |
| A2 | Add Component A using current OpenAQ only | What does the cheapest recent-local-observation correction buy? |
| A3 | Use direct-source observations only to fill live pre-init gaps in Component A | Does lower latency/completeness improve event skill? |
| A4 | Add earlier ground observations to the authorized fit pool, with the evaluation population unchanged | Does additional seasonal truth improve transfer? |
| A5 | Add lead-dependent CAMS meteorological/composition features to a small correction model | Can existing synchronized fields explain surface bias? |
| A6 | Add FIRMS/GFAS features available by init | Do fires improve post-monsoon POD/CSI beyond CAMS information? |
| A7 | Add satellite aerosol features available by init | Does satellite context add skill after cloud/latency missingness? |
| A8 | Add static emissions/context features | Do slow-varying city/source characteristics improve L2 transfer? |

Do not jump directly from A0 to a model containing every source. If A6 or A7
adds no robust skill, keep it only as an explanatory layer.

### 10.3 Advancement criterion

Promote a feature source into the experimental feed's correction method only
when it:

- improves L2 Very Poor+ CSI or improves POD with a pre-declared acceptable FAR
  tradeoff at +24 to +72 hours;
- does not materially degrade L1 or multiple individual cities;
- is supported by enough observed events to interpret;
- passes the existing no-harm event guard;
- remains useful on common support;
- has a reliable live availability path.

MAE-only improvement is not sufficient.

---

## 11. Proposed implementation ownership

This section proposes future ownership; it does not override
`docs/WORKSTREAMS.md`. The coordinator must assign it before code begins.

### Disjoint future implementation ownership

The source audit is complete. If implementation is parallelized, assign these
non-overlapping paths:

| Session | Exclusive paths |
|---|---|
| Source framework and identity | `src/data/sources/base.py`, `src/data/station_identity.py`, `src/data/provenance.py`, `tests/data/test_station_identity.py`, `tests/data/test_provenance.py` |
| Actual CAMS forecast | `src/data/sources/cams_forecast.py`, `tests/data/test_cams_forecast_contract.py` |
| OGD/CPCB ground pilot | `src/data/sources/cpcb.py`, `src/data/harmonize_external.py`, `tests/data/test_harmonize_external.py` |
| Context layers | `src/data/sources/firms.py`, `src/data/sources/sentinel5p.py`, source-specific tests under `tests/data/context/` |

`tests/data/**` belongs to WS-8 during these assignments; WS-3's historical
guardrail work does not edit it. Shared integration points remain read-only
until a coordinated review.

Suggested data/artifact locations:

```text
data/external/raw/<source>/<retrieval_id>/       # normally ignored/private
data/external/manifests/<source>.jsonl           # publishable when permitted
data/registry/physical_stations.csv
data/registry/provider_stations.csv
data/registry/sensors.csv
results/data_expansion/patna_varanasi/
```

### Files initially read-only

- `data/stations.csv`
- `data/openaq/**`
- `src/data/openaq_client.py`
- `src/data/cams_composition.py`
- `src/splits.py`
- `src/eval/**`
- `results/pairs/**`

Integration into those files happens through a reviewed handoff after the
two-city pilot. This avoids changing the current registry or benchmark while
the GPU rollout is in flight.

### Suggested session sequence

1. **Source dossier session:** rights/access investigation and pilot manifest
   specification; no bulk download.
2. **Identity session:** implement schema, matching candidates, and review
   report using tiny fixture data.
3. **CAMS forecast session:** add lead-dependent CAMS retrieval and extraction
   as a separate baseline.
4. **Ground pilot session:** acquire only the approved Patna/Varanasi slices,
   match, and produce the gate report.
5. **Context session:** add FIRMS and satellite UI artifacts only after the live
   forecast schema is stable.
6. **Ablation session:** run one-source-at-a-time comparisons after valid
   current-registry forecast pairs exist.

---

## 12. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| OpenAQ and CPCB/state-board data share the same upstream feed | Inflated apparent coverage and duplicate weighting | Canonical physical/provider/sensor identity; lineage-based deduplication |
| Provider IDs or station names change | False new station or broken history | Validity intervals, aliases, immutable provider IDs, manual crosswalk review |
| Coordinates are rounded, centroids, or relocated | False station merge | Distance bands plus names/operators/dates; retain relocation status |
| Timestamp labels mean different interval starts/ends | Large artificial disagreement and leakage | Preserve raw interval semantics; audit hour shifts |
| Hourly values are compared with 24-hour aggregates | Invalid event labels | Separate targets; never expand daily values into hourly rows |
| Severe values are treated as sensor errors | Artificially good MAE and lost events | Keep extremes; report QC exclusions by event regime |
| Historical products are revised after the fact | Retrospective inputs look better than live inputs | Store retrieval/version time; separate NRT from final/science-quality data |
| Additional truth changes the evaluation population | Apparent gain caused by easier stations/times | Common-support metrics plus separate expanded-coverage results |
| Feature is unavailable in real time | Retrospective skill cannot ship | Availability-time enforcement and shadow-mode audit |
| Direct portal has captcha or unstable undocumented endpoints | Brittle or inappropriate production dependency | Use only allowed official access; seek data agreement; stop if not reproducible |
| Redistribution is unclear | Public release risk | Source dossier and explicit publication class before committing data |
| Fire/satellite feature duplicates information already in CAMS | Complexity without gain | One-source ablations; contextual-only default |
| One short severe season drives design | Weak year-round claim | Seal external historical tests and continue prospective live verification |
| More rows come mainly from Delhi | Project drifts away from underserved cities | Pilot and report Patna/Varanasi first; require L2 results |

---

## 13. Definitions of done

### Discovery done

- Official source and custodian documented.
- Access route tested with a tiny request.
- Terms, attribution, and redistribution status recorded without assumption.
- Product role assigned: truth, baseline, feature, context, or diagnostic.
- Availability-time behavior understood.

### Patna/Varanasi pilot done

- Raw snapshots and append-only manifests exist for approved small windows.
- Provider station and sensor inventories exist.
- Every proposed physical-station link has a confidence and review status.
- Time/unit/averaging semantics are tested.
- Overlap, uniqueness, severe-event, missingness, disagreement, and latency
  reports exist per city.
- Safety and material-value gates are reported pass/fail with exact counts.
- No existing benchmark data or registry has been modified.

### Source integration done

- Parser, harmonizer, provenance, and identity tests pass.
- Raw and derived schemas are versioned.
- Live acquisition is resumable, rate-limited, and fails visibly.
- Feature availability is enforced at each forecast initialization.
- Publication behavior follows the recorded rights decision.
- The integrity audit still passes.

### Scientific value demonstrated

- An ablation compares the source on common support.
- Per-city, L1, and L2 Very Poor+ counts/POD/FAR/CSI are published.
- No-harm guardrails pass.
- Improvement is not MAE-only.
- Negative or null results are retained and reported.

### Year-round evidence strengthened

One of the following is completed and labelled accurately:

- an untouched external retrospective post-monsoon test using independently
  acquired station observations; or
- a prospective live post-monsoon scorecard from immutable forecasts.

Additional training coverage alone does not satisfy this definition.

---

## 14. Immediate first actions

1. Assign a new data-expansion workstream with the new-only ownership in
   section 11.
2. Implement actual CAMS +12 to +96-hour extraction as a separate baseline.
3. Complete the Patna/Varanasi source-and-rights dossier before downloading
   national data.
4. Freeze tiny overlap/history/live pilot request manifests.
5. Build the identity crosswalk and review report from pilot metadata.
6. Apply the continuation gates before any national ingestion.
7. Keep FIRMS and Sentinel-5P contextual in the first public feed.
8. Run ablations only after the current-registry 56-date rollout produces valid
   forecast pairs.

The expansion succeeds when it creates more trustworthy evidence or better
held-out severe-event forecasts—not when it merely creates a larger data
directory.
