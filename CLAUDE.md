# CLAUDE.md — IndiaAQBench

**Read `docs/AGENT_BRIEF.md` first. It is the canonical brief** (project goal,
repo map, ground rules, settled decisions, rejected approaches).
Then `docs/HANDOFF.md` for current state and the exact next command.

Kept thin on purpose: the brief lives in one place so `CLAUDE.md`, `AGENTS.md`
and `.github/copilot-instructions.md` cannot drift apart — the same
duplication-drift failure `src/splits.py` exists to prevent.

## Non-negotiables (apply even if you read nothing else)

1. **Success is Very Poor+ (≥121 µg/m³) event skill — POD / FAR / CSI — not MAE.**
   GRAP emergency actions trigger on forecast category. A calibrator that
   improved MAE while catching 0 of 99 events has already been built and
   rejected; don't rebuild it.
2. **Do not reinstate the falsified “unserved cities” premise.** The 400 m
   AQEWS figure is the Delhi nest, and Patna/Varanasi/Kanpur/Lucknow have
   national or regional forecast products. Read `docs/TARGET_REEVALUATION.md`.
3. **Split constants are defined only in `src/splits.py`.**
4. **Run `python -m src.eval.audit` before trusting any results table.**
5. **Verify before asserting** — run the check rather than reasoning from memory.
   Several confident beliefs in this project turned out to be wrong.
6. **Report negative results honestly.** They are the most valuable output here.
7. **Stay inside your workstream's files** (`docs/WORKSTREAMS.md`), on its branch.
8. **Before stopping:** update `docs/HANDOFF.md`, append to `JOURNAL.md`, commit.

## Settled — do not re-litigate

- No A100 needed (0.4° inference fits a ~$0.50/hr 48 GB spot GPU).
- OpenAQ serves no data before ~Feb 2025; backfill is impossible.
- Temporal cutoff is 2025-12-01 (revised once, disclosed — see the brief).
- No replacement concentration regressor: model exceedance probability. The
  Option B ERA5 ceiling and free GFS forecast-BLH gates passed. Use GFS for
  forecast BLH; do not run Aurora 1.5 for this purpose.

Environment: Windows, `.venv/Scripts/python.exe`. Credentials in `.env`
(`OPENAQ_API_KEY`) and `~/.cdsapirc` (Copernicus ADS).
