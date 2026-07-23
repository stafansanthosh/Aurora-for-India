"""Aurora 0.4 Air Pollution inference wrapper (Phase 2).

Aurora 0.4 Air Pollution is Aurora 0.25 Pretrained fine-tuned on CAMS *analysis*
data; it predicts PM1/PM2.5/PM10 and gases (CO, NO, NO2, O3, SO2) directly.
That makes it the direct test of the project's research question (vs. the Phase-1
CAMS-reanalysis proxy).

IMPORTANT constraints (from the official Aurora docs):
  * Run it ONLY on CAMS *analysis* data for optimal skill -- NOT the EAC4
    reanalysis used in Phase 1. Other inputs give "sensible but not optimal"
    output.
  * Inference at 0.4 deg fits well under Aurora's stated 40 GB-at-0.25 deg
    memory figure -- a ~48 GB spot GPU (A6000) is comfortable; no A100 needed.
    It also runs on a 32 GB CPU (~12 min/step), which is how the pilot dates
    were produced. Full 56-date pass + runbook: scripts/setup_gpu.md.
  * Needs TWO history timesteps (t-dim = 2), 12h apart for this checkpoint.
  * Static emission fields (static_ammonia, static_nox, ...) come from a
    Microsoft-provided pickle, not from CAMS/ERA5 -- see load_static_vars().

This file provides:
  * The exact variable name lists the model expects.
  * build_batch(): assembles a valid aurora.Batch from plain numpy arrays with
    the correct shapes, dtype, longitude range, and level ordering (validated
    on CPU).
  * run(): loads the checkpoint and runs a forward pass (GPU).
The CAMS-analysis -> arrays loading (fetch_cams_analysis / assemble_inputs) is
left as a documented stub to complete on the GPU box against real data.

Usage (on the GPU box):
    python -m src.model.aurora_runner --check      # construct a dummy Batch (no GPU)
    # the full CAMS-analysis loaders (assemble_inputs) are wired and in use by
    # src.pipeline.orchestrate; --validate / --run exercise them directly.
"""
from __future__ import annotations

import argparse
from datetime import datetime

import numpy as np

# Exact variable sets AuroraAirPollution expects (from the model signature).
SURF_VARS = ("2t", "10u", "10v", "msl",
             "pm1", "pm2p5", "pm10", "tcco", "tc_no", "tcno2", "gtco3", "tcso2")
STATIC_VARS = ("lsm", "z", "slt",
               "static_ammonia", "static_ammonia_log",
               "static_co", "static_co_log",
               "static_nox", "static_nox_log",
               "static_so2", "static_so2_log")
ATMOS_VARS = ("z", "u", "v", "t", "q", "co", "no", "no2", "go3", "so2")
ATMOS_LEVELS = (50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000)

CHECKPOINT_REPO = "microsoft/aurora"
CHECKPOINT_NAME = "aurora-0.4-air-pollution.ckpt"
HISTORY_STEPS = 2  # Aurora needs two consecutive timesteps as context.


def to_0_360(lon: np.ndarray) -> np.ndarray:
    """Aurora expects longitudes in [0, 360). India is positive-lon so this is
    a no-op here, but keep it explicit for correctness on other regions."""
    return np.mod(lon, 360.0)


