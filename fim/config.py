"""
Configuration handling.

Defaults work with zero setup. A config.json next to the baseline file
(or passed via --config) can override watched paths and ignore patterns,
so you don't have to retype --path every time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_IGNORE_PATTERNS = [
    ".git",
    "__pycache__",
    "*.pyc",
    "node_modules",
    ".venv",
    "venv",
    ".DS_Store",
    "*.log",
    ".pytest_cache",
    ".mypy_cache",
    "*.egg-info",
]

DEFAULT_DATA_DIR = Path.home() / ".fim"
DEFAULT_BASELINE_PATH = DEFAULT_DATA_DIR / "baseline.json"
DEFAULT_LOG_PATH = DEFAULT_DATA_DIR / "fim.log"


@dataclass
class Config:
    watch_path: Path
    baseline_path: Path = DEFAULT_BASELINE_PATH
    log_path: Path = DEFAULT_LOG_PATH
    ignore_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS))

    @classmethod
    def load(cls, config_file: Path | None, watch_path: Path | None) -> "Config":
        data = {}
        if config_file and config_file.exists():
            with open(config_file) as f:
                data = json.load(f)

        resolved_watch = watch_path or (
            Path(data["watch_path"]).expanduser() if "watch_path" in data else None
        )
        if resolved_watch is None:
            raise ValueError(
                "No watch path given. Pass --path or set 'watch_path' in your config file."
            )

        return cls(
            watch_path=resolved_watch.resolve(),
            baseline_path=Path(data.get("baseline_path", DEFAULT_BASELINE_PATH)).expanduser(),
            log_path=Path(data.get("log_path", DEFAULT_LOG_PATH)).expanduser(),
            ignore_patterns=data.get("ignore_patterns", list(DEFAULT_IGNORE_PATTERNS)),
        )
