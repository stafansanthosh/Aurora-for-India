# Current session starters

**Updated:** 2026-08-04

The earlier archive, guardrail, reporting, Component A, product-design,
additional-data, public-documentation, GPU-rollout, manifest-integration, and
first-scorecard and 24-hour-headline sessions are complete. Do not restart
them. The next bounded task is freezing report artifacts and connecting the
validated tables to the reporting package.

Every new agent must first read `docs/AGENT_BRIEF.md`, `docs/HANDOFF.md`, and
the relevant section of `docs/WORKSTREAMS.md`. The owner requested work on
`master` for this phase; do not create or switch branches.

## Versioned reporting artifacts — next local session

The GPU phase and separate 24-hour/hourly scorecards are complete. Do not
provision another Pod, rerun a slice, re-merge manifests, tune Component A on
test outcomes, or refit the rejected calibrator. Use this assignment:

```text
Read docs/AGENT_BRIEF.md, docs/HANDOFF.md, docs/BENCHMARK_SPEC.md, and
docs/WORKSTREAMS.md. Work on master as requested by the owner.

Freeze deterministic report artifacts from the existing hourly and 24-hour
metric files. Preserve separate labels and never pool their counts. Include
per-city, per-window, pooled train-city, L1, and L2 results with exact Very
Poor+ event counts and POD/FAR/CSI. Clearly label Component A uncertified and
raw Aurora as the safe fallback. Connect the versioned artifacts to
src/report/** without altering model outputs or split constants.

Before stopping, run the full suite, update docs/HANDOFF.md and JOURNAL.md, and
commit only reviewed files. Do not push or change visibility without approval.
```

## Actual CAMS forecast baseline — completed

Do not start another implementation session. The reviewed implementation is in
`src/data/cams_forecast.py` with tests in `tests/test_cams_forecast.py`; it is
integrated into the orchestrator and evaluator. The block below is retained
only as the original assignment record.

```text
Read docs/AGENT_BRIEF.md, docs/HANDOFF.md, docs/DATA_SOURCE_AUDIT.md section 5,
and docs/DATA_EXPANSION_PLAN.md sections 4.1, 8, 10, and 11.

Implement the actual CAMS +12 through +96-hour PM2.5 forecast source as a new,
lead-dependent baseline. Own only:
  src/data/sources/cams_forecast.py
  tests/data/test_cams_forecast_contract.py
  new tiny fixtures/manifests required by those tests

Do not change Aurora's lead-zero CAMS inputs. Preserve source units and convert
kg/m3 to ug/m3 exactly once. Store initialization, valid time, lead, request,
retrieval time, dataset/version, hash, registry version, and source licence.
Use a one-date minimal pilot, no bulk download. Do not edit src/eval/** or
shared data until the coordinator reviews the handoff.

Before stopping: run the relevant tests, document the exact pilot request and
result, update docs/HANDOFF.md only if the critical state changed, append
JOURNAL.md, and commit reviewed files.
```

## OGD India Patna/Varanasi pilot — implementation completed

Do not start another implementation session. The bounded official API pilot is
in `src/data/ogd_aqi.py` with tests in `tests/test_ogd_aqi.py`. A live probe
requires `DATA_GOV_IN_API_KEY`. The block below is retained as the original
assignment record.

```text
Read docs/AGENT_BRIEF.md, docs/HANDOFF.md, docs/DATA_SOURCE_AUDIT.md section 4.2,
and docs/DATA_EXPANSION_PLAN.md sections 5, 6, 8, and 11.

Build a tiny, licence-aware current-feed pilot for the official OGD India CPCB
resource. Own only:
  src/data/sources/cpcb.py
  src/data/harmonize_external.py
  tests/data/test_harmonize_external.py
  data/external/manifests/ files that are safe and permitted to publish

Request only Patna and Varanasi for the smallest useful window. Preserve raw
station/provider names, coordinates, pollutant, unit, observed time, retrieved
time, resource ID, and raw hash. Produce a review report for identity,
overlap with OpenAQ, latency, missingness, units, duplicates, and licence.
Do not call it independent truth unless lineage proves that. Do not scrape
undocumented endpoints or alter the frozen benchmark/registry.

Before stopping: run tests, record pass/fail counts, append JOURNAL.md, and
commit reviewed files.
```

## Live runner and immutable ledger — future coding session

```text
Read docs/AGENT_BRIEF.md, docs/HANDOFF.md, docs/PRODUCT_SPEC.md, and
docs/LIVE_FEED_SPEC.md completely.

Implement only the first vertical slice: latest-cycle state machine, validated
input manifest, immutable forecast ledger, and generation of the documented
public JSON using fixture forecasts. Own new src/live/** and tests/live/**.
Do not connect cloud credentials, schedule production jobs, deploy a site, or
replace web fixtures in this session. Enforce retrieved_at <= init_time for
every live correction input. A failed correction must fall back visibly to raw
Aurora and must never mutate an earlier forecast record.

Before stopping: validate schema fixtures, failure/retry/idempotency tests,
append JOURNAL.md, and commit reviewed files.
```

## Fine-tuning design — blocked future research session

Do not start this until raw Aurora, persistence, actual CAMS forecast,
Component A, and the guarded calibrator have valid current-registry results.

```text
Read docs/AGENT_BRIEF.md, docs/BENCHMARK_SPEC.md, docs/EXECUTION_PLAN.md section
6, and the versioned baseline tables.

Write docs/FINETUNE_DESIGN.md only. Define trainable parameters, loss design,
station-sparse/gridded supervision, rollout length, memory and cost, L1/L2 and
temporal controls, catastrophic-forgetting checks, and the exact event-skill
gain required to justify training. Do not implement or run fine-tuning.
```
