# IndiaAQBench — canonical agent brief

**This file is the single source of truth for any AI agent working on this repo**
(Claude Code, OpenAI Codex, GitHub Copilot, or a human picking it up cold).
`CLAUDE.md`, `AGENTS.md` and `.github/copilot-instructions.md` are thin pointers
to this file — deliberately, so three copies cannot drift apart.

> Note: `COPILOT_CONTEXT.md` (553 lines, Phase 1) is **historically useful but
> its framing is outdated**. Trust its data contracts (§4.1 QC rules, §6 geo
> matching); ignore its objective statement — the project moved on from
> "does Aurora work out of the box vs persistence" to the benchmark below.

## What this project is

An open, reproducible benchmark testing whether **cheap adaptation** can lift
**Microsoft Aurora** (1.3B-parameter atmospheric foundation model) into a
*practically useful* multi-day PM2.5 forecaster for Indian cities.

- **The target is NOT Delhi.** Delhi already runs AQEWS (WRF-Chem 400 m,
  Performance Index 87). We cannot and should not try to beat it. The target is
  the **~465 Indian cities with no public forecast system** — Patna, Varanasi,
  Kanpur, Lucknow and peers.
- **Success is event skill, not MAE.** Very Poor+ (≥121 µg/m³)
  **POD / FAR / CSI** per lead time, because India's GRAP emergency actions
  trigger on forecast *category*. A model with excellent MAE that misses every
  pollution episode is worthless here — and we have already been burned by
  exactly that (see "Rejected" below).
- **Adaptation ladder:** calibration first (cheap, CPU), then scoped
  fine-tuning. Calibration does not replace fine-tuning; it establishes the bar
  fine-tuning must clear.

## Map of the repo

| You need | File |
|---|---|
| Current state + the exact next command | **`docs/HANDOFF.md`** |
| Who owns which files (parallel work) | `docs/WORKSTREAMS.md` |
| Copy-paste session prompts | `docs/SESSION_STARTERS.md` |
| Schedule, risks | `docs/EXECUTION_PLAN.md` |
| Benchmark definition (metrics, splits, cities) | `docs/BENCHMARK_SPEC.md` |
| Split constants — **only source of truth** | `src/splits.py` |
| History and reasoning, session by session | `JOURNAL.md` |
| GPU runbook | `scripts/setup_gpu.md` |

Pipeline: `src/data/` (OpenAQ + CAMS) → `src/pipeline/orchestrate.py` (Aurora
rollout +12h…+96h, sampled at station cells) → `src/eval/benchmark.py` (baselines
+ metrics). Adaptation lives in `src/model/`.

## Ground rules

1. **Verify, don't assume.** Run the check before asserting. This project has
   repeatedly found that plausible beliefs were wrong — a "structural data gap"
   that was really a sensor-selection bug, a calibrator that looked good on MAE
   while catching 0 of 99 events.
2. **Report negative results honestly.** They are the most valuable output here.
3. **Never define split constants outside `src/splits.py`.** They were once
   duplicated across three modules; drift there silently corrupts train/test.
4. **Run `python -m src.eval.audit` before trusting any results table.**
5. **Record decisions in the repo** — spec, docstring, or `JOURNAL.md`. Never
   leave a decision only in a chat session.
6. **Stay inside your workstream's file ownership** (`docs/WORKSTREAMS.md`) and
   work on its branch. Two agents editing one file is the main way parallel work
   breaks.

## Settled — do NOT re-litigate

- **No A100 needed.** Aurora's docs specify ~40 GB for 0.25° *inference*; the
  A100-80GB figure applies to 0.1° + backprop through rollouts. We run 0.4°
  inference → a ~$0.50/hr 48 GB spot GPU (A6000). Azure quota was denied and is
  irrelevant.
- **OpenAQ has no data before ~Feb 2025.** Location metadata advertises 2016, but
  the hours endpoint serves nothing earlier for *any* sensor, retired or active —
  verified at sensor level (`src/data/archive_probe.py`). Backfill is impossible.
- **Temporal cutoff is 2025-12-01**, revised once from 2025-07-01 under the
  contingency pre-registered in spec §6, before any adaptation was trained on it.
  **Disclose this wherever results appear.**
- **Delhi is a diagnostic instrument, not the goal** (most stations = fastest
  signal), but never the headline claim.

## Rejected — do not propose again

- **v1 pooled calibrator** — gradient boosting predicting `log1p(obs)` directly
  from Aurora features. Scored Very Poor+ POD **0.00** at every lead, caught
  **0 of 99** events, versus raw Aurora's 0.64 — while MAE *improved*. Two
  structural causes: predicting the target caps output at the training
  distribution, and trees cannot extrapolate. Kept in `src/model/calibrator.py`
  as a documented negative baseline.
- **Backfilling OpenAQ history** — proven unavailable.
- **Any A100 / fighting the Azure quota.**
- **Serial 56-date rollout on one box** (~10 h) — dates are independent, so split
  across 4 GPUs (~2.5 h, ~$5).

## Commands

```bash
python -m src.eval.audit                          # integrity checks - run often
python -m src.data.archive_pull                   # resumable OpenAQ pull
python -m src.data.archive_pull --assemble-only   # rebuild CSVs offline
python -m src.data.build_station_registry         # data/stations.csv
python -m src.eval.coverage_audit --n 56          # re-freeze benchmark dates
python -m src.pipeline.orchestrate --dates-file docs/benchmark_dates.csv --device cuda
python -m src.eval.benchmark                      # score all baselines
```

Windows: use `.venv/Scripts/python.exe`. Credentials: `.env`
(`OPENAQ_API_KEY`), `~/.cdsapirc` (Copernicus ADS).

## Before you stop

Update `docs/HANDOFF.md` ("Current state" and "Immediate next step"), append a
`JOURNAL.md` entry explaining what changed and *why*, then commit and push.
