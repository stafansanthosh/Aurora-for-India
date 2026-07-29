# Presenting IndiaAQBench in a portfolio

This guide helps the project owner describe the work accurately in job
applications, interviews, and public posts. It separates demonstrated
engineering work from scientific results that are still pending.

## Accurate one-line description

> Building an open, event-focused benchmark and experimental forecasting
> pipeline that tests whether Microsoft Aurora can be adapted with public
> observations and modest compute for multi-day PM2.5 forecasting across nine
> Indian cities.

Short version:

> An open, low-compute PM2.5 forecasting benchmark for Indian cities, built on
> Aurora, CAMS, and OpenAQ.

## Resume bullets available now

Use three to five, adjusted to the role:

- Designed a reproducible PM2.5 forecasting benchmark spanning **1,489,534
  hourly observations, 159 stations, and nine Indian cities**, with
  chronological, held-out-station, and held-out-city evaluation.
- Built an end-to-end data and evaluation pipeline joining OpenAQ surface
  observations with CAMS-initialized Microsoft Aurora forecasts at eight lead
  times from **+12 to +96 hours**.
- Defined safety-oriented model evaluation around **Very Poor+ event detection
  (POD, FAR, and CSI)** rather than relying on average error alone.
- Diagnosed a calibration failure that improved MAE while eliminating severe
  event detection, then added no-harm model-save guardrails and regime-shift
  tests to prevent recurrence.
- Implemented reproducibility controls including a versioned station registry,
  frozen dates, centralized split constants, registry-aware resumption, strict
  stale-artifact rejection, and a 39-check integrity audit.

Do not add an accuracy-improvement percentage until the valid 159-station
rollout and full benchmark table exist.

## Evidence to link

For an application submitted now, include:

1. The repository [README](../README.md).
2. The current [project scoreboard](PROJECT_STATUS.md).
3. The [benchmark specification](BENCHMARK_SPEC.md).
4. One code sample appropriate to the role:
   - data engineering: [`src/data/`](../src/data/);
   - ML systems: [`src/pipeline/orchestrate.py`](../src/pipeline/orchestrate.py);
   - evaluation/research:
     [`src/eval/audit.py`](../src/eval/audit.py) and
     [`src/eval/metrics.py`](../src/eval/metrics.py);
   - model safety:
     [`src/model/calibrator.py`](../src/model/calibrator.py);
   - online adaptation:
     [`src/model/anchor.py`](../src/model/anchor.py);
   - reporting: [`src/report/`](../src/report/).
5. The [development journal](../JOURNAL.md) when the audience values research
   reasoning, debugging, and negative results.

Once available, replace secondary code links with:

- a tagged benchmark release;
- a versioned result table;
- one clear per-city event-skill figure;
- the interactive experimental feed;
- a public methodology and limitations page;
- a compute-cost ledger.

Every linked figure should state whether it is diagnostic, pilot, historical,
or from the valid full benchmark. Do not present the existing stale pilot
scorecards as current results.

## What the project demonstrates today

The current repository provides evidence of:

- translating a public-interest problem into a falsifiable ML task;
- designing chronological and spatial evaluation under limited data;
- building resilient environmental-data ingestion and identity handling;
- running a large atmospheric model through a reproducible pipeline;
- choosing metrics based on decision risk rather than convenience;
- identifying leakage and provenance risks;
- documenting negative results and redesigning safety gates;
- coordinating a multi-stage research and product roadmap.

These are already strong engineering and research signals even before the final
accuracy table exists.

## Claims to avoid for now

Do not say:

- “Built an operational air-quality warning system.”
- “Deployed real-time forecasts across India.”
- “Aurora outperforms persistence or CAMS in Indian cities.”
- “The adaptation improves PM2.5 forecasts by X%.”
- “Validated year-round performance.”
- “Proved transfer to cities without observations.”
- “Fine-tuned Aurora for India.”
- “Completed a 56-date benchmark.”
- “The dashboard shows live results.”
- “The system can replace AQEWS, SILAM, CPCB, or official health guidance.”

More precise alternatives are:

- “Building an experimental forecast feed” instead of “deployed a service.”
- “Testing held-out-city transfer” instead of “generalizes nationally.”
- “Designed for low-compute operation” instead of “proved nationwide
  scalability.”
- “An early pilot motivated the guardrail” instead of quoting pilot metrics as
  final results.
