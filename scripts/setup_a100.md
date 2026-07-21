# Phase 2 GPU setup — Aurora 0.4° Air Pollution on an A100

Aurora 0.4° Air Pollution predicts PM2.5 (and PM1/PM10 + gases) **directly**.
It is full-size (~24 GB VRAM) → needs an **A100** (Azure `NC24ads_A100_v4`,
your pending quota). It must be run on **CAMS analysis** data for optimal skill,
**not** the EAC4 reanalysis used in Phase 1.

## 0. Provision
- Azure VM: `Standard_NC24ads_A100_v4` (1× A100 80GB) in your quota-approved
  region (West/South India). Ubuntu 22.04 + NVIDIA driver image.
- Verify: `nvidia-smi` shows the A100.

## 1. Environment
```bash
git clone https://github.com/stafansanthosh/Aurora-for-India.git
cd Aurora-for-India
python -m venv .venv && source .venv/bin/activate

# CUDA build of torch (the repo's default install is CPU-only):
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt      # microsoft-aurora, xarray, cdsapi, ...

python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

## 2. Credentials
- Copy `~/.cdsapirc` (CDS + ADS use the same token; see repo JOURNAL).
- Put `OPENAQ_API_KEY` / `CDS_API_KEY` in `.env`.
- Accept the **CAMS analysis** dataset licence on ADS (one-time, on the website).

## 3. Checkpoint + static fields
```bash
python -c "from src.model.aurora_runner import load_model; load_model('cuda')"
# downloads microsoft/aurora :: aurora-0.4-air-pollution.ckpt
```
- Download the Microsoft-provided **static emissions pickle** (static_ammonia,
  static_nox, static_co, static_so2 + their _log variants) per the Aurora docs
  and wire it into `aurora_runner.load_static_vars()`.

## 4. Data — CAMS analysis + ERA5 (two 12h-apart timesteps)
- CAMS analysis (ADS atmospheric-composition **analysis**): pm1/pm2p5/pm10,
  total columns (tcco/tc_no/tcno2/gtco3/tcso2), and the atmos composition
  (co/no/no2/go3/so2) at the 13 pressure levels.
- ERA5: `2t/10u/10v/msl/z` (surface) + `t/u/v/q/z` at the 13 levels + static
  `lsm/slt/z`. Extend `src/data/era5_downloader.py` with a pressure-levels +
  static request (the surface-only Phase-1 download is not sufficient).

## 5. Run
```bash
python -m src.model.aurora_runner --check      # sanity: Batch construction
# then wire assemble_inputs() against the real CAMS-analysis + ERA5 files and
# call run() to get predicted pm2p5.
```

## 6. Evaluate
- Sample predicted `pm2p5` at OpenAQ station cells (reuse `src/data/align.py`
  and `src/eval/`), compare vs OpenAQ, and against the Phase-1 CAMS baseline.
- Success (per plan): Aurora runs end-to-end on real ERA5/CAMS; then compare
  its PM2.5 skill vs the Phase-1 CAMS-reanalysis MAE per city.
