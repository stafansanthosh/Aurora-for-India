# Data-source audit for IndiaAQBench

**Status:** source-access and provenance audit
**Access date for every web source below:** 2026-07-29
**Scope:** additional ground observations, an operational CAMS forecast
baseline, fire information, satellite aerosol information, and independent
historical data that could strengthen the benchmark or a public experimental
forecast feed.

This document verifies access routes and defines small pilots. It does **not**
authorize bulk retrieval, undocumented scraping, credential bypass, or use of a
source whose licence has not been checked.

## 1. The decisions this audit supports

IndiaAQBench needs to keep four different jobs separate:

| Job | Plain-language definition | Examples | Can it be called ground truth? |
|---|---|---|---|
| Ground observation | A sensor measurement used to determine what actually happened at a station | CPCB/SPCB CAAQMS PM2.5 | Yes, after the repository's quality checks |
| Forecast baseline | A forecast that was available at the same initialization time as Aurora | CAMS PM2.5 at +12…+96 h | No |
| Predictive feature | Information available before initialization that may help a correction model | recent fires, wind, boundary-layer height | No |
| Explanatory UI context | Information that helps a person understand a forecast without being used to fit or score it | fire dots, satellite aerosol layer | No |

The immediate conclusions are:

1. **Implement actual CAMS forecast leads first.** This is the largest
   scientific gap in the existing baseline and requires no new ground-data
   licence.
2. **Pilot the official OGD India real-time CPCB API for live-feed
   observations.** It is documented, hourly, and released under the Government
   Open Data License. It is a current feed, not a verified historical archive.
3. **Do not make a historical-data claim about the CPCB CCR interface yet.**
   The public dashboard is verified; a stable, documented historical API and
   its redistribution terms were not found in the official material reviewed.
4. **Use FIRMS and Sentinel-5P as explanatory layers first.** Their incremental
   predictive value must be established by an ablation: the same benchmark with
   and without the source.
5. **Do not depend on the public GFAS v1.2 archive for a live feed.** The
   official ADS dataset is discontinued after 2025-12-03.
6. **There is a useful independent 2022–2024 post-monsoon hourly sensor
   archive, but it is not a Patna/Varanasi truth set.** The Aakash Project
   covers Punjab, Haryana, Delhi-NCR and parts of western Uttar Pradesh, uses
   low-cost sensors, and is licensed CC BY-NC-ND 4.0. It is valuable for
   transport/fire diagnostics; reuse in a transformed or commercial public
   product needs written clarification.
7. **No public, documented, licence-clear 2023/2024 hourly station archive for
   Patna or Varanasi was verified.** The next route is a narrow official export
   test or a formal data request, not a bulk scraper.

These conclusions add detail to
[`DATA_EXPANSION_PLAN.md`](DATA_EXPANSION_PLAN.md); they do not change the
benchmark split, cutoff, event threshold, or current OpenAQ archive.

## 2. What is already in this repository

### Verified from repository files

- `data/stations.csv` contains 159 stations.
- Seven registry rows are labelled `patna` and four are labelled `varanasi`.
  One Patna-labelled row is physically named “Industrial Area, Hajipur -
  BSPCB”; downstream displays should not silently relabel that station as
  central Patna.
- The ground-observation pipeline uses OpenAQ v3 and preserves sensor identity.
- `src/data/cams_composition.py` requests the CAMS global atmospheric
  composition **forecast** dataset at `leadtime_hour=0`. Those fields initialize
  Aurora. The current benchmark then carries the lead-zero PM2.5 value forward
  and calls that fixed comparator `raw_cams`.
- The benchmark grid is +12, +24, …, +96 hours.

### Consequence

`raw_cams` is not the operational CAMS forecast baseline. It asks, “Is Aurora
better than leaving CAMS's initialization value unchanged?” The missing
baseline asks, “Is Aurora better than the CAMS forecast that was actually
available for the same future time?” Both can remain in the table, but their
labels must make the distinction obvious:

- `cams_lead0_fixed`
- `cams_forecast`
- `raw_aurora`

The lead-zero files needed by Aurora must remain separate from the new
lead-dependent baseline files. Adding the baseline must not change Aurora's
inputs.

## 3. Source decision matrix

“Verified” means the cited primary/official page documents the relevant
property. “Unverified” means this audit did not find official documentation for
that property; it does not prove the property cannot exist.