def build_batch(
    surf: dict[str, np.ndarray],
    static: dict[str, np.ndarray],
    atmos: dict[str, np.ndarray],
    lat: np.ndarray,
    lon: np.ndarray,
    time: datetime,
    levels: tuple[int, ...] = ATMOS_LEVELS,
):
    """Assemble a validated ``aurora.Batch``.

    Expected array shapes (H = n_lat, W = n_lon, L = n_levels):
      surf[v]:   (HISTORY_STEPS, H, W)          -> stored as (1, T, H, W)
      static[v]: (H, W)
      atmos[v]:  (HISTORY_STEPS, L, H, W)       -> stored as (1, T, L, H, W)

    ``lat`` must be descending (90 -> -90 convention); ``lon`` in [0, 360).
    """
    import torch  # local import so shape validation works without torch on path

    H, W, L = len(lat), len(lon), len(levels)

    def _surf(v: str) -> "torch.Tensor":
        a = np.asarray(surf[v], dtype=np.float32)
        assert a.shape == (HISTORY_STEPS, H, W), f"surf {v}: {a.shape} != {(HISTORY_STEPS,H,W)}"
        return torch.from_numpy(a)[None]  # (1, T, H, W)

    def _atmos(v: str) -> "torch.Tensor":
        a = np.asarray(atmos[v], dtype=np.float32)
        assert a.shape == (HISTORY_STEPS, L, H, W), f"atmos {v}: {a.shape} != {(HISTORY_STEPS,L,H,W)}"
        return torch.from_numpy(a)[None]  # (1, T, L, H, W)

    def _static(v: str) -> "torch.Tensor":
        a = np.asarray(static[v], dtype=np.float32)
        assert a.shape == (H, W), f"static {v}: {a.shape} != {(H,W)}"
        return torch.from_numpy(a)

    from aurora import Batch, Metadata

    missing = [v for v in SURF_VARS if v not in surf] + \
              [v for v in STATIC_VARS if v not in static] + \
              [v for v in ATMOS_VARS if v not in atmos]
    if missing:
        raise ValueError(f"missing required variables: {missing}")

    return Batch(
        surf_vars={v: _surf(v) for v in SURF_VARS},
        static_vars={v: _static(v) for v in STATIC_VARS},
        atmos_vars={v: _atmos(v) for v in ATMOS_VARS},
        metadata=Metadata(
            lat=__import__("torch").from_numpy(np.asarray(lat, dtype=np.float32)),
            lon=__import__("torch").from_numpy(to_0_360(np.asarray(lon, dtype=np.float32))),
            time=(time,),
            atmos_levels=tuple(levels),
        ),
    )


def load_model(device: str = "cuda"):
    """Load AuroraAirPollution with its pretrained checkpoint (needs GPU)."""
    from aurora import AuroraAirPollution

    model = AuroraAirPollution()
    model.load_checkpoint(CHECKPOINT_REPO, CHECKPOINT_NAME)
    model.eval()
    return model.to(device)


def run(batch, device: str = "cuda"):
    """Run a single forward pass; returns the predicted Batch (pm2p5 etc.)."""
    import torch

    model = load_model(device)
    with torch.inference_mode():
        pred = model.forward(batch.to(device))
    return pred


def run_rollout(batch, steps: int = 8, device: str = "cuda", model=None):
    """Yield (step, pred_batch) for +12h..+steps*12h using aurora.rollout.

    Each yielded pred is moved to CPU immediately; the caller should extract
    what it needs (India region / station cells) and drop the reference, so
    memory stays bounded on long rollouts.
    """
    import torch
    from aurora import rollout

    model = model if model is not None else load_model(device)
    with torch.inference_mode():
        for i, pred in enumerate(rollout(model, batch.to(device), steps=steps), start=1):
            yield i, pred.to("cpu")


# --------------------------------------------------------------------------- #
# Real-data loaders (CAMS analysis + HuggingFace static pickle)
# --------------------------------------------------------------------------- #

STATIC_PICKLE_REPO = "microsoft/aurora"
STATIC_PICKLE_NAME = "aurora-0.4-air-pollution-static.pickle"

# Aurora surface-var name -> CAMS NetCDF short name. Most match; only the
# ECMWF-style met names differ.
SURF_NC_NAME = {"2t": "t2m", "10u": "u10", "10v": "v10"}
# Atmos vars use identical short names in the CAMS pressure-level file.


def load_static_vars(pickle_path: str | None = None) -> dict[str, np.ndarray]:
    """Load the air-pollution static emission fields from the HF pickle.

    Returns a dict {var: (H, W) float32 array} on the canonical 451x900 grid.
    Downloads from HuggingFace if no local path is given.
    """
    import pickle

    if pickle_path is None:
        from huggingface_hub import hf_hub_download
        pickle_path = hf_hub_download(repo_id=STATIC_PICKLE_REPO, filename=STATIC_PICKLE_NAME)
    with open(pickle_path, "rb") as f:
        static = pickle.load(f)
    return {k: np.asarray(v, dtype=np.float32) for k, v in static.items()}


