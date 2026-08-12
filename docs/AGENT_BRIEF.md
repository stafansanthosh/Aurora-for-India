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

An open, reproducible benchmark testing whether **cheap, observation-grounded
adaptation** can make global-tier PM2.5 forecasts more useful for pollution
episode warning. The completed India retrospective compares Microsoft Aurora,
actual CAMS, persistence, and local anchoring at 159 stations; it is evidence
about method behaviour, not yet a validated public service.

- **The original target premise was falsified.** Patna, Varanasi, Kanpur and
  Lucknow must not be described as having no forecast. The 400 m AQEWS figure is
  the Delhi nest, not the national domain; India also has national/regional
  AQEWS, SILAM, and multi-city bulletin products. Direct portal coverage still
  needs confirmation before making a precise city-by-city incumbent claim.
- **Delhi is a development and diagnostic environment, not a transferable
  headline.** It supplies 89.1% of the benchmark's Very Poor+ windows. Any
  pooled result must travel with per-city counts, and the present L2 result is
  mostly Kolkata rather than evidence for Varanasi, Kanpur, or Patna.
- **Success is event skill, not MAE.** Very Poor+ (≥121 µg/m³)
  **POD / FAR / CSI** per lead time, because India's GRAP emergency actions
  trigger on forecast *category*. A model with excellent MAE that misses every
  pollution episode is worthless here — and we have already been burned by
  exactly that (see "Rejected" below).
- **Current direction:** predict `P(24 h PM2.5 >= 121)` directly and publish an
  operating point. The train-only, perfect-prognosis ERA5 boundary-layer
  kill-test passed its pre-declared gate (`docs/BLH_CEILING_RESULT.md`), but it
  is a ceiling rather than forecast skill. Next quantify forecast-vs-analysis
  BLH degradation and verify whether a free NWP forecast supplies the field.
  Do not spend GPU money on Aurora 1.5 yet.

## Map of the repo

| You need | File |
|---|---|
| Current state + the exact next command | **`docs/HANDOFF.md`** |
| Current Option B experiment contract | **`docs/CODEX_BRIEF_OPTION_B.md`** |
| Why the founding target changed | `docs/TARGET_REEVALUATION.md` |
| Why concentration calibration failed | `docs/EPISODE_SKILL_DIAGNOSIS.md` |
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
- **The no-forecast-city premise is retired.** Do not reinstate the claim that
  Patna or Varanasi is unserved. The defensible question is whether cheap local
  and meteorological adaptation improves episode skill over the global tier or
  a verified incumbent.
- **Option B cleared its CPU ceiling gate.** Perfect-prognosis ERA5 improved
  pooled AUC by 0.046 and best CSI by 0.206; Patna improved by 0.183 and 0.296.
  These are upper-bound analysis results, not an operational forecast. The next
  gate is forecast BLH degradation; no GPU rollout is authorized yet.

## Rejected — do not propose again

- **v1 pooled calibrator** — gradient boosting predicting `log1p(obs)` directly
  from Aurora features. Scored Very Poor+ POD **0.00** at every lead, caught
  **0 of 99** events, versus raw Aurora's 0.64 — while MAE *improved*. Two
  structural causes: predicting the target caps output at the training
  distribution, and trees cannot extrapolate. Kept in `src/model/calibrator.py`
  as a documented negative baseline.
- **Any replacement concentration regressor followed by thresholding.** The
  binding failure is the average-error objective, not merely the tree family.
  New adaptation must model exceedance probability under a pre-declared
  validation design.
- **Patna/Varanasi as cities with no forecast.** The founding framing is
  falsified; see `docs/TARGET_REEVALUATION.md`.
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
python -m src.pipeline.orchestrate --dates-file slice_0N --device cuda --offline-inputs
python -m src.eval.benchmark                      # score all baselines
```

Windows: use `.venv/Scripts/python.exe`. Local acquisition credentials: `.env`
(`OPENAQ_API_KEY`), `~/.cdsapirc` (Copernicus ADS). GPU workers receive neither.

## Before you stop

Update `docs/HANDOFF.md` ("Current state" and "Immediate next step"), append a
`JOURNAL.md` entry explaining what changed and *why*, then commit and push.
