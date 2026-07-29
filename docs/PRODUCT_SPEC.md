# IndiaAQBench public product specification

Status: proposed implementation contract
Audience: product, science, data, live-pipeline, and web workstreams

## 1. Repository facts and explicit assumptions

This specification separates what exists from what is proposed.

What exists in the repository:

- A retrospective pipeline downloads CAMS zero-hour forecast fields (used as
  analysis), initializes Aurora at 12:00 UTC, rolls it out at 12-hour steps from
  +12 h through +96 h, and samples the grid at registered stations.
- The evaluator matches predictions to OpenAQ observations, builds persistence,
  station climatology, CAMS-analysis-held-constant, actual lead-dependent CAMS,
  and raw Aurora baselines, and reports concentration, category, and Very
  Poor+ event metrics.
- The benchmark covers nine cities. Kanpur, Kolkata, and Varanasi are held-out
  cities; Delhi is a diagnostic city, not the target.
- The official Indian PM2.5 category thresholds refer to a 24-hour averaging
  period. Applying those thresholds to instantaneous values is a sensitivity
  analysis, not the public headline.
- No live scheduler, public endpoint, immutable forecast ledger, validated
  forecast feed, or complete 56-date current-registry rollout exists. The
  actual lead-dependent CAMS baseline code is implemented and integrated, and
  an owner-only illustrative website is deployed.

Assumptions this product contract makes:

- The separate operational `cams_forecast` method is implemented. The
  lead-zero fixed-field evaluator method is named `cams_lead0_fixed`; neither
  has a complete 56-date score until the pending rollout finishes.
- The first live release covers the existing nine-city registry. Expansion is a
  later, separately validated step.
- The live pipeline will be generalized from one 12:00 UTC initialization per
  date to the latest complete 00:00 or 12:00 UTC CAMS cycle.
- The public product may launch with raw Aurora if no correction method has
  passed the event-safety gate. An unsafe or unavailable correction is never a
  launch blocker and is never silently substituted.
- “CAMS forecast” means actual CAMS values at each future lead. The separate
  `cams_lead0_fixed` evaluator method is the CAMS initial field carried forward
  and is labeled “CAMS starting field held constant.”
- Product copy asserting that a particular city has no other forecast service
  requires a source check immediately before publication. The stable claim is
  that the product is designed for underserved Indian cities and transparent
  evaluation of the public/global forecasting tier.

## 2. Product promise

### Single-sentence purpose

**Show whether a global atmospheric foundation model, recent public surface
observations, and limited compute can produce useful, openly verified PM2.5
forecasts for underserved Indian cities.**

### Primary audiences

1. Residents and local organizations who want an understandable experimental
   view of pollution over the next four days.
2. Researchers and public-interest technologists who want the raw forecast,
   correction, provenance, cost, and continuing scorecard.
3. City and air-quality practitioners evaluating whether a low-compute system
   deserves deeper local validation.
4. Contributors who want to reproduce, inspect, or extend the work.

The interface must work for a non-technical visitor. Technical details remain
available without becoming prerequisites for reading the forecast.

### Public claim

At the first public release, the product may claim:

> IndiaAQBench is an experimental, openly evaluated PM2.5 forecast built from
> Aurora, CAMS atmospheric inputs, recent public surface observations, and
> limited compute. It publishes the raw model, any correction, simple
> baselines, data freshness, and its accumulating record of hits and misses.

Every results page must disclose that the temporal cutoff was revised once to
2025-12-01 before adaptation on the revised split, as required by the benchmark
contract.

### Non-claims

The product must not claim that it:

- is an official AQI or public-health warning service;
- replaces CPCB, state pollution-control boards, or official local guidance;
- has proven year-round operational reliability before the evidence exists;
- is accurate in every city, season, station neighborhood, or extreme event;
- reconstructs street-level pollution from a roughly 0.4-degree global model;
- provides source attribution unless a separate validated method does so;
- provides a probability of an event unless a probabilistic method has been
  implemented and calibrated;
