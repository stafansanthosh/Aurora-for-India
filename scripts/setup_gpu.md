# GPU setup — run the frozen IndiaAQBench 56-date orchestrator

This is the runbook for the expensive part of the benchmark: roll out
AuroraAirPollution at every frozen init date and bring the small forecast-pair
files back to the machine that holds the untracked OpenAQ archive. Calibration
and scoring happen there after the integrity audit.

**Observed project run (2026-08-04):** all four slices are complete and local:
56 dates, 80,136 rows, 159 stations, and zero worker errors. Every returned pair
and worker manifest matched its remote SHA-256. This document is now a
reproduction runbook; do not provision another Pod for the current benchmark.
The remaining work is to merge the four manifests and pass the local audit.

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

## Package all CAMS inputs locally; send each worker only its assigned dates

Both CAMS inputs are downloaded and hash-validated locally before renting GPUs:

- the lead-dependent PM2.5 forecasts used as the operational comparator;
- the global 00/12 UTC atmospheric analyses that initialize Aurora.

Each worker receives one exact 14-date input bundle and runs with
`--offline-inputs`. That flag fails closed if any file is absent and prohibits
all Copernicus retrieval. No Copernicus or OpenAQ credential belongs on a GPU
worker.

---

## 0. Validate and package locally before provisioning

Run on the laptop that holds the complete local data:

```powershell
.\.venv\Scripts\python.exe -m src.data.cams_composition `
  --dates-file docs\benchmark_dates.csv --validate-only --deep-validate
.\.venv\Scripts\python.exe -m scripts.validate_cams_download
.\.venv\Scripts\python.exe -m scripts.package_gpu_inputs
```

The packager writes four untracked TAR files and SHA-256 sidecars under
`artifacts/gpu_inputs/`. Each contains exactly 14 dates, its matching
`slice_0N`, the analysis ZIPs, actual CAMS forecast artifacts, and a per-file
manifest. Do not provision GPUs unless both validators pass and all four
bundles exist.

Create an exact source archive from the reviewed commit after it is pushed:

```powershell
git archive --format=tar.gz --prefix=indiaaqbench/ `
  --output="$env:TEMP\indiaaqbench-source.tar.gz" HEAD
```

## 1. Provision (RunPod example)

- RunPod → Deploy → an **A6000 48 GB** pod. Region no longer affects
  Copernicus access because all inputs are local. Template: a PyTorch/CUDA
  image on Ubuntu 22.04.
- Give it ~60 GB disk (globals are deleted per-date, but leave headroom).
- Open a web terminal or SSH in. `nvidia-smi` should show the card.

(Vast.ai / Lambda / Modal all work — only this provisioning step differs.)

## 2. Upload and environment

Upload the source archive and only the assigned worker bundle. For example,
worker 0 receives `worker_00_cams_inputs.tar`; never send all four bundles to
every worker. Extract both under `/workspace`:

```bash
cd /workspace
tar -xzf indiaaqbench-source.tar.gz
tar -xf worker_00_cams_inputs.tar -C indiaaqbench
cd indiaaqbench

# Source snapshots may contain tracked legacy pilot artifacts. A disposable
# worker must start with an empty output ledger so its manifest contains only
# records produced by this worker.
rm -f results/pairs/pairs_*.parquet results/pairs/manifest.jsonl
```

```bash
# The official RunPod PyTorch template already contains a tested CUDA build.
# Verify it first, then expose those system packages to a disposable venv on
# fast container storage. Keep inputs, checkpoints, and outputs in /workspace.
python -c "import torch; assert torch.cuda.is_available(); print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0))"
python -m venv --system-site-packages /opt/indiaaqbench-venv
source /opt/indiaaqbench-venv/bin/activate

pip install --upgrade pip
pip install --upgrade-strategy only-if-needed -r requirements.txt
pip check

python -c "import torch, pyarrow; assert torch.cuda.is_available(); x=torch.ones(1, device='cuda'); print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0), float(x.item()), pyarrow.__version__)"
export HF_HOME=/workspace/huggingface
```

## 3. Credentials

**None.** Do not copy `.cdsapirc`, `.env`, an OpenAQ key, a GitHub token, or an
SSH private key to any worker. The source snapshot and assigned CAMS bundle are
the complete GPU inputs. SSH authentication uses only the public key injected
by the provider; the private key remains on the laptop.

The environment must import the GRIB stack used for the operational CAMS
baseline:

```bash
python -c "import cfgrib, eccodes; print(cfgrib.__version__, eccodes.__version__)"
```

## 4. Checkpoint

```bash
HF_HOME=/workspace/huggingface python -c "from src.model.aurora_runner import load_model; load_model('cuda')"
# pulls microsoft/aurora :: aurora-0.4-air-pollution.ckpt into the HF cache
```

## 5. Run the full benchmark pass

The orchestrator is resumable and self-cleaning for Aurora's extracted global
inputs. The assigned raw analysis ZIP is removed from the disposable worker
after that date completes; the validated source remains on the laptop. Run only
the bundle-provided slice and require offline inputs:

```bash
python -m src.pipeline.orchestrate \
  --dates-file slice_00 --device cuda --offline-inputs
```

Observed on the RunPod RTX A6000 canary on 2026-08-03: 59–66 seconds/date for
the eight-step rollout after model load, with 29.2 GB peak VRAM. Budget roughly
20–30 minutes per 14-date worker including setup and validation. Dates remain
independent and the manifest makes each box resumable:

```bash
# worker 0 uses slice_00; workers 1, 2, and 3 use slice_01, slice_02, slice_03
python -m src.pipeline.orchestrate \
  --dates-file slice_00 --device cuda --offline-inputs
```

Run under `tmux`/`nohup` so an SSH drop doesn't kill it. Progress: `tail -f` the
log or watch `results/pairs/manifest.jsonl`.

**Verify before trusting results:** a complete run produces **1,431 rows per
date** (159 stations × 9 lead rows) and **80,136 rows** across all 56. Resume is
registry-aware, so dates rolled out at an older station registry are re-run
rather than silently reused.

## 6. Pull results back + tear down

```bash
# from your laptop; repeat with worker/index 1, 2, and 3
scp <worker-0>:/workspace/indiaaqbench/results/pairs/pairs_*.parquet results/pairs/
scp <worker-0>:/workspace/indiaaqbench/results/pairs/manifest.jsonl \
  results/pairs/manifest_worker_0.jsonl
```

Never copy `results/pairs/*` wholesale: every worker uses the same
`manifest.jsonl` name, so later copies would overwrite earlier workers'
provenance. Confirm the disposable-worker cleanup above happened before using
the wildcard; otherwise inherited pilot pairs and manifest records will be
copied too. After all four transfers, append their distinct records safely:

```bash
python scripts/merge_worker_manifests.py \
  results/pairs/manifest_worker_0.jsonl \
  results/pairs/manifest_worker_1.jsonl \
  results/pairs/manifest_worker_2.jsonl \
  results/pairs/manifest_worker_3.jsonl
```

Then **stop/terminate every worker** so billing ends. The pair files are small.
Aurora's extracted initialization files and assigned raw analysis ZIPs are not
retained on the disposable workers. Their validated source archives and the
lead-dependent CAMS GRIBs remain on the laptop as reproducibility evidence.

## 7. Audit, score, and evaluate adaptation locally

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
