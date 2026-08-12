# IndiaAQBench live-feed implementation specification

Status: proposed implementation contract
Companion: `docs/PRODUCT_SPEC.md`

Strategic note (2026-08-12): the ledger, provenance, freshness, and failover
contracts remain valid, but the target/default city and public claim are under
revision after `TARGET_REEVALUATION.md`. Do not deploy the Varanasi fixtures as
evidence or preserve the old “unserved city” story in product copy.

## 1. Scope and assumptions

This document specifies a twice-daily experimental PM2.5 forecast feed. It does
not claim that the live system exists.

Repository facts relevant to implementation:

- `src/data/cams_composition.py` downloads CAMS lead-zero fields at 00:00 and
  12:00 UTC for one date, and `src/pipeline/orchestrate.py` initializes Aurora
  at 12:00 UTC.
- The current orchestrator is date-oriented, writes one Parquet file per date,
  stamps the station-registry version, and has registry-aware resume behavior.
- The orchestrator output contains a CAMS-derived lead-zero initial state,
  CAMS's actual +12 h through +96 h forecast, and Aurora samples on identical
  station/lead support.
- OpenAQ archival rows contain observation timestamps, values, station
  identity, coordinates, and city, but not the time at which an observation
  first became available to the system.
- The current evaluator matches the nearest observation within 90 minutes.
- The fixed-field comparator is now named `cams_lead0_fixed`. The separate
  `cams_forecast` method is implemented in `src/data/cams_forecast.py` and
  attached by the orchestrator.

Implementation assumptions:

- Expected live initialization cycles are 00:00 and 12:00 UTC.
- The live runner generalizes CAMS retrieval to the exact pair of times
  `init_time - 12 h` and `init_time`, including a cross-date pair for 00:00 UTC.
- Static public JSON is the first distribution mechanism. No always-on
  application API is required for MVP.
- A temporary GPU worker performs Aurora inference. An inexpensive CPU service
  schedules, adapts, verifies, publishes, and monitors.
- All thresholds below are versioned configuration, not eternal scientific
  constants. Shadow mode must measure whether they are appropriate.

## 2. End-to-end architecture

Each expected cycle moves through an explicit state machine:

```text
waiting_for_cams
  -> inputs_ready
  -> inference_running
  -> inference_complete
  -> adaptation_complete | adaptation_skipped
  -> validated
  -> ledger_committed
  -> published
  -> verification_pending
  -> partially_verified
  -> verified
```

Failure states are recorded, not erased:

```text
input_timeout | inference_failed | adaptation_failed |
validation_failed | publication_failed
```

The flow is:

1. CPU scheduler enumerates candidate CAMS cycles.
2. Detector confirms the latest complete cycle and both Aurora input times.
3. Input manifest is frozen.
4. Temporary GPU worker downloads/reads CAMS and runs Aurora.
5. Station samples and India-region fields are validated.
6. CPU worker obtains recent OpenAQ observations and builds persistence.
7. Certified adaptation is applied using only data available by initialization.
8. Actual CAMS lead forecasts are added when that workstream is complete.
9. A candidate forecast artifact is validated.
10. Immutable ledger entry is committed.
11. Public versioned JSON is written, then the `latest` pointer is atomically
    switched.
12. Later observations verify the saved forecast and update scorecards without
    altering its prediction payload.

## 3. Latest-CAMS-cycle detection

### Candidate generation

At each scheduler check:

1. Floor current UTC time to the most recent 00:00 or 12:00 boundary.
2. Generate that cycle and the preceding three 12-hour cycles, newest first.
3. Exclude any cycle already `published`, or retry it only if its recorded state
   permits another attempt.

The scheduler checks every 30 minutes. It does not assume that a CAMS cycle is
available at a fixed wall-clock delay.

### Availability test

A candidate is ready only when all of the following have been retrieved and
validated:

- lead-zero data at `T - 12 h` and `T`;
- every surface and pressure-level variable required by
  `cams_composition.py`;
- every required pressure level;
- the expected global 0.4-degree grid and compatible coordinates;
- non-empty, finite arrays at both times;
- request parameters and response checksums recorded in an input manifest.

A zip file’s existence alone is not proof of readiness. Temporary downloads use
an `.incomplete` suffix and become cache entries only after validation.

### Cross-date input

For a 00:00 UTC initialization, the two Aurora input times are 12:00 UTC on the
previous date and 00:00 UTC on the current date. The live downloader must accept
explicit datetimes; it must not inherit the retrospective assumption that both
times are on one date.

### Selection and timeout

- Select the newest complete candidate.
- If the newest expected cycle is unavailable, continue showing the previous
  publication and label its age.
- Do not publish a duplicate forecast under a new ID merely because the detector
  checked again.
- Record input latency from cycle time to confirmed availability.
- Initially mark an expected cycle `input_timeout` after 18 hours, while still
  allowing a later backfill attempt. Revisit this threshold after shadow mode.

## 4. Inputs and contracts

| Input | Required fields | Role | MVP failure behavior |
|---|---|---|---|
| CAMS lead-zero analysis | Required Aurora variables at `T-12 h`, `T` | Aurora initialization | No new Aurora forecast |
| Aurora checkpoint/static fields | Exact artifact identity and digest | Raw forecast | Use CAMS forecast only if independently complete; otherwise retain stale prior publication |
| Station registry | Stable station ID, city, coordinates, version | Sampling and display | Reject mixed/unknown version |
| OpenAQ recent observations | Station, observed time, value, retrieval time | Current display, persistence, local correction, later truth | Publish raw forecast; mark persistence/correction unavailable where unsupported |
| Certified correction artifact | Version, training cutoff, digest, gate result | Corrected forecast | Publish raw Aurora; never use rejected artifact |
| Actual CAMS lead forecast | Valid time and PM2.5 at matching leads | Operational comparator/fallback | Method shown unavailable; never relabel held analysis as forecast |
| Code/configuration | Git commit and configuration digest | Reproducibility | Refuse publication if missing |

