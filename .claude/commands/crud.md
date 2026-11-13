---
description: Создать CRUD-роутер mysite/api/<entity>.py в стиле автора (skill crud-router) и подключить в main.py
argument-hint: <сущность, например brand или car_model>
---

Создай CRUD-роутер для сущности **$ARGUMENTS** по skill `crud-router`.

1. Прочитай `CLAUDE.md`, `docs/STYLE_GUIDE.md`, `docs/ROADMAP.md`.
2. Проверь, что `$ARGUMENTS` входит в текущий этап. Если нет — остановись и скажи об этом.
3. Проверь, что модель есть в `mysite/db/models.py`. Если нет — остановись (нужен db-specialist).
4. Через агента **coder**: схемы в `mysite/db/schema.py` (если их нет), файл `mysite/api/$ARGUMENTS.py`,
   права по `docs/PROJECT_SPEC.md`, подключение в `main.py`.
5. Через агента **tester**: тесты `tests/test_$ARGUMENTS.py`, прогон `pytest -q`.
6. Через агента **reviewer**: короткое ревью созданного.

Отчёт: файлы, эндпоинты (метод, путь, роли), результат тестов, замечания. Не коммить.
