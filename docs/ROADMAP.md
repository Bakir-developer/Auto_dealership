# ROADMAP

Работаем строго по одному этапу. Следующий этап начинается только после подтверждения автора.
Отмечайте `[x]` по мере выполнения.

**Текущий этап:** Этап 0 (харнес) завершён → следующий: **Этап 1**.

---

## Этап 0 — Харнес Claude Code ✅
- [x] CLAUDE.md, docs/ (STYLE_GUIDE, PROJECT_SPEC, ROADMAP)
- [x] .claude/agents, skills, commands, hooks, settings.json
- [x] .gitignore, pyproject.toml, .flake8

## Этап 1 — Фундамент
Модели, схемы, база данных, настройки FastAPI, библиотеки. БЕЗ роутеров, Docker и бизнес-логики.
Локальный PostgreSQL (без Docker).
- [x] `requirements.txt` + установка в `.venv`
- [x] `.env`, `.env.example`, `.gitignore`
- [x] `mysite/__init__.py`, `mysite/db/__init__.py`, `mysite/config.py`
- [x] минимальный `main.py` (`auto_app`, CORS, `GET /health`)
- [x] `mysite/db/database.py` (engine, SessionLocal, Base, get_db)
- [x] `mysite/db/models.py` — все Enum и все модели из ТЗ
- [x] `mysite/db/schema.py` — все схемы
- [x] `alembic.ini`, `migrations/env.py`
- [ ] БД `auto_salon_db`, миграция `initial` (upgrade head → downgrade base → upgrade head)
      — ⏳ ждём пароль PostgreSQL в `.env`
- [x] black / isort / flake8 чисто, `/health` и `/docs` работают, ревью пройдено

## Этап 2 — Docker, Auth и роли
- [ ] `Dockerfile`, `docker-compose.yml` (fast_web, fast_db, nginx)
- [ ] `nginx/Dockerfile`, `nginx/nginx.conf`
- [ ] `api/auth.py` (register → только client, login, logout, access_generate)
- [ ] `api/dependencies.py` (get_current_user, require_role)
- [ ] `api/user.py` (профиль; админ: продавцы, блокировка, лимит скидки)
- [ ] `admin/setup.py`, `admin/view.py` (sqladmin)
- [ ] seed-скрипт первого админа (+ SalonSettings)
- [ ] тесты auth и ролей

## Этап 3 — Справочники и авто
- [ ] `api/brand.py`
- [ ] `api/car_model.py`
- [ ] `api/car.py` — каталог (без входа), фильтры, пагинация, история цен, мягкое удаление,
      правила new/used
- [ ] `api/car_image.py`
- [ ] тесты

## Этап 4 — CRM
- [ ] `api/lead.py` (+ LeadNote; seller — только свои)
- [ ] `api/test_drive.py` (рабочие часы, пересечения, статусы авто, не в прошлое)
- [ ] `api/notification.py`
- [ ] тесты

## Этап 5 — Продажи
- [ ] `api/deal.py` — машина состояний (409), final_price на сервере, мягкое удаление
- [ ] `api/discount.py` — лимит продавца, DiscountRequest, решение админа
- [ ] бронь с `SELECT ... FOR UPDATE` + фоновая задача истечения брони
- [ ] AuditLog для важных действий
- [ ] тесты

## Этап 6 — Остальное
- [ ] `api/trade_in.py` (+ TradeInImage)
- [ ] `api/favorite.py`
- [ ] `api/review.py` (только после delivered, один на сделку)
- [ ] `api/credit.py` (кредитный калькулятор, сравнение до 4 авто)
- [ ] `api/statistic.py` (админ — общая, seller — своя)
- [ ] тесты