Secrets such as OpenAQ and Copernicus credentials are runtime inputs but must
never enter manifests, logs, ledgers, or public JSON.

## 5. Chronological and no-future-data rules

For a forecast initialized at `T`:

1. Aurora may use only atmospheric fields whose modeled time is at or before
   `T`.
2. Persistence may use only an observation with `observed_at <= T`.
3. A local correction may use only rows with `observed_at <= T`.
4. Live ingestion records `retrieved_at`. The strict prospective support set
   additionally requires `retrieved_at <= forecast_generated_at`.
5. A trained adapter records `training_data_max_time < T`.
6. Station, normalization, and feature statistics obey the same cutoff.
7. Verification observations are joined only after the forecast is committed.
8. If provider corrections later alter an observation, retain both source
   versions and recompute verification as a new verification version. Never
   mutate the forecast.

The first live retrieval of every OpenAQ row must add:

```text
observed_at, retrieved_at, provider_record_id, payload_digest
```

Retrospective data without `retrieved_at` may be used for historical benchmark
analysis but cannot prove what was available in a live cycle.

Automated tests must fail if any support row crosses a forecast’s chronological
boundary.

## 6. Immutable forecast ledger

### Identity

`forecast_id` is deterministic:

```text
iaqb_<init YYYYMMDDTHHMMZ>_<first 12 hex of SHA-256 identity digest>
```

The identity digest covers:

- initialization time;
- model/checkpoint digest;
- correction artifact digest or `none`;
- station-registry version;
- code commit;
- configuration digest;
- CAMS input-manifest digest.

Running identical inputs is idempotent and returns the existing artifact. If the
same `forecast_id` would produce different bytes, the run fails with an
immutability violation.

### Storage layout

Proposed canonical layout:

```text
artifacts/live/ledger/
  2026/07/29/12/
    iaqb_20260729T1200Z_a1b2c3d4e5f6/
      metadata.json
      input_manifest.json
      station_forecasts.parquet
      city_summaries.parquet
      forecast.sha256
      run.json

artifacts/live/verification/
  <forecast_id>/
    verification_v001.parquet
    verification_v001.json

web/public/data/
  forecasts/<forecast_id>.json
  scorecards/<scorecard_version>.json
  latest.json
  status.json
```

The canonical ledger may live in versioned object storage rather than Git.
Bucket/object versioning and a retention lock should be enabled where
available. The public repository contains schemas, fixtures, and reproducible
code, not credentials or every large artifact.

### Append-only rules

- Forecast prediction fields are never updated.
- A rerun with changed code/model/configuration creates a new `forecast_id`.
- Verification is a separately versioned child record.
- Publication status and operational incidents are append-only events.
- Deletion requires a documented retention/legal procedure, never routine
  cleanup.

## 7. Normative public JSON schema

