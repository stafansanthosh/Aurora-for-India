# AGENTS.md — IndiaAQBench

**Read `docs/AGENT_BRIEF.md` first. It is the canonical brief.**
Then read `docs/HANDOFF.md` for current state and the exact next command.

This file is intentionally thin: the brief lives in one place so tool-specific
instruction files (`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`)
cannot drift apart.

## Non-negotiables (apply even if you read nothing else)

1. **Success is Very Poor+ (≥121 µg/m³) event skill — POD / FAR / CSI — not MAE.**
   A model with great MAE that misses pollution episodes is worthless here. A
   calibrator that improved MAE while catching 0 of 99 events has already been
   built and rejected.
2. **Do not reinstate the falsified “unserved cities” premise.** Patna,
   Varanasi, Kanpur, and Lucknow have national/regional forecast products.
   Delhi is a diagnostic environment and supplies most benchmark events; read
   `docs/TARGET_REEVALUATION.md` before making a target claim.
3. **Split constants are defined only in `src/splits.py`.** Never redefine the
   cutoff, held-out cities, or L1 hash anywhere else.
4. **Run `python -m src.eval.audit` before trusting any results table.**
5. **Verify before asserting.** Run the check; don't reason from memory.
6. **Stay inside your workstream's files** (`docs/WORKSTREAMS.md`), on its branch.
7. **Before stopping:** update `docs/HANDOFF.md`, append to `JOURNAL.md`, commit.

## Settled — do not re-litigate

- No A100 needed (0.4° inference fits a 48 GB spot GPU).
- OpenAQ serves no data before ~Feb 2025; backfill is impossible.
- Temporal cutoff is 2025-12-01 (revised once, disclosed — see the brief).
- The Option B ERA5 ceiling test passed, but it used perfect-prognosis analysis.
  Next quantify forecast BLH degradation and check free NWP sources; no Aurora
  1.5 GPU rollout is authorized yet.

Environment: Windows, `.venv/Scripts/python.exe`. Credentials in `.env` and
`~/.cdsapirc`.
