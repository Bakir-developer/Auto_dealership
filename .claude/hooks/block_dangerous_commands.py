"""PreToolUse (Bash|PowerShell): блокирует разрушительные команды и git/gh-операции, меняющие историю."""

import re
import sys

from _common import block, read_payload

DANGEROUS = [
    (r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b', 'rm -rf'),
    (r'\brm\s+(-\w+\s+)*--recursive\b.*--force|\brm\s+(-\w+\s+)*--force\b.*--recursive', 'rm --recursive --force'),
    (r'\brm\s+-r\s+-f\b|\brm\s+-f\s+-r\b', 'rm -r -f'),
    (r'remove-item\b(?=.*-recurse)(?=.*-force)', 'Remove-Item -Recurse -Force'),
    (r'\brd\s+/s\b|\brmdir\s+/s\b', 'rmdir /s'),
    (r'\bdrop\s+(table|database|schema)\b', 'DROP TABLE/DATABASE/SCHEMA'),
    (r'\btruncate\s+(table\s+)?["\w]', 'TRUNCATE'),
    (r'\bdocker\s+volume\s+(rm|prune)\b', 'docker volume rm/prune'),
    (r'\bdocker\s+system\s+prune\b.*--volumes', 'docker system prune --volumes'),
    (r'\bdocker[\s-]compose\s+down\b.*(\s-v\b|--volumes)', 'docker compose down -v'),
    (
        r'\b(rm|del|erase|unlink|remove-item|ri|mv|move|move-item)\b[^;&|\n]*\.(db|sqlite3?|db-journal)\b',
        'удаление/перемещение файла БД SQLite (*.db, *.sqlite3)',
    ),
]

GIT_FORBIDDEN = (
    'push',
    'pull',
    'fetch',
    'remote',
    'commit',
    'merge',
    'rebase',
    'reset',
    'checkout',
    'switch',
    'branch',
    'tag',
    'stash',
    'clean',
    'restore',
    'cherry-pick',
    'revert',
    'am',
)


def main():
    payload = read_payload()
    command = (payload.get('tool_input') or {}).get('command', '') or ''
    lowered = command.lower()

    for pattern, name in DANGEROUS:
        if re.search(pattern, lowered):
            block(
                f'ЗАБЛОКИРОВАНО хуком: опасная команда ({name}). '
                'Если это действительно нужно — попроси автора выполнить её вручную.'
            )

    git_pattern = r'(^|[\s;&|(])git(\.exe)?\s+(-c\s+\S+\s+|-C\s+\S+\s+)*(' + '|'.join(GIT_FORBIDDEN) + r')\b'
    match = re.search(git_pattern, lowered)
    if match:
        block(
            f'ЗАБЛОКИРОВАНО хуком: git {match.group(4)} запрещён. Агент не меняет историю git и не работает '
            'с remote. Разрешено: git status / diff / log / show. Коммит делает автор вручную.'
        )

    if re.search(r'(^|[\s;&|(])gh(\.exe)?\s', lowered + ' '):
        block('ЗАБЛОКИРОВАНО хуком: GitHub CLI (gh) запрещён в этом проекте.')

    sys.exit(0)


if __name__ == '__main__':
    main()
