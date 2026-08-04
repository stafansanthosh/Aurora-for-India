"""Build one canonical manifest from distinct GPU-worker records."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile


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
    """Atomically replace ``output`` with deduplicated worker records.

    The canonical manifest represents the accepted rollout, not an append-only
    history. Superseded pilot records in an existing output must therefore not
    survive a worker merge. Exact duplicate input records are ignored, while
    two different records for the same date are rejected as ambiguous.

    Returns ``(written, exact_duplicates)``.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    canonical: dict[str, tuple[str, dict]] = {}
    duplicates = 0
    for path in inputs:
        for record in _records(path):
            date = str(record["date"])
            key = json.dumps(record, sort_keys=True, separators=(",", ":"))
            prior = canonical.get(date)
            if prior is None:
                canonical[date] = (key, record)
            elif prior[0] == key:
                duplicates += 1
            else:
                raise ValueError(
                    f"Conflicting worker records for {date}; refusing to "
                    "choose provenance implicitly."
                )

    records = [canonical[date][1] for date in sorted(canonical)]
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return len(records), duplicates


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
    print(f"Wrote {added} records; skipped {duplicates} exact duplicates.")


if __name__ == "__main__":
    main()
