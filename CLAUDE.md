# IndiaAQBench — read this first

Auto-loaded every session. **If you read nothing else, read this file, then
`docs/HANDOFF.md`.** Everything needed to continue lives in this repo; no
knowledge is stranded in a chat session.

## What this project is

An open, reproducible benchmark testing whether cheap adaptation can lift
**Microsoft Aurora** (1.3B atmospheric foundation model) into a *practically
useful* multi-day PM2.5 forecaster for Indian cities.

- **Target is NOT Delhi.** Delhi already has AQEWS (WRF-Chem 400 m, PI 87) and we
  cannot and should not try to beat it. The target is the **~465 Indian cities
  with no public forecast system** — Patna, Varanasi, Kanpur, Lucknow and peers.
- **Success is event skill, not MAE.** Very Poor+ (≥121 µg/m³) **POD / FAR / CSI**
  per lead time, because GRAP emergency actions trigger on forecast *category*.
  A model with great MAE that misses every episode is worthless here. We have
  already been burned by exactly this (see Rejected below).

## Where to look

| You need | File |
|---|---|
| Current state + next command | **`docs/HANDOFF.md`** |
| Who owns which files (parallel work) | `docs/WORKSTREAMS.md` |
| 2-day schedule, risks | `docs/EXECUTION_PLAN.md` |
| The benchmark definition (metrics, splits, cities) | `docs/BENCHMARK_SPEC.md` |
| Split constants — **the only source of truth** | `src/splits.py` |
| Session-by-session history and reasoning | `JOURNAL.md` |
| GPU runbook | `scripts/setup_gpu.md` |

## Ground rules

1. **Verify, don't assume.** Run the check before asserting. This project has
   repeatedly found that plausible-looking beliefs were wrong (see below).
2. **Report negative results honestly.** They are the most valuable output here.
3. **Never edit split constants outside `src/splits.py`.** They used to be
   duplicated in three modules; drift there silently corrupts train/test.
4. **Run `python -m src.eval.audit` before trusting any results table.**
5. Record decisions in the repo (spec, docstring, journal) — never only in chat.
6. Working on something in parallel? Claim a workstream in `docs/WORKSTREAMS.md`,
   use its branch, and stay inside its file ownership.

## Settled — do NOT re-litigate

- **No A100 needed.** Aurora's docs specify ~40 GB for 0.25° *inference*; the
  A100-80GB figure applies to 0.1° + backprop. We run 0.4° inference → a
  ~$0.50/hr 48 GB spot GPU (A6000). Azure quota was denied and is irrelevant.
- **OpenAQ has no data before ~Feb 2025.** Location metadata claims 2016, but the
  hours endpoint serves nothing earlier for *any* sensor, old or new — verified
  at sensor level (`src/data/archive_probe.py`). Backfill is impossible.
- **Temporal cutoff is 2025-12-01**, revised once from 2025-07-01 under the
  contingency pre-registered in spec §6, before any adaptation was trained on it.
  **Disclose this wherever results appear.**
- **Calibration comes before fine-tuning, but does not replace it.** Fine-tuning
  is still planned (task #14); it needs the baseline as a bar to beat.

## Rejected — do not propose again

- **v1 pooled calibrator** (gradient boosting predicting `log1p(obs)` directly):
  Very Poor+ POD **0.00** at every lead, caught **0 of 99** events, vs raw
  Aurora's 0.64 — while MAE *improved*. Trees cannot extrapolate and predicting
  the target caps output at the training distribution. Kept in
  `src/model/calibrator.py` as a documented negative baseline.
- **Serial 56-date rollout on one box** (~10 h). Dates are independent — split
  across 4 GPUs (~2.5 h, ~$5).

## Common commands

```bash
python -m src.eval.audit                     # integrity checks — run this often
python -m src.data.archive_pull              # resumable OpenAQ pull
python -m src.data.archive_pull --assemble-only   # rebuild CSVs offline, no network
python -m src.data.build_station_registry    # data/stations.csv
python -m src.eval.coverage_audit --n 56     # re-freeze benchmark dates
python -m src.pipeline.orchestrate --dates-file docs/benchmark_dates.csv --device cuda
python -m src.eval.benchmark                 # score all baselines
```

Environment: `.venv/Scripts/python.exe` (Windows). Credentials in `.env`
(`OPENAQ_API_KEY`) and `~/.cdsapirc` (Copernicus ADS).