| Source | Intended role | Access status | Expected incremental value | Engineering burden | Legal/reproducibility risk | Decision |
|---|---|---:|---:|---:|---:|---|
| Existing OpenAQ archive | Ground observations | Verified in repository | Already essential | Existing | Existing provenance controls apply | Keep |
| OGD India real-time AQI API | Live ground observations and redundancy check | **Verified current/hourly API** | Medium for live robustness; probably low for historical expansion | Low | Low if GODL attribution and raw-data warnings are preserved | Pilot now |
| CPCB CCR dashboard | Possible official historical station export | Public UI verified; stable historical API and redistribution terms **unverified** | Potentially very high | Medium to high | Medium/high until terms and export route are written down | Manual one-day access test, then request permission |
| CPCB NAMP year-wise data | Long-run regulatory context | Verified public page | Low for hourly PM2.5 events; NAMP is not the same as CAAQMS event data | Low | Attribution required | Context only |
| BSPCB old Patna reports | Historical context | Verified download links, exact file structure not inspected | Low for the present benchmark; public page exposes 2016 and 2016–2018 air-quality reports, not a 2023/24 hourly feed | Low/medium | Terms for redistribution unverified | Do not prioritize |
| UPPCB/UPECP city data page | Possible Varanasi official data | Link verified; machine API, availability and terms unverified | Potentially high | Medium/high | Medium/high | Manual one-day test |
| Varanasi Smart City OGD catalog | Monthly city context | Verified monthly-mean catalog/API | Low for event scoring | Low | Low under GODL | UI/context only |
| WBPCB hourly historic portal | Kolkata/West Bengal observation cross-check | Public hourly UI verified; API and reuse terms unverified | Medium for held-out Kolkata diagnostics | Medium | Medium; portal warns about intended use and sensor character | Pilot only after station-class check |
| CAMS forecast +12…+96 h | Operational forecast baseline | **Verified official dataset and API** | **Very high** | Low/medium | Low with attribution and version capture | Implement first |
| NASA FIRMS NRT fire detections | Explanatory UI; later candidate feature | **Verified official API**; free MAP_KEY required | High explanatory value; predictive gain uncertain | Low | Low, but cite product and retain source/version | UI pilot now; feature only after ablation |
| CAMS GFAS v1.2 | Retrospective fire-emission diagnostic | Verified archive; **not a current live public feed after 2025-12-03** | Low incremental value over CAMS forecasts because GFAS already drives CAMS fire emissions | Low for archive, high for unresolved live replacement | Low licence risk; high operational risk | Archive diagnostics only |
| Sentinel-5P UV aerosol index | Explanatory plume layer; later candidate feature | **Verified CDSE product/API** | Medium explanatory value; predictive gain uncertain | Medium | Low/medium; quality/timeliness and processor version must be stored | UI pilot, not truth |
| Aakash CUPI-G 2022–2024 | Independent post-monsoon transport/fire diagnostics | **Verified hourly download** | High for northwest-India fire-season diagnostics; little direct Patna/Varanasi value | Medium | **High for product reuse:** CC BY-NC-ND 4.0 | Contact project before integrating |
| Stanford/CREA daily 10 km PM2.5, 2005–2023 | Independent gridded comparison/context | Verified open repository; licence field is blank on the record page reviewed | Medium for spatial/daily plausibility; not station truth and not 2024 | Medium | Medium until licence is clarified; source may share monitor inputs | Optional research analysis |
| Other Zenodo CPCB-derived summaries | Monthly/annual context | Verified | Low | Low | Varies | Do not use for event scoring |

## 4. Direct Indian ground-observation routes

### 4.1 CPCB public routes

#### Verified facts

- CPCB's [air-quality data page](https://cpcb.nic.in/rules-7/) separates
  year-wise NAMP data from real-time air-quality data.
