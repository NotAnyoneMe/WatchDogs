"""
Baseline persistence and diffing.

A baseline is a JSON file capturing:
  - the root directory it was taken against
  - timestamp it was created
  - a map of relative path -> {sha256, size, mtime}

Diffing compares a fresh scan's records against a loaded baseline and
classifies every path as added, removed, or modified.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .scanner import FileRecord, walk_and_hash


@dataclass
class DiffResult:
    added: list[str]
    removed: list[str]
    modified: list[str]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)


def save_baseline(
    root: Path,
    records: dict[str, FileRecord],
    baseline_path: Path,
) -> None:
    data = {
        "root": str(root.resolve()),
        "created_at": time.time(),
        "file_count": len(records),
        "files": {path: rec.to_dict() for path, rec in records.items()},
    }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "w") as f:
        json.dump(data, f, indent=2)


def load_baseline(baseline_path: Path) -> dict:
    if not baseline_path.exists():
        raise FileNotFoundError(
            f"No baseline found at {baseline_path}. Run `fim baseline` first."
        )
    with open(baseline_path) as f:
        return json.load(f)


def diff_against_baseline(
    current: dict[str, FileRecord],
    baseline_files: dict[str, dict],
) -> DiffResult:
    """
    current: fresh scan results (path -> FileRecord)
    baseline_files: the "files" section loaded from a baseline JSON
                     (path -> dict with sha256/size/mtime)
    """
    current_paths = set(current.keys())
    baseline_paths = set(baseline_files.keys())

    added = sorted(current_paths - baseline_paths)
    removed = sorted(baseline_paths - current_paths)

    modified = sorted(
        path
        for path in current_paths & baseline_paths
        if current[path].sha256 != baseline_files[path]["sha256"]
    )

    return DiffResult(added=added, removed=removed, modified=modified)


def run_scan_and_diff(
    root: Path,
    baseline_path: Path,
    ignore_patterns: list[str],
) -> tuple[DiffResult, dict[str, FileRecord]]:
    """Convenience wrapper: load baseline, scan root, diff. Returns (diff, fresh_records)."""
    baseline = load_baseline(baseline_path)
    fresh_records = walk_and_hash(root, ignore_patterns)
    diff = diff_against_baseline(fresh_records, baseline["files"])
    return diff, fresh_records