- is zero-shot in a held-out city when a correction used trailing observations
  from that target station.

Negative and inconclusive results are part of the product, not hidden defects.

## 3. Product principles

1. **Underserved cities first.** Varanasi is the default landing city. Patna,
   Kanpur, and Lucknow are first-level alternatives. Delhi appears under
   “More cities” as a data-rich diagnostic reference.
2. **Event usefulness before average error.** The first performance view is
   Very Poor+ detection, with counts. MAE is secondary.
3. **Raw output remains visible.** A correction never replaces the raw Aurora
   record.
4. **Observations and forecasts are different.** OpenAQ is labeled as observed
   surface data; CAMS and Aurora are model-derived estimates.
5. **Freshness before polish.** A stale, delayed, or partially supported result
   is visibly marked.
6. **No implied precision.** Public values are rounded to whole micrograms per
   cubic metre. Exact machine values remain in downloadable data.
7. **Every forecast earns its evidence later.** Once observations arrive, the
   saved forecast is verified without being overwritten.
8. **Low compute is measured, not marketed vaguely.** Runtime, hardware, and
   estimated cost are shown with their assumptions.

## 4. Information hierarchy

The landing and city pages follow this order.

### Level 1 — “What is expected?”

- City selector, defaulting to Varanasi.
- System status and the age of the atmospheric initialization.
- Latest available observed PM2.5 and the number of reporting stations.
- Forward-looking rolling 24-hour PM2.5 estimates for the next available
  windows, with category names and explicit window start/end times.
- A plain statement such as “3 of 4 modeled station locations are Very Poor or
  above in this 24-hour window,” rather than an invented official city AQI.

### Level 2 — “Where and when?”

- Station map.
- Rolling 24-hour window selector.
- Station-level observed and forecast values.
- The city median and station range, with the contributing station count.

### Level 3 — “What did each method say?”

- Corrected Aurora, if it passed its scientific and operational gates.
- Raw Aurora.
- Actual CAMS forecast.
- Persistence from the last timely OpenAQ observation.
- “CAMS starting field held constant” as a technical baseline while that is the
  only CAMS comparator available.

### Level 4 — “Has it worked?”

- Per-city, per-lead 7-, 30-, and 90-day scorecards.
- Very Poor+ hits, misses, false alarms, POD, FAR, and CSI.
- Verified sample count, observed-event count, and forecast-event count.
- Category accuracy and MAE as secondary measures.
- A visible “not enough events yet” state.

### Level 5 — “How was it made?”

- One-page method explanation.
- Data and model provenance.
- Split and evaluation explanation.
- Limitations and failure history.
- Runtime and cost ledger.
- Repository, reproducibility instructions, and downloadable forecast files.

## 5. City page contract

### Header

The header contains:

- city name;
- “Experimental research forecast” badge;
- last successful publication time in IST, with UTC in the accessible label;
- initialization time and current age;
- overall cycle status: `current`, `delayed`, `stale`, or `unavailable`;
- link to official local/CPCB guidance where a verified stable URL exists.

### Current observation

Show:

- the median of the latest eligible station observations;
- minimum and maximum station values;
- `n reporting / N registered`;
- time of the oldest and newest contributing observation;
- “Observed by OpenAQ/provider” label.

This is a monitoring summary, not an official city AQI. If fewer than two
stations are eligible, show station values but suppress the city median.

### Forecast summary

For each rolling 24-hour window and method, calculate the city display summary
from eligible station forecasts:

- median PM2.5;
- minimum and maximum;
- station count;
- count and fraction of stations at Very Poor+;
- category distribution across stations.

The city median is a navigation aid, not the evaluation target. Scientific
verification remains station-level before any explicitly defined aggregation.

### Trend

The default chart overlays:

- observations;
- corrected Aurora, if available;
- raw Aurora;
- actual CAMS forecast;
- persistence.