- “Research forecast” instead of “warning” or “advisory.”

Also present the train/test cutoff revision openly. It was made once, under a
pre-registered contingency, before adaptation was trained on the revised split.
Hiding it would weaken the project; explaining it demonstrates scientific
judgment.

## Repository readiness before sharing

Before placing the repository in an application or profile, follow the
[publication-readiness gate](PUBLICATION_READINESS.md). In particular, the
current private repository still contains historical raw observation blobs in
reachable Git history, so it must not simply be made public as-is.

- [ ] Decide between a reviewed history rewrite and a clean public mirror.

- [ ] Confirm the repository contains no credentials, private data, machine
  paths, or cloud account details.
- [ ] Choose and add an explicit software and data licence. A public repository
  without a licence is viewable but does not automatically grant reuse rights.
- [ ] Set a concise repository description and relevant topics on GitHub.
- [ ] Ensure the default branch opens on the current README and project status.
- [ ] Run the integrity audit and tests in a clean environment.
- [x] Add continuous integration so visitors can see the 26-test and web-build
  checks passing.
- [ ] Check that every README link and image renders on GitHub.
- [ ] Pin the repository on the owner’s GitHub profile.
- [ ] Label legacy artifacts clearly or move them into a tagged historical
  release.
- [ ] Create a stable release tag for any result quoted outside the repository.

The repository is suitable as supplementary application material once the
public-facing documentation is merged and the security/licence checks above are
complete. Its status page must remain visible so reviewers understand that
full-registry results are pending.

## When to post publicly

### Stage 1 — portfolio soft launch

**Timing:** after the README/status documentation is merged, secrets are
checked, a licence is selected, and tests run cleanly.

Appropriate channels:

- job applications;
- a pinned GitHub repository;
- a short “building in public” post;
- direct sharing with researchers or potential collaborators.

Lead with the problem, benchmark design, negative calibration lesson, and
low-compute thesis. Say that the valid full benchmark is running; do not lead
with pilot accuracy.

### Stage 2 — first substantial technical post

**Timing:** after all 56 dates have valid 159-station pairs, the audit passes,
and at least one versioned per-city/L1/L2 scorecard is published.

This is the best moment for the main technical post because readers will have:

- a clear question;
- a reproducible evaluation;
- defensible baseline results;
- an honest failure and redesign story;
- concrete next steps toward a public feed.

If a single “launch post” is preferred, wait for this milestone.

### Stage 3 — experimental product launch

**Timing:** after a live runner has operated in private shadow mode long enough
to expose scheduling, data-latency, and missing-input failures.

The launch should link directly to:

- the interactive feed;
- current forecast freshness;
- the immutable model/version record;
- a rolling scorecard;
- methodology and limitations;
- an “experimental research forecast, not an official warning” disclaimer.

The initial feed can cover nine cities. Nationwide claims are unnecessary.

### Stage 4 — prospective evidence updates

Post updates after meaningful evidence milestones, not on a fixed marketing
calendar:

- 30 and 90 days of live verification;
- the first independently observed severe episodes;
- new held-out-city results;
- an untouched post-monsoon evaluation;
- a dataset release that materially increases history or coverage;
- a controlled fine-tuning result that clears the cheap-adaptation baseline.

Negative or mixed outcomes are post-worthy when they change the design. The
calibrator failure is a good example: it demonstrates why average error alone
is unsafe for an event-warning use case.

## Suggested interview narrative

Use a five-part structure:

1. **Problem:** useful multi-day forecasts are unevenly available across Indian
   cities.
2. **Constraint:** build with public data and modest compute rather than a
   national high-resolution chemistry-model budget.
3. **Scientific design:** test time transfer, new stations, and entirely
   held-out cities; prioritize severe-event detection.
4. **Failure and response:** an MAE-improving calibrator erased the severe tail,
   exposing data, split, and metric weaknesses; the pipeline now rejects unsafe
   models and stale artifacts.
5. **Product direction:** publish an experimental feed whose predictions are
   versioned before outcomes exist and whose rolling accuracy is visible to
   everyone.

That story is stronger than claiming the model is already solved. It shows
technical depth, scientific discipline, product judgment, and a credible route
from research to public utility.

Return to the [README](../README.md) or check the current
[project status](PROJECT_STATUS.md).
