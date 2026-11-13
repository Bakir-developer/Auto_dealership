"""Общие функции для хуков Claude Code (Windows + Linux/macOS)."""

import json
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass


def read_payload():
    raw = sys.stdin.buffer.read().decode('utf-8', errors='replace')
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def project_dir():
    return Path(os.environ.get('CLAUDE_PROJECT_DIR') or Path(__file__).resolve().parents[2])


def venv_python():
    root = project_dir()
    for candidate in (root / '.venv' / 'Scripts' / 'python.exe', root / '.venv' / 'bin' / 'python'):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def state_dir():
    path = project_dir() / '.claude' / 'state'
    path.mkdir(parents=True, exist_ok=True)
    return path


def block(message):
    """Exit code 2 = блокировка; stderr уходит агенту."""
    print(message, file=sys.stderr)
    sys.exit(2)