The public feed uses JSON Schema draft 2020-12. `null` means unavailable;
absence is allowed only where the schema marks a field optional. PM2.5 values
are µg/m³.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://indiaaqbench.example/schema/forecast-v1.json",
  "title": "IndiaAQBench public forecast",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "forecast_id",
    "generated_at",
    "published_at",
    "status",
    "cycle",
    "provenance",
    "compute",
    "methods",
    "locations",
    "city_summaries",
    "disclaimer"
  ],
  "properties": {
    "schema_version": {"const": "1.0.0"},
    "forecast_id": {"type": "string", "pattern": "^iaqb_[0-9]{8}T[0-9]{4}Z_[a-f0-9]{12}$"},
    "generated_at": {"type": "string", "format": "date-time"},
    "published_at": {"type": "string", "format": "date-time"},
    "status": {"enum": ["complete", "degraded"]},
    "cycle": {
      "type": "object",
      "additionalProperties": false,
      "required": ["init_time", "input_times", "leads_h", "freshness"],
      "properties": {
        "init_time": {"type": "string", "format": "date-time"},
        "input_times": {
          "type": "array",
          "prefixItems": [
            {"type": "string", "format": "date-time"},
            {"type": "string", "format": "date-time"}
          ],
          "items": false,
          "minItems": 2,
          "maxItems": 2
        },
        "leads_h": {
          "type": "array",
          "items": {"enum": [0, 12, 24, 36, 48, 60, 72, 84, 96]},
          "minItems": 9,
          "maxItems": 9,
          "uniqueItems": true
        },
        "freshness": {"enum": ["current", "delayed", "stale"]}
      }
    },
    "provenance": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "code_commit",
        "config_digest",
        "registry_version",
        "raw_model",
        "correction",
        "sources"
      ],
      "properties": {
        "code_commit": {"type": "string", "pattern": "^[a-f0-9]{7,40}$"},
        "config_digest": {"type": "string"},
        "registry_version": {"type": "string"},
        "raw_model": {
          "type": "object",
          "additionalProperties": false,
          "required": ["name", "checkpoint", "artifact_digest"],
          "properties": {
            "name": {"const": "AuroraAirPollution"},
            "checkpoint": {"type": "string"},
            "artifact_digest": {"type": "string"}
          }
        },
        "correction": {
          "type": "object",
          "additionalProperties": false,
          "required": ["name", "version", "artifact_digest", "gate_status", "training_data_max_time"],
          "properties": {
            "name": {"type": ["string", "null"]},
            "version": {"type": ["string", "null"]},
            "artifact_digest": {"type": ["string", "null"]},
            "gate_status": {"enum": ["passed", "not_used", "failed", "unavailable"]},
            "training_data_max_time": {"type": ["string", "null"], "format": "date-time"}
          }
        },
        "sources": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["name", "dataset", "retrieved_at", "manifest_digest"],
            "properties": {
              "name": {"enum": ["cams", "openaq", "station_registry"]},
              "dataset": {"type": "string"},
              "retrieved_at": {"type": "string", "format": "date-time"},
              "manifest_digest": {"type": "string"},
              "license_url": {"type": ["string", "null"], "format": "uri"}
            }
          }
        }
      }
    },
    "compute": {
      "type": "object",
      "additionalProperties": false,
      "required": ["hardware", "inference_seconds", "cycle_seconds", "gpu_hours", "estimated_cost", "currency", "rate_note"],
      "properties": {
        "hardware": {"type": "string"},
        "inference_seconds": {"type": "number", "minimum": 0},
        "cycle_seconds": {"type": "number", "minimum": 0},
        "gpu_hours": {"type": "number", "minimum": 0},
        "estimated_cost": {"type": ["number", "null"], "minimum": 0},
        "currency": {"type": "string"},
        "rate_note": {"type": "string"}
      }
    },
    "methods": {
      "type": "array",
      "items": {"$ref": "#/$defs/method"},
      "minItems": 5,
      "maxItems": 5,
      "uniqueItems": true,
      "allOf": [
        {"contains": {"properties": {"id": {"const": "corrected"}}}, "minContains": 1, "maxContains": 1},
        {"contains": {"properties": {"id": {"const": "raw_aurora"}}}, "minContains": 1, "maxContains": 1},
        {"contains": {"properties": {"id": {"const": "cams_forecast"}}}, "minContains": 1, "maxContains": 1},
        {"contains": {"properties": {"id": {"const": "persistence"}}}, "minContains": 1, "maxContains": 1},
        {"contains": {"properties": {"id": {"const": "cams_analysis_persistence"}}}, "minContains": 1, "maxContains": 1}
      ]
    },
    "locations": {
      "type": "array",
      "items": {"$ref": "#/$defs/location"}
    },
    "city_summaries": {
      "type": "array",
      "items": {"$ref": "#/$defs/citySummary"}
    },
    "disclaimer": {"type": "string", "minLength": 40}
  },
  "$defs": {
    "method": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "label", "status", "unavailable_reason"],
      "properties": {
        "id": {
          "enum": [
            "corrected",
            "raw_aurora",
            "cams_forecast",
            "persistence",
            "cams_analysis_persistence"
          ]
        },
        "label": {"type": "string"},
        "status": {"enum": ["available", "unavailable", "rejected"]},
        "unavailable_reason": {"type": ["string", "null"]}
      }
    },
    "methodValue": {
      "type": "object",
      "additionalProperties": false,
      "required": ["method_id", "pm25_ugm3", "quality_flags"],
      "properties": {
        "method_id": {
          "enum": [
            "corrected",
            "raw_aurora",
            "cams_forecast",
            "persistence",
            "cams_analysis_persistence"
          ]
        },
        "pm25_ugm3": {"type": ["number", "null"], "minimum": 0, "maximum": 1000},
        "quality_flags": {
          "type": "array",
          "items": {"type": "string"},
          "uniqueItems": true
        }
      }
    },
    "observation": {
      "type": ["object", "null"],
      "additionalProperties": false,
      "required": ["pm25_ugm3", "observed_at", "retrieved_at", "freshness"],
      "properties": {
        "pm25_ugm3": {"type": "number", "minimum": 0, "maximum": 1000},
        "observed_at": {"type": "string", "format": "date-time"},
        "retrieved_at": {"type": "string", "format": "date-time"},
        "freshness": {"enum": ["fresh", "delayed", "stale"]}
      }
    },
    "point": {
      "type": "object",
      "additionalProperties": false,
      "required": ["valid_time", "lead_h", "values"],
      "properties": {
        "valid_time": {"type": "string", "format": "date-time"},
        "lead_h": {"enum": [0, 12, 24, 36, 48, 60, 72, 84, 96]},
        "values": {
          "type": "array",
          "items": {"$ref": "#/$defs/methodValue"},
          "minItems": 5,
          "maxItems": 5,
          "uniqueItems": true,
          "allOf": [
            {"contains": {"properties": {"method_id": {"const": "corrected"}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"method_id": {"const": "raw_aurora"}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"method_id": {"const": "cams_forecast"}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"method_id": {"const": "persistence"}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"method_id": {"const": "cams_analysis_persistence"}}}, "minContains": 1, "maxContains": 1}
          ]
        }
      }
    },
    "window": {
      "type": "object",
      "additionalProperties": false,
      "required": ["window_start", "window_end", "aggregation", "values"],
      "properties": {
        "window_start": {"type": "string", "format": "date-time"},
        "window_end": {"type": "string", "format": "date-time"},
        "aggregation": {"const": "forward_24h_piecewise_linear_12h"},
        "values": {
          "type": "array",
          "items": {"$ref": "#/$defs/methodValue"},
          "minItems": 5,
          "maxItems": 5,
          "uniqueItems": true,
          "allOf": [
            {"contains": {"properties": {"method_id": {"const": "corrected"}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"method_id": {"const": "raw_aurora"}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"method_id": {"const": "cams_forecast"}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"method_id": {"const": "persistence"}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"method_id": {"const": "cams_analysis_persistence"}}}, "minContains": 1, "maxContains": 1}
          ]
        }
      }
    },
    "support": {
      "type": "object",
      "additionalProperties": false,
      "required": ["selected_method", "local_observation_count", "latest_support_observed_at", "support_status"],
      "properties": {
        "selected_method": {"type": "string"},
        "local_observation_count": {"type": "integer", "minimum": 0},
        "latest_support_observed_at": {"type": ["string", "null"], "format": "date-time"},
        "support_status": {"enum": ["local", "pooled", "raw_fallback", "unavailable"]}
      }
    },
    "location": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "station_id",
        "station_name",
        "city",
        "lat",
        "lon",
        "observation",
        "support",
        "points",
        "rolling_24h"
      ],
      "properties": {
        "station_id": {"type": "string"},
        "station_name": {"type": "string"},
        "city": {"type": "string"},
        "lat": {"type": "number", "minimum": -90, "maximum": 90},
        "lon": {"type": "number", "minimum": -180, "maximum": 180},
        "observation": {"$ref": "#/$defs/observation"},
        "support": {"$ref": "#/$defs/support"},
        "points": {
          "type": "array",
          "items": {"$ref": "#/$defs/point"},
          "minItems": 9,
          "maxItems": 9,
          "uniqueItems": true,
          "allOf": [
            {"contains": {"properties": {"lead_h": {"const": 0}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"lead_h": {"const": 12}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"lead_h": {"const": 24}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"lead_h": {"const": 36}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"lead_h": {"const": 48}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"lead_h": {"const": 60}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"lead_h": {"const": 72}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"lead_h": {"const": 84}}}, "minContains": 1, "maxContains": 1},
            {"contains": {"properties": {"lead_h": {"const": 96}}}, "minContains": 1, "maxContains": 1}
          ]
        },
        "rolling_24h": {
          "type": "array",
          "items": {"$ref": "#/$defs/window"},
          "minItems": 7,
          "maxItems": 7
        }
      }
    },
    "citySummary": {
      "type": "object",
      "additionalProperties": false,
      "required": ["city", "window_start", "window_end", "method_id", "station_count", "median_pm25_ugm3", "min_pm25_ugm3", "max_pm25_ugm3", "very_poor_plus_count"],
      "properties": {
        "city": {"type": "string"},
        "window_start": {"type": "string", "format": "date-time"},
        "window_end": {"type": "string", "format": "date-time"},
        "method_id": {"type": "string"},
        "station_count": {"type": "integer", "minimum": 0},
        "median_pm25_ugm3": {"type": ["number", "null"], "minimum": 0, "maximum": 1000},
        "min_pm25_ugm3": {"type": ["number", "null"], "minimum": 0, "maximum": 1000},
        "max_pm25_ugm3": {"type": ["number", "null"], "minimum": 0, "maximum": 1000},
        "very_poor_plus_count": {"type": "integer", "minimum": 0}
      }
    }
  }
}
```

The `$id` host above is a schema identifier placeholder, not a deployed
endpoint. Replace it with a controlled project URL before schema v1 is frozen.

## 8. Example public forecast

The example uses one fictional location. Identity, values, timings, and costs
are fixtures rather than a real forecast.

```json
{
  "schema_version": "1.0.0",
  "forecast_id": "iaqb_20260729T1200Z_a1b2c3d4e5f6",
  "generated_at": "2026-07-29T15:42:11Z",
  "published_at": "2026-07-29T15:44:02Z",
  "status": "degraded",
  "cycle": {
    "init_time": "2026-07-29T12:00:00Z",
    "input_times": ["2026-07-29T00:00:00Z", "2026-07-29T12:00:00Z"],
    "leads_h": [0, 12, 24, 36, 48, 60, 72, 84, 96],
    "freshness": "current"
  },
  "provenance": {
    "code_commit": "0123456789abcdef",
    "config_digest": "sha256:config-example",
    "registry_version": "159:example1",
    "raw_model": {
      "name": "AuroraAirPollution",
      "checkpoint": "aurora-0.4-air-pollution",
      "artifact_digest": "sha256:model-example"
    },
    "correction": {
      "name": "trailing_ratio_anchor",
      "version": "0.1.0",
      "artifact_digest": "sha256:anchor-example",
      "gate_status": "passed",
      "training_data_max_time": "2025-11-30T23:00:00Z"
    },
    "sources": [
      {
        "name": "cams",
        "dataset": "cams-global-atmospheric-composition-forecasts leadtime=0",
        "retrieved_at": "2026-07-29T13:25:00Z",
        "manifest_digest": "sha256:cams-example",
        "license_url": null
      },
      {
        "name": "openaq",
        "dataset": "OpenAQ v3 hourly PM2.5",
        "retrieved_at": "2026-07-29T15:10:00Z",
        "manifest_digest": "sha256:openaq-example",
        "license_url": null
      },
      {
        "name": "station_registry",
        "dataset": "IndiaAQBench station registry",
        "retrieved_at": "2026-07-29T15:11:00Z",
        "manifest_digest": "sha256:registry-example",
        "license_url": null
      }
    ]
  },
  "compute": {
    "hardware": "example 48 GB GPU",
    "inference_seconds": 420,
    "cycle_seconds": 1860,
    "gpu_hours": 0.117,
    "estimated_cost": 0.08,
    "currency": "USD",
    "rate_note": "Illustrative fixture, not a measured production cost"
  },
  "methods": [
    {"id": "corrected", "label": "Corrected Aurora", "status": "available", "unavailable_reason": null},
    {"id": "raw_aurora", "label": "Raw Aurora", "status": "available", "unavailable_reason": null},
    {"id": "cams_forecast", "label": "CAMS forecast", "status": "unavailable", "unavailable_reason": "Illustrative fixture contains no downloaded forecast"},
    {"id": "persistence", "label": "Persistence", "status": "available", "unavailable_reason": null},
    {"id": "cams_analysis_persistence", "label": "CAMS starting field held constant", "status": "available", "unavailable_reason": null}
  ],
  "locations": [
    {
      "station_id": "example-station",
      "station_name": "Example station",
      "city": "varanasi",
      "lat": 25.31,
      "lon": 82.98,
      "observation": {
        "pm25_ugm3": 88,
        "observed_at": "2026-07-29T12:00:00Z",
        "retrieved_at": "2026-07-29T15:10:00Z",
        "freshness": "delayed"
      },
      "support": {
        "selected_method": "corrected",
        "local_observation_count": 30,
        "latest_support_observed_at": "2026-07-29T12:00:00Z",
        "support_status": "local"
      },
      "points": [
        {
          "valid_time": "2026-07-29T12:00:00Z",
          "lead_h": 0,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 52, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 82, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "valid_time": "2026-07-30T00:00:00Z",
          "lead_h": 12,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 61, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 96, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "valid_time": "2026-07-30T12:00:00Z",
          "lead_h": 24,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 70, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 112, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "valid_time": "2026-07-31T00:00:00Z",
          "lead_h": 36,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 68, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 108, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "valid_time": "2026-07-31T12:00:00Z",
          "lead_h": 48,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 64, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 99, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "valid_time": "2026-08-01T00:00:00Z",
          "lead_h": 60,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 58, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 90, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "valid_time": "2026-08-01T12:00:00Z",
          "lead_h": 72,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 55, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 85, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "valid_time": "2026-08-02T00:00:00Z",
          "lead_h": 84,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 50, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 78, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "valid_time": "2026-08-02T12:00:00Z",
          "lead_h": 96,
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 48, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 74, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        }
      ],
      "rolling_24h": [
        {
          "window_start": "2026-07-29T12:00:00Z",
          "window_end": "2026-07-30T12:00:00Z",
          "aggregation": "forward_24h_piecewise_linear_12h",
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 61, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 96.5, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "window_start": "2026-07-30T00:00:00Z",
          "window_end": "2026-07-31T00:00:00Z",
          "aggregation": "forward_24h_piecewise_linear_12h",
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 67.25, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 107, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "window_start": "2026-07-30T12:00:00Z",
          "window_end": "2026-07-31T12:00:00Z",
          "aggregation": "forward_24h_piecewise_linear_12h",
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 67.5, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 106.75, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "window_start": "2026-07-31T00:00:00Z",
          "window_end": "2026-08-01T00:00:00Z",
          "aggregation": "forward_24h_piecewise_linear_12h",
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 63.5, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 99, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "window_start": "2026-07-31T12:00:00Z",
          "window_end": "2026-08-01T12:00:00Z",
          "aggregation": "forward_24h_piecewise_linear_12h",
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 58.75, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 91, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "window_start": "2026-08-01T00:00:00Z",
          "window_end": "2026-08-02T00:00:00Z",
          "aggregation": "forward_24h_piecewise_linear_12h",
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 54.5, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 84.5, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        },
        {
          "window_start": "2026-08-01T12:00:00Z",
          "window_end": "2026-08-02T12:00:00Z",
          "aggregation": "forward_24h_piecewise_linear_12h",
          "values": [
            {"method_id": "raw_aurora", "pm25_ugm3": 50.75, "quality_flags": []},
            {"method_id": "corrected", "pm25_ugm3": 78.75, "quality_flags": []},
            {"method_id": "persistence", "pm25_ugm3": 88, "quality_flags": []},
            {"method_id": "cams_analysis_persistence", "pm25_ugm3": 52, "quality_flags": []}
          ]
        }
      ]
    }
  ],
  "city_summaries": [
    {
      "city": "varanasi",
      "window_start": "2026-07-29T12:00:00Z",
      "window_end": "2026-07-30T12:00:00Z",
      "method_id": "corrected",
      "station_count": 1,
      "median_pm25_ugm3": 96.5,
      "min_pm25_ugm3": 96.5,
      "max_pm25_ugm3": 96.5,
      "very_poor_plus_count": 0
    }
  ],
  "disclaimer": "Experimental research forecast — not an official warning. Follow CPCB, local authorities, and qualified health guidance."
}
```

All example identities, values, timings, and costs are fixtures, not real
forecasts or measured performance. The pre-publication validator requires a
value or an explicit unavailable flag for every declared available method.

## 9. Raw, corrected, and fallback behavior

The publisher selects the public method independently for each location, while
retaining all available method values.

Priority:

1. Certified `corrected`, with adequate support.
2. `raw_aurora`.
3. Complete `cams_forecast`.
4. No new forecast; retain prior publication and mark stale.

Rules:

- A failed or rejected correction never blocks raw publication.
- Missing OpenAQ disables persistence and any correction that requires local
  support. It does not invalidate raw Aurora.
- A certified pooled correction may be used only if its artifact explicitly
  supports that station/city tier; it is labeled `pooled`.
- An old observation is never silently treated as current.
- The held CAMS initial field is a comparator, not a substitute for an actual
  CAMS future forecast.
- Out-of-range or non-finite public values become `null` with a quality flag.
  The unmodified value remains in the private diagnostic artifact.
- No prediction is silently clipped for display.
- A cycle is `degraded` if any public method, location, lead, provenance field,
  or freshness requirement is incomplete.

## 10. Validation before ledger commit

Required checks:

- schema validation;
- exact station-registry fingerprint match;
- no unexpected or duplicate station IDs;
- one row per expected station and lead for raw Aurora;
- leads exactly 0, 12, ..., 96;
- `valid_time = init_time + lead_h`;
- all raw arrays finite before sampling;
- all public values finite and in [0, 1000], or explicitly nulled and flagged;
- all correction support is chronological;
- correction artifact gate status is `passed`;
- source, model, code, configuration, and registry provenance present;
- rolling 24-hour arithmetic reproducible from points;
- city summaries reproducible from station windows;
- no credential-like keys or values in artifacts;
- deterministic forecast ID and checksum.

Validation produces a machine-readable report stored in the ledger. A failed
hard check prevents publication. A permitted partial condition produces
`degraded` plus explicit flags.

## 11. Atomic publication

Publication order:

1. Write and validate the canonical ledger artifact.
2. Build public JSON in a temporary/versioned location.
3. Validate JSON against the frozen schema.
4. Upload/write `<forecast_id>.json`.
5. Verify its checksum after write.
6. Atomically replace `latest.json` with a small pointer containing
   `forecast_id`, URL/path, checksum, published time, and status.
7. Update `status.json`.

On a local filesystem, use write-to-sibling-temporary-file plus atomic rename.
On object storage, write immutable versioned objects and update the pointer with
a conditional request/ETag. Never overwrite a forecast object.

If pointer update fails, clients continue reading the previous complete
forecast. A partial artifact is never reachable through `latest.json`.

## 12. Retry, idempotency, and staleness

### Retry

- Network calls use bounded exponential backoff with provider `Retry-After`.
- Record every attempt, duration, status, and sanitized error class.
- A retry reuses validated cached inputs by checksum.
- Retry GPU inference at most once on a fresh worker for infrastructure errors.
- Deterministic validation failures are not blindly retried.
- Publication retries operate on the already committed ledger artifact.

### Idempotency

- Scheduling the same cycle many times produces one forecast per unique
  provenance identity.
- A claimed cycle uses an expiring distributed lock or conditional object write.
- Workers may resume individual stages, but every stage verifies its inputs.
- Existing valid output with the same checksum is success.
- Existing output with a different checksum is a hard incident.

### Staleness

Public forecast freshness:

- `current`: initialization age <=18 h;
- `delayed`: >18 h and <30 h;
- `stale`: >=30 h;
- `unavailable`: no forecast covers the requested time.

Observation freshness:

- `fresh`: age <=3 h;
- `delayed`: >3 h and <=12 h;
- `stale`: >12 h and <=24 h;
- `unavailable`: no eligible observation in 24 h.

Staleness is recalculated at read/build time, not frozen at initial publication.
The immutable forecast JSON retains its publication-time state; `status.json`
provides current state.

## 13. Verification after observations arrive

### Instantaneous sensitivity

- Match station/valid-time forecasts to the nearest eligible OpenAQ observation
  within 90 minutes, matching the current evaluator.
- Store the chosen observation timestamp, time offset, provider identity,
  retrieval time, value, and payload digest.
- A pair is verified only after the forecast ledger commit time.

### Forward 24-hour headline

- Aggregate station observations over the same UTC window used by the forecast.
- Require at least 18 distinct hourly observations within 24 hours for MVP.
- Record coverage count and suppress the verified window when coverage fails.
- The 18-hour rule is stricter than the current helper’s generic default and
  must be tested as a live-product choice.

### Verification versions

- First verification may be partial.
- Later observations create `verification_v002`, and so on.
- Record the observation-data maximum time and digest for each version.
- Never alter forecast values.
- Scorecards name their verification version and generation time.

## 14. Rolling scorecards

Generate 7-, 30-, and 90-day scorecards for:

- each station;
- each city;
- pooled train-pool cities;
- L1 held-out stations;
- L2 held-out cities;
- each lead/24-hour window;
- each method;
- instantaneous sensitivity and rolling-24-hour headline separately.

For event results store and publish:

```text
verified_pairs
observed_events
forecast_events
hits
misses
false_alarms
POD = hits / (hits + misses)
FAR = false_alarms / (hits + false_alarms)
CSI = hits / (hits + misses + false_alarms)
```

Undefined denominators produce `null`, not zero. Pooled metrics are recomputed
from pooled counts. They are not unweighted averages of per-city rates.

Also report category hit/adjacent rate, bias, and MAE. The scorecard generator
must not treat its existing simple across-city mean as the normative live
pooled estimator.

An incident or missing forecast remains in the operational denominator even
when it cannot enter accuracy metrics. Publish both:

- forecast completion/verification coverage; and
- accuracy on verified pairs.

## 15. Compute placement

### Temporary GPU worker

Responsibilities:

- obtain validated CAMS analysis inputs from cache/storage;
- load Aurora once per cycle;
- perform +12 h through +96 h rollout;
- produce station samples and India-region fields;
- emit timing, memory, hardware, and failure metadata;
- upload candidate artifacts;
- terminate after success or bounded failure handling.

The worker does not publish directly and does not need OpenAQ credentials.

### Always-on/scheduled CPU service

Responsibilities:

- latest-cycle detection;
- locks and state machine;
- OpenAQ live ingestion;
- chronological adaptation and persistence;
- actual CAMS forecast extraction;
- validation;
- ledger commit and public publication;
- later observation matching;
- rolling scorecards;
- monitoring and alerts;
- triggering and terminating GPU workers through narrowly scoped credentials.

The CPU service may be a small VM or managed scheduled/container service. A
personal laptop is not the production scheduler.

## 16. Monitoring and operational status

Record metrics for:

- expected, detected, started, completed, published, and missed cycles;
- CAMS input latency;
- OpenAQ observation latency by city/station;
- download attempts and provider response classes;
- GPU queue/startup time;
- inference and total cycle duration;
- expected versus produced station/lead rows;
- correction availability and fallback fraction;
- invalid/out-of-range values;
- publication and pointer-update failures;
- current forecast age;
- cost per cycle and cumulative cost;
- verification coverage;
- station-registry changes.

Initial alerts:

- no newest cycle detected 12 hours after expected initialization;
- no successful public forecast with age under 18 hours;
- inference or publication hard failure;
- registry mismatch;
- immutable-ID checksum conflict;
- raw forecast missing any expected station/lead;
- more than 20% of locations using fallback;
- any secret-scanner finding in an artifact;
- daily cost above a configured cap.

Alerts must link to the forecast/cycle ID and sanitized run record.

`status.json` contains current cycle, last success, forecast age, degraded
reasons, affected cities, and next scheduled check. It contains no stack traces.

## 17. Privacy, licensing, and responsible publication

### Privacy

- Station observations and coordinates are public environmental data, not
  personal measurements.
- MVP collects no accounts or precise visitor location.
- If analytics are used, prefer aggregate privacy-preserving counts and publish
  the analytics policy.
- Logs must not store user IP addresses beyond infrastructure necessity and
  documented retention.
- Credentials and home-directory paths never enter artifacts.

### Licensing and attribution

Before public launch, record:

- Aurora code/checkpoint license and required attribution;
- Copernicus/CAMS license, dataset identifier, and attribution;
- OpenAQ/provider terms, source attribution, and redistribution limits;
- station metadata source;
- repository code and data licenses;
- whether India-region derived fields may be redistributed.

Do not re-host global CAMS inputs. Publish retrieval manifests and permitted
derived/extracted data only after license review. A source being accessible by
API does not itself prove redistribution permission.

### Responsible use

Every payload carries the experimental-not-warning disclaimer. UI and API docs
must distinguish observed, modeled, corrected, and fallback values.

## 18. Failure-mode matrix

| Failure | Public behavior | Internal action |
|---|---|---|
| Latest CAMS cycle late | Keep prior forecast; show delayed/stale | Continue bounded detection; record latency |
| CAMS input incomplete | Do not run Aurora | Quarantine partial files; retry retrieval |
| GPU unavailable | Keep prior forecast, or CAMS forecast fallback if complete | One fresh-worker retry; alert |
| Aurora inference fails | Never publish partial Aurora leads | Preserve diagnostics; use certified fallback only |
| OpenAQ unavailable | Publish raw Aurora; persistence/correction unavailable as applicable | Retry independently; verify later |
| Observation stale | Name age; disable local correction if its support rule fails | Use certified pooled/raw fallback |
| Correction raises/fails validation | Publish raw Aurora | Record failure; alert; do not save corrupted method |
| Correction failed scientific gate | Never offer it as selected public method | Mark `rejected` in method registry |
| Actual CAMS forecast unavailable | Show method unavailable | Retain explicitly named analysis-held baseline |
| Registry changes | Reject mixed outputs | Require a new forecast identity and full sampling |
| Missing station/lead | Degraded only if policy permits; never impute silently | Identify exact rows; alert |
| Non-finite/out-of-range value | Public value `null` plus flag | Preserve raw diagnostic; fail selected method if widespread |
| Ledger write fails | Publish nothing new | Retry commit |
| Versioned JSON write fails | `latest` remains previous | Retry from committed ledger |
| `latest` pointer update fails | Previous complete forecast remains live | Retry conditional update |
| Verification observation corrected | New verification version | Keep prior verification and forecast |
| Cost cap exceeded | Stop new GPU launch; show delayed status | Alert operator for explicit override |

## 19. Tests

### Unit

- candidate-cycle enumeration around UTC date boundaries;
- exact `T-12 h`, `T` pairing;
- freshness boundary values;
- deterministic IDs and digests;
- chronological filters;
- method fallback selection;
- rolling-24-hour formula;
- city aggregation and sparse-station behavior;
- event contingency counts and null denominators;
- retry classification;
- secret redaction.

### Contract

- normative JSON Schema accepts canonical fixtures;
- missing required provenance fails;
- unknown fields fail while schema version is fixed;
- null/unavailable methods render correctly;
- OpenAPI/TypeScript types, if introduced, are generated from or tested against
  the same schema.

### Integration

- fake CAMS service exposes a delayed then complete cycle;
- fake OpenAQ returns fresh, stale, missing, duplicate, and corrected rows;
- CPU service launches a stub GPU worker;
- all expected station/leads reach a candidate artifact;
- correction failure still yields raw publication;
- complete CAMS forecast can become named fallback;
- publish and verify one end-to-end synthetic cycle.

### Integrity and leakage

- any observation after initialization in persistence/adaptation raises;
- adapter training cutoff at or after initialization raises;
- stale registry pair raises;
- duplicate station/lead raises;
- verification cannot run before ledger commit;
- forecast bytes remain unchanged after verification.

### Failure injection

- kill worker after each pipeline stage;
- corrupt cached zip;
- truncate Parquet/JSON;
- simulate rate limit and timeout;
- race two workers for one cycle;
- fail between versioned-object write and pointer update;
- return invalid PM2.5 values;
- exhaust cost cap.

### UI/system

- `latest` always resolves to a complete schema-valid object;
- delayed/stale/unavailable states are visible;
- raw/corrected/CAMS/persistence labels are exact;
- keyboard and screen-reader flows work;
- no chart bridges missing values;
- low-bandwidth view works without client JavaScript where practical.

### Pre-release scientific

- current-registry frozen-date rollout complete;
- `python -m src.eval.audit` passes;
- event metrics include counts;
- correction gate passes or correction is not selected;
- rolling-24-hour and instantaneous results remain separate.

## 20. Staged rollout

### Stage 0 — contract and fixtures

- Freeze product copy, schema, method IDs, freshness rules, and example fixtures.
- Build the web interface against explicitly labeled fixture/historical data.
- No live claim.

### Stage 1 — one-cycle local prototype

- Detect or explicitly select one current complete cycle.
- Produce ledger and public JSON.
- Do not publish externally.

### Stage 2 — continuous private shadow mode

- Run both expected daily cycles.
- Keep immutable predictions and verify them later.
- Exercise failures and measure input latency/cost.
- Minimum public-beta gate: 14 consecutive days, 20 complete cycles, at least
  90% within six hours of confirmed input availability.

### Stage 3 — public experimental beta

- Publish nine-city feed and operational status.
- Keep disclaimer and version history prominent.
- Publicize raw and corrected comparisons and empty/sparse scorecards honestly.
- Continue incident logging.

### Stage 4 — broader promotion

- After at least 30 public/shadow days, publish a dated methods/results note.
- Promote only when repository docs reproduce the displayed retrospective
  result and live scorecards contain meaningful verified coverage.

### Stage 5 — evidence and coverage expansion

- Add cities by monitored/intermittent/unmonitored tier.
- Add independently matched historical data and actual CAMS forecasts.
- Add fire/satellite context only through ablation-tested versions.
- Accumulate prospective seasonal evidence, including post-monsoon.

## 21. Proposed directory and module ownership

These are new workstreams proposed for the coordinator to add to
`docs/WORKSTREAMS.md`. That existing file remains authoritative until updated.

```text
src/live/
  __init__.py
  config.py                 # versioned operational thresholds
  cycle_detector.py         # candidate generation and CAMS readiness
  input_manifest.py         # source checksums and provenance
  runner.py                 # state-machine orchestration
  adaptation.py             # calls certified src/model artifacts
  validation.py             # hard/degraded checks
  ledger.py                 # immutable canonical writes
  publication.py            # public JSON and atomic latest pointer
  verification.py           # later observation matching
  scorecards.py             # rolling counts/metrics
  schemas/
    forecast-v1.json
    status-v1.json
    scorecard-v1.json

