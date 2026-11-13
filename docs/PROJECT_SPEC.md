# Техническое задание — Бэкенд автосалона

## 1. Контекст

- Один автосалон, Кыргызстан. Продаются **новые и б/у** автомобили.
- Только бэкенд (REST API). Фронтенда в этом проекте нет.
- **Онлайн-оплаты нет** — продавец вручную отмечает факт оплаты в сделке.
- Валюта: `KGS` по умолчанию; у авто и сделки есть поле `currency` (`KGS` | `USD`).
- Деньги — `Numeric(14, 2)`.
- Телефон — формат `+996XXXXXXXXX`.
- Время в БД — **UTC**. Часовой пояс салона — `Asia/Bishkek` (рабочие часы, тест-драйвы считаются в нём).
- Ошибки для пользователя — **на русском**.

## 2. Стек

FastAPI, синхронный SQLAlchemy 2.0, SQLite, Alembic, Pydantic v2, passlib/bcrypt,
python-jose (JWT access + refresh), sqladmin, Docker + docker-compose + nginx, pytest.

## 3. Роли

### admin
- Управляет продавцами: создать, заблокировать (`is_active=False`), установить лимит скидки.
- Справочники: марки, модели.
- Видит и меняет всё.
- Подтверждает/отклоняет скидки выше лимита продавца.
- Настройки салона (`SalonSettings`).
- Аналитика.
- Журнал действий (`AuditLog`).
- Первый админ создаётся **seed-скриптом**.

### seller
- Добавляет/редактирует авто и фото.
- Меняет цену — изменение пишется в `PriceHistory`.
- Берёт заявки в работу, пишет заметки по клиенту (`LeadNote`).
- Тест-драйвы.
- Создаёт сделки, бронирует, отмечает оплату и выдачу.
- Скидка до своего `discount_limit`; выше — запрос админу (`DiscountRequest`).
- Своя статистика.
- Работает **только со СВОИМИ** заявками/сделками.
- Продавцов создаёт только админ.

### client
- Регистрация (открытая регистрация — **только** для роли client).
- Каталог (доступен и **без входа**).
- Избранное.
- Сравнение — до 4 авто.
- Запись на тест-драйв.
- Заявка на покупку.
- Trade-in.
- Кредитный калькулятор.
- Отзыв после завершённой сделки.
- Видит **ТОЛЬКО свои** объекты; чужой объект → **404** (не 403, чтобы не раскрывать существование).

## 4. Модели (все — в `mysite/db/models.py`)

### 4.1 Enum

| Enum | Значения |
|---|---|
| UserRole | admin, seller, client |
| CarCondition | new, used |
| CarStatus | in_transit, available, reserved, sold, withdrawn |
| BodyType | sedan, hatchback, suv, crossover, coupe, minivan, pickup, wagon, other |
| FuelType | petrol, diesel, hybrid, electric, gas |
| Transmission | manual, automatic, robot, cvt |
| DriveType | front, rear, full |
| Steering | left, right |
| Currency | KGS, USD |
| LeadType | purchase, test_drive, trade_in, question |
| LeadStatus | new, in_progress, closed, rejected |
| TestDriveStatus | scheduled, confirmed, completed, cancelled |
| DealStatus | new, in_progress, reserved, paid, delivered, cancelled |
| DiscountStatus | pending, approved, rejected |
| TradeInStatus | new, evaluating, offered, accepted, rejected |
| NotificationType | lead, test_drive, deal, discount, reservation, system |

### 4.2 Таблицы

**UserProfile** (`user_profile`): first_name, last_name, username (unique), email (unique),
phone_number (default `'+996'`), profile_image, role, password, is_active,
discount_limit (`Numeric(5,2)`, default 0 — для seller), created_at.

**RefreshToken**: user_id, token.

**Brand**: brand_name (unique), brand_logo.

**CarModel**: brand_id, model_name (unique вместе с brand_id).

**Car**: vin (unique, 17 символов), brand_id, car_model_id, year, body_type, color,
engine_volume, fuel_type, transmission, drive_type, steering, condition, status,
price, currency, description, mileage (default 0), owners_count, has_accidents,
accident_notes, customs_cleared, registered_in_kr, created_by_id,
created_at, updated_at, deleted_at.

**CarImage**: car_id, car_image, is_main, position.

**PriceHistory**: car_id, old_price, new_price, changed_by_id, changed_at.

**Lead**: client_id, car_id (nullable), lead_type, status, seller_id (nullable), comment, created_at.

**LeadNote**: lead_id, seller_id, note, created_at.

**TestDrive**: car_id, client_id, seller_id (nullable), start_time, end_time, status, created_at.

