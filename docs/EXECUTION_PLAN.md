# IndiaAQBench execution plan

**Updated:** 2026-08-12

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
| Calibrator guardrails | Complete; 91-test suite passes locally (84 tests passed on RunPod at that time) |
| Component A | Scored; pooled gains, one L1 lead-specific POD regression |
| Reporting code | Complete |
| Product/live-feed specification | Complete |
| UI preview | Complete; CI build/render and private deployment pass |
| Aurora rollout and manifest | **Complete: 56 dates and 80,136 rows** |
| Hourly-threshold scorecard | Complete; preliminary sensitivity result |
| 24-hour headline scorecard | Generated; preliminary and not yet released |
| Actual CAMS forecast baseline | Complete: 56 dates, 71,232 station-lead rows |
| Aurora CAMS analysis inputs | Complete: 56 dates, 12.397 GiB, deep validated |
| Live runner/ledger | **Absent** |
| Public repository | **Blocked by licence/history/checks** |
| Event-skill diagnosis | Complete; train-only/out-of-fold, pooled result is Delhi-dominated |
| Target re-evaluation | Complete; “Patna/Varanasi are unserved” premise retired |
| Option B | Kill-test **passed**: dAUC +0.046, dCSI +0.206; Patna +0.183/+0.296 |
| Forecast-BLH gate | **Free GFS sufficient**: dAUC +0.0336, dCSI +0.1620; no Aurora 1.5 run |
| SILAM incumbent archive | Prospective rolling capture in progress |

## 2. Scientific critical path

```text
Option B perfect-prognosis kill-test PASSED
  -> free GFS forecast-vs-analysis BLH gate PASSED (no GPU)
  -> Aurora 1.5 outputs BLH, but adds no justified value over qualified GFS
  -> freeze/version retrospective scorecards
  -> verify incumbent and target-city evidence
  -> private live shadow runner
```

The four-worker Aurora rollout is complete. Each isolated 14-date slice
produced 20,034 rows with 159 stations and zero errors; the combined local
inventory is 56 dates and 80,136 rows. All transferred pair files and worker
manifests matched the remote SHA-256 hashes. No provider credentials or OpenAQ
archive were placed on the workers. No more GPU compute is required for this
retrospective pass. The train-only forecast-BLH gate has now shown that free GFS
retains enough episode signal. No Aurora 1.5 rollout is justified for BLH.

For reproduction, use one distinct slice on each configured worker:

```bash
tail -n +2 docs/benchmark_dates.csv | cut -d, -f1 | split -n l/4 -d - slice_
python -m src.pipeline.orchestrate --dates-file slice_00 --device cuda --offline-inputs
```

Use one distinct slice (`slice_00` through `slice_03`) per worker. See
`scripts/setup_gpu.md`.

The current run has completed these commands. They remain here for
reproduction; the calibrator command is expected to refuse saving when its
event-safety gate fails:

```bash
python -m src.eval.audit
python -m src.eval.benchmark
python -m src.eval.benchmark --anchor
python -m src.model.calibrator
python -m src.eval.benchmark --calibrator results/models/accepted_pooled_calibrator.joblib
```

The known PM-bin audit failure remains blocking for any claim about all Aurora
channels. PM2.5-only scoring follows the explicit scoped decision in
`docs/BENCHMARK_SPEC.md`; it does not convert that failure into a pass.

## 3. Product path

This path can proceed while retrospective audit and scoring run:

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

The actual lead-dependent CAMS forecast addition is complete and scored. The
active data work is now deliberately bounded:

1. Complete and validate the train-only ERA5 boundary-layer acquisition used
   only for the perfect-prognosis Option B ceiling test.
2. Aggregate BLH, ventilation, and dew-point depression over exactly the same
   forward-24-hour windows as the target.
3. Preserve the test split; use GroupKFold by initialization date and report
   results per city.
4. Continue prospective SILAM capture while its rolling public cycles remain
   online, then design an initialization-aligned comparison.
5. Resolve the Varanasi level anomaly against an independent CPCB/UPPCB source
   before making any Varanasi claim.

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

A portfolio soft launch can happen once those software/publication gates pass.
The main technical post should wait
for a versioned 159-station scorecard. The product launch should wait for
shadow-mode evidence.

## 6. Model-spend decision

The Option B ceiling gate passed: pooled ΔAUC +0.046 and ΔCSI +0.206, with
Patna +0.183/+0.296. The follow-on free GFS gate also passed: ΔAUC +0.0336 and
ΔCSI +0.1620, with Patna +0.108/+0.101. Microsoft documentation confirms the
released Aurora 1.5 weather checkpoint outputs BLH, but GFS already clears the
pre-declared hurdle without its HRES input burden or GPU inference. Do not run
Aurora 1.5 for BLH.

Any future Aurora or fine-tuning design would require a new incremental-value
case over GFS and must define:

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
| Pooled skill is mistaken for target-city skill | Always report per-city counts; 89.1% of current events are Delhi |
| Perfect-prognosis ERA5 is presented as achievable | Label it as a ceiling test, never an operational forecast |
| Falsified “unserved city” story returns | Cite target re-evaluation and verify incumbent coverage directly |
