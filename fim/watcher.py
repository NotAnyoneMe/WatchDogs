"""
Real-time watch mode using `watchdog`.

Instead of polling (re-walking + re-hashing the whole tree on demand like
`scan` does), this subscribes to OS-level filesystem events and reacts
immediately to the specific file that changed. Much cheaper on large
trees, and changes are caught the moment they happen instead of at the
next scheduled `scan`.

Key design points:
  - In-memory state starts from the loaded baseline, so `watch` and `scan`
    never disagree about what "normal" looks like.
  - Events are debounced per-path: editors/compilers often fire several
    write events for a single logical save, so we wait a short quiet
    period before hashing and reporting, instead of alerting 3x per save.
  - The baseline file on disk is updated as changes are confirmed (this
    is configurable) so a later `scan` reflects the new reality rather
    than re-flagging everything `watch` already reported.
  - Renames are reported as a REMOVED (old path) + ADDED (new path) pair,
    since that's what the underlying OS events actually tell us.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Iterable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .baseline import save_baseline
from .scanner import FileRecord, hash_file, should_ignore

DEBOUNCE_SECONDS = 0.75  # quiet period after the last event for a path before we act on it


class _DebouncedHandler(FileSystemEventHandler):
    """
    Translates raw watchdog events into debounced (path -> event_type) work items,
    then hands them to the FIM watcher for hashing + comparison.
    """

    def __init__(
        self,
        root: Path,
        ignore_patterns: Iterable[str],
        on_settled,  # callback: (relative_path: str, kind: str) -> None
    ):
        super().__init__()
        self.root = root
        self.ignore_patterns = list(ignore_patterns)
        self.on_settled = on_settled

        self._pending: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _should_skip(self, src_path: str) -> bool:
        path = Path(src_path)
        if path.is_dir():
            return True
        return should_ignore(path, self.ignore_patterns)

    def _schedule(self, src_path: str, kind: str) -> None:
        if self._should_skip(src_path):
            return

        with self._lock:
            existing = self._pending.get(src_path)
            if existing:
                existing.cancel()

            timer = threading.Timer(
                DEBOUNCE_SECONDS, self._settle, args=(src_path, kind)
            )
            timer.daemon = True
            self._pending[src_path] = timer
            timer.start()

    def _settle(self, src_path: str, kind: str) -> None:
        with self._lock:
            self._pending.pop(src_path, None)

        try:
            rel_path = Path(src_path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return  # outside root somehow, ignore

        self.on_settled(rel_path, kind)

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path, "modified")

    def on_deleted(self, event):
        if not event.is_directory:
            self._schedule(event.src_path, "deleted")

    def on_moved(self, event):
        if not event.is_directory:
            self._schedule(event.src_path, "deleted")
            self._schedule(event.dest_path, "created")


class Watcher:
    """
    Watches `root` in real time, keeping an in-memory copy of the baseline
    up to date and logging ADDED / MODIFIED / REMOVED as events settle.
    """

    def __init__(
        self,
        root: Path,
        baseline_files: dict[str, dict],
        baseline_path: Path,
        ignore_patterns: list[str],
        logger: logging.Logger,
        persist_baseline: bool = True,
    ):
        self.root = root.resolve()
        self.baseline_path = baseline_path
        self.ignore_patterns = ignore_patterns
        self.logger = logger
        self.persist_baseline = persist_baseline

        # Working copy of known-good state, seeded from the loaded baseline.
        # Keyed by relative path -> dict(sha256, size, mtime) to match the
        # baseline JSON shape directly.
        self._state: dict[str, dict] = dict(baseline_files)
        self._state_lock = threading.Lock()

        self._observer = Observer()
        self._handler = _DebouncedHandler(
            root=self.root,
            ignore_patterns=ignore_patterns,
            on_settled=self._handle_settled_event,
        )

    def _handle_settled_event(self, rel_path: str, kind: str) -> None:
        full_path = self.root / rel_path

        with self._state_lock:
            existed_before = rel_path in self._state

            if kind == "deleted" or not full_path.exists():
                if existed_before:
                    del self._state[rel_path]
                    self.logger.warning(f"  [REMOVED]  {rel_path}")
                    self._maybe_persist()
                return

            try:
                stat = full_path.stat()
                digest = hash_file(full_path)
            except (PermissionError, FileNotFoundError, OSError):
                return  # vanished or unreadable between event and now; skip quietly

            new_record = {
                "path": rel_path,
                "sha256": digest,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }

            if not existed_before:
                self._state[rel_path] = new_record
                self.logger.warning(f"  [ADDED]    {rel_path}")
                self._maybe_persist()
            elif self._state[rel_path]["sha256"] != digest:
                self._state[rel_path] = new_record
                self.logger.warning(f"  [MODIFIED] {rel_path}")
                self._maybe_persist()
            # else: hash unchanged (e.g. touch with no content change) — stay quiet

    def _maybe_persist(self) -> None:
        if not self.persist_baseline:
            return
        records = {
            path: FileRecord(**rec) for path, rec in self._state.items()
        }
        save_baseline(self.root, records, self.baseline_path)

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self.root), recursive=True)
        self._observer.start()
        self.logger.info(f"Watching {self.root} for changes (Ctrl+C to stop)...")

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()

    def run_forever(self) -> None:
        """Blocking loop; call start() first or use this which calls it for you."""
        self.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Stopping watch mode...")
            self.stop()