def assemble_inputs(sfc_path, plev_path, static: dict | None = None):
    """Build a validated Batch from CAMS analysis NetCDFs + static pickle.

    ``sfc_path`` / ``plev_path`` are the data_sfc.nc / data_plev.nc unpacked by
    src.data.cams_composition. Follows the official example_cams.ipynb: select
    the zero-hour forecast (analysis), use both timesteps (UTC 00 and 12), build
    the batch at the later time. Returns an ``aurora.Batch``.
    """
    import xarray as xr

    static = static if static is not None else load_static_vars()

    sfc = xr.open_dataset(sfc_path, engine="netcdf4", decode_timedelta=True)
    plev = xr.open_dataset(plev_path, engine="netcdf4", decode_timedelta=True)
    # Zero-hour forecast = analysis product.
    if "forecast_period" in sfc.dims:
        sfc = sfc.isel(forecast_period=0)
        plev = plev.isel(forecast_period=0)

    # surf[v]: (T=2, H, W); atmos[v]: (T=2, L, H, W) -- shapes build_batch expects.
    surf = {v: sfc[SURF_NC_NAME.get(v, v)].values for v in SURF_VARS}
    atmos = {v: plev[v].values for v in ATMOS_VARS}

    lat = plev.latitude.values
    lon = plev.longitude.values
    # Build the batch at the LAST available time (UTC 12).
    time = plev.valid_time.values.astype("datetime64[s]").tolist()
    time = time[-1] if isinstance(time, list) else time
    levels = tuple(int(x) for x in plev.pressure_level.values)

    return build_batch(surf, static, atmos, lat, lon, time, levels=levels)


def _dummy_batch():
    """Build a tiny all-zeros Batch to validate construction without data/GPU."""
    H, W = 17, 32
    surf = {v: np.zeros((HISTORY_STEPS, H, W), np.float32) for v in SURF_VARS}
    static = {v: np.zeros((H, W), np.float32) for v in STATIC_VARS}
    atmos = {v: np.zeros((HISTORY_STEPS, len(ATMOS_LEVELS), H, W), np.float32) for v in ATMOS_VARS}
    lat = np.linspace(30, 26, H, dtype=np.float32)   # descending
    lon = np.linspace(76, 80, W, dtype=np.float32)
    return build_batch(surf, static, atmos, lat, lon, datetime(2018, 2, 1, 6))


def _describe(b) -> None:
    print("  surf 2t:", tuple(b.surf_vars["2t"].shape), "(1, T, H, W)")
    print("  surf pm2p5:", tuple(b.surf_vars["pm2p5"].shape))
    print("  atmos t:", tuple(b.atmos_vars["t"].shape), "(1, T, L, H, W)")
    print("  static lsm:", tuple(b.static_vars["lsm"].shape), "(H, W)")
    print("  lat:", float(b.metadata.lat[0]), "->", float(b.metadata.lat[-1]),
          "| lon:", float(b.metadata.lon[0]), "->", float(b.metadata.lon[-1]))
    print("  time:", b.metadata.time, "| levels:", b.metadata.atmos_levels)


def main() -> None:
    p = argparse.ArgumentParser(description="Aurora Air Pollution runner.")
    p.add_argument("--check", action="store_true",
                   help="Construct a dummy Batch and report shapes (no GPU).")
    p.add_argument("--validate", action="store_true",
                   help="Assemble the Batch from real CAMS files and report (no GPU).")
    p.add_argument("--run", action="store_true",
                   help="Assemble + run a forward pass (needs GPU) and save output.")
    p.add_argument("--sfc", type=str, help="Path to data_sfc.nc")
    p.add_argument("--plev", type=str, help="Path to data_plev.nc")
    p.add_argument("--device", default="cuda", help="Torch device for --run.")
    p.add_argument("--out", type=str, default="results/aurora_pred.nc",
                   help="Where to save the predicted Batch (--run).")
    args = p.parse_args()

    if args.check:
        b = _dummy_batch()
        print("Dummy Batch constructed OK.")
        _describe(b)
        return

    if args.validate or args.run:
        if not (args.sfc and args.plev):
            raise SystemExit("--validate/--run need --sfc and --plev.")
        print("Assembling Batch from CAMS analysis files...")
        b = assemble_inputs(args.sfc, args.plev)
        print("Batch assembled OK.")
        _describe(b)
        if args.validate:
            return
        print(f"Running forward pass on {args.device}...")
        pred = run(b, device=args.device)
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pred.to_netcdf(args.out)
        print(f"Saved prediction -> {args.out}")
        print("  predicted pm2p5:", tuple(pred.surf_vars["pm2p5"].shape))
        return

    raise SystemExit("Use --check, --validate --sfc ... --plev ..., or --run ...")


if __name__ == "__main__":
    main()
