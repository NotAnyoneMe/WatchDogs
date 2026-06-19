"""
Command-line interface for the File Integrity Monitor.

Usage:
    python -m fim baseline --path /path/to/watch
    python -m fim scan --path /path/to/watch
    python -m fim scan --path /path/to/watch --json
    python -m fim watch --path /path/to/watch
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .baseline import diff_against_baseline, load_baseline, save_baseline
from .config import Config
from .logger import setup_logging
from .scanner import walk_and_hash


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fim",
        description="File Integrity Monitor — detect unauthorized file changes.",
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Path to a JSON config file (default: none, use CLI args).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show debug-level output on the console.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    baseline_parser = subparsers.add_parser(
        "baseline", help="Create or overwrite the baseline snapshot."
    )
    baseline_parser.add_argument("--path", type=Path, default=None, help="Directory to watch.")
    baseline_parser.add_argument(
        "--baseline-file", type=Path, default=None,
        help="Where to save the baseline JSON (default: ~/.fim/baseline.json).",
    )

    scan_parser = subparsers.add_parser(
        "scan", help="Scan and compare against the saved baseline."
    )
    scan_parser.add_argument("--path", type=Path, default=None, help="Directory to watch.")
    scan_parser.add_argument(
        "--baseline-file", type=Path, default=None,
        help="Baseline JSON to compare against (default: ~/.fim/baseline.json).",
    )
    scan_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Print results as JSON instead of human-readable text.",
    )
    scan_parser.add_argument(
        "--fail-on-change", action="store_true",
        help="Exit with code 2 if any changes are detected (useful in CI/cron).",
    )

    watch_parser = subparsers.add_parser(
        "watch", help="Continuously watch in real time and alert on changes."
    )
    watch_parser.add_argument("--path", type=Path, default=None, help="Directory to watch.")
    watch_parser.add_argument(
        "--baseline-file", type=Path, default=None,
        help="Baseline JSON to start from / update (default: ~/.fim/baseline.json).",
    )
    watch_parser.add_argument(
        "--no-persist", action="store_true",
        help="Don't write changes back to the baseline file as they're detected "
             "(baseline stays exactly as it was until you run `baseline` again).",
    )

    return parser


def cmd_baseline(args: argparse.Namespace) -> int:
    config = Config.load(args.config, args.path)
    if args.baseline_file:
        config.baseline_path = args.baseline_file

    logger = setup_logging(config.log_path, args.verbose)

    logger.info(f"Scanning {config.watch_path} ...")
    records = walk_and_hash(config.watch_path, config.ignore_patterns)
    save_baseline(config.watch_path, records, config.baseline_path)

    logger.info(f"Baseline saved: {len(records)} files hashed.")
    logger.info(f"Baseline file: {config.baseline_path}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    config = Config.load(args.config, args.path)
    if args.baseline_file:
        config.baseline_path = args.baseline_file

    logger = setup_logging(config.log_path, args.verbose)

    try:
        baseline = load_baseline(config.baseline_path)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1

    logger.info(f"Scanning {config.watch_path} ...")
    fresh_records = walk_and_hash(config.watch_path, config.ignore_patterns)
    diff = diff_against_baseline(fresh_records, baseline["files"])

    if args.json_output:
        result = {
            "watch_path": str(config.watch_path),
            "baseline_file": str(config.baseline_path),
            "added": diff.added,
            "removed": diff.removed,
            "modified": diff.modified,
            "total_changes": diff.total_changes,
        }
        print(json.dumps(result, indent=2))
    else:
        if not diff.has_changes:
            logger.info("No changes detected. All files match the baseline.")
        else:
            logger.warning(f"{diff.total_changes} change(s) detected:")
            for path in diff.modified:
                logger.warning(f"  [MODIFIED] {path}")
            for path in diff.added:
                logger.warning(f"  [ADDED]    {path}")
            for path in diff.removed:
                logger.warning(f"  [REMOVED]  {path}")

    if args.fail_on_change and diff.has_changes:
        return 2
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    # Imported here (not at module top) so `baseline`/`scan` still work even
    # in an environment where the optional `watchdog` dependency isn't installed.
    from .watcher import Watcher

    config = Config.load(args.config, args.path)
    if args.baseline_file:
        config.baseline_path = args.baseline_file

    logger = setup_logging(config.log_path, args.verbose)

    try:
        baseline = load_baseline(config.baseline_path)
    except FileNotFoundError as e:
        logger.error(str(e))
        logger.error("Run `fim baseline --path ...` first, then `fim watch`.")
        return 1

    watcher = Watcher(
        root=config.watch_path,
        baseline_files=baseline["files"],
        baseline_path=config.baseline_path,
        ignore_patterns=config.ignore_patterns,
        logger=logger,
        persist_baseline=not args.no_persist,
    )
    watcher.run_forever()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "baseline":
        return cmd_baseline(args)
    elif args.command == "scan":
        return cmd_scan(args)
    elif args.command == "watch":
        return cmd_watch(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
