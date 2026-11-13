"""PreToolUse (Edit|Write): запрет записи в .env (кроме .env.example) и в закоммиченные миграции."""

import subprocess
import sys
from pathlib import Path

from _common import block, project_dir, read_payload


def is_tracked_by_git(path: Path) -> bool:
    try:
        result = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', str(path)], cwd=project_dir(), capture_output=True, text=True
        )
    except OSError:
        return True  # git недоступен — считаем файл защищённым
    return result.returncode == 0


def main():
    payload = read_payload()
    file_path = (payload.get('tool_input') or {}).get('file_path', '') or ''
    if not file_path:
        sys.exit(0)

    path = Path(file_path)
    name = path.name.lower()

    if name == '.env' or (name.startswith('.env.') and name != '.env.example'):
        block(
            f'ЗАБЛОКИРОВАНО хуком: запись в {path.name} запрещена (секреты). '
            'Добавь переменную в .env.example и mysite/config.py, а значение в .env впишет автор.'
        )

    parts = [p.lower() for p in path.parts]
    in_versions = any(parts[i] == 'migrations' and parts[i + 1] == 'versions' for i in range(len(parts) - 1))
    if in_versions and path.exists() and is_tracked_by_git(path):
        block(
            f'ЗАБЛОКИРОВАНО хуком: {path.name} — закоммиченная миграция, её нельзя менять. '
            'Создай новую миграцию: alembic revision --autogenerate -m "..."'
        )

    sys.exit(0)


if __name__ == '__main__':
    main()
