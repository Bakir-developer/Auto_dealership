"""PostToolUse (Edit|Write): black + isort на изменённом .py, затем flake8. Ошибки flake8 -> агенту."""

import subprocess
import sys
from pathlib import Path

from _common import block, project_dir, read_payload, state_dir, venv_python

SKIP_PARTS = {'.venv', 'venv', '.claude', '.git'}


def run(args):
    return subprocess.run(
        [venv_python(), '-m', *args],
        cwd=project_dir(),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )


def main():
    payload = read_payload()
    file_path = (payload.get('tool_input') or {}).get('file_path', '') or ''
    path = Path(file_path)
    if path.suffix != '.py' or not path.exists() or SKIP_PARTS & set(path.parts):
        sys.exit(0)
    if not path.resolve().is_relative_to(project_dir().resolve()):
        sys.exit(0)  # файлы вне проекта не трогаем

    session_id = payload.get('session_id') or 'default'
    (state_dir() / f'py_changed_{session_id}').touch()

    missing = []
    for tool in ('black', 'isort'):
        result = run([tool, '-q', str(path)])
        if 'No module named' in result.stderr:
            missing.append(tool)

    result = run(['flake8', str(path)])
    if 'No module named' in result.stderr:
        missing.append('flake8')
    elif result.returncode != 0:
        block(f'flake8 нашёл проблемы в {path.name} — исправь:\n{result.stdout.strip()}')

    if missing:
        print(
            f'Внимание: не установлены {", ".join(missing)} в .venv — форматирование/линт пропущены.', file=sys.stderr
        )
    sys.exit(0)


if __name__ == '__main__':
    main()
