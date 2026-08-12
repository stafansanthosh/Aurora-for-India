# GitHub Copilot instructions — IndiaAQBench

**Read `docs/AGENT_BRIEF.md` first. It is the canonical brief.**
Then `docs/HANDOFF.md` for current state and the exact next command.

Kept thin on purpose: the brief lives in one place so `CLAUDE.md`, `AGENTS.md`
and this file cannot drift apart.

> `COPILOT_CONTEXT.md` in the repo root is **stale Phase-1 material**. Its data
> contracts (QC rules, geo matching) are still valid; its stated objective is
> not. Use `docs/AGENT_BRIEF.md` for the current goal.

## Non-negotiables

1. **Optimize for Very Poor+ (≥121 µg/m³) event skill — POD / FAR / CSI — not
   MAE.** A calibrator that improved MAE while catching 0 of 99 pollution events
   has already been built and rejected. Do not propose MAE-minimizing
   post-processing.
2. **Do not reinstate the falsified “unserved cities” premise.** Patna,
   Varanasi, Kanpur, and Lucknow have national/regional forecast products;
   Delhi is a diagnostic environment. Read `docs/TARGET_REEVALUATION.md`.
3. **Split constants are defined only in `src/splits.py`** — never redefine the
   temporal cutoff, held-out cities, or the L1 station hash elsewhere.
4. **Run `python -m src.eval.audit` before trusting any results table.**
5. **Stay inside your workstream's file ownership** (`docs/WORKSTREAMS.md`) and
   work on its branch.
6. **Option B passed only a perfect-prognosis ceiling test.** Do not present
   ERA5 analysis skill as forecast skill or start Aurora 1.5 GPU work before
   forecast BLH degradation is quantified.

## Code conventions

- Python 3.11, stdlib + pandas / numpy / xarray / scikit-learn / torch.
- CLI modules invoked as `python -m src.<pkg>.<mod>`; argparse, no config files.
- Comments explain *why*, not *what*. Match surrounding density; don't narrate.
- Long-running jobs must be **resumable** (manifest + skip completed units) —
  the network here is unreliable and this has bitten us repeatedly.
- Never let a partial run overwrite complete data.

Environment: Windows, `.venv/Scripts/python.exe`. Credentials in `.env`
(`OPENAQ_API_KEY`) and `~/.cdsapirc` (Copernicus ADS).