- The [Central Control Room for Air Quality
  Management](https://airquality.cpcb.gov.in/ccr/) is a public visualization
  route for data supplied by CPCB, state boards and other agencies. Its notice
  asks research/publication users to acknowledge the agencies that supplied the
  data.
- The [CPCB air-quality management
  portals](https://cpcb.gov.in/air-quality-management-portals/) page points
  network participants to the newer NAMP/EAQDES system and says the older NAMP
  portal is discontinued. This is an operational/submission route, not public
  historical API documentation.
- The [CPCB industrial CAAQMS
  portal](https://airquality.cpcb.gov.in/industrial/) requires login,
  password and captcha. It is an industry data-upload system, not authority to
  retrieve public ambient-monitor history.
- CPCB's official [air-quality data-management system technical
  document](https://cpcb.nic.in/openpdffile.php?id=VGVuZGVyRmlsZXMvODg3XzE3MzQzNDczMjZfbWVkaWFwaG90bzI3NDYucGRm)
  describes the CCR, portals, applications and system APIs, but it does not
  document a stable, unauthenticated public historical-download API.

#### Not verified

- A CPCB-supported, stable public API for arbitrary historical hourly CAAQMS
  PM2.5 ranges.
- The right to mirror or redistribute a bulk CCR export under an open licence.
- A service-level guarantee for CCR availability or latency.

#### Interpretation

The dashboard is good evidence that official data exist. It is not, by itself,
an API contract or redistribution licence. Browser network inspection,
reverse-engineered endpoints, captcha automation and copied bearer tokens would
make the benchmark fragile and are outside this plan.

### 4.2 OGD India: the verified official live API route

#### Verified facts

The CPCB/MoEFCC [Real time Air Quality Index
catalog](https://www.data.gov.in/catalog/real-time-air-quality-index) and
[resource](https://www.data.gov.in/resource/real-time-air-quality-index-various-locations)
state that:

- the resource has hourly granularity;
- it exposes a “Data API”;
- fields include country, state, city, station and coordinates, with pollutant
  records;
- field-instrument data are displayed live without human intervention and may
  contain abnormal or erroneous values;
- it is released under the National Data Sharing and Accessibility Policy.

The [Government Open Data License -
India](https://up.data.gov.in/godl) permits use, adaptation, publication and
commercial/non-commercial use with attribution, subject to its exclusions,
non-endorsement language and no-warranty terms.

#### Inference to test

This feed probably overlaps the same CPCB/SPCB measurements that reach OpenAQ.
Its value is therefore likely to be:

- a live-feed fallback;
- a latency/completeness comparison;
- a way to detect broker outages or station-name drift.

It should not be counted as independent evidence unless station/operator
provenance proves otherwise.

#### Required controls

- Use the resource page's “Data API” control to generate the current endpoint;
  do not hard-code an endpoint copied from a third-party tutorial.
- Store `retrieved_at`, the source's update timestamp, station string, city,
  state, pollutant, coordinates, unit, raw value and the exact API/resource
  identifier.
- Treat the feed as unvalidated live data until range, duplicate, unit and
  timestamp checks pass.
- Do not replace the frozen OpenAQ benchmark archive with this current feed.

### 4.3 Bihar

#### Verified facts

The official Bihar State Pollution Control Board
[environment-monitoring page](https://bspcb.bihar.gov.in/environment-monitoring-data.html)
links downloadable air-quality reports for:

- continuous air-quality monitoring in Patna in 2016; and
- Patna, Muzaffarpur and Gaya for 2016–2018.

The subsequent monthly links on that page are labelled water-quality data, not
air-quality data.

#### Not verified

- A BSPCB public API for 2023/24 hourly PM2.5.
- A BSPCB public 2023/24 Patna CAAQMS bulk archive.
- The time resolution inside the older PDFs or permission to redistribute
  extracted tables. The links were identified, but files were not downloaded in
  this audit.

#### Decision

Do not spend engineering time parsing the older reports before the live OGD and
one-day official-export pilots. They cannot fill the 2023/24 post-monsoon
station-history gap.

### 4.4 Uttar Pradesh

#### Verified facts

- The official [UP Environmental Compliance
  Portal](https://www.upecp.in/) links “Air Quality Data of different Cities of
  Uttar Pradesh” to the UPPCB city-data page.
- The Varanasi Smart City [OGD environment
  catalog](https://up.data.gov.in/catalog/environmentvaranasi-city) describes
  **monthly mean** PM2.5, PM10, NO2, SO2 and O3, provides a catalog API/ZIP
  route, was updated 2025-02-14, and is published under the government open-data
  framework.

#### Not verified

- That the linked UPPCB city-data page currently provides downloadable
  station-hour PM2.5 for Varanasi.
- A supported UPPCB machine API.
- Open redistribution terms for any data outside the OGD catalog.

#### Decision

The Smart City catalog can support a monthly context chart, not the hourly or
24-hour event benchmark. Manually test one day on the UPPCB route before any
implementation.

### 4.5 West Bengal

#### Verified facts

The WBPCB-linked [hourly data portal](https://aqmsdata.wbpcb.gov.in/hourly)
advertises “Today's Data” and “Hourly Historic Data” and exposes fields
including location, district, date, hour, coordinates, AQI and hourly PM2.5
average. The portal also says its sensor network is periodically calibrated
against reference monitors and is intended for research/broad trends rather
than regulatory determinations.

#### Not verified

- A documented public machine API.
- The exact instrument class and operator for every location.
- Bulk redistribution terms.

#### Decision

This may add spatial diagnostics around held-out Kolkata, but it cannot be
silently pooled with reference-grade CAAQMS observations. First match one
location to the registry and verify operator, instrument class, unit, timezone
and overlap with OpenAQ.

## 5. Actual CAMS forecast baseline

### 5.1 What the source provides

#### Verified facts

The official [CAMS global atmospheric-composition forecast
dataset](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=overview)
documents:

- global coverage on a 0.4° grid;
- forecasts initialized at 00:00 and 12:00 UTC each day;
- forecasts extending five days;
- one-hourly single-level output and three-hourly multi-level output;
- surface PM2.5 (`particulate_matter_2.5um`) in kg m-3;
- GRIB output and optional NetCDF conversion;
- DOI `10.24381/04a0b097`;
- CC BY licensing on the dataset page.

The official [CAMS global forecast data
documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=347605172)
provides web-form/CDS API access and request fields including dataset, date,
time, lead time, type, variable, area and format. It says the 00 UTC forecast
should be available by 10 UTC and the 12 UTC forecast by 22 UTC, but also warns
that ADS is not an operational time-critical service and delays can occur. The
[dissemination
schedule](https://confluence.ecmwf.int/spaces/DAC/pages/272310483/Dissemination%2Bschedule)
shows the same nominal times. API setup is documented on the [ADS API
page](https://ads.atmosphere.copernicus.eu/how-to-api).

### 5.2 Small, semantically exact request

Use the ADS dataset form and click **Show API request** at implementation time,
because API parameter names and format selectors can change. The required
selection is:

```text
dataset: cams-global-atmospheric-composition-forecasts
type: forecast
date: one YYYY-MM-DD initialization date
time: 12:00 UTC
lead times: 12, 24, 36, 48, 60, 72, 84, 96 hours
variable: particulate_matter_2.5um
area: north=30.0, west=72.0, south=8.0, east=90.0
format: GRIB for the reproducibility pilot
```

The proposed area is an India-focused bounding box, not an official domain.
The official documentation recommends GRIB where numeric precision matters;
NetCDF conversion should be tested as a convenience output, not assumed
bit-equivalent.

### 5.3 File and metadata contract

Store actual forecasts separately from initialization inputs, for example:

```text
data/cams_forecast/
  init=YYYY-MM-DDT12-00Z/
    pm25_leads_12_96.grib
    request.json
    provenance.json
```

`provenance.json` should contain:

- dataset identifier and DOI;
- generated request payload;
- request submission and completion UTC timestamps;
- initialization time and all lead/valid times;
- downloaded filename, byte size and SHA-256;
- variable name, source unit and conversion expression;
- grid, area, output format and library versions;
- any dataset/model-system version exposed by the file metadata;
- extraction method and station-registry version.

Convert kg m-3 to µg m-3 exactly once by multiplying by `1e9`. Keep the source
variable unchanged in the raw file. Unit tests must catch a second conversion.

### 5.4 Evaluation contract

For each `(init_time, station_id, lead_h)`:

1. compute `valid_time = init_time + lead_h`;
2. sample the actual CAMS forecast for that lead at the station using the same
   declared spatial-sampling convention for every model;
3. write a new column such as `cams_forecast_pm25`;
4. compare it with the same observation row used by persistence, climatology,
   fixed CAMS and Aurora;
5. report Very Poor+ event count, POD, FAR and CSI per lead and split, in
   addition to concentration metrics.

Do not interpolate one forecast initialization into another. Do not substitute
a later reanalysis. The baseline must have been available from the same
initialization cycle.

### 5.5 Live-feed implication

A 12 UTC CAMS forecast is nominally available by 22 UTC, which is 03:30 IST the
next day. A public feed must therefore show:

- forecast initialization time;
- source arrival time;
- data age/staleness;
- whether the displayed run is the expected cycle or a fallback;
- “experimental, not an official warning” language.

The latency must be measured for at least 14 daily retrievals before promising a
fixed publication time. That measurement is an engineering observation, not a
GPU task.

### 5.6 Licence

Follow the dataset-page CC BY requirement and the [Copernicus product
licence](https://ads.atmosphere.copernicus.eu/licences/licence-to-use-copernicus-products):
credit Copernicus/CAMS and ECMWF as required, identify modifications, avoid
implied endorsement, and retain the no-warranty notice. The exact attribution
string should be frozen in the product specification before public deployment.

## 6. Fire information

### 6.1 NASA FIRMS

#### Verified facts

The official [FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/)
documents:

- CSV requests of the form
  `/api/area/csv/[MAP_KEY]/[SOURCE]/[AREA]/[DAY_RANGE]`;
- a free MAP_KEY;
- west,south,east,north bounding-box order;
- a 1–5 day range;
- MODIS and VIIRS near-real-time sources;
- a quota of 5,000 transactions per ten minutes.

The [FIRMS API
tutorial](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html)
documents source selection and response fields. The official
[WFS page](https://firms.modaps.eosdis.nasa.gov/mapserver/wfs-info/) says the
WFS is updated every 15 minutes. NASA's Earthdata forum
[latency explanation](https://forum.earthdata.nasa.gov/viewtopic.php?t=5161)
describes near-real-time data as best-effort within roughly three hours and
notes that map and downloadable-file update timing differs.

NASA's [Earth science data-use
policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy)
states that NASA-led mission data are generally CC0 unless specifically marked,
while strongly requesting citation and prohibiting implied endorsement. The
specific FIRMS product citation and version still need to be stored.

#### Smallest useful live query

After obtaining a MAP_KEY through the official form, make one one-day query per
VIIRS source:

```text
https://firms.modaps.eosdis.nasa.gov/api/area/csv/
  [MAP_KEY]/VIIRS_SNPP_NRT/72,20,90,33/1
```

Repeat with the currently listed NOAA-20 and NOAA-21 NRT source identifiers
from the FIRMS source table. The proposed box is an Indo-Gangetic-basin context
box; it is intentionally broader than Patna or Varanasi because upwind fires
matter more than city-local fire dots.

Never place the MAP_KEY in Git, logs, screenshots, browser URLs shared publicly,
or client-side application code. The production UI should read a server-side
cached derivative rather than call FIRMS from every browser.

#### Role and incremental value

**Verified:** FIRMS supplies satellite fire detections, not PM2.5 observations
and not a surface-concentration forecast.

**Inference:** it can explain where recent burning was detected and may add
some fresh information not represented in prior-day fire emissions. However,
CAMS already incorporates GFAS fire emissions. Predictive gain is therefore
uncertain and must be tested:

- base correction model;
- same model plus only pre-initialization FIRMS aggregates;
- identical splits and event metrics;
- retain only if held-out-city POD/CSI improve without unacceptable FAR.

Start with UI dots/counts and a clear “satellite-detected fires, not proof of
city pollution source” label.

### 6.2 GFAS

#### Verified facts

The official [CAMS GFAS v1.2
dataset](https://ads.atmosphere.copernicus.eu/datasets/cams-global-fire-emissions-gfas?tab=overview)
provides:

- daily mean fire-emission estimates on a 0.1° grid;
- coverage from 2003 through 2025-12-03;
- fire-emission fluxes including PM2.5;
- DOI `10.24381/a05253c7`;
- CC BY licensing;
- an explicit notice that this public dataset was discontinued on
  2025-12-03.

The CAMS forecast documentation also explains that GFAS fire information is
used in the CAMS atmospheric-composition forecast. An official [CAMS evaluation
report for winter
2026](https://atmosphere.copernicus.eu/sites/default/files/publications/45_CAMS2_82_bis_2025SC1_D82_bis.1.1.1-DJF2026.pdf)
references a newer operational GFAS version internally, but this audit did not
verify a public, current, documented ADS/API replacement for the discontinued
v1.2 feed.

The v1.2 archive is accessible through the ADS web form/API and has daily
temporal resolution. A live-data latency is no longer applicable after the
discontinuation date; ADS queue time for an archive request is not forecast
latency.

#### Decision

- Use v1.2 only for retrospective 2003–2025 fire-emission diagnostics.
- Do not make it a dependency of the live product.
- Do not describe it as independent of CAMS.
- Do not begin a feature-integration workstream until a supported current
  public source is verified.

## 7. Sentinel-5P aerosol products

### 7.1 Product meaning

#### Verified facts

The official [Sentinel-5P ultraviolet aerosol-index product
page](https://sentinels.copernicus.eu/data-products/-/asset_publisher/fp37fc19FN8F/content/sentinel-5-precursor-level-2-ultraviolet-aerosol-index)
describes UV aerosol index as a daily global indicator for absorbing aerosols
such as smoke, dust and volcanic ash.

The [product user
manual](https://sentinels.copernicus.eu/documents/247904/2474726/Sentinel-5P-Level-2-Product-User-Manual-Aerosol-Index-product)
explains that positive UVAI is associated with absorbing aerosols and that the
quantity depends on aerosol optical thickness, single-scattering albedo,
aerosol-layer height and surface albedo. It recommends a high quality-value
threshold for many uses and documents sun-glint and other artifacts.

The [Copernicus Data Space Sentinel-5P L2
documentation](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S5PL2.html)
documents collection `sentinel-5p-l2`, UVAI bands including
`AER_AI_340_380` and `AER_AI_354_388`, and `NRTI`, `OFFL` and `RPRO`
timeliness classes. If timeliness is not constrained, the service prefers the
more consolidated OFFL/RPRO product over NRTI.

The current TROPOMI validation service
[warns](https://mpc-vdaf.tropomi.eu/aerosols?showall=1) that UVAI is not a
direct geophysical surface quantity and documents a small product offset under
evaluation after a late-2025 processor change.

### 7.2 Limitations

- UVAI is **not** surface PM2.5 and cannot be ground truth.
- Satellite overpass timing is sparse compared with hourly scoring.
- Clouds do not make UVAI impossible in the same way they often make AOD
  impossible, but cloud, surface, viewing and sun-glint conditions still affect
  interpretation and quality.
- A plume aloft may not reach a surface station.
- NRTI availability latency must be measured in the proposed pilot; this audit
  did not verify a binding latency guarantee for this exact S5P product.
- Processor version and timeliness class can change the numerical series.

### 7.3 Pilot and role

Use the official CDSE browser or Catalog/Process API:

```text
collection: sentinel-5p-l2
product/band: AER_AI_340_380
timeliness: NRTI
time range: one UTC day
bbox: west=72, south=20, east=90, north=33
quality: follow the current product readme/manual
```

For each result, record acquisition time, publication/availability time,
timeliness class, orbit/product identifier, processor version and quality
threshold. The first output should be an explanatory UI layer labelled
“absorbing aerosol seen from space,” not an estimated ground PM2.5 map.

Only after a season of coverage/latency statistics should a pre-initialization
aggregate be tested as a predictive feature. Use the same held-out-city event
gate as FIRMS.

The [Copernicus Data Space terms](https://dataspace.copernicus.eu/terms-and-conditions)
distinguish the open Sentinel data from portal/site assets. Reuse the data with
required attribution; do not copy portal map imagery into the product.

## 8. Independent historical and research archives

### 8.1 Aakash Project: the most relevant verified post-monsoon archive

#### Verified facts

The Aakash Project's official [dataset
page](https://aakash-rihn.org/en/data-set/) offers ZIP archives of hourly mean
PM2.5 and CO for September–November 2022, 2023 and 2024, with station
locations and a readme. It describes an India-Japan campaign using CUPI-G
low-cost sensors across Punjab, Haryana, Delhi-NCR and parts of western Uttar
Pradesh.

The [temporary 2024
archive](https://aakash-rihn.org/en/data-set2/) documents daily CSVs with:

- timestamp in IST;
- PM2.5 in µg m-3;
- temperature and relative humidity;
- station/instrument identifier and coordinates.

The official dataset page licenses the work under **CC
BY-NC-ND 4.0** and strongly encourages users to contact the project leader.
The related Zenodo record
[15702750](https://zenodo.org/records/15702750) contains derived daily map
plots under CC BY 4.0; those plots are not the hourly station archive.

#### What it can and cannot do

It can help answer:

- whether the product depicts the timing and regional movement of major
  northwest-India post-monsoon episodes;
- whether FIRMS/satellite/fire narratives are consistent with an independent
  campaign;
- how low-cost sensor and reference-station event timing differ.

It cannot, without additional stations:

- validate Patna or Varanasi;
- substitute for CPCB/SPCB CAAQMS truth;
- establish all-season skill;
- be assumed safe for transformed, redistributed, or commercial product use.

Because “NoDerivatives” may conflict with publishing cleaned subsets,
aggregations or derived product files, obtain written clarification before
integration. A private, non-public evaluation may still have research value,
but the licence and project guidance must be reviewed by the user, not inferred
by code.

### 8.2 Other public research records reviewed

#### Stanford/CREA daily 10 km India PM2.5

[Zenodo 13694585](https://zenodo.org/records/13694585) provides daily 10 km
PM2.5 estimates for India through 2023 from machine-learning models using
satellite and other inputs. The authors report spatial cross-validation and
publish predictions, scripts and source data.

Use it only as a gridded daily plausibility/context comparison:

- it is model-derived, not station truth;
- it may share CPCB monitor inputs with this project;
- its 2023 files end on 2023-09-30, before most of the desired post-monsoon
  period;
- the Zenodo record's licence field was blank when reviewed, so redistribution
  rights need clarification.

#### CPCB-derived trend spreadsheet

[Zenodo 11107527](https://zenodo.org/records/11107527) is CC BY 4.0, but its
description says it contains processed monthly and annual PM2.5 trends derived
from CPCB data. It is not hourly event truth.

#### High-time-resolution trace-element campaign

[Zenodo 12212768](https://zenodo.org/records/12212768) is a CC BY 4.0
measurement-report dataset for PM2.5 trace elements at three Indo-Gangetic
Plain urban sites. It is valuable source-composition research, not a broad
2023/24 station PM2.5 archive.

### 8.3 Negative result and next route

No source reviewed here meets all of these conditions:

- Patna or Varanasi station coverage;
- hourly PM2.5;
- October–November 2023 or 2024;
- documented provenance;
- independent enough to add information beyond the current OpenAQ/CPCB route;
- a licence that clearly permits the intended public reuse.

That gap is real. The smallest responsible next action is a written request to
CPCB, BSPCB and UPPCB specifying:

```text
Cities: Patna-area registry stations and Varanasi registry stations
Pollutant: PM2.5 concentration, not AQI
Time basis: native hourly records with timezone and averaging period
Period: 2023-10-01 through 2024-11-30
Metadata: station ID/name, coordinates, operator, instrument/method,
          unit, QA flag, missing-value code, update/revision timestamp
Use: reproducible non-commercial research benchmark and public aggregate metrics
Request: supported delivery method and explicit attribution/redistribution terms
```

If data are supplied, hash and seal the raw files before looking at model
results. Decide in advance whether the source is a new external test set, a
diagnostic-only set, or eligible training data. It cannot be all three after
results are seen.

## 9. Exact smallest pilots

These pilots are intentionally tiny. Their purpose is to verify schema,
timestamps, units, latency, overlap and rights before any engineering
workstream or bulk request.

### Pilot A — official current ground feed, Patna and Varanasi

1. Open the OGD [real-time AQI
   resource](https://www.data.gov.in/resource/real-time-air-quality-index-various-locations).
2. Use **Data API** and the official API-key flow.
3. In the generated API controls, request five records for:
   `city=Patna`, pollutant `PM2.5`.
4. Repeat for `city=Varanasi`, pollutant `PM2.5`.
5. Save only the request template with the key replaced by
   `${DATA_GOV_IN_API_KEY}` and ten response rows in a local ignored scratch
   directory.
6. For each city, compare station strings and coordinates against
   `data/stations.csv`. The expected registry counts are seven Patna-labelled
   rows and four Varanasi rows; the live feed may legitimately differ.
7. Record API response time, latest source timestamp, timezone, unit, missing
   values, duplicate station/pollutant rows and any limit/pagination metadata.
8. Repeat at the same local times on three days. This tests current
   availability, not historical depth.

**Pass condition:** concentration values, units, timestamps and station
identities are explicit; at least one registry station per city can be matched
without name-only guessing; GODL attribution can be attached to the stored
sample.

**Stop condition:** only AQI category/index is returned, PM2.5 units or time
basis are ambiguous, or station identity requires fuzzy matching with no
coordinates.

### Pilot B — supported historical ground export

1. Open the public [CPCB CCR](https://airquality.cpcb.gov.in/ccr/) manually.
2. Check whether its public interface offers a documented history/report/export
   function; do not inspect hidden network endpoints.
3. If available, select **one station**, **PM2.5**, and one 24-hour period:
   2024-11-15 00:00–23:59 in the portal's displayed timezone.
4. Use `IGSC Planetarium Complex, Patna - BSPCB`, then
   `Ardhali Bazar, Varanasi - UPPCB`. These exact strings occur in the current
   repository registry; a board portal may expose a different stable identifier,
   which must be recorded rather than overwritten.
5. Before download, capture the page's attribution/terms text and the displayed
   timezone/averaging period.
6. Download only through the visible supported export control.
7. Record filename, format, byte size, hash, column names, unit, timezone,
   missing-value convention, QA flags and station identifier.
8. If no supported export or reuse terms are visible, stop and send the narrow
   formal request in §8.3.

**Pass condition:** a visible supported export produces station-hour PM2.5 with
clear time/unit/station metadata and the data custodian confirms intended use.

**Stop condition:** captcha automation, copied session tokens, reverse-engineered
endpoints, unclear units, or no reuse guidance.

For UPPCB, the [UPECP portal](https://www.upecp.in/) city-data link may be
checked manually for the same one-day Varanasi request. For BSPCB, the public
[environment-monitoring page](https://bspcb.bihar.gov.in/environment-monitoring-data.html)
does not currently establish a 2023/24 hourly route; do not bulk-download its
older PDFs.

### Pilot C — actual CAMS baseline

1. Open the [CAMS dataset
   form](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=download).
2. Select the frozen training initialization date `2025-11-06`, 12:00 UTC,
   surface PM2.5, leads 12…96 by 12 hours, GRIB, and the two-city pilot box
   `north=26.2, west=82.4, south=24.8, east=85.6`. This box covers the current
   Patna/Varanasi registry coordinates with a grid-cell buffer. Use the wider
   India box in §5.2 only after this pilot passes.
3. Click **Show API request**; save the generated payload with no credentials.
4. Retrieve that one request through the existing ADS credentials.
5. Inspect the file metadata and verify eight lead times and valid times.
6. Sample the seven Patna-labelled and four Varanasi stations.
7. Verify one conversion from kg m-3 to µg m-3 and retain raw and converted
   columns.
8. Compare the same rows with fixed lead-zero CAMS and raw Aurora. Do not fit
   anything in this pilot.

**Pass condition:** all eight leads, valid times, units, station samples,
request metadata and hash are reproducible.

### Pilot D — FIRMS explanatory layer

1. Request a free MAP_KEY from the official [FIRMS API
   page](https://firms.modaps.eosdis.nasa.gov/api/area/).
2. Query the one-day Indo-Gangetic bounding box in §6.1 once for each currently
   documented VIIRS NRT source.
3. Cache the raw response server-side; never expose the key.
4. Record source, satellite/instrument, acquisition date/time, latitude,
   longitude, confidence, fire-radiative-power field if present, retrieval time
   and product citation.
5. Display dots/counts only, with the source/latency disclaimer.

**Pass condition:** schema and source timing are explicit, queries remain within
quota, and no client receives the key.

### Pilot E — Sentinel-5P explanatory layer

1. Create/sign in to the official Copernicus Data Space account.
2. Search one UTC day over `72,20,90,33` for
   `sentinel-5p-l2`, aerosol index, with timeliness fixed to `NRTI`.
3. Retrieve only the smallest product/subset needed to inspect
   `AER_AI_340_380`, quality flags and metadata.
4. Store acquisition time, availability time, orbit/product ID, processor
   version, timeliness and quality rule.
5. Render it as an “absorbing aerosol” layer, never PM2.5 concentration.

**Pass condition:** a repeatable NRTI query, metadata-complete output, measured
latency and an honest label.

### Pilot F — Aakash research comparison

Do not download the full archive first. Email the project contact linked on the
[dataset page](https://aakash-rihn.org/en/data-set/) with:

- the non-commercial research and possible public-demo purpose;
- the exact desired 2023/24 hourly files;
- the intended cleaning, aggregation and event-metric transformations;
- whether transformed data or only aggregate charts would be published;
- a request for written permission/required attribution under BY-NC-ND.

If permission is clear, download one station-week, save the readme/licence and
hash, and test timestamp/unit/coverage parsing. Keep it diagnostic-only and
outside the train/calibration pool.

## 10. Ranked recommendations

### P0 — do now

1. Add the actual CAMS +12…+96 forecast baseline as separate data and columns.
2. Run the two-city OGD current-feed pilot.
3. Run one manual supported historical-export test for Patna and Varanasi.
4. Freeze source attribution, provenance and staleness fields in the live-feed
   specification before implementation expands.

### P1 — useful for the first public experimental feed

5. Add FIRMS VIIRS NRT as an explanatory map/count layer with cached retrieval,
   latency and “not attribution” language.
6. Add Sentinel-5P UVAI only if the NRTI pilot shows acceptable coverage and
   latency; label it as absorbing aerosol, not surface PM2.5.
7. Submit narrow 2023/24 hourly-data requests to CPCB/BSPCB/UPPCB.

### P2 — research strengthening

8. Seek permission to use Aakash hourly 2023/24 data for an independent
   northwest-India fire-season diagnostic.
9. Evaluate the Stanford/CREA gridded product only after licence clarification
   and overlap analysis.
10. Test FIRMS or satellite inputs in one-at-a-time ablations only after the
    CAMS forecast baseline and current benchmark are valid.

### Do not prioritize

- scraping undocumented CPCB/SPCB endpoints;
- automating captcha/login portals;
- parsing old BSPCB PDFs for the current benchmark;
- using monthly Varanasi data as event truth;
- calling Sentinel-5P UVAI or a gridded model “ground truth”;
- depending on discontinued GFAS v1.2 for live operation;
- pooling low-cost WBPCB/Aakash sensors with CAAQMS without a declared sensor
  class and validation;
- adding many correlated features before proving incremental held-out-city
  Very Poor+ event skill.

## 11. Acceptance criteria for any new source

A source is not “integrated” until all applicable checks pass:

- **Identity:** stable source, station/product and variable identifiers.
- **Time:** UTC conversion, source timezone, averaging interval,
  initialization, lead/valid time, acquisition time and availability time.
- **Units:** source unit preserved and exactly one named conversion.
- **Quality:** source QA flags preserved; missing and invalid values explicit.
- **Availability:** measured latency, failure rate and stale-data behavior.
- **Provenance:** request, version, retrieval time, raw hash and transformation
  version.
- **Rights:** licence/terms saved; attribution and redistribution path clear.
- **Leakage:** every predictive value existed before forecast initialization.
- **Independence:** shared upstream inputs disclosed; no double-counting as
  independent validation.
- **Scientific value:** held-out-city Very Poor+ event counts, POD, FAR and CSI
  reported with and without the source.
- **Product honesty:** observations, forecasts, features and context layers
  visually and verbally distinct.

Passing these checks may show that a source is useful only for the UI or for
diagnosis. That is still a valid outcome. More data are valuable only when they
add information without weakening the benchmark's provenance or leakage
controls.
