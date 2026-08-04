# Handoff: IndiaAQBench current state

**Updated:** 2026-08-04
**Branch:** `master`
**Scientific blocker:** merge the four worker manifests and pass the full local audit
**Product status:** interface preview and specifications exist; no live feed

## Objective and non-negotiables

IndiaAQBench tests whether Microsoft Aurora plus inexpensive, auditable
adaptation can provide useful multi-day PM2.5 forecasts for Indian cities that
lack a strong public forecasting system. Delhi is a dense diagnostic
environment, not the target.

Success means detecting **Very Poor+ events (at least 121 µg/m³)**. POD, FAR,
CSI, and event counts are headline results; MAE is secondary. Split constants
live only in `src/splits.py`. Run `python -m src.eval.audit` before trusting a
results table.

## Verified current state

| Item | State |
|---|---|
| OpenAQ archive | Complete: 1,489,534 observations |
| Station registry | Complete: 159 stations across 9 cities |
| Frozen dates | Complete: 56 dates, 32 train and 24 test |
| Actual CAMS forecasts | Complete: 56 dates, 71,232 station-lead rows |
| Aurora CAMS analysis inputs | Complete: 56 dates, 12.397 GiB, deep validated |
| Aurora rollout artifacts | **Complete: 56 dates, 80,136 rows, 159 stations** |
| Worker validation | Four slices; 14 dates and 20,034 unique rows each; zero errors |
| Transfer integrity | All returned pair files and worker manifests match remote SHA-256 hashes |
| Canonical manifest | **Not merged yet**; `manifest_worker_0.jsonl` through `_3.jsonl` are preserved separately |
| Integrity audit | **Pending after the full rollout** |
| Tests | 84/84 passed in the exact RunPod environment; local launcher is broken |
| Valid full benchmark table | **Absent** |
| Public live forecast | **Absent** |

The four-worker rollout used three RTX A6000 GPUs for slices 01–03 after the
earlier slice 00 run. Every worker used an isolated tree, its exact 14-date
offline bundle, a clean output ledger, and one assigned GPU. The source archive
for slices 01–03 came from commit `ad898e3` and had SHA-256
`978f0c25edcc1cecd2ed1e401f0b276bc1fe079373aa0591b4c5090db0d04cac`.
No Copernicus, OpenAQ, GitHub, or SSH private credentials were copied to the
workers.

Two legacy pilot-only pair files remain for 2025-11-15 and 2025-11-20. Neither
date is in the frozen schedule, so the strict loader must continue to reject
them. The current rollout replaced the three pilot files whose dates do occur
in the schedule.

The temporal cutoff changed once from 2025-07-01 to 2025-12-01 under the
pre-registered data-coverage contingency, before adaptation was fitted on the
revised split. Every public result must disclose that change. The frozen test
period has no post-monsoon dates, so the present benchmark cannot support a
year-round utility claim.

## Model and product state

- Component A is implemented in `src/model/anchor.py` and integrated through
  `src/eval/benchmark.py --anchor`, but it has not been scored on the completed
  rollout. It uses trailing local observations, including in held-out cities;
  call it “held-out-city transfer with trailing local observations,” not pure
  zero-shot transfer.
- The v1 calibrator remains a negative baseline. Its guardrail refuses to save
  a model that reduces Very Poor+ POD relative to raw Aurora. No full-registry
  calibrator result exists.
- Reporting code exists, but no official full-registry table or figure exists.
- The `web/` application is an illustrative private preview, not a live
  forecast service. The latest-cycle runner and immutable ledger are absent.
- Fine-tuning design and implementation are absent and remain downstream of
  the cheap baseline comparison.

## Publication boundary

The GitHub repository remains private. It must not simply be switched public:

- reachable Git history contains large raw OpenAQ files even though they are
  not tracked at `HEAD`;
- there is no repository licence;
- the post-rollout audit and official scorecards are not complete.

The safest publication route remains a clean public mirror containing only an
approved source snapshot. A history rewrite is destructive and requires
explicit owner approval. See `docs/PUBLICATION_READINESS.md`.

## Exact next scientific action

No more GPU compute is required for this retrospective rollout. First repair or
recreate the local Python 3.11 environment. Then run:

```powershell
python scripts/merge_worker_manifests.py `
  results/pairs/manifest_worker_0.jsonl `
  results/pairs/manifest_worker_1.jsonl `
  results/pairs/manifest_worker_2.jsonl `
  results/pairs/manifest_worker_3.jsonl
python -m src.eval.audit
```

Only if the audit passes, continue in this order:

```powershell
python -m src.eval.benchmark
python -m src.eval.benchmark --anchor
python -m src.model.calibrator
python -m src.eval.benchmark --calibrator results/models/pooled_calibrator.joblib
```

Do not fit calibration, publish metrics, or label Component A accepted before
the audit and raw baseline scorecard exist.

## Local environment

The project `.venv` launcher targets a missing Python 3.11 base executable, and
neither `python` nor `py` is currently available on `PATH` in the Codex shell.
That blocks the required local manifest merge, audit, and benchmark. It does
not invalidate the remotely validated and checksum-verified rollout files.

## Rejected paths

- The v1 direct-target calibrator as an accepted model: it improved MAE while
  detecting 0 of 99 pilot Very Poor+ events.
- OpenAQ pre-February-2025 backfill: unavailable at sensor level.
- An A100: unnecessary for 0.4° inference.
- Calling Component A zero-shot: it uses recent local observations.
- Publishing pilot metrics or unaudited rollout outputs as current results.
