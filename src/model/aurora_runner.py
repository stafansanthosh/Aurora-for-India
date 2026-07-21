"""Aurora 0.4 Air Pollution inference wrapper (Phase 2).

Aurora 0.4 Air Pollution is Aurora 0.25 Pretrained fine-tuned on CAMS *analysis*
data; it predicts PM1/PM2.5/PM10 and gases (CO, NO, NO2, O3, SO2) directly.
That makes it the direct test of the project's research question (vs. the Phase-1
CAMS-reanalysis proxy).

IMPORTANT constraints (from the official Aurora docs):
  * Run it ONLY on CAMS *analysis* data for optimal skill -- NOT the EAC4
    reanalysis used in Phase 1. Other inputs give "sensible but not optimal"
    output.
  * Full-size model (~24 GB VRAM) -> needs an A100. Local CPU-only torch here
    cannot run the forward pass; this module is validated only for Batch
    construction (shape/convention correctness). Run the forward pass on the
    GPU box (see scripts/setup_a100.md).
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

Usage (on the A100 box):
    python -m src.model.aurora_runner --check      # construct a dummy Batch
    # full run wired once CAMS-analysis loaders are filled in.
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


# --------------------------------------------------------------------------- #
# TODO (complete on the GPU box against real CAMS *analysis* data)
# --------------------------------------------------------------------------- #

def load_static_vars(pickle_path):
    """Load the Microsoft-provided static emission fields (pickle).

    The static_* emission fields are not in CAMS/ERA5; Microsoft distributes
    them as a pickle. Download per the Aurora docs and load here, regridded to
    the target lat/lon.
    """
    raise NotImplementedError(
        "Download the Aurora static-variables pickle on the GPU box and wire it "
        "in here (regrid to target lat/lon)."
    )


def assemble_inputs(cams_analysis_path, era5_path, static_pickle, lat, lon, time):
    """Map CAMS analysis + ERA5 fields into the surf/static/atmos dicts.

    CAMS analysis (ADS: atmospheric-composition analysis) supplies pm*/gases and
    the atmospheric composition levels; ERA5 supplies 2t/10u/10v/msl/z and the
    met atmos vars (t,u,v,q,z). Fill this in against the real files, then call
    build_batch().
    """
    raise NotImplementedError(
        "Wire CAMS-analysis + ERA5 variables into surf/static/atmos dicts here."
    )


def _dummy_batch():
    """Build a tiny all-zeros Batch to validate construction without data/GPU."""
    H, W = 17, 32
    surf = {v: np.zeros((HISTORY_STEPS, H, W), np.float32) for v in SURF_VARS}
    static = {v: np.zeros((H, W), np.float32) for v in STATIC_VARS}
    atmos = {v: np.zeros((HISTORY_STEPS, len(ATMOS_LEVELS), H, W), np.float32) for v in ATMOS_VARS}
    lat = np.linspace(30, 26, H, dtype=np.float32)   # descending
    lon = np.linspace(76, 80, W, dtype=np.float32)
    return build_batch(surf, static, atmos, lat, lon, datetime(2018, 2, 1, 6))


def main() -> None:
    p = argparse.ArgumentParser(description="Aurora Air Pollution runner.")
    p.add_argument("--check", action="store_true",
                   help="Construct a dummy Batch and report shapes (no GPU).")
    args = p.parse_args()
    if args.check:
        b = _dummy_batch()
        print("Dummy Batch constructed OK.")
        print("  surf 2t:", tuple(b.surf_vars["2t"].shape), "(1, T, H, W)")
        print("  atmos t:", tuple(b.atmos_vars["t"].shape), "(1, T, L, H, W)")
        print("  static lsm:", tuple(b.static_vars["lsm"].shape), "(H, W)")
        print("  levels:", b.metadata.atmos_levels)
        return
    raise SystemExit("Nothing to do. Use --check, or wire assemble_inputs() on the GPU box.")


if __name__ == "__main__":
    main()
