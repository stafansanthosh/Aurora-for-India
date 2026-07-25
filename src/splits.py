"""THE split contract for IndiaAQBench — single source of truth (spec §3, §6).

Every module that trains, evaluates, or selects dates imports these constants.
They were previously duplicated across src/eval/benchmark.py,
src/eval/coverage_audit.py and src/model/calibrator.py, which risks the worst
kind of bug in a benchmark: the definitions silently drifting apart so a model
trains on rows another module calls "test".

--------------------------------------------------------------------------------
TEMPORAL CUTOFF — REVISED ONCE, 2026-07-24, BEFORE ANY ADAPTATION WAS TRAINED
--------------------------------------------------------------------------------
Original: 2025-07-01. Revised to 2025-12-01 under the contingency pre-registered
in spec §6 ("if winter 2024-25 OpenAQ density is insufficient for training, fall
back to a within-winter split with the cutoff inside Nov 2025, documented in the
results").

The pre-registered condition was objectively met: OpenAQ serves essentially no
Indian station data before ~Feb 2025 (0-2 stations reporting per city in
Oct 2024 - Jan 2025; verified at sensor level -- see src/data/archive_probe.py).
The original cutoff therefore left the TRAIN period as Feb-Jun 2025 only: the
calm half of the year, 95th percentile ~142 ug/m3, with no severe season at all.
A calibrator fit on it collapsed the severe tail entirely (Very Poor+ POD 0.00
vs raw Aurora's 0.64) because it had never seen an extreme value.

The revision puts post-monsoon 2025 (Diwali + stubble burning) in TRAIN and
keeps winter 2025-26 in TEST, so BOTH sides contain the severe regime:
    train events (>=121):  13,844 -> 40,538   (2.9x)
    train p95:               ~142 -> ~360
    test  events (>=121):            51,875   (Dec 2025 - Feb 2026 severe season)

Disclosure requirement: this revision happened once, before any adaptation model
was trained on the new split, and must be reported wherever results appear.
"""
from __future__ import annotations

import pandas as pd

# --------------------------------------------------------------------------- #
# Temporal split
# --------------------------------------------------------------------------- #
SPLIT_CUTOFF = pd.Timestamp("2025-12-01", tz="UTC")  # train < cutoff <= test
SPLIT_CUTOFF_ORIGINAL = pd.Timestamp("2025-07-01", tz="UTC")  # superseded; kept for provenance

# --------------------------------------------------------------------------- #
# Spatial splits (spec §3)
# --------------------------------------------------------------------------- #
# L2 — cities never seen in training. Tests regional transfer, i.e. the
# difference between "good interpolation" and a method that generalizes.
HELDOUT_CITIES: frozenset[str] = frozenset({"kanpur", "varanasi", "kolkata"})

# L1 — held-out stations inside training cities. Tests within-city
# interpolation. Frozen by stable hash so the partition never depends on run
# order, station count, or pull recency.
L1_HOLDOUT_FRAC = 0.20
L1_HASH_SALT = "indiaaqbench-L1-v1"


def l1_is_holdout(station_id) -> bool:
    """True if this station is in the frozen L1 held-out set."""
    import hashlib

    h = hashlib.sha1(f"{L1_HASH_SALT}:{station_id}".encode()).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF) < L1_HOLDOUT_FRAC


def is_test(times) -> "pd.Series":
    """Vectorized temporal-split membership for a datetime-like series."""
    t = pd.to_datetime(times, utc=True)
    return t >= SPLIT_CUTOFF
