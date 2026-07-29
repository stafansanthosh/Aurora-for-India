"""Append distinct GPU-worker manifest records without overwriting provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _records(path: Path) -> list[dict]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
        if not isinstance(record, dict) or not record.get("date") or not record.get("status"):
            raise ValueError(
                f"{path}:{line_number} lacks required date/status fields"
            )
        records.append(record)
    return records


def merge_manifests(inputs: list[Path], output: Path) -> tuple[int, int]:
    """Append new canonical JSON records and return (added, duplicates)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    existing_records = _records(output) if output.exists() else []
    canonical = {
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        for record in existing_records
    }
    added = 0
    duplicates = 0
    with output.open("a", encoding="utf-8", newline="\n") as handle:
        for path in inputs:
            for record in _records(path):
                key = json.dumps(record, sort_keys=True, separators=(",", ":"))
                if key in canonical:
                    duplicates += 1
                    continue
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                canonical.add(key)
                added += 1
    return added, duplicates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append distinct per-worker rollout manifests safely."
    )
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/pairs/manifest.jsonl"),
    )
    args = parser.parse_args()
    added, duplicates = merge_manifests(args.inputs, args.output)
    print(f"Appended {added} records; skipped {duplicates} exact duplicates.")


if __name__ == "__main__":
    main()
