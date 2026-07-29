# GPU setup — run the frozen IndiaAQBench 56-date orchestrator

This is the runbook for the expensive part of the benchmark: roll out
AuroraAirPollution at every frozen init date and bring the small forecast-pair
files back to the machine that holds the untracked OpenAQ archive. Calibration
and scoring happen there after the integrity audit.

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

## Run CAMS retrieval and Aurora inference on the box

The real bottleneck is **not** compute — it is the CAMS download from Copernicus
ADS (~240 MB/date). Over a home connection this repeatedly drops mid-stream
(`IncompleteRead`, 120 s backoffs → ~14 min for one file). A cloud box has a
datacenter pipe to Copernicus, so **both** CAMS retrieval and the rollout get
faster and more reliable. Copy only the small pair files back. The cloud box
does not need the untracked OpenAQ archive to generate those pairs.

---

## 0. Provision (RunPod example)

- RunPod → Deploy → an **A6000 48 GB** pod, an EU/India region if available
  (closer to Copernicus). Template: a PyTorch/CUDA image on Ubuntu 22.04.
- Give it ~60 GB disk (globals are deleted per-date, but leave headroom).
- Open a web terminal or SSH in. `nvidia-smi` should show the card.

(Vast.ai / Lambda / Modal all work — only this provisioning step differs.)

## 1. Environment

```bash
# The repository is currently private. Use an authenticated GitHub clone or
# upload the exact reviewed source snapshot.
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
```

Accept the **CAMS global-atmospheric-composition-forecasts** licence once on the
ADS website, or the first download 403s.

An OpenAQ key and the observation archive are not required for the rollout.
They are required later on the local scoring machine.

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
tail -n +2 docs/benchmark_dates.csv | cut -d, -f1 | split -n l/4 -d - slice_
# worker 0 uses slice_00; workers 1, 2, and 3 use slice_01, slice_02, slice_03
python -m src.pipeline.orchestrate --dates-file slice_00 --device cuda
```

Run under `tmux`/`nohup` so an SSH drop doesn't kill it. Progress: `tail -f` the
log or watch `results/pairs/manifest.jsonl`.

**Verify before trusting results:** a complete run produces **1,431 rows per
date** (159 stations × 9 lead rows) and **80,136 rows** across all 56. Resume is
registry-aware, so dates rolled out at an older station registry are re-run
rather than silently reused.

## 5. Pull results back + tear down

```bash
# from your laptop; repeat for workers 1, 2, and 3
scp -r <worker-0>:Aurora-for-India/results/pairs/* results/pairs/
```

Then **stop/terminate every worker** so billing ends. The pair files are small;
the roughly 240 MB/date global inputs were not retained.

## 6. Audit, score, and evaluate adaptation locally

Run this on the machine that holds the complete OpenAQ archive:

```bash
python -m src.eval.audit
python -m src.eval.benchmark
python -m src.eval.benchmark --anchor
python -m src.model.calibrator
python -m src.eval.benchmark --calibrator results/models/pooled_calibrator.joblib
```

The evaluator writes `results/metrics/indiaaqbench.csv` and the corresponding
`_extremes` file. Do not fit or publish an adaptation if the audit fails.
Component A is online local adaptation and must be labeled as using trailing
observations in L1 and L2 cities.

## Reproducibility note

Everything the rollout consumes is pinned: the frozen
`docs/benchmark_dates.csv`, versioned `data/stations.csv` (159 stations), code
commit, and CAMS request/provenance manifests. Reproducing the final results
also requires the separately versioned OpenAQ archive and its provenance.
