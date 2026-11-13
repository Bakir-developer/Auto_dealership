"""Stop: если есть tests/ и в сессии менялись .py — pytest -q -x. Падение -> exit 2 (агент продолжает)."""

import subprocess
import sys

from _common import block, project_dir, read_payload, state_dir, venv_python


def main():
    payload = read_payload()
    if payload.get('stop_hook_active'):
        sys.exit(0)  # уже продолжаем из-за этого хука — не зацикливаемся

    if not (project_dir() / 'tests').is_dir():
        sys.exit(0)

    marker = state_dir() / f'py_changed_{payload.get("session_id") or "default"}'
    if not marker.exists():
        sys.exit(0)

    result = subprocess.run(
        [venv_python(), '-m', 'pytest', '-q', '-x'],
        cwd=project_dir(),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    # 0 — всё прошло, 5 — тестов нет
    if result.returncode in (0, 5):
        marker.unlink(missing_ok=True)
        sys.exit(0)
    if 'No module named pytest' in result.stderr:
        sys.exit(0)

    tail = '\n'.join((result.stdout + result.stderr).strip().splitlines()[-40:])
    block(f'pytest упал после изменений .py — разберись (не подгоняй тест под баг):\n{tail}')


if __name__ == '__main__':
    main()
