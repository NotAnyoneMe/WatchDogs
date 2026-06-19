"""
Tests for real-time watch mode (fim/watcher.py).

These use the actual watchdog Observer against a real temp directory,
since that's the only way to meaningfully test OS filesystem event
integration. A short sleep is required after each filesystem operation
to clear the debounce window (DEBOUNCE_SECONDS in watcher.py).
"""

import logging
import time
from pathlib import Path

import pytest

from fim.scanner import walk_and_hash
from fim.watcher import Watcher, DEBOUNCE_SECONDS

# Give the debounce timer plus OS event delivery a bit of headroom in tests
SETTLE_TIME = DEBOUNCE_SECONDS + 0.75


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    (tmp_path / "file1.txt").write_text("original\n")
    (tmp_path / "config.yml").write_text("config\n")
    return tmp_path


@pytest.fixture
def test_logger():
    logger = logging.getLogger("fim_test_watcher")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    records = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = ListHandler()
    logger.addHandler(handler)
    logger.records = records  # type: ignore[attr-defined]
    return logger


def make_watcher(sandbox, baseline_path, logger, persist=True):
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    baseline_files = {p: r.to_dict() for p, r in records.items()}
    return Watcher(
        root=sandbox,
        baseline_files=baseline_files,
        baseline_path=baseline_path,
        ignore_patterns=[".git", "__pycache__"],
        logger=logger,
        persist_baseline=persist,
    )


def test_watcher_detects_modification(sandbox, test_logger, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    watcher = make_watcher(sandbox, baseline_path, test_logger)
    watcher.start()
    try:
        (sandbox / "config.yml").write_text("tampered content\n")
        time.sleep(SETTLE_TIME)
    finally:
        watcher.stop()

    assert any("[MODIFIED]" in r and "config.yml" in r for r in test_logger.records)


def test_watcher_detects_new_file(sandbox, test_logger, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    watcher = make_watcher(sandbox, baseline_path, test_logger)
    watcher.start()
    try:
        (sandbox / "evil.sh").write_text("payload\n")
        time.sleep(SETTLE_TIME)
    finally:
        watcher.stop()

    assert any("[ADDED]" in r and "evil.sh" in r for r in test_logger.records)


def test_watcher_detects_deletion(sandbox, test_logger, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    watcher = make_watcher(sandbox, baseline_path, test_logger)
    watcher.start()
    try:
        (sandbox / "file1.txt").unlink()
        time.sleep(SETTLE_TIME)
    finally:
        watcher.stop()

    assert any("[REMOVED]" in r and "file1.txt" in r for r in test_logger.records)


def test_watcher_debounces_rapid_writes(sandbox, test_logger, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    watcher = make_watcher(sandbox, baseline_path, test_logger)
    watcher.start()
    try:
        for i in range(5):
            (sandbox / "config.yml").write_text(f"rapid edit {i}\n")
            time.sleep(0.05)
        time.sleep(SETTLE_TIME)
    finally:
        watcher.stop()

    modified_events = [
        r for r in test_logger.records if "[MODIFIED]" in r and "config.yml" in r
    ]
    assert len(modified_events) == 1


def test_watcher_persists_baseline_by_default(sandbox, test_logger, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    watcher = make_watcher(sandbox, baseline_path, test_logger, persist=True)
    watcher.start()
    try:
        (sandbox / "evil.sh").write_text("payload\n")
        time.sleep(SETTLE_TIME)
    finally:
        watcher.stop()

    assert baseline_path.exists()
    from fim.baseline import load_baseline
    saved = load_baseline(baseline_path)
    assert "evil.sh" in saved["files"]


def test_watcher_no_persist_leaves_baseline_file_untouched(sandbox, test_logger, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    watcher = make_watcher(sandbox, baseline_path, test_logger, persist=False)
    watcher.start()
    try:
        (sandbox / "evil.sh").write_text("payload\n")
        time.sleep(SETTLE_TIME)
    finally:
        watcher.stop()

    assert not baseline_path.exists()


def test_watcher_ignores_ignored_paths(sandbox, test_logger, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    git_dir = sandbox / ".git"
    git_dir.mkdir()

    watcher = make_watcher(sandbox, baseline_path, test_logger)
    watcher.start()
    try:
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        time.sleep(SETTLE_TIME)
    finally:
        watcher.stop()

    assert not any("HEAD" in r for r in test_logger.records)
