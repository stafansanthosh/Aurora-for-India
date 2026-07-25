# Session starters — copy, paste, go

`CLAUDE.md` is auto-loaded in every Claude Code session, so the agent already
knows the project, the ground rules and what is settled. These prompts only say
*which job to do*. Pick one and paste it; nothing else is needed.

**Rule: one workstream per session.** Two sessions editing the same file is the
only way parallel work goes wrong. Ownership is in `docs/WORKSTREAMS.md`.

---

## The one you need right now

### WS-1 — finish the data pull *(critical path; everything else waits on it)*

```
Read docs/HANDOFF.md, then continue WS-1 (data acquisition).
The OpenAQ re-pull is incomplete - several cities have failed windows.
Re-run the pull until every city reports status "ok" in
data/openaq/archive/pull_manifest.jsonl, then rebuild the station registry and
re-run the coverage audit to re-freeze the benchmark dates under cutoff
2025-12-01. Report which cities gained stations.
```

To split the pull across 2-3 sessions (max 3 — one connection, one API key),
give each a different city set:

```
Read docs/HANDOFF.md. Run only: python -m src.data.archive_pull --cities lucknow kolkata
Re-run until both report status "ok". Do not touch other cities or other files.
```

---

## Runs in parallel today (not blocked by anything)

### WS-2 — Component A: per-station anchoring *(Claude; design-heavy)*

```
Read docs/HANDOFF.md and docs/WORKSTREAMS.md, then implement WS-2 in a NEW file
src/model/anchor.py. Per-station trailing-ratio anchoring: trailing median
obs/aurora per station over ~14 days at short leads, shrunk toward 1.0 when the
sample is thin, clipped to [1/3, 3], applied multiplicatively at all leads.
No training set, so it cannot inherit a training distribution ceiling.
Register it as a method in benchmark.py and score it against raw Aurora on
Very Poor+ POD/FAR - not MAE. Work on branch ws2-anchor.
```

### WS-3 — guardrails + tests *(good for Copilot / Codex; fully specified)*

```
Read docs/WORKSTREAMS.md section WS-3 and implement it exactly. You own
src/model/calibrator.py and tests/ only. Four items: (1) the calibrator CLI must
print Very Poor+ POD/FAR beside MAE and refuse to save a model whose POD is below
raw Aurora's; (2) extend --selftest so train and test come from different regimes
(calm train -> severe test); (3) add a seasonal-transfer check (train winter-only
-> test monsoon-only); (4) move inline _test() functions into a real tests/ tree.
Work on branch ws3-guardrails.
```

### WS-4 — dashboard *(good for Copilot / Codex; read-only, cannot break anything)*

```
Read docs/WORKSTREAMS.md section WS-4. Build src/report/ that reads
results/metrics/indiaaqbench.csv and renders per-city x per-lead scorecards:
Very Poor+ POD/FAR/CSI and AQI category hit-rate, comparing raw Aurora,
persistence and calibrated. You own src/report/ and docs/figures/ only - do not
modify the pipeline. Work on branch ws4-dashboard.
```

### WS-5 — fine-tune design doc *(Claude; research-heavy, no code)*

```
Read docs/EXECUTION_PLAN.md section 5, then write docs/FINETUNE_DESIGN.md
settling all six prerequisites: what to unfreeze (LoRA/head-only vs full), loss
design for extremes (the literature finds plain MSE under-serves them), training
rollout length and its memory cost, and a catastrophic-forgetting protocol using
the L2 held-out cities. Research Aurora's actual fine-tuning API in its repo/docs
rather than assuming. No pipeline code. Work on branch ws5-finetune-design.
```

---

## Blocked until WS-1 finishes

### WS-6 — the 56-date GPU rollout

```
Read docs/HANDOFF.md and scripts/setup_gpu.md. WS-1 is done and
docs/benchmark_dates.csv is re-frozen. Run the rollout on a 48GB spot GPU
(NOT an A100), splitting the date list across 4 boxes so it finishes in ~2.5h.
Then fit the calibrator and run the full benchmark, and report Very Poor+
POD/FAR by lead for every method.
```

---

## Ending any session

```
Update docs/HANDOFF.md (Current state + Immediate next step) and append a
JOURNAL.md entry for what changed and why. Commit and push.
```
