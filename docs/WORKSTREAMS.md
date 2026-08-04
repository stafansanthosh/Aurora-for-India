# IndiaAQBench workstreams

**Updated:** 2026-08-04
**Integration policy for this phase:** the owner requested work directly on
`master`. Do not create or switch branches unless that instruction changes.

The repository is the shared memory. Read `docs/AGENT_BRIEF.md` and
`docs/HANDOFF.md` before starting. File ownership below prevents concurrent
sessions from overwriting each other; it does not authorize changes outside a
session's assigned scope.

For future WS-8 implementation, `tests/data/**` belongs to WS-8. WS-3's
completed guardrail ownership is limited to existing calibrator/AQI tests;
exact source-by-source paths are assigned in `docs/DATA_EXPANSION_PLAN.md`.

## Scoreboard

| ID | Workstream | State | Main outputs | Next gate |
|---|---|---|---|---|
| WS-1 | OpenAQ archive and station registry | **Complete** | `src/data/**`, `data/stations.csv`, frozen dates | Preserve provenance; no new bulk source without licence review |
| WS-2 | Component A local anchoring | **Implementation complete; evaluation pending audit** | `src/model/anchor.py`, `tests/test_anchor.py`, benchmark hook | Score after the post-rollout audit passes |
| WS-3 | Calibrator guardrails and tests | **Complete; remote suite green** | `src/model/calibrator.py`, guardrail tests | Score after audited raw and anchored baselines |
| WS-4 | Reporting package | **Complete; real table blocked** | `src/report/**`, diagnostic figures | Render only after valid audit and metrics |
| WS-5 | Fine-tuning design | **Not started** | planned `docs/FINETUNE_DESIGN.md` | Start after cheap baselines are scored |
| WS-6 | 56-date Aurora rollout | **Artifact generation complete: 56/56 dates, 80,136 rows** | `results/pairs/**` | Merge manifests and pass the full local audit |
| WS-7 | Public product and interface | **Private preview deployed; live system absent** | `docs/PRODUCT_SPEC.md`, `docs/LIVE_FEED_SPEC.md`, `web/**` | Shadow runner |
| WS-8 | Additional data and baselines | **Both CAMS archives and worker bundles complete; OGD probe optional** | `src/data/cams_forecast.py`, `src/data/cams_composition.py`, `src/data/ogd_aqi.py` | Preserve provenance; optional keyed OGD probe |
| WS-9 | Repository publication | **Blocked** | README, status, portfolio and readiness docs, CI | Tests/build, licence, clean-history decision |

## Critical path

```text
repair the local Python launcher
  -> merge four worker manifests
  -> integrity audit
  -> raw baseline scorecards
  -> Component A scorecard and event-safety decision
  -> calibrator comparison
  -> decide whether fine-tuning is justified
```

The product path can proceed beside that scientific path:

```text
interface preview
  -> validated public JSON/ledger implementation
  -> latest-cycle runner
  -> private shadow mode
  -> experimental public beta
  -> rolling prospective scorecard
```

## WS-1 — OpenAQ archive and registry

The nine-city archive is complete at 1,489,534 observations and the registry is
complete at 159 stations. The sensor-selection, partial-overwrite, and
rate-limit bugs have been fixed. The 56 dates are frozen at 32 train and 24
test.

Do not spend time attempting OpenAQ backfill before February 2025. Any direct
CPCB/state-board addition is a separate source with its own station matching,
quality checks, licence, availability time, and provenance.

## WS-2 — Component A

Component A estimates a per-station multiplier from recent short-lead
`observation / Aurora` ratios. Only observations verified strictly before the
new initialization are eligible. Thin samples shrink toward 1.0 and no-history
cases fall back to raw Aurora.

It is online local adaptation, not ordinary fitted calibration and not
zero-shot city transfer. Its implementation exists, but acceptance requires:

