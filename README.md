<div align="center">

# 🐺 WatchDogs

### Real-time File Integrity Monitor — catch unauthorized file changes the moment they happen

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#license)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)](#installation)

[Features](#-features) •
[Installation](#-installation) •
[Usage](#-usage) •
[Configuration](#-configuration) •
[Donate](#-support-the-project)

</div>

---

## 📖 About

**WatchDogs** is a File Integrity Monitor (FIM) written in Python. It detects unauthorized changes to your files — the kind of thing that happens when malware drops a backdoor, a server gets compromised, or someone tampers with a config file they shouldn't have touched.

It works by:
1. Hashing every file in a directory with **SHA-256**
2. Saving that as a **baseline** snapshot
3. Comparing future scans (or live filesystem events) against that baseline
4. Reporting exactly what was **added**, **removed**, or **modified**

No bloat, no external services required, no telemetry. Just hashing, diffing, and alerting — built to be readable, scriptable, and easy to bolt into your own workflows (cron, CI, systemd, whatever you've got).

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **SHA-256 hashing** | Cryptographically strong file fingerprinting — not MD5/SHA-1, which are broken for collision resistance |
| 📸 **Baseline snapshots** | Save a point-in-time "known good" state of any directory tree as a portable JSON file |
| 🔄 **On-demand scanning** | Re-hash and diff against your baseline whenever you want — perfect for cron jobs or CI pipelines |
| 👁️ **Real-time watch mode** | Live monitoring powered by `watchdog` — reacts to OS filesystem events instantly instead of polling |
| ⏱️ **Debounced alerts** | Rapid saves (editors writing a file 2–3 times per save) collapse into a single alert, not a flood |
| 🚫 **Smart ignore patterns** | Skip `.git`, `node_modules`, `__pycache__`, and anything else you don't care about, with glob support |
| 📝 **Dual logging** | Console output + rotating log file, so nothing gets lost and your disk doesn't fill up |
| 🤖 **Automation-friendly** | `--json` output and `--fail-on-change` exit codes built for scripting, cron, and CI/CD |
| ⚙️ **Config file support** | Define watch paths, ignore rules, and baseline locations once — no more retyping flags |
| 🔌 **Zero required dependencies for core scanning** | `baseline` and `scan` run on the Python standard library alone; only `watch` needs `watchdog` |

---

## 📦 Installation

### Clone the repo

```bash
git clone https://github.com/NotAnyoneMe/WatchDogs.git
cd WatchDogs
```

### Install

```bash
pip install -e .
```

> **Windows users:** if the `fim` command isn't recognized after install, run it as a module instead — this always works regardless of your `PATH`:
> ```powershell
> python -m fim baseline --path C:\path\to\watch
> ```
> Or add Python's `Scripts` folder to your `PATH` (find it with `python -m site --user-site`, then look in the sibling `Scripts` directory).

### Requirements
- Python 3.10+
- `watchdog` (only required for `watch` mode — installed automatically via `pip install -e .`)

---

## 🚀 Usage

WatchDogs has three core commands: `baseline`, `scan`, and `watch`.

### 1. `baseline` — take a snapshot

Hash every file in a directory and save it as your "known good" reference point.

```bash
fim baseline --path /path/to/your/project
```

```
Scanning /path/to/your/project ...
Baseline saved: 142 files hashed.
Baseline file: ~/.fim/baseline.json
```

| Flag | Description |
|---|---|
| `--path` | Directory to baseline |
| `--baseline-file` | Custom save location (default: `~/.fim/baseline.json`) |

---

### 2. `scan` — check for changes on demand

Re-hash the directory and compare it against your saved baseline.

```bash
fim scan --path /path/to/your/project
```

```
Scanning /path/to/your/project ...
3 change(s) detected:
  [MODIFIED] config.yml
  [ADDED]    subdir/evil.sh
  [REMOVED]  file1.txt
```

| Flag | Description |
|---|---|
| `--path` | Directory to scan |
| `--baseline-file` | Baseline to compare against |
| `--json` | Machine-readable output for piping into other tools |
| `--fail-on-change` | Exit code `2` if changes are found — `0` if clean, `1` on error. Ideal for cron/CI. |

**Cron example** — scan every 15 minutes and only make noise when something's wrong:

```cron
*/15 * * * * /usr/bin/python3 -m fim scan --config ~/.fim/config.json --fail-on-change || /usr/bin/mail -s "WatchDogs ALERT" you@example.com < ~/.fim/fim.log
```

---

### 3. `watch` — real-time monitoring

Continuously watches the directory using OS-level filesystem events (via `watchdog`) and alerts the instant something changes — no polling delay.

```bash
fim watch --path /path/to/your/project
```

```
Watching /path/to/your/project for changes (Ctrl+C to stop)...
  [MODIFIED] config.yml
  [ADDED]    subdir/evil.sh
  [REMOVED]  file1.txt
```

| Flag | Description |
|---|---|
| `--path` | Directory to watch |
| `--baseline-file` | Baseline to start from / live-update |
| `--no-persist` | Don't write detected changes back to the baseline file — it stays frozen until you re-run `baseline` |

**Behavior notes:**
- **Debounced** (0.75s quiet period) — one save triggers one alert, not three
- **Live baseline updates** by default, so a later `scan` agrees with what `watch` already caught
- **Renames** appear as `[REMOVED]` (old path) + `[ADDED]` (new path) — that's what the underlying OS events actually report
- Stop with `Ctrl+C`. Run it under `systemd`, `pm2`, `supervisor`, or `tmux` if you want it to survive reboots/terminal closures — WatchDogs doesn't daemonize itself

---

## ⚙️ Configuration

Instead of retyping `--path` every time, define a config file:

```json
{
  "watch_path": "/home/you/projects/my-api",
  "baseline_path": "/home/you/.fim/my-api-baseline.json",
  "log_path": "/home/you/.fim/my-api.log",
  "ignore_patterns": [".git", "__pycache__", "*.pyc", "node_modules", ".venv", "*.log"]
}
```

Then run any command with `--config`:

```bash
fim scan --config /path/to/config.json
```

`ignore_patterns` matches against any directory/file name in the path, with glob support (`*.pyc`, `*.log`, etc).

### Default storage locations

| Item | Default path |
|---|---|
| Baseline snapshot | `~/.fim/baseline.json` |
| Log file (rotating, 5MB × 3 backups) | `~/.fim/fim.log` |

---

## 🏗️ Project Structure

```
WatchDogs/
├── fim/
│   ├── __init__.py
│   ├── __main__.py      # `python -m fim` entry point
│   ├── cli.py            # argparse subcommands: baseline, scan, watch
│   ├── scanner.py        # directory walking + SHA-256 hashing
│   ├── baseline.py       # save/load baseline JSON, diffing logic
│   ├── watcher.py        # real-time watch mode (watchdog-based)
│   ├── config.py         # config file + defaults
│   └── logger.py         # console + rotating file logging
├── tests/
│   ├── test_fim.py        # scanner/baseline test suite
│   └── test_watcher.py    # watch mode test suite
├── config.example.json
├── pyproject.toml
└── README.md
```

## 🧪 Running tests

```bash
pip install pytest
pytest tests/ -v
```

---

## 🗺️ Roadmap

- [ ] **Notifications** — email / webhook / Slack / Telegram alerts when changes are detected
- [ ] **Baseline signing** — HMAC-sign the baseline file so an attacker who can modify files can't quietly edit the baseline to cover their tracks
- [ ] **Multiple watch targets** — monitor several directories with independent baselines/ignore rules from one config

---

## 🤝 Contributing

Issues and pull requests are welcome. If you're adding a feature, try to keep the same separation of concerns: `scanner.py` only hashes, `baseline.py` only persists/diffs, `watcher.py` only handles live events — keeps things testable.

---

## 💖 Support the Project

WatchDogs is free and open-source. If it's saved you time, caught something it shouldn't have, or you just want to support future development, donations are genuinely appreciated:

| Platform | Link |
|---|---|
| 💳 PayPal | [paypal.me/HassanBakhs](https://paypal.me/HassanBakhs) |

You're also welcome to support the project just by starring the repo, opening issues, or contributing code — that helps just as much.

---

## 👤 Credits

**Author:** NotAnyone

- 🐙 GitHub: [@NotAnyoneMe](https://github.com/NotAnyoneMe)
- ✈️ Telegram: [@MLBOR](https://t.me/MLBOR)
- 📦 Repository: [github.com/NotAnyoneMe/WatchDogs](https://github.com/NotAnyoneMe/WatchDogs)

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details. Use it, modify it, ship it — just don't hold me liable if something breaks.

---

<div align="center">

**If WatchDogs caught something it shouldn't have, consider giving it a ⭐**

</div>
