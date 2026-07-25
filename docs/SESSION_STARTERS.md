# Session starters — copy, paste, go

Each tool auto-loads its own instructions file, and all three point at the same
canonical brief (`docs/AGENT_BRIEF.md`), so **you never have to explain the
project**. These prompts only say *which job to do*.

| Tool | Auto-loads | You still paste |
|---|---|---|
| Claude Code | `CLAUDE.md` | the workstream prompt |
| OpenAI Codex | `AGENTS.md` | the workstream prompt |
| GitHub Copilot (VS Code) | `.github/copilot-instructions.md` | the workstream prompt |

**Rule: one workstream per session.** Two sessions editing the same file is the
only way parallel work goes wrong. Ownership: `docs/WORKSTREAMS.md`.

Every prompt below starts with a read instruction anyway — belt and braces, in
case a tool's auto-load is off or truncated.

---

# The one that matters right now

## WS-1 — finish the data pull *(critical path; everything waits on it)*

**Claude Code:**
```
Read docs/AGENT_BRIEF.md and docs/HANDOFF.md, then continue WS-1 (data acquisition).
The OpenAQ re-pull is incomplete - several cities have failed windows. Re-run
python -m src.data.archive_pull until every city reports status "ok" in
data/openaq/archive/pull_manifest.jsonl. Then rebuild the station registry and
re-run the coverage audit to re-freeze benchmark dates under cutoff 2025-12-01.
Report which cities gained stations, and run python -m src.eval.audit at the end.
```

**Split across 2-3 sessions** (max 3 — one connection, one API key; more just
triggers rate limiting). Give each session a different city set:
```
Read docs/AGENT_BRIEF.md. Run ONLY: python -m src.data.archive_pull --cities lucknow kolkata
Re-run until both report status "ok" in data/openaq/archive/pull_manifest.jsonl.
Do not touch other cities or any other files.
```

---

# Runs in parallel today (nothing blocks these)

## WS-2 — Component A: per-station anchoring → **Claude** (design judgement)

```
Read docs/AGENT_BRIEF.md and docs/WORKSTREAMS.md, then implement WS-2 in a NEW
file src/model/anchor.py, on branch ws2-anchor.

Per-station trailing-ratio anchoring: trailing median obs/aurora per station over
~14 days at short leads, shrunk toward 1.0 when the sample is thin, clipped to
[1/3, 3], applied multiplicatively at all leads. It uses no training set, so it
cannot inherit a training-distribution ceiling - that is the whole point, since
the v1 learned calibrator collapsed the severe tail.

Register it as a method in src/eval/benchmark.py (coordinate that single line
with WS-3) and score it against raw Aurora on Very Poor+ POD/FAR/CSI, not MAE.
Report whether it beats raw Aurora on events at each lead time.
```

## WS-3 — guardrails + tests → **Codex or Copilot** (fully specified)

```
Read docs/AGENT_BRIEF.md and docs/WORKSTREAMS.md section WS-3, then implement it
exactly. You own src/model/calibrator.py and tests/ ONLY. Branch: ws3-guardrails.

1. The calibrator CLI must print Very Poor+ POD and FAR beside MAE, and refuse to
   save a model whose POD is below raw Aurora's ("no-harm-on-events" gate).
2. Extend --selftest so train and test come from DIFFERENT regimes (calm train ->
   severe test). This is the case that would have caught the v1 tail collapse and
   the current same-distribution selftest misses it.
3. Add a seasonal-transfer check: train winter-only -> test monsoon-only.
4. Move the inline _test() functions in src/eval/aqi.py and src/model/calibrator.py
   into a real tests/ tree, preserving every existing assertion.

Do not modify the pipeline or any file outside your ownership.
```

## WS-4 — dashboard → **Codex or Copilot** (read-only, cannot break anything)

```
Read docs/AGENT_BRIEF.md and docs/WORKSTREAMS.md section WS-4, then build
src/report/ on branch ws4-dashboard. You own src/report/ and docs/figures/ ONLY.

Read results/metrics/indiaaqbench.csv and render per-city x per-lead scorecards:
Very Poor+ POD/FAR/CSI and AQI category hit-rate, comparing raw Aurora,
persistence, climatology and calibrated. Event metrics are the headline; show MAE
as secondary. Static matplotlib output to docs/figures/ is fine.

This is a read-only consumer of an existing CSV schema - do not modify the
pipeline, the metrics code, or anything under src/eval or src/model.
```

## WS-5 — fine-tune design doc → **Claude** (research-heavy, no code)

```
Read docs/AGENT_BRIEF.md and docs/EXECUTION_PLAN.md section 5, then write
docs/FINETUNE_DESIGN.md on branch ws5-finetune-design. No pipeline code.

Settle all six prerequisites: what to unfreeze (LoRA / head-only / full), loss
design for extremes (the literature finds plain MSE under-serves them - see
asymmetric and quantile losses), station-sparse vs gridded supervision, training
rollout length and its memory cost, and a catastrophic-forgetting protocol using
the L2 held-out cities (Kanpur, Varanasi, Kolkata).

Research Aurora's actual fine-tuning API in its repo and docs rather than
assuming what it supports. State clearly what we must measure BEFORE spending
GPU money on fine-tuning.
```

---

# Blocked until WS-1 finishes

## WS-6 — the 56-date GPU rollout

```
Read docs/AGENT_BRIEF.md, docs/HANDOFF.md and scripts/setup_gpu.md.
WS-1 is complete and docs/benchmark_dates.csv has been re-frozen.

Run the rollout on 48GB spot GPUs (NOT an A100 - see the brief), splitting the
date list across 4 boxes so it finishes in ~2.5h instead of ~10h. Run the CAMS
downloads on the boxes too; the datacenter link is the fix for our flaky
downloads. Then fit the calibrator, run the full benchmark, and report Very Poor+
POD/FAR by lead for every method. Run python -m src.eval.audit before reporting.
```

---

# Ending any session (paste this before you close the tab)

```
Update docs/HANDOFF.md (Current state + Immediate next step) and append a
JOURNAL.md entry covering what changed and why. Run python -m src.eval.audit,
then commit and push.
```
