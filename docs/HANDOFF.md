# Handoff: IndiaAQBench current state

**Updated:** 2026-08-11
**Branch:** `master`
**Scientific state:** 24-hour and hourly scorecards complete; one audit failure remains
**Product status:** illustrative preview only; no live feed
**Documentation state:** README, `PRODUCT_SPEC`, `PROJECT_STATUS`,
`PUBLICATION_READINESS`, `EXECUTION_PLAN` and `WORKSTREAMS` reconciled with the
completed rollout on 2026-08-11. No scientific result changed.

## Objective and claim boundary

IndiaAQBench tests whether Microsoft Aurora plus inexpensive adaptation can
provide useful multi-day PM2.5 forecasts for underserved Indian cities. Delhi
is a diagnostic environment, not the target. Success means Very Poor+ event
skill (POD/FAR/CSI and event counts), not MAE alone.

The current results use hourly observation matching and hourly application of
CPCB thresholds. They are a sensitivity analysis, not the official 24-hour
headline and not evidence of year-round operational utility.

## Verified state

| Item | State |
|---|---|
| OpenAQ archive | 1,489,534 observations, 159 stations, 9 cities |
| Frozen schedule | 56 dates: 32 train, 24 test |
| Actual CAMS forecast archive | 56 dates, 71,232 positive-lead station rows |
| Aurora rollout | 56 dates, 80,136 rows, registry `159:4c0b55ad238f` |
| Canonical manifest | 56 records, 56 unique dates, zero errors, zero duplicates |
| Legacy pairs | 2025-11-15 and 2025-11-20 remain on disk and are strictly excluded |
| Tests | 91/91 pass locally (re-verified 2026-08-11) |
| Audit | 39 checks: 36 pass, 2 expected legacy warnings, 1 size-bin failure (re-verified 2026-08-11) |
| Raw/Component A scorecards | 24-hour headline and hourly sensitivity generated separately |
| Accepted calibrator | Absent; full-registry fit failed the POD no-harm gate |
| Public live forecast | Absent |

The local `.venv` is healthy: Python 3.11.9. The earlier broken-environment
claim was caused by a restricted Codex sandbox, not the repository runtime.

## Outstanding audit failure and scoped decision

Aurora violates `PM1 <= PM2.5 <= PM10` on 463 of 80,730 stored rows (0.5735%).
The median excess is 0.265 µg/m³ and the maximum is 6.269 µg/m³. Violations
span 23 dates and every positive lead. The audit retains this as a failure.

Raw Aurora, persistence, CAMS, and Component A consume only PM2.5. PM1 and PM10
were removed from the calibrator and regression-tested as non-features. The
benchmark specification records this path-specific scoring decision. Do not
describe the full Aurora output as physically clean, and do not remove or
downgrade the audit check.

## First scorecard decision

On pooled temporal-test rows, Component A improves raw Aurora from POD 0.483,
FAR 0.721, CSI 0.215, and MAE 32.76 to POD 0.566, FAR 0.585, CSI 0.315, and MAE
26.52 across 2,113 observed Very Poor+ events.

In the 24-hour headline, Component A improves L1 at every window and improves
pooled CSI, but L2 POD falls from 0.798 to 0.755 across 94 events. The hourly
sensitivity also has an L1 +84-hour POD regression. Component A is promising
but **not certified for public selection**.

The direct-target calibrator again improved MAE while destroying event POD:

- L1: MAE 33.9 → 24.5, POD 0.474 → 0.125;
- L2: MAE 34.2 → 20.2, POD 0.748 → 0.299.

The guardrail refused to save an accepted model. The prior binary was renamed
`results/models/rejected_pilot_calibrator.joblib`; the accepted default path is
`results/models/accepted_pooled_calibrator.joblib` and does not exist.

## Exact next scientific action

1. Freeze/version the generated per-city, per-window, pooled train-city, L1,
   and L2 table and connect it to the reporting package. Concretely:
   `src/eval/rolling24.py` writes `results/metrics/indiaaqbench_24h.csv` (and
   `indiaaqbench_24h_anchor.csv`), but `src/report/scorecard.py` still defaults
   to the hourly `results/metrics/indiaaqbench.csv`, so the reporting package
   does not yet render the 24-hour headline.
2. Keep raw Aurora as the public fallback; do not tune Component A on observed
   test outcomes. Any new policy needs a newly predeclared validation design.
3. Start `docs/FINETUNE_DESIGN.md` only after the cheap-baseline findings are
   frozen; any learned method must beat raw Aurora and Component A on event
   skill, not merely MAE.
4. Continue the live-runner/immutable-ledger path in private shadow mode.

No more GPU compute is required for this retrospective benchmark.

## Publication boundary

The repository remains private. Before publication it still needs a software
licence, a clean-mirror or reviewed-history decision for historical OpenAQ
blobs, current CI on the eventual publication commit, and anonymous link and
secret checks. Scientific posts must disclose the cutoff revision, missing
post-monsoon test, hourly-versus-24-hour distinction, audit failure, and the
rejected calibrator.
