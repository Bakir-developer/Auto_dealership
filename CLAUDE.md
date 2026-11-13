# CLAUDE.md — FastAPI Auto Salon

Бэкенд (REST API) одного автосалона в Кыргызстане: новые и б/у авто, CRM (заявки,
тест-драйвы), сделки с бронью и скидками, trade-in, отзывы. Онлайн-оплаты нет.
Отвечай пользователю на русском.

## Стек
FastAPI · синхронный SQLAlchemy 2.0 · PostgreSQL 17 · Alembic · Pydantic v2 ·
passlib/bcrypt · python-jose (JWT access + refresh) · sqladmin · Docker + docker-compose + nginx ·
pytest · black / isort / flake8.

## Главные документы
- **Стиль и структура — СТРОГО по `docs/STYLE_GUIDE.md`.** Не изобретай свою архитектуру,
  не добавляй слои `services/` / `repositories/`, не разбивай `models.py` и `schema.py` на файлы,
  не переходи на async SQLAlchemy.
- ТЗ — `docs/PROJECT_SPEC.md` (роли, модели, бизнес-правила).
- Этапы — `docs/ROADMAP.md`. Планы этапов — `docs/plans/`.

## ПРАВИЛО ЭТАПОВ (обязательно)
1. Работаем строго по **одному** этапу из `docs/ROADMAP.md`.
2. Делай **только** то, что входит в текущий этап. Не создавай файлы будущих этапов «заранее»
   (никаких пустых роутеров, заглушек, TODO-модулей).
3. Если для текущего этапа нужно что-то из будущего — остановись и спроси.
4. После этапа — отчёт и **ОСТАНОВКА** до подтверждения автора. Следующий этап сам не начинай.

## Структура (кратко, подробно — в STYLE_GUIDE)
```
main.py  alembic.ini  migrations/  Dockerfile  docker-compose.yml  nginx/  requirements.txt
mysite/config.py
mysite/db/{database.py, models.py, schema.py}
mysite/api/{auth.py, dependencies.py, <entity>.py}
mysite/admin/{setup.py, view.py}
tests/
```
Ключевое: `get_db` — один раз в `mysite/db/database.py`; приложение — `auto_app`;
роутеры — `<entity>_router` с путями `/create`, `/list`, `/detail`, `/update/{id}`, `/delete/{id}`;
`model_dump()` вместо `.dict()`; ошибки — `HTTPException` с текстом на русском.

## Окружение
- **Windows 11 + PyCharm.** Виртуальное окружение: `.venv` (`.venv\Scripts\python.exe`).
- Shell-инструменты: Bash (Git Bash) и PowerShell. Пути в командах — через `/` или в кавычках.
- В PowerShell 5.1 нет `&&` — используй `;` или `if ($?) { ... }`.
- Предпочитай `python -m <tool>` (работает без активации venv):
  `.venv/Scripts/python.exe -m pytest -q`.

## Команды
| Задача | Команда |
|---|---|
| Запуск | `docker compose up --build` |
| Логи | `docker compose logs -f fast_web` |
| Новая миграция | `alembic revision --autogenerate -m "описание"` |
| Применить | `alembic upgrade head` |
| Откатить одну | `alembic downgrade -1` |
| Миграции в docker | `docker compose exec fast_web alembic upgrade head` |
| Тесты | `pytest -q` |
| Форматирование | `black . && isort .` (PowerShell: `black .; isort .`) |
| Линтер | `flake8` |
| Локальный сервер | `uvicorn main:auto_app --reload` |

## Агенты (`.claude/agents/`)
explorer (поиск), architect (план этапа → `docs/plans/`), coder (код), db-specialist (модели и
миграции), tester (pytest), reviewer (ревью diff), security-auditor (безопасность),
debugger (баги). Каждый агент первым делом читает этот файл и `docs/STYLE_GUIDE.md`.

## Команды Claude (`.claude/commands/`)
- `/stage <N>` — выполнить этап N: architect → coder/db-specialist → tester →
  reviewer + security-auditor → исправления → отчёт → СТОП.
- `/crud <сущность>` — CRUD-роутер по skill `crud-router`.
- `/review` — reviewer + security-auditor по текущему `git diff`.
- `/fix <описание>` — debugger → tester → reviewer.
- `/plan <описание>` — только architect.

## Skills (`.claude/skills/`)
`my-style`, `crud-router`, `alembic-migration`, `testing`.

## Хуки (`.claude/hooks/`, работают автоматически)
- Блокируются: `rm -rf`, `DROP TABLE/DATABASE/SCHEMA`, `TRUNCATE`, `docker volume rm/prune`,
  `docker compose down -v`, git-команды, меняющие историю/remote, и `gh`.
- Запрещена запись в `.env` (кроме `.env.example`) и правка **закоммиченных** файлов
  `migrations/versions/` (новую ещё не закоммиченную миграцию править можно).
- После правки `.py` — автоматически black + isort, затем flake8 (ошибки вернутся агенту — исправь).
- При завершении ответа, если менялись `.py` и есть `tests/` — `pytest -q -x`; падение = доработать.

## Git — СТРОГО
- Агент **НЕ делает коммиты**, не делает push/pull/fetch/merge/rebase/reset/checkout/switch/
  branch/tag/stash, не трогает remote и **не работает с GitHub** (`gh` запрещён).
  GitHub MCP **не подключать**.
- Разрешено только читать: `git status`, `git diff`, `git log`, `git show`.
- В конце этапа выдай: список изменённых/созданных файлов и **предложенное сообщение коммита**
  в формате Conventional Commits, например:
  `feat(db): add models, schemas and initial migration (stage 1)`.
- Коммит и push автор делает **вручную**.

## Безопасность
- Никогда не читай и не выводи содержимое `.env`. Секреты — только через `mysite/config.py`.
- В схемах ответа нет `password`/токенов. Пароли — только bcrypt-хеш.
- Client видит только свои объекты (чужой → 404); seller — только свои заявки/сделки.
- Только ORM / параметризованные запросы, никаких f-строк в SQL.

## Определение «готово» (Definition of Done)
- [ ] Код строго в стиле `docs/STYLE_GUIDE.md`, в рамках текущего этапа.
- [ ] `black --check .`, `isort --check-only .`, `flake8` — чисто.
- [ ] `pytest -q` — зелёный (если тесты есть).
- [ ] Миграции применяются (`upgrade head`) и откатываются (`downgrade -1`).
- [ ] Ревью (reviewer + security-auditor) пройдено, 🔴 critical исправлены.
- [ ] `docs/ROADMAP.md` — чекбоксы этапа отмечены.
- [ ] Отчёт: что сделано, список файлов, предложенный коммит. Затем СТОП.
