# Parallel workstreams — Claude / Copilot / Codex

The repository is the shared memory. Any agent picks up from `docs/HANDOFF.md`
plus this file; nothing important lives only in a chat session.

## The one rule that makes parallelism safe

**One workstream = one branch = a disjoint set of files.** Two agents editing
the same file in parallel is the only way this goes wrong. Ownership below is
binding; if a workstream needs to touch a file it does not own, it opens a PR
against that owner's branch instead of editing directly.

Shared-by-everyone (read-only unless you own it): `src/splits.py`,
`docs/BENCHMARK_SPEC.md`, `data/`, `results/`.

## Does parallelism actually help here?

Partly. The critical path is **inherently serial**:

```
re-pull -> station registry -> coverage audit -> 56-date rollout -> score
```

Nothing downstream can start before the pull finishes. So parallelism buys
nothing *on* that path — but three things run fully in parallel *beside* it
(WS-2/4/5 below), and the pull itself can be split by city.

**Highest-value parallelism right now:** split the remaining re-pull by city
across 2–3 sessions. Part files are per-city-per-window, so there is no
collision:

```bash
# session A
python -m src.data.archive_pull --cities lucknow kolkata
# session B
python -m src.data.archive_pull --cities delhi
# session C
python -m src.data.archive_pull --cities mumbai bangalore
```

**Cap it at ~3.** All sessions share one home connection and one OpenAQ API key;
too many concurrent pullers trigger rate limiting (the client retries 429s, so
the failure mode is slowness, not corruption) and compete for the same flaky
bandwidth that caused these failures in the first place.

## Workstreams

| ID | Workstream | Owns (exclusive) | Blocked by | Best tool |
|---|---|---|---|---|
| **WS-1** | Data acquisition | `src/data/**`, `data/**` | — | **Claude** (judgment on partial data) |
| **WS-2** | Component A: anchoring | `src/model/anchor.py` (new) | — | **Claude** (design-heavy) |
| **WS-3** | Guardrails + tests | `src/model/calibrator.py`, `tests/**` | — | **Copilot / Codex** (well-specified) |
| **WS-4** | Dashboard + reporting | `src/report/**`, `docs/figures/**` | — | **Copilot / Codex** (self-contained) |
| **WS-5** | Fine-tune design doc | `docs/FINETUNE_DESIGN.md` (new) | — | **Claude** (research-heavy) |
| **WS-6** | 56-date GPU rollout | `results/pairs/**` | **WS-1** | Claude, on the cloud box |

### WS-1 — Data acquisition *(critical path; in flight)*
Finish the re-pull (second pass required), then rebuild the registry and re-run
the coverage audit. Exit criterion: every city logs `status: "ok"`, and
`docs/benchmark_dates.csv` is regenerated under cutoff 2025-12-01 **with
post-monsoon train dates present**.

### WS-2 — Component A: per-station trailing-ratio anchoring
Literature-standard adaptive bias correction (Kalman/MOS family; Djalalova &
Delle Monache 2015 for CMAQ). Trailing median `obs/aurora` per station over ~14
days at short leads, shrunk toward 1.0 when the sample is thin, clipped to
`[1/3, 3]`, applied multiplicatively at all leads. No training set → no
distribution ceiling, adapts through seasons, transfers to held-out cities,
cannot flatten the tail. **New file**, so zero conflict with WS-3.
Registers itself as a method in `benchmark.py` via a one-line addition —
coordinate that single line with WS-3.

### WS-3 — Guardrails + tests *(good first Copilot/Codex task)*
Fully specified, mechanical, no design judgment needed:
1. `calibrator.py` CLI must print Very Poor+ **POD/FAR beside MAE**, and refuse
   to save a model whose POD is below raw Aurora's ("no-harm-on-events" gate).
2. Extend `--selftest` so train and test come from **different regimes**
   (calm train → severe test) — the case that would have caught the v1 collapse.
3. Add a seasonal-transfer check: train winter-only → test monsoon-only.
4. Move the existing inline `_test()` functions into a real `tests/` tree.

### WS-4 — Dashboard + reporting *(good Copilot/Codex task)*
Read `results/metrics/indiaaqbench.csv`, render per-city × per-lead scorecards:
POD/FAR/CSI and category hit-rate, raw vs calibrated vs persistence. Pure
read-only consumer of an existing schema — cannot break the pipeline.

### WS-5 — Fine-tune design doc
Settle, on paper, the six prerequisites in `docs/EXECUTION_PLAN.md` §5: what to
unfreeze (LoRA/head-only vs full), loss design (station-sparse vs gridded;
asymmetric/quantile, since the literature finds plain MSE under-serves
extremes), training rollout length (the genuinely memory-bound part), and a
catastrophic-forgetting protocol using the L2 held-out cities.

## Handoff discipline (all agents)

1. Read `docs/HANDOFF.md` first, then this file.
2. Work on your branch; commit early with real messages.
3. Record decisions in the repo — spec, plan, or a docstring — never only in chat.
4. When a claim rests on data, put the verifying command in the commit message.
5. Update `docs/HANDOFF.md` "Current state" + "Immediate next step" before you stop.
