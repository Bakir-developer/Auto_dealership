---
name: alembic-migration
description: Применяй при любом изменении mysite/db/models.py и при работе с Alembic — создать миграцию autogenerate, проверить её содержимое, применить, откатить, убедиться что autogenerate видит все модели.
---

# Alembic-миграции

## Настройка (Этап 1)
- `alembic init migrations` в корне проекта → `alembic.ini` и `migrations/` в корне.
- `migrations/env.py`:
  ```python
  from mysite.config import DATABASE_URL
  from mysite.db.models import *  # noqa: F401,F403

  config = context.config
  config.set_main_option('sqlalchemy.url', DATABASE_URL)
  ...
  target_metadata = Base.metadata
  ```
- В `alembic.ini` `sqlalchemy.url` не хардкодить (оставить пустым — URL берётся из `.env`).
- Локально `DATABASE_URL=sqlite:///./auto_salon.db`,
  в docker — `sqlite:////app/data/auto_salon.db` (bind-mount `./data:/app/data`, файл `./data/auto_salon.db` на хосте).

## Создание
```bash
alembic revision --autogenerate -m "create car and deal tables"
```
Сообщение — по-английски, осмысленное, в нижнем регистре. Не оставляй пустое `-m ""`.

## Проверка сгенерированного файла (ОБЯЗАТЕЛЬНО прочитать)
- Все новые таблицы/колонки/FK/UniqueConstraint/индексы на месте.
- SQLite не умеет большинство `ALTER TABLE`: в `env.py` включён `render_as_batch=True`, изменения столбцов
  идут через `with op.batch_alter_table(...)`. Enum в SQLite — VARCHAR без CHECK (`create_constraint=False` по умолчанию), значения проверяет Pydantic.
- Новый NOT NULL столбец в таблице с данными → нужен `server_default` или двухшаговая миграция.
- Переименование autogenerate видит как drop+add — исправь вручную на `op.alter_column(..., new_column_name=...)`
  (данные иначе пропадут).
- Неотслеживаемую (ещё не закоммиченную) миграцию править можно. **Закоммиченную — нельзя** (хук заблокирует);
  нужна новая миграция поверх.

## Применение и откат
```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
alembic current
alembic history
```
В docker: `docker compose exec fast_web alembic upgrade head`.

## Проверка, что autogenerate видит всё
```bash
alembic revision --autogenerate -m "check empty"
```
Файл должен содержать только `pass` в upgrade/downgrade → удали его. Если там есть операции —
модели и миграции рассинхронизированы (не импортирована модель, забыт столбец) → исправь.

## Запрещено
`DROP TABLE/DATABASE`, `TRUNCATE`, `docker compose down -v`, `docker volume rm` (хуки заблокируют),
`alembic stamp` без согласования с автором, правка закоммиченных миграций.
