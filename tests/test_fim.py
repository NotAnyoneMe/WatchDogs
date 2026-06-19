"""
Automated tests for the FIM core logic.
Run with: pytest -v
"""

import time
from pathlib import Path

import pytest

from fim.scanner import walk_and_hash, hash_file, should_ignore
from fim.baseline import save_baseline, load_baseline, diff_against_baseline


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """Create a small directory tree with known content."""
    (tmp_path / "file1.txt").write_text("hello world\n")
    (tmp_path / "config.yml").write_text("config data\n")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested file\n")

    # Should be ignored by default patterns
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

    return tmp_path


def test_hash_file_is_deterministic(sandbox: Path):
    h1 = hash_file(sandbox / "file1.txt")
    h2 = hash_file(sandbox / "file1.txt")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest length


def test_hash_changes_when_content_changes(sandbox: Path):
    target = sandbox / "file1.txt"
    before = hash_file(target)
    target.write_text("different content\n")
    after = hash_file(target)
    assert before != after


def test_should_ignore_matches_dir_and_glob():
    assert should_ignore(Path("/a/.git/HEAD"), [".git"])
    assert should_ignore(Path("/a/b/__pycache__/x.pyc"), ["__pycache__"])
    assert should_ignore(Path("/a/b/c.pyc"), ["*.pyc"])
    assert not should_ignore(Path("/a/b/c.txt"), [".git", "*.pyc"])


def test_walk_and_hash_finds_all_files_and_skips_ignored(sandbox: Path):
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    paths = set(records.keys())

    assert paths == {"file1.txt", "config.yml", "subdir/nested.txt"}
    assert ".git/HEAD" not in paths


def test_walk_and_hash_relative_paths_are_posix_style(sandbox: Path):
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    assert "subdir/nested.txt" in records
    assert "subdir\\nested.txt" not in records  # no Windows-style separators leak through


def test_baseline_roundtrip(sandbox: Path, tmp_path: Path):
    baseline_file = tmp_path / "out" / "baseline.json"
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])

    save_baseline(sandbox, records, baseline_file)
    assert baseline_file.exists()

    loaded = load_baseline(baseline_file)
    assert loaded["file_count"] == 3
    assert set(loaded["files"].keys()) == {"file1.txt", "config.yml", "subdir/nested.txt"}
    assert loaded["files"]["file1.txt"]["sha256"] == records["file1.txt"].sha256


def test_load_baseline_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_baseline(tmp_path / "does_not_exist.json")


def test_diff_detects_no_changes_when_nothing_changed(sandbox: Path):
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    baseline_files = {path: rec.to_dict() for path, rec in records.items()}

    diff = diff_against_baseline(records, baseline_files)
    assert not diff.has_changes
    assert diff.total_changes == 0


def test_diff_detects_modified_file(sandbox: Path):
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    baseline_files = {path: rec.to_dict() for path, rec in records.items()}

    (sandbox / "config.yml").write_text("tampered content\n")
    fresh = walk_and_hash(sandbox, ignore_patterns=[".git"])

    diff = diff_against_baseline(fresh, baseline_files)
    assert diff.modified == ["config.yml"]
    assert diff.added == []
    assert diff.removed == []


def test_diff_detects_added_file(sandbox: Path):
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    baseline_files = {path: rec.to_dict() for path, rec in records.items()}

    (sandbox / "subdir" / "evil.sh").write_text("payload\n")
    fresh = walk_and_hash(sandbox, ignore_patterns=[".git"])

    diff = diff_against_baseline(fresh, baseline_files)
    assert diff.added == ["subdir/evil.sh"]
    assert diff.modified == []
    assert diff.removed == []


def test_diff_detects_removed_file(sandbox: Path):
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    baseline_files = {path: rec.to_dict() for path, rec in records.items()}

    (sandbox / "file1.txt").unlink()
    fresh = walk_and_hash(sandbox, ignore_patterns=[".git"])

    diff = diff_against_baseline(fresh, baseline_files)
    assert diff.removed == ["file1.txt"]
    assert diff.added == []
    assert diff.modified == []


def test_diff_detects_combination_of_changes(sandbox: Path):
    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    baseline_files = {path: rec.to_dict() for path, rec in records.items()}

    (sandbox / "config.yml").write_text("tampered\n")
    (sandbox / "subdir" / "evil.sh").write_text("payload\n")
    (sandbox / "file1.txt").unlink()

    fresh = walk_and_hash(sandbox, ignore_patterns=[".git"])
    diff = diff_against_baseline(fresh, baseline_files)

    assert diff.modified == ["config.yml"]
    assert diff.added == ["subdir/evil.sh"]
    assert diff.removed == ["file1.txt"]
    assert diff.total_changes == 3


def test_symlinks_are_skipped(sandbox: Path, tmp_path: Path):
    outside_target = tmp_path / "outside.txt"
    outside_target.write_text("outside content\n")
    link = sandbox / "link_to_outside.txt"
    try:
        link.symlink_to(outside_target)
    except OSError:
        pytest.skip("Symlinks not supported in this environment")

    records = walk_and_hash(sandbox, ignore_patterns=[".git"])
    assert "link_to_outside.txt" not in records