**Deal**: car_id, client_id, seller_id, base_price, discount_percent, final_price, currency,
status, reserved_until, paid_at, delivered_at, cancel_reason, created_at, deleted_at.

**DiscountRequest**: deal_id, seller_id, requested_percent, status, decided_by_id, decided_at, comment.

**TradeIn**: client_id, brand_name, model_name, year, mileage, description,
estimated_price, currency, status, seller_id (nullable), created_at.

**TradeInImage**: trade_in_id, trade_in_image.

**Favorite**: user_id, car_id (unique вместе).

**Review**: client_id, deal_id (unique), seller_id, stars (1–5), comment, created_at.

**Notification**: user_id, notification_type, text, is_read, created_at.

**AuditLog**: user_id, action, entity_name, entity_id, old_value (JSON), new_value (JSON), created_at.

**SalonSettings** (одна запись): salon_name, address, phone_number, work_start, work_end,
test_drive_minutes (60), reservation_hours (48), default_discount_limit (3).

## 5. Бизнес-правила

1. **Статусы сделки — машина состояний:**
   `new → in_progress → reserved → paid → delivered`;
   из любого статуса, кроме `delivered`, → `cancelled`.
   Недопустимый переход → **409**.
2. **Двойная бронь невозможна** — в SQLite нет блокировки строк, поэтому смена статуса авто на
   `reserved` — одним атомарным `UPDATE car SET status='reserved' WHERE id=:id AND status='available'`;
   `rowcount == 0` → **409** «Авто уже забронировано».
3. **Истечение брони:** через `reservation_hours` без оплаты → сделка `cancelled`,
   авто `available`, уведомления продавцу и клиенту. Реализация — фоновая задача
   (по образцу `game_scheduler` из mafia_app).
4. **Тест-драйвы:** только в рабочие часы салона (`work_start`–`work_end`, Asia/Bishkek),
   без пересечений по авто и по продавцу, не на `reserved`/`sold` авто, не в прошлое.
   Длительность — `test_drive_minutes`.
5. **Скидка:** `<= discount_limit` продавца — применяется сразу;
   больше — создаётся `DiscountRequest` админу (`pending`).
6. **`final_price` считает сервер** (`base_price * (1 - discount_percent / 100)`), клиент его не передаёт.
7. Изменение цены авто → запись в `PriceHistory`. Важные действия → `AuditLog`.
8. **Мягкое удаление** (`deleted_at`) для `Car` и `Deal`; удалённые не попадают в выборки.
9. Для `used` обязательны поля б/у (mileage, owners_count, has_accidents, ...);
   для `new` — `mileage = 0`.
10. **Отзыв** — только после сделки в статусе `delivered`, один на сделку.

## 6. Нефункциональные требования

- Структура и стиль кода — строго `docs/STYLE_GUIDE.md`.
- Секреты — только в `.env` (не в git); в репозитории — `.env.example`.
- Пароли — bcrypt-хеш; в ответах API пароль и токены из БД не возвращаются.
- Все списки с пагинацией (`skip`/`limit`) там, где данных может быть много (каталог, заявки, сделки).
- Каталог: фильтры по марке, модели, году, цене, состоянию, кузову, топливу, КПП, приводу, статусу.
  Поиск без учёта регистра по кириллице в SQLite (`ilike`, `lower()`) работает только для латиницы —
  для текстовых фильтров нормализовать регистр в Python или хранить отдельное поле в нижнем регистре.

## 7. База данных — SQLite

- Файл `auto_salon.db` (в Docker — `./data/auto_salon.db`). Отдельного сервера БД нет.
- Внешние ключи включаются `PRAGMA foreign_keys=ON` при каждом подключении.
- **Деньги:** `Numeric(14, 2)`, проценты `Numeric(5, 2)`; все расчёты (скидки, `final_price`,
  кредитный калькулятор) — только через `Decimal`, без `float`.
- **Время:** хранится в UTC; текущее время — `datetime.now(timezone.utc)` в Python. SQLite возвращает
  naive datetime — перед сравнением приводить к UTC. На часовые пояса БД не полагаться.
  При записи tzinfo отбрасывается без перевода — входящие datetime (тест-драйв, бронь) сначала
  переводить в UTC (`astimezone(timezone.utc)`); naive datetime от клиента → 422.
- **Enum:** в SQLite хранится как строка (VARCHAR); допустимые значения проверяют Pydantic-схемы
  (CHECK в БД нет).
- **JSON** вместо `JSONB` (поля `old_value` / `new_value` в `AuditLog`).
- Запись — по одной транзакции за раз: uvicorn без `--workers`.
