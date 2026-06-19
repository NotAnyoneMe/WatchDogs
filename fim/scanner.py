"""
Core scanning logic: walk a directory tree, hash files, and produce
a snapshot dict that can be saved as a baseline or compared against one.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

CHUNK_SIZE = 65536  # 64KB chunks, keeps memory flat for huge files


@dataclass
class FileRecord:
    path: str          # path relative to the watched root, POSIX-style
    sha256: str
    size: int
    mtime: float        # last modified time (epoch seconds)

    def to_dict(self) -> dict:
        return asdict(self)


def hash_file(filepath: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def should_ignore(path: Path, ignore_patterns: Iterable[str]) -> bool:
    """
    Check a path's parts against simple ignore patterns.
    Patterns match against directory/file *names* anywhere in the path,
    e.g. ".git", "__pycache__", "node_modules", "*.pyc".
    """
    import fnmatch

    parts = path.parts
    for pattern in ignore_patterns:
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
        if fnmatch.fnmatch(path.name, pattern):
            return True
    return False


def walk_and_hash(
    root: Path,
    ignore_patterns: Iterable[str] = (),
) -> dict[str, FileRecord]:
    """
    Walk `root` recursively, hash every file not matched by ignore_patterns,
    and return a dict mapping relative POSIX path -> FileRecord.

    Symlinks are skipped (not followed) to avoid loops and to avoid hashing
    content outside the intended tree.
    """
    root = root.resolve()
    records: dict[str, FileRecord] = {}

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current_dir = Path(dirpath)

        # Prune ignored directories in-place so os.walk doesn't descend into them
        dirnames[:] = [
            d for d in dirnames
            if not should_ignore(current_dir / d, ignore_patterns)
        ]

        for filename in filenames:
            full_path = current_dir / filename

            if full_path.is_symlink():
                continue
            if should_ignore(full_path, ignore_patterns):
                continue

            try:
                stat = full_path.stat()
                digest = hash_file(full_path)
            except (PermissionError, FileNotFoundError, OSError) as e:
                # File vanished mid-scan, or we don't have read access.
                # Record nothing for it; scanner.py callers can decide
                # whether unreadable files should be surfaced separately.
                continue

            rel_path = full_path.relative_to(root).as_posix()
            records[rel_path] = FileRecord(
                path=rel_path,
                sha256=digest,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )

    return records