1. all source tests passing;
2. the integrity audit passing on current-registry pairs;
3. fallback/sample-age coverage reported by city and lead;
4. Very Poor+ POD/FAR/CSI and event counts compared with raw Aurora and
   persistence;
5. no public selection unless event safety is protected.

## WS-3 — Calibrator guardrails

The v1 direct-target calibrator remains a documented negative baseline. Its
save path reports event metrics beside MAE and refuses a model that reduces
Very Poor+ POD relative to raw Aurora. Regime-shift and seasonal-transfer tests
exist. The complete 84-test suite passed in the exact RunPod environment. The
local Python launcher is currently broken, so this is not described as a fresh
local pass.

## WS-4 — Reporting

`src/report/` can render per-city and per-lead scorecards. It is a consumer of
metrics, not evidence by itself. Do not publish the legacy PNGs as current
results. Every event score must carry its event count and split label.

## WS-5 — Fine-tuning design

Fine-tuning is deliberately downstream of the cheap baselines. The design
document must define what is trainable, loss weighting for severe events,
rollout length, memory budget, split discipline, catastrophic-forgetting
checks, and the exact improvement needed over raw Aurora, persistence,
Component A, and the guarded calibrator.

## WS-6 — GPU rollout

The required cloud inference is complete. Four isolated slices produced 14
dates and 20,034 rows each, for 56 dates and 80,136 rows total. Each slice has
159 stations, the expected nine rows per station, a current registry stamp,
and zero worker errors. All returned pair files and worker manifests matched
their remote copies by SHA-256.

All 56 atmospheric-analysis and actual-forecast inputs are local and validated.
Each worker receives one 14-date bundle and runs with `--offline-inputs`; no
provider credentials belong on a worker.

The rollout created model/station pairs without receiving the untracked OpenAQ
archive or provider credentials. All outputs are back on the machine holding
the archive. The remaining WS-6 work is CPU-side: merge the four worker
manifests, run the integrity audit, and only then hand the pairs to evaluation.

## WS-7 — Product and interface

The current `web/` application is a product preview. Its numbers are fixtures,
not forecasts or benchmark results. The live implementation must consume the
versioned contract in `docs/LIVE_FEED_SPEC.md`, display source age and missing
methods, preserve immutable forecasts before observations arrive, and carry an
experimental-research disclaimer.

## WS-8 — Additional data

Implemented foundations:

1. actual CAMS forecast values at +12 through +96 hours as a separate baseline,
   integrated into the resumable orchestrator and strict evaluator; all 56
   frozen dates are downloaded and validated at 71,232 station-lead rows;
2. all 56 global CAMS atmospheric-analysis inputs for Aurora, deep validated at
   12.397 GiB and ready for credential-free worker bundles;
3. a minimal official OGD India CPCB live-feed pilot for Patna/Varanasi with
   immutable private snapshots and conservative station matching;

Remaining priorities are:

4. one-day/manual official historical export tests or formal data requests;
5. FIRMS and Sentinel-5P as explanatory UI layers;
6. predictive feature experiments only after availability-time controls and
   held-out-city ablations.

No licence-clear historical Patna/Varanasi hourly archive has yet been
verified. Aakash data can support northwest-India transport diagnostics, but
its geography and CC BY-NC-ND terms make it unsuitable for silent integration.

## WS-9 — Publication

The repository remains private. Before any visibility change:

1. pass Python CI and the web build;
2. rerun the data-dependent integrity audit locally;
3. choose a software licence;
4. choose a clean public mirror or explicitly authorize a reviewed history
   rewrite;
5. recheck secrets and large historical blobs;
6. set the GitHub description/topics and verify all links anonymously.

See `docs/PUBLICATION_READINESS.md`.

## Handoff discipline

Before stopping any workstream:

1. verify claims with a command or cited primary source;
2. update `docs/HANDOFF.md` if the critical state or exact next command changed;
3. append the decision and verification to `JOURNAL.md`;
4. commit only reviewed files;
5. never present an unrun test, illustrative UI value, or legacy pair as a
   validated result.