The chart must not connect across missing periods. Hover/focus reveals the
method, value, averaging window, valid time, initialization time, lead, and
quality flags.

### Evidence panel

Show a compact scorecard for the selected city and lead. The first row is event
skill; MAE never precedes it. Include definitions in plain language:

- **POD:** of the Very Poor+ periods that happened, the fraction forecast.
- **FAR:** of the Very Poor+ forecasts issued, the fraction that were false.
- **CSI:** hits divided by hits, misses, and false alarms combined.

If there are no observed events, POD and CSI are `not available`, not zero.
If there are no forecast events, FAR is `not available`, not zero.

## 6. Interactions

### City

- Search and keyboard-select any supported city.
- Quick choices: Varanasi, Patna, Kanpur, Lucknow.
- Preserve the selected city in the URL.
- Never rank cities as “best” or “worst” on sparse observations without showing
  coverage.

### Map

- Default to modeled station locations, not a falsely high-resolution
  interpolated heat map.
- Marker fill encodes the selected value; a text/icon state also encodes the
  category so color is not the only signal.
- Selecting a station synchronizes the chart and scorecard.
- A later gridded layer must retain the native grid outline and the label
  “model-derived grid estimate; not a street-level measurement.”

### Time

- Default view: forward-looking rolling 24-hour windows.
- Technical view: initialization and +12 h through +96 h instantaneous model
  outputs.
- Every time label includes date, IST, forecast lead, and averaging window.
- Animation has play/pause, respects reduced-motion preferences, and never
  auto-plays for screen-reader users.

### Method

- Default to the certified public method for that cycle.
- A compare toggle shows raw Aurora, corrected Aurora, CAMS, and persistence.
- Unavailable methods remain listed with an explanation; missing values are
  never plotted as zero.
- If the public method falls back, the fallback method is named above the
  forecast and in every tooltip.

## 7. Averaging and category contract

### Public headline: forward rolling 24-hour estimate

Indian PM2.5 category thresholds are applied only to a 24-hour value in the
headline product.

Aurora currently produces 12-hour snapshots. For MVP, a forward 24-hour mean
starting at lead `s` is approximated by piecewise-linear integration of the
values at `s`, `s+12`, and `s+24`:

```text
mean_24h(s) = (value_s + 2 * value_s+12 + value_s+24) / 4
```

Windows may start at 0, 12, 24, ..., 72 hours. Lead zero is the initialized
state for raw Aurora/CAMS, the contemporaneous persistence observation for
persistence, and an explicitly generated lead-zero value for a correction.
If any required point is unavailable, that method’s window is unavailable.

The UI label is:

> Forward 24-hour PM2.5 estimate, approximated from 12-hour model outputs

This is not an official hourly-resolved AQI calculation. A later model that
produces hourly values may replace the approximation only with a schema and
method-version change.

### Technical sensitivity: instantaneous thresholds

The +12 h to +96 h view may optionally color instantaneous outputs using the
same concentration bands, but it must be titled:

> Instantaneous concentration threshold sensitivity — not official 24-hour AQI

Headline and sensitivity results must never be pooled in one scorecard.

## 8. Method display contract

| Public label | Method ID | Meaning |
|---|---|---|
| Corrected Aurora | `corrected` | Raw Aurora plus the certified, versioned correction for this cycle |
| Raw Aurora | `raw_aurora` | Unmodified Aurora rollout |
| CAMS forecast | `cams_forecast` | Actual CAMS value at the corresponding future lead |
| Persistence | `persistence` | Timely observed PM2.5 at initialization carried forward |
| CAMS starting field held constant | `cams_analysis_persistence` | CAMS lead-zero analysis carried forward; evaluator method `cams_lead0_fixed` |

Rules:

- OpenAQ is the verifying observation source and the source of the persistence
  baseline; it is not presented as a future forecast.