web/
  ...                       # public interactive application only

infra/
  ...                       # scheduler, GPU worker, storage, alerts, budgets

tests/live/
  ...                       # owned with the corresponding live module
```

Ownership proposal:

| Proposed stream | Exclusive files | Depends on |
|---|---|---|
| Live contract | `docs/PRODUCT_SPEC.md`, `docs/LIVE_FEED_SPEC.md`, schema decisions | Benchmark spec |
| Cycle and inference | `src/live/cycle_detector.py`, `input_manifest.py`, `runner.py` | CAMS/Aurora interfaces |
| Adaptation bridge | `src/live/adaptation.py` | Component A and calibrator gates |
| Ledger and publication | `src/live/ledger.py`, `validation.py`, `publication.py`, schema files | Frozen JSON contract |
| Verification | `src/live/verification.py`, `scorecards.py` | Ledger and OpenAQ ingestion |
| Web | `web/**` | Frozen JSON fixtures |
| Infrastructure | `infra/**` | Runnable cycle and publication commands |
| Additional data | new `src/data/sources/**`, station-matching modules | Separate discovery contract |

No two sessions should edit `src/live/config.py`, shared schema files, or shared
tests concurrently. The coordinating session owns updates to existing shared
documents, `HANDOFF.md`, and `JOURNAL.md`.

## 22. Dependencies and definitions of done

### Contract and fixture

Depends on: product decision.
Done when: schema-valid full-size fixtures represent complete, degraded, stale,
missing-observation, rejected-correction, and fallback cases.

### Cycle detector

Depends on: generalized CAMS datetime retrieval.
Done when: it finds the newest complete 00/12 cycle across a date boundary,
never mistakes a partial file for readiness, and is idempotent.

### GPU live runner

Depends on: detector, Aurora interface, registry.
Done when: one command emits all expected raw station/leads plus provenance from
one current cycle and the worker terminates.

### Adaptation bridge

Depends on: certified Component A/calibrator artifacts.
Done when: support is strictly chronological, failures fall back to raw, and
the selected method/support status is explicit per location.

### Actual CAMS forecast

Implemented: deterministic lead-dependent CAMS retrieval, raw GRIB retention,
checksummed provenance, station sampling, exact support/registry attachment,
and the `cams_forecast` evaluator method. The analysis-held-constant comparator
remains separately named `cams_lead0_fixed`. The 56-date data acquisition is
part of the pending integrated GPU rollout.

### Ledger/publication

Depends on: frozen schema and candidate artifact.
Done when: forecasts are immutable, repeated runs are idempotent, checksum
conflicts fail, and `latest` never points to partial data.

### Verification/scorecards

Depends on: ledger and live OpenAQ retrieval timestamps.
Done when: saved forecasts match later observations, verification is versioned,
24-hour coverage is enforced, and counts reproduce POD/FAR/CSI.

### Web

Depends on: schema fixtures, not live infrastructure.
Done when: a non-technical visitor can read a city forecast, compare methods,
see freshness/support, understand event evidence, and access the disclaimer
with keyboard/screen-reader/mobile support.

### Infrastructure

Depends on: runnable CPU and GPU commands.
Done when: both daily cycles run without a laptop, failures alert, costs are
capped, secrets are scoped, and the GPU terminates.

### Public beta

Depends on: all launch gates in `PRODUCT_SPEC.md`.
Done when: the feed is current or honestly stale, the repository and site state
match, every forecast is auditable, and no unsupported operational claim is
made.
