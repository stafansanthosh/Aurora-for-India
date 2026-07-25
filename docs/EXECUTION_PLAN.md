# 2-Day Execution Plan — full IndiaAQBench baseline + Component A

**Goal at the end of Day 2:** the real benchmark table — all baselines across the
frozen dates × 9 cities × 8 leads, plus Component A scored on it — with severe
events present in both train and test. That is spec §9's S1 criterion met.

**Explicitly NOT in 2 days:** fine-tuning. It needs its own cycle (design
decisions, memory-bound training, forgetting checks) and it *needs* this
baseline first to have anything to beat. Prereqs listed in §5.

---

## 1. Critical path

```
re-pull  ->  registry  ->  coverage audit  ->  56-date rollout  ->  calibrate + score
(~11h, running)  (min)        (min)            (~2.5h parallel)        (~min)
```

Only the rollout needs the cloud. Everything else is local and fast. The long
pole is the re-pull, which is why it is already running and why Component A is
built *while* it runs.

## 2. Day 1

**Running unattended:** OpenAQ re-pull (task #17). Monthly resumable windows,
target cities first, `status="partial"` if any window fails.
- Disruption? Re-run the identical command — completed windows are skipped.
- Need data before it finishes? `python -m src.data.archive_pull --assemble-only`
  rebuilds every city CSV from whatever parts exist, no network.

**Meanwhile (local, no conflict with the pull — reads `results/pairs/` only):**
1. **Component A** (task #18) — per-station trailing-ratio anchoring.
2. **Guardrails** (task #19) — no-harm-on-events gate at fit time, OOD selftest,
   seasonal-transfer check.
3. Validate both against the 5 existing dates. Numbers will be thin; the point
   is that the code path and the gate work.

**End of Day 1, once the pull completes:**
```bash
python -m src.data.build_station_registry     # 127 -> ~170 stations
python -m src.eval.coverage_audit --n 56      # NEW frozen dates, post-revision
```
The audit now runs with cutoff 2025-12-01, so it should yield **post-monsoon
train dates** for the first time — the whole point of the revision.

## 3. Day 2 — the rollout, parallelized

The orchestrator is embarrassingly parallel across dates (per-date manifest,
independent CAMS files). Do **not** run 56 dates serially on one box (~10 h).
Split across 4 cheap GPUs instead:

```bash
# on each of 4 boxes (see scripts/setup_gpu.md for provisioning):
split -n l/4 -d <(tail -n +2 docs/benchmark_dates.csv | cut -d, -f1) slice_
python -m src.pipeline.orchestrate --dates-file slice_0X --device cuda
```

~14 dates/box × ~10 min = **~2.5 h wall**, ~$5 total on 48 GB A6000 spot.
Run the pull *and* the rollout on the box — a datacenter link to Copernicus is
the fix for the flaky-download problem, not just faster compute.

Pull back only the small outputs (`results/pairs/`, `results/india_fields/`),
then locally:
```bash
python -m src.model.calibrator                # now fits WITH severe-season data
python -m src.eval.benchmark --calibrator results/models/pooled_calibrator.joblib
```

**Deliverable:** `results/metrics/indiaaqbench.csv` — the real table.

## 4. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Connection drops during re-pull | Already handled: per-window parts, resume on re-run, `--assemble-only` |
| Re-pull slower than 11 h | Target cities first; Delhi (slowest, least relevant) last; proceed on partial data |
| Copernicus ADS queues/throttles | 4 boxes fetch independently; start early; orchestrator is resumable per date |
| Coverage audit yields < 56 usable dates | Run what it yields; the audit reports density honestly |
| Registry changes after the rollout | Already de-risked (`4c3041f`): all feature vars saved on the India grid, so station samples re-derive offline without re-running Aurora |
| Component A underperforms | That is a result, not a failure — it is scored against raw Aurora either way |

## 5. What to settle before fine-tuning (not Day 1–2)

1. The 56-date raw baseline (Day 2) — the bar to beat.
2. Component A's numbers — how much a $0 correction already buys.
3. What to unfreeze: LoRA / head-only vs full (Aurora's repo documents its
   fine-tuning API).
4. Loss design: station-sparse supervision vs gridded; asymmetric/quantile loss,
   since the literature consistently finds plain MSE under-serves extremes.
5. Rollout length during training — this is the genuinely memory-bound part and
   the only step that wants a 40–80 GB card.
6. A catastrophic-forgetting protocol: naive fine-tuning can improve Delhi while
   silently degrading held-out cities. The L2 split is the check.
