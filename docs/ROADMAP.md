# ROADMAP

Работаем строго по одному этапу. Следующий этап начинается только после подтверждения автора.
Отмечайте `[x]` по мере выполнения.

**Текущий этап:** Этап 4 завершён (CRM) → следующий: **Этап 5** (ждёт подтверждения).

---

## Этап 0 — Харнес Claude Code ✅
- [x] CLAUDE.md, docs/ (STYLE_GUIDE, PROJECT_SPEC, ROADMAP)
- [x] .claude/agents, skills, commands, hooks, settings.json
- [x] .gitignore, pyproject.toml, .flake8

## Этап 1 — Фундамент
Модели, схемы, база данных, настройки FastAPI, библиотеки. БЕЗ роутеров, Docker и бизнес-логики.
База — SQLite (файл `auto_salon.db` в корне, в git не попадает).
- [x] `requirements.txt` + установка в `.venv`
- [x] `.env`, `.env.example`, `.gitignore`
- [x] `mysite/__init__.py`, `mysite/db/__init__.py`, `mysite/config.py`
- [x] минимальный `main.py` (`auto_app`, CORS, `GET /health`)
- [x] `mysite/db/database.py` (engine, SessionLocal, Base, get_db)
- [x] `mysite/db/models.py` — все Enum и все модели из ТЗ
- [x] `mysite/db/schema.py` — все схемы
- [x] `alembic.ini`, `migrations/env.py`
- [x] БД SQLite `auto_salon.db`, миграция `initial` (upgrade head → downgrade base → upgrade head)
- [x] black / isort / flake8 чисто, `/health` и `/docs` работают, ревью пройдено

## Этап 2 — Docker, Auth и роли
- [x] `Dockerfile`, `docker-compose.yml` (fast_web + `./data` для `auto_salon.db`, nginx)
- [x] `nginx/Dockerfile`, `nginx/nginx.conf`
- [x] `api/auth.py` (register → только client, login, logout, access_generate)
- [x] `api/dependencies.py` (get_current_user, require_role)
- [x] `api/user.py` (профиль; админ: продавцы, блокировка, лимит скидки)
- [x] `admin/setup.py`, `admin/view.py` (sqladmin)
- [x] seed-скрипт первого админа (+ SalonSettings)
- [x] тесты auth и ролей

## Этап 3 — Справочники и авто
- [x] `api/brand.py`
- [x] `api/car_model.py`
- [x] `api/car.py` — каталог (без входа), фильтры, пагинация, история цен, мягкое удаление,
      правила new/used
- [x] `api/car_image.py`
- [x] тесты

## Этап 4 — CRM
- [x] `api/lead.py` (+ LeadNote; seller — только свои)
- [x] `api/test_drive.py` (рабочие часы, пересечения, статусы авто, не в прошлое)
- [x] `api/notification.py`
- [x] тесты

## Этап 5 — Продажи
- [ ] `api/deal.py` — машина состояний (409), final_price на сервере, мягкое удаление
- [ ] `api/discount.py` — лимит продавца, DiscountRequest, решение админа
- [ ] бронь атомарным `UPDATE ... WHERE status='available'` (rowcount 0 → 409) + фоновая задача истечения брони
- [ ] AuditLog для важных действий
- [ ] тесты

## Этап 6 — Остальное
- [ ] `api/trade_in.py` (+ TradeInImage)
- [ ] `api/favorite.py`
- [ ] `api/review.py` (только после delivered, один на сделку)
- [ ] `api/credit.py` (кредитный калькулятор, сравнение до 4 авто)
- [ ] `api/statistic.py` (админ — общая, seller — своя)
- [ ] тесты
