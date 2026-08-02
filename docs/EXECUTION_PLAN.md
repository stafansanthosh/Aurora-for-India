# IndiaAQBench execution plan

**Updated:** 2026-08-02

The goal is a publicly understandable experimental forecast feed backed by a
credible benchmark. The product can become useful before year-round scientific
validation is complete, but every screen and post must distinguish
illustrative design, retrospective evidence, and prospective live forecasts.

## 1. Current gates

| Gate | State |
|---|---|
| Nine-city observation archive | Complete |
| 159-station registry | Complete |
| 56-date schedule | Complete |
| Calibrator guardrails | Complete; 83-test suite passes |
| Component A implementation | Complete; evaluation pending |
| Reporting code | Complete |
| Product/live-feed specification | Complete |
| UI preview | Complete; CI build/render and private deployment pass |
| Valid 159-station pairs | **0** |
| Actual CAMS forecast baseline | Complete: 56 dates, 71,232 station-lead rows |
| Aurora CAMS analysis inputs | Complete: 56 dates, 12.397 GiB, deep validated |
| Live runner/ledger | **Absent** |
| Public repository | **Blocked by licence/history/checks** |

## 2. Scientific critical path

```text
four-worker Aurora rollout
  -> copy 56 current-registry pair files home
  -> verify 1,431 rows/date and 80,136 total
  -> integrity audit
  -> raw baseline scorecards
  -> Component A scorecard
  -> guarded calibrator scorecard
  -> fine-tuning decision
```

Both CAMS archives have been downloaded and validated locally. Build four
disjoint input bundles with `python -m scripts.package_gpu_inputs`; each worker
receives only its 14 dates. The orchestrator verifies every retained request
and raw-file checksum before loading Aurora and fails closed if any local input
is absent. Workers need no Copernicus, OpenAQ, GitHub, or SSH credentials. Only
Aurora inference requires the GPU. Pair generation does not need the untracked
OpenAQ archive; scoring does, so copy the pairs back before evaluation.

On each configured worker:

```bash
tail -n +2 docs/benchmark_dates.csv | cut -d, -f1 | split -n l/4 -d - slice_
python -m src.pipeline.orchestrate --dates-file slice_00 --device cuda --offline-inputs
```

Use one distinct slice (`slice_00` through `slice_03`) per worker. See
`scripts/setup_gpu.md`.

After retrieval:

```bash
python -m src.eval.audit
python -m src.eval.benchmark
python -m src.eval.benchmark --anchor
python -m src.model.calibrator
python -m src.eval.benchmark --calibrator results/models/pooled_calibrator.joblib
```

Do not trust or publish any table if the audit fails.

## 3. Product path

This path can proceed while the retrospective rollout runs:

1. Pass the web build and source tests in a clean CI environment.
2. Replace interface fixtures with the versioned public JSON contract.
3. Implement latest-CAMS-cycle detection, input validation, and an immutable
   forecast ledger.
4. Publish raw Aurora first if no correction has passed the event-safety gate.
5. Run privately in shadow mode for at least 14 days and 20 complete cycles.
6. Publish an experimental nine-city beta with freshness, missing-method
   states, provenance, cost, and an explicit non-warning disclaimer.
7. Score observations only after they arrive and retain every miss.

The initial product is useful as an auditable experiment. It is not a
year-round reliability claim or an official health service.

## 4. Additional-data path

The first addition is the actual lead-dependent CAMS forecast:

1. Retrieve CAMS PM2.5 at +12 through +96 hours from the same initialization.
2. Store it separately from Aurora's lead-zero CAMS inputs.
3. Sample it at the same stations and match it to the same observations.
4. Label the existing comparator “CAMS starting field held constant.”
5. Report whether Aurora adds skill over the forecast CAMS actually issued.

A tiny official OGD India CPCB live-feed pilot for Patna and Varanasi is
implemented. It writes immutable private snapshots, preserves provider fields,
and refuses fuzzy station matches. Running the live probe requires a
`DATA_GOV_IN_API_KEY`; it remains an optional latency/completeness diagnostic,
not a prerequisite for the frozen benchmark.

FIRMS and Sentinel-5P begin as explanatory layers. They become predictive
features only after availability-time controls and one-at-a-time held-out-city
ablations.

## 5. Publication path

The current repository remains private. Before sharing a GitHub link publicly:

1. pass Python CI and the web build;
2. rerun the local data-dependent audit;
3. choose a software licence;
4. create a clean public mirror or explicitly authorize a reviewed destructive
   history rewrite;
5. rerun secret and large-history checks;
6. set the GitHub description/topics;
7. verify README links anonymously.

A portfolio soft launch can happen once those software/publication gates pass,
even while the full benchmark is running. The main technical post should wait
for a versioned 159-station scorecard. The product launch should wait for
shadow-mode evidence.

## 6. Fine-tuning decision

Do not buy substantially more training compute until the cheap ladder is
scored. A fine-tuning design must define:

1. which parameters are trainable;
2. a loss that protects severe-event detection;
3. station-sparse versus gridded supervision;
4. training rollout length and memory budget;
5. L1/L2 and temporal leakage controls;
6. catastrophic-forgetting tests;
7. the minimum gain over raw Aurora, persistence, actual CAMS forecast,
   Component A, and the guarded calibrator that justifies the cost.

More compute is transformational only if the error is representational rather
than a missing-input, data-quality, or surface-observation problem. The
baseline ladder identifies which case applies.

## 7. Main risks

| Risk | Control |
|---|---|
| Stale or wrong-registry pairs | Registry stamp, frozen-date filter, audit |
| Correction improves MAE but misses events | POD no-harm gate and event counts |
| Component A is mislabeled zero-shot | State that it uses trailing local observations |
| Actual CAMS and lead-zero CAMS are conflated | Separate storage, columns, and labels |
| Live input arrives after forecast initialization | Availability-time enforcement |
| Illustrative UI values are mistaken for results | Persistent demo labeling and source tests |
| Raw data leak during repository publication | Clean mirror/history decision and audit |
| One season drives public claims | Prospective immutable scorecard and untouched post-monsoon evidence |
