"""Resume and fixed-support contracts for the integrated GPU orchestrator."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.merge_worker_manifests import merge_manifests
from src.pipeline import orchestrate


def _complete_pairs(
    date: str = "2025-02-19",
    registry_version: str = "2:test",
) -> pd.DataFrame:
    rows = []
    for station_id in ("s1", "s2"):
        for lead_h in range(0, 97, 12):
            rows.append(
                {
                    "init_date": date,
                    "station_id": station_id,
                    "lead_h": lead_h,
                    "registry_version": registry_version,
                    "cams_forecast_pm25": (
                        np.nan if lead_h == 0 else 20.0 + lead_h
                    ),
                }
            )
    return pd.DataFrame(rows)


def test_resume_requires_the_complete_pair_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "pairs_2025-02-19.parquet"
    path.write_bytes(b"fixture")
    frame = _complete_pairs()
    monkeypatch.setattr(pd, "read_parquet", lambda _: frame.copy())

    assert orchestrate._pair_artifact_complete(
        path,
        "2025-02-19",
        "2:test",
        expected_stations=2,
        steps=8,
    )

    frame.loc[frame["lead_h"] == 96, "cams_forecast_pm25"] = np.nan
    assert not orchestrate._pair_artifact_complete(
        path,
        "2025-02-19",
        "2:test",
        expected_stations=2,
        steps=8,
    )
    assert not orchestrate._pair_artifact_complete(
        tmp_path / "missing.parquet",
        "2025-02-19",
        "2:test",
        expected_stations=2,
        steps=8,
    )


def test_process_date_rejects_nonstandard_steps_before_download() -> None:
    with pytest.raises(ValueError, match="pinned to 8"):
        orchestrate.process_date(
            "2025-02-19",
            model=object(),
            reg=pd.DataFrame(),
            steps=7,
            device="cpu",
            cleanup=True,
        )


def test_offline_preflight_requires_both_cams_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, bool]] = []

    monkeypatch.setattr(
        orchestrate.cams_forecast,
        "retrieve_forecast",
        lambda request, allow_retrieve: calls.append(
            ("forecast", request.date, allow_retrieve)
        ),
    )
    monkeypatch.setattr(
        orchestrate.cams_composition,
        "retrieve",
        lambda date, allow_retrieve: calls.append(
            ("analysis", date, allow_retrieve)
        ),
    )

    orchestrate._preflight_offline_inputs(["2025-02-19", "2025-02-20"])

    assert calls == [
        ("forecast", "2025-02-19", False),
        ("analysis", "2025-02-19", False),
        ("forecast", "2025-02-20", False),
        ("analysis", "2025-02-20", False),
    ]


def test_batch_continues_after_date_error_then_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted: list[str] = []
    logged: list[dict] = []

    def fake_process(date: str, *args, **kwargs) -> int:
        attempted.append(date)
        if date == "2025-02-19":
            raise ValueError("synthetic failure")
        return 1431

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "orchestrate",
            "--dates",
            "2025-02-19",
            "2025-02-20",
            "--device",
            "cpu",
        ],
    )
    monkeypatch.setattr(
        orchestrate,
        "_load_registry",
        lambda: pd.DataFrame({"station_id": [1]}),
    )
    monkeypatch.setattr(orchestrate, "_registry_version", lambda _: "1:test")
    monkeypatch.setattr(orchestrate, "_manifest_done", lambda *args, **kwargs: set())
    monkeypatch.setattr(orchestrate.aurora_runner, "load_model", lambda _: object())
    monkeypatch.setattr(orchestrate, "process_date", fake_process)
    monkeypatch.setattr(orchestrate, "_log", logged.append)

    with pytest.raises(RuntimeError, match="1 rollout date.*2025-02-19"):
        orchestrate.main()

    assert attempted == ["2025-02-19", "2025-02-20"]
    assert logged[0]["status"] == "error"
    assert logged[0]["registry_version"] == "1:test"


def test_worker_manifests_replace_stale_output_without_duplicate_records(
    tmp_path: Path,
) -> None:
    worker_a = tmp_path / "worker_a.jsonl"
    worker_b = tmp_path / "worker_b.jsonl"
    output = tmp_path / "manifest.jsonl"
    first = {"date": "2025-02-19", "status": "done", "rows": 1431}
    second = {"date": "2025-02-20", "status": "done", "rows": 1431}
    worker_a.write_text(f"{json.dumps(first)}\n", encoding="utf-8")
    worker_b.write_text(
        f"{json.dumps(first)}\n{json.dumps(second)}\n",
        encoding="utf-8",
    )

    stale = {"date": "2025-11-15", "status": "done", "rows": 297}
    output.write_text(f"{json.dumps(stale)}\n", encoding="utf-8")

    assert merge_manifests([worker_a, worker_b], output) == (2, 1)
    assert merge_manifests([worker_a, worker_b], output) == (2, 1)
    records = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [first, second]


def test_worker_manifest_merge_rejects_conflicting_date_records(
    tmp_path: Path,
) -> None:
    worker_a = tmp_path / "worker_a.jsonl"
    worker_b = tmp_path / "worker_b.jsonl"
    output = tmp_path / "manifest.jsonl"
    worker_a.write_text(
        f'{json.dumps({"date": "2025-02-19", "status": "done", "rows": 1431})}\n',
        encoding="utf-8",
    )
    worker_b.write_text(
        f'{json.dumps({"date": "2025-02-19", "status": "done", "rows": 1143})}\n',
        encoding="utf-8",
    )
    output.write_text("preserve me\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Conflicting worker records"):
        merge_manifests([worker_a, worker_b], output)

    assert output.read_text(encoding="utf-8") == "preserve me\n"