- `cams_analysis_persistence` must never be labeled simply “CAMS forecast.”
- The selected correction method and support data are shown by version.
- If corrected output is unavailable, raw Aurora remains visible.
- If Aurora is unavailable and a complete actual CAMS forecast exists, CAMS may
  be the named fallback.
- Climatology may appear in the technical benchmark view but is not required in
  the MVP city chart.

## 9. Event and scorecard contract

The headline event is station-level forward-24-hour PM2.5 at or above
121 µg/m³.

For every city, lead/window, method, and scorecard period, publish:

- `verified_pairs`;
- `observed_events`;
- `forecast_events`;
- `hits`;
- `misses`;
- `false_alarms`;
- POD;
- FAR;
- CSI;
- exact and adjacent category accuracy;
- MAE and bias as secondary metrics.

Pooled metrics are calculated from pooled contingency counts, not by averaging
city percentages. Every pooled result links to its per-city breakdown.

Display rules:

- Fewer than five observed events: show counts and metrics with “very limited
  event evidence.”
- Five to nineteen observed events: show “limited event evidence.”
- Twenty or more: remove the sparse-event label, while retaining counts.
- These labels communicate sample support, not statistical certainty.

## 10. Freshness, support, and uncertainty language

### Observation freshness

Measured from the latest contributing observation to page generation:

- `fresh`: at most 3 hours old;
- `delayed`: more than 3 and at most 12 hours old;
- `stale`: more than 12 and at most 24 hours old;
- `unavailable`: no eligible observation in the last 24 hours.

### Forecast freshness

Measured from atmospheric initialization:

- `current`: at most 18 hours old;
- `delayed`: more than 18 and less than 30 hours old;
- `stale`: at least 30 hours old;
- `unavailable`: no valid published forecast covers the requested time.

These initial thresholds are operational assumptions and must be re-evaluated
using shadow-mode CAMS and OpenAQ latency.

### Support, not vague confidence

Until calibrated forecast probabilities exist, the interface uses **data
support**, not “high/medium/low confidence.”

For each corrected station forecast, show:

- correction method and version;
- number of prior observations used;
- age of the newest supporting observation;
- whether the station had enough support for a local correction;
- whether a pooled/regional correction or raw fallback was used;
- any missing-input or range flags.

Do not show a percent confidence derived from data freshness.

## 11. Compute and cost transparency

Every cycle exposes:

- GPU/CPU hardware type;
- model inference seconds;
- total cycle duration;
- peak memory when available;
- GPU-hours;
- estimated cost and currency;
- price source/rate and whether spot pricing was used;
- number of cities, stations, leads, and completed forecasts;
- retry count;
- code and model version.

The public methodology page provides both per-cycle and cumulative cost. Cost
must be labeled “estimated” unless taken from a reconciled invoice. Engineering
time is reported separately from cloud compute.

## 12. Accessibility and comprehensibility

MVP requirements:

- WCAG 2.2 AA color contrast.
- Keyboard access to city, time, method, map-location, and chart controls.
- Visible focus states.
- Text/category/icon alternatives to every color encoding.
- Screen-reader summaries for charts and maps.
- Table alternative for every chart.
- No required hover-only interaction.
- Reduced-motion support.
- Mobile layout at 320 CSS pixels.
- Plain-language definitions next to POD, FAR, CSI, PM2.5, persistence, CAMS,
  Aurora, correction, and “held out.”
- Units always rendered as `µg/m³`; dates shown in IST with UTC accessible.
- A low-bandwidth page containing the latest text forecast and scorecard.

## 13. Disclaimer

The following text appears on every forecast page, above the footer:

> **Experimental research forecast — not an official warning.** IndiaAQBench
> provides model-derived PM2.5 estimates for research and transparency. It may
> be delayed, incomplete, or wrong, especially during local or rapidly changing
> pollution events. Do not use it as the sole basis for health, safety, or
> regulatory decisions. Follow CPCB, local authorities, and qualified health
> guidance.

