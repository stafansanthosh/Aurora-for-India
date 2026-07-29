# GPU setup — run the frozen IndiaAQBench 56-date orchestrator

This is the runbook for the full benchmark pass: roll out AuroraAirPollution at
every frozen init date, fit the pooled calibrator, and score the whole metric
suite. It supersedes the old `setup_a100.md` (which was written for the earlier
single-timestep Phase-2 validation, before the orchestrator/calibrator existed).

## You do NOT need an A100

Aurora's official docs (microsoft.github.io/aurora/usage.html) state the memory
need by resolution, not by card: **~40 GB GPU memory for the regular model at
0.25°**, and **32 GB for the memory-optimized 1.5**. The A100-80GB requirement
they mention is specifically for **0.1° resolution + backpropagating through
rollouts** (training at the finest grid) — "even a single step rollout is close
to the memory limit of an A100 80GB."

**We do neither.** IndiaAQBench runs the **0.4°** air-pollution model (coarser
than 0.25°) for **inference only** (`torch.inference_mode`, no autograd). So the
requirement is *below* 40 GB. This also matches what we already see: the model
runs in ~32 GB of **CPU** RAM on the laptop.

| GPU | VRAM | ~$/hr (spot) | Verdict for this job |
|---|---|---|---|
| **RTX A6000** | **48 GB** | **~0.50** | **Recommended — comfortable, no OOM risk** |
| L40S | 48 GB | ~0.90 | Faster, still cheap |
| A100 40 GB | 40 GB | ~1.30 | Fine, but you're paying for headroom you don't use |
| RTX 4090 / L4 | 24 GB | ~0.35–0.40 | Likely fits (0.4°, inference) but tighter — try if cost-sensitive |

**Skip the Azure quota fight.** GPU marketplaces (RunPod, Vast.ai, Lambda,
Modal) rent by the hour with no quota approval and boot in ~2 minutes. Estimated
total for all 56 dates: **~$10–30**.

## Run the WHOLE pipeline on the box, not just the GPU step

The real bottleneck is **not** compute — it is the CAMS download from Copernicus
ADS (~240 MB/date). Over a home connection this repeatedly drops mid-stream
(`IncompleteRead`, 120 s backoffs → ~14 min for one file). A cloud box has a
datacenter pipe to Copernicus, so **both** the download and the rollout get
faster and more reliable. Do everything on the box; copy only the small result
parquet/CSV files back.

---

## 0. Provision (RunPod example)

- RunPod → Deploy → an **A6000 48 GB** pod, an EU/India region if available
  (closer to Copernicus). Template: a PyTorch/CUDA image on Ubuntu 22.04.
- Give it ~60 GB disk (globals are deleted per-date, but leave headroom).
- Open a web terminal or SSH in. `nvidia-smi` should show the card.

(Vast.ai / Lambda / Modal all work — only this provisioning step differs.)

## 1. Environment

```bash
git clone https://github.com/stafansanthosh/Aurora-for-India.git
cd Aurora-for-India
python -m venv .venv && source .venv/bin/activate

pip install torch --index-url https://download.pytorch.org/whl/cu124   # CUDA build
pip install -r requirements.txt                                        # aurora, xarray, cdsapi, sklearn, ...

python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

## 2. Credentials

```bash
# Copernicus (CDS + ADS share one token; CAMS analysis is on ADS):
cat > ~/.cdsapirc <<'EOF'
url: https://ads.atmosphere.copernicus.eu/api
key: <YOUR_ADS_KEY>
EOF

# OpenAQ (required: the archive CSVs are NOT tracked in git -- see spec section 7.
# Either re-pull with src.data.archive_pull, or fetch the published release asset):
echo "OPENAQ_API_KEY=<YOUR_KEY>" > .env
```

Accept the **CAMS global-atmospheric-composition-forecasts** licence once on the
ADS website, or the first download 403s.

## 3. Checkpoint

```bash
python -c "from src.model.aurora_runner import load_model; load_model('cuda')"
# pulls microsoft/aurora :: aurora-0.4-air-pollution.ckpt into the HF cache
```

## 4. Run the full benchmark pass

The orchestrator is resumable (skips dates already `done` in the manifest) and
self-cleaning (deletes the ~240 MB/date globals after extracting). Point it at
the frozen date list and let it run:

```bash
python -m src.pipeline.orchestrate --dates-file docs/benchmark_dates.csv --device cuda
```

Rough budget on an A6000: ~2–4 min/date download (datacenter) + ~5–10 min/date
rollout (8 steps). Serially that is ~10–14 h for 56 dates, so **split the date
list across 4 boxes for ~2.5 h wall, ~$5 total** — dates are independent and the
manifest makes each box resumable:

```bash
split -n l/4 -d <(tail -n +2 docs/benchmark_dates.csv | cut -d, -f1) slice_
python -m src.pipeline.orchestrate --dates-file slice_0X --device cuda
```

Run under `tmux`/`nohup` so an SSH drop doesn't kill it. Progress: `tail -f` the
log or watch `results/pairs/manifest.jsonl`.

**Verify before trusting results:** a complete run produces **1,431 rows per
date** (159 stations × 9 lead rows) and **80,136 rows** across all 56. Resume is
registry-aware, so dates rolled out at an older station registry are re-run
rather than silently reused.

## 5. Fit the calibrator + score everything

```bash
python -m src.model.calibrator                                             # fits on train-split pairs
python -m src.eval.benchmark                                               # baselines only
python -m src.eval.benchmark --calibrator results/models/pooled_calibrator.joblib  # + calibrated method
```

This writes `results/metrics/indiaaqbench.csv` (+ `_extremes`) — the headline
per lead × city × method table, including whether the calibrator fixes the level
error **without** killing Aurora's long-lead Very-Poor+ event skill.

## 6. Pull results back + tear down

```bash
# from your laptop:
scp -r <pod>:Aurora-for-India/results/pairs      results/
scp -r <pod>:Aurora-for-India/results/metrics    results/
scp -r <pod>:Aurora-for-India/results/models     results/
scp -r <pod>:Aurora-for-India/results/india_fields results/
```

Then **stop/terminate the pod** so billing ends. The pairs + metrics + model are
small and get committed; the 240 MB/date globals were never persisted.

## Reproducibility note

Everything the run consumes is pinned: the frozen `docs/benchmark_dates.csv`, the
versioned `data/stations.csv` (159 stations), the archived OpenAQ pulls, and the
CAMS extraction scripts + date manifest. A second person can reproduce the exact
results table from a clean clone by repeating steps 1–5.