Short status cards may use “Experimental — not an official warning,” linked to
the full text. The full text must not be hidden behind acceptance.

## 14. MVP and later scope

### MVP

- Nine existing benchmark cities, with Varanasi as default.
- Static, versioned public JSON consumed by a client-rendered site.
- Latest cycle plus downloadable history.
- Current observations and station map.
- Raw Aurora.
- Corrected Aurora only if certified.
- Persistence.
- Explicit CAMS-analysis-held-constant baseline; actual CAMS forecast if ready.
- Rolling 24-hour headline and separate instantaneous sensitivity view.
- Per-city 7/30/90-day scorecards as evidence accumulates.
- Freshness, support, provenance, compute, cost, limitations, and disclaimer.
- No account, notification, or precise-user-location collection.

### Later

- Complete 56-date CAMS forecast data and scorecards if not ready for MVP.
- Additional cities in monitored/intermittent/unmonitored tiers.
- Fire, dust, satellite, boundary-layer, and wind context.
- Probabilistic Very Poor+ forecasts and reliability diagrams.
- Gridded native-resolution view.
- Notifications only after alert quality and delivery failure modes are
  validated.
- Multilingual interface.
- Download/API stability commitments.
- Independent post-monsoon and multi-season prospective reports.

Out of scope until separately validated:

- official warnings;
- personalized health advice;
- street-level inference;
- unqualified source attribution;
- a national city ranking;
- full-model fine-tuning as a prerequisite for launch.

## 15. Launch gates

### Repository/public-documentation gate

- README-level purpose, current state, limitations, architecture, quick start,
  reproducibility path, license/attribution, and roadmap are accurate.
- No placeholder metrics are presented as real.
- Screenshots and demonstration data are labeled historical or synthetic.
- Secrets, private datasets, machine-specific paths, and stale claims are
  absent from the public repository.

### Scientific gate

- The current frozen-date, current-registry retrospective rollout is complete.
- `python -m src.eval.audit` passes before publishing any benchmark table.
- Raw Aurora, persistence, and the existing CAMS-analysis baseline are scored
  per city and lead with event counts.
- The rolling-24-hour headline path and instantaneous sensitivity path are
  evaluated separately.
- A correction is selected publicly only if it passes the repository’s
  no-harm-on-events rule on the required temporal, L1, and L2 evaluations.
- If no correction passes, the MVP launches with raw Aurora and says so.

### Data/provenance gate

- Every published forecast has a model version, code commit, station-registry
  version, input timestamps, input retrieval timestamps, and checksums.
- Observation and forecast licenses/attributions have been reviewed.
- CAMS-analysis persistence and actual CAMS forecast are unambiguously named.

### Operational gate

- At least 14 consecutive shadow-mode days and 20 completed forecast cycles.
- At least 90% of expected cycles publish within six hours of confirmed input
  availability; every miss is represented in the status history.
- Retry, stale-data, missing-OpenAQ, failed-correction, GPU-failure, fallback,
  and atomic-publication paths have been exercised.
- A forecast already published cannot be mutated.
- Credentials are absent from logs and artifacts.

The team should aim for 30 shadow-mode days before broad promotion, but the
14-day/20-cycle gate permits an explicitly labeled early public beta.

### User-experience gate

- A non-technical usability check confirms that visitors can identify the
  city, forecast window, units, freshness, selected method, and disclaimer.
- Keyboard, screen-reader, reduced-motion, mobile, and low-bandwidth checks
  pass.
- Empty, sparse, delayed, stale, and unavailable states are understandable.

### Promotion gate

Public beta and broad promotion are different decisions. Promote broadly only
after:

- the feed has remained public and auditable for at least 30 days;
- the live scorecard contains enough verified pairs to avoid an empty showcase;
- known failures and sparse-event counts are visible;
- the repository can reproduce the displayed benchmark;
- the post text describes the work as an experiment with accumulating evidence,
  not a completed operational service.
