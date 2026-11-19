# План: Этап 5 — Продажи (сделки, скидки, бронь, AuditLog)

> Тест-драйвы удалены из проекта по решению автора (миграция `610fbbdbd05f_remove_test_drive`). Не упоминать и не
> возвращать.

## Открытые вопросы (блокирующие)

Нет. Всё, что помечено **[дефолт]**, — решение архитектора по умолчанию; автор может переопределить
(сводка неблокирующих вопросов — в разделе «Риски и открытые вопросы»).

---

## Цель и границы

Цель: продажи — сделка (`Deal`) с машиной состояний и серверным расчётом `final_price`, бронь авто атомарным
`UPDATE`, фоновая отмена просроченной брони, скидки (лимит продавца → сразу; выше → `DiscountRequest` админу),
журнал важных действий (`AuditLog`), уведомления типов `deal` / `discount` / `reservation`, тесты.

Границы:
- Новые файлы в `mysite/` — **только** `mysite/api/deal.py` и `mysite/api/discount.py` (ROADMAP).
  Никаких `audit.py`, `scheduler.py`, `utils.py`, `services/`. Вспомогательные функции — внутри `deal.py`
  (`create_audit_log`, `calc_final_price`, `expire_reservations` и т.д.), `discount.py` импортирует их из `deal.py`
  (`deal.py` **не** импортирует `discount.py` — без циклического импорта).
- Фоновая задача `reservation_scheduler` — в `main.py` (STYLE §9), тело — синхронная `expire_reservations(db)` в `deal.py`.
- **Изменений моделей нет. Миграции нет** (обоснование — в разделе «Модели»).
- Ничего из этапа 6 (trade_in, favorite, review, credit, statistic).

Текущее состояние (проверено):
- `models.py`: `Deal` (car/client/seller FK + индексы, `status` индекс, `reserved_until`, `paid_at`, `delivered_at`,
  `cancel_reason`, `deleted_at`, CHECK: `base_price > 0`, `final_price > 0`, `0 <= discount_percent <= 100`,
  `final_price <= base_price`), `DiscountRequest` (`deal_id` индекс, `seller_id`, `requested_percent` CHECK `> 0 AND <= 100`,
  `status`, `decided_by_id`, `decided_at`, `comment`; **нет `created_at`**), `AuditLog` (`user_id` nullable, `action String(50)`,
  `entity_name String(50)`, `entity_id`, `old_value/new_value JSON`, `created_at`), `UserProfile.discount_limit Numeric(5,2)`,
  `SalonSettings.reservation_hours` (48) / `default_discount_limit` (3), `NotificationType.deal/discount/reservation`.
  Связи двусторонние (`Deal.client/seller` с `foreign_keys`, `DiscountRequest.seller/decided_by` с `foreign_keys`).
- `schema.py`: `Deal*`, `DiscountRequest*`, `AuditLog*` есть (заготовки этапа 1, требуют правок), типы `Money`, `Percent`,
  `Text2000`, `UtcDatetime`, `UtcDatetimeOut`.
- `car.py`: `get_car_or_404`, `ManualCarStatus` запрещает ручную установку `reserved`/`sold`; `update_car` — 409 на смену
  статуса у `reserved` и на любые правки `sold`; `delete_car` — 409 для `reserved`.
- `notification.py`: `create_notification` (без commit, неактивным не шлёт), `notify_active_sellers`.
- `lead.py`: образец атомарного условного `UPDATE` (`take`), видимость через `visible_*_query`, чужое → 404.
- `user.py`: `PUT /user/discount-limit/{user_id}` (admin, только seller).
- `conftest.py`: `db`, `client`, `make_user`, `auth_headers`, `admin`, `seller`, `client_user`, `make_car`, `salon_settings`,
  `admin_session_local` (+ кортеж view-классов), pysqlite-обход для SAVEPOINT.
- Alembic head: `610fbbdbd05f`.

---

## Файлы (создать / изменить)

### Создать
| Путь | Что |
|---|---|
| `mysite/api/deal.py` | `deal_router` (`prefix='/deal'`, `tags=['Deal']`) + функции: `get_deal_or_404`, `visible_deals_query`, `calc_final_price`, `to_audit_value`, `create_audit_log`, `change_deal_status`, `release_car`, `reject_pending_discounts`, `cancel_deal_internal`, `expire_reservations`, `get_reservation_hours`. |
| `mysite/api/discount.py` | `discount_router` (`prefix='/discount'`, `tags=['DiscountRequest']`). |
| `tests/test_deal.py`, `tests/test_discount.py`, `tests/test_reservation.py`, `tests/test_audit_log.py` | тесты. |

### Изменить
| Путь | Что |
|---|---|
| `mysite/config.py` | `RESERVATION_CHECK_SECONDS = int(os.getenv('RESERVATION_CHECK_SECONDS', 60))`, `RESERVATION_SCHEDULER_ENABLED = os.getenv('RESERVATION_SCHEDULER_ENABLED', 'true').lower() == 'true'`. |
| `.env.example` | две новые переменные (без секретов). |
| `mysite/db/schema.py` | правки `Deal*`, `DiscountRequest*`, `AuditLog*` (см. «Схемы»); новые `DealCancelSchema`, `DiscountRequestDecisionSchema`, тип `DiscountPercent`. |
| `mysite/api/notification.py` | новая функция `notify_active_admins(db, notification_type, text, exclude_user_id=None)` (по образцу `notify_active_sellers`). |
| `mysite/api/user.py` | `update_discount_limit` пишет `AuditLog` (`create_audit_log` из `deal.py`) **[дефолт]**. |
| `main.py` | `from mysite.api import ... deal, discount`; `include_router(deal.deal_router)`, `include_router(discount.discount_router)`; `reservation_scheduler()` + `lifespan` (см. «Фоновая задача»). |
| `mysite/admin/view.py` | `DealView`, `DiscountRequestView`, `AuditLogView` — только чтение. |
| `mysite/admin/setup.py` | `admin.add_view(...)` для трёх view. |
| `tests/conftest.py` | `os.environ['RESERVATION_SCHEDULER_ENABLED'] = 'false'` до импорта приложения; фикстуры `make_deal`, `make_discount_request`, `seller2`, `client2`; три новых view в кортеж `admin_session_local`. |
| `tests/test_admin.py` | списки и read-only для трёх новых view. |
| `docs/ROADMAP.md` | чекбоксы этапа 5, строка «Текущий этап». |

`mysite/api/car.py` — **не меняем** (уже защищает `reserved`/`sold` от ручных правок).

---

## Модели / поля / связи / ограничения

**Изменений моделей нет, миграции нет.** Всё нужное есть в `initial` (`f907a8edf483`).

Рассмотрено и осознанно **не добавляем** **[дефолт]**:
| Кандидат | Почему не нужно сейчас |
|---|---|
| `DiscountRequest.created_at` | сортировка списка — по `id.desc()` (autoincrement монотонен). Время решения — `decided_at`; время создания есть в `AuditLog`. |
| Частичный уникальный индекс «один `pending` на сделку» (`sqlite_where`) | проверка в коде; один воркер uvicorn и отсутствие `await` между проверкой и `commit` исключают гонку. |
| `DiscountRequest.decision_comment` | комментарий админа идёт в уведомление продавцу и в `AuditLog.new_value`; поле `comment` хранит обоснование продавца. Если автору нужно хранить отдельно — новая миграция (неблокирующий вопрос 3). |
| Индекс `deal.reserved_until` | фоновая выборка фильтрует по `status` (индекс есть) — броней единицы. |
| `Deal.updated_at`, `Deal.lead_id` | не требуются ТЗ. |

Используемые ограничения БД: CHECK `final_price > 0` и `final_price <= base_price` — страховка от ошибок расчёта
(на уровне API ловим заранее → 400).

---

## Время (UTC / SQLite)

- Текущее время — `datetime.now(timezone.utc)`. `reserved_until = now + timedelta(hours=reservation_hours)` — пишется
  из Python (aware UTC → SQLite хранит без смещения, но значение уже UTC).
- Сравнение в SQL (`Deal.reserved_until <= now`) — bind-параметр строго UTC (`datetime.now(timezone.utc)`).
- Сравнение в Python (проверка истечения в `pay`) — `deal_db.reserved_until.replace(tzinfo=timezone.utc)` если naive.
- В ответах все datetime сделки/скидки/журнала — `UtcDatetimeOut` (`...+00:00`).
- От клиента datetime на этом этапе не принимаются (срок брони считает сервер).
- Тексты уведомлений с датой — в UTC с пометкой `UTC` (формат `%d.%m.%Y %H:%M UTC`) **[дефолт]**: `zoneinfo('Asia/Bishkek')`
  на Windows требует пакет `tzdata`, которого нет в `requirements.txt` (неблокирующий вопрос 5).

---

## Деньги (Decimal)

```python
CENT = Decimal('0.01')

def calc_final_price(base_price: Decimal, discount_percent: Decimal) -> Decimal:
    return (base_price * (Decimal('100') - discount_percent) / Decimal('100')).quantize(CENT, rounding=ROUND_HALF_UP)
```
- Округление — `ROUND_HALF_UP` до копеек **[дефолт]** (пример: 100.30 × 5% → `95.285` → **95.29**; при HALF_EVEN было бы 95.28).
- `float` нигде; `discount_percent` из схемы — `Decimal` (Pydantic, `decimal_places=2`).
- Если результат `<= 0` → 400 `'Итоговая цена должна быть больше нуля'` (возможен лишь на копеечных ценах — защита от CHECK).
- `base_price = car.price`, `currency = car.currency` — **снимок на момент создания сделки** **[дефолт]**; последующее
  изменение цены авто сделку не меняет.

---

## Машина состояний сделки

```
new ──start──▶ in_progress ──reserve──▶ reserved ──pay──▶ paid ──deliver──▶ delivered
 │                 │                       │                │
 └──────cancel─────┴───────cancel──────────┴──cancel────────┘ ──▶ cancelled
                                           └──(истечение брони, система)──▶ cancelled
```

| Переход | Эндпоинт | Кто | Что с авто (`Car.status`) | Поля сделки | Доп. проверки / 409 |
|---|---|---|---|---|---|
| — → `new` | `POST /deal/create` | seller, admin | не меняется | `base_price`, `final_price = base_price`, `discount_percent = 0`, `currency` | авто: не удалено и `available`/`in_transit`, иначе 409 `'Автомобиль недоступен для сделки'`; дубль активной сделки клиент+авто → 409 |
| `new → in_progress` | `POST /deal/start/{deal_id}` | seller-владелец, admin | не меняется | — | |
| `in_progress → reserved` | `POST /deal/reserve/{deal_id}` | seller-владелец, admin | **атомарно** `available → reserved` | `reserved_until = now + reservation_hours` | `rowcount == 0` → 409 `'Авто уже забронировано'` (если авто `reserved`) / `'Автомобиль недоступен для брони'` (`in_transit`/`withdrawn`/`sold`/удалено) |
| `reserved → paid` | `POST /deal/pay/{deal_id}` | seller-владелец, admin | остаётся `reserved` | `paid_at = now` | есть `pending` `DiscountRequest` → 409 `'Есть нерассмотренный запрос на скидку'`; бронь истекла (`reserved_until <= now`) → сделка отменяется сразу (как фоновой задачей), commit, затем 409 `'Срок брони истёк'` **[дефолт]** |
| `paid → delivered` | `POST /deal/deliver/{deal_id}` | seller-владелец, admin | атомарно `reserved → sold` | `delivered_at = now` | `rowcount == 0` → 409 `'Некорректный статус автомобиля'`. Прочие активные сделки (`new`/`in_progress`) по этому авто → автоматически `cancelled` с причиной `'Автомобиль продан'` **[дефолт]** |
| `* → cancelled` (кроме `delivered`, `cancelled`) | `POST /deal/cancel/{deal_id}` | seller-владелец (из `new`/`in_progress`/`reserved`), admin (из любого, включая `paid`) **[дефолт]** | если сделка была `reserved`/`paid`: атомарно `reserved → available` | `cancel_reason` (обязателен), `reserved_until` не трогаем | seller отменяет `paid` → 403 `'Отменить оплаченную сделку может только администратор'` |
| `reserved → cancelled` | фоновая задача | система (`user_id=None`) | `reserved → available` | `cancel_reason = 'Срок брони истёк'` | |

Общее:
- Недопустимый переход (в т.ч. повтор, пропуск шага, из `delivered`/`cancelled`) → 409 `'Недопустимый переход статуса сделки'`.
- `DEAL_TRANSITIONS = {new: (in_progress, cancelled), in_progress: (reserved, cancelled), reserved: (paid, cancelled),
  paid: (delivered, cancelled)}`.
- Каждый переход — через `change_deal_status(db, deal_db, from_status, to_status, **fields)`: условный
  `db.query(Deal).filter(Deal.id == id, Deal.status == from_status, Deal.deleted_at.is_(None)).update({...}, synchronize_session=False)`;
  `rowcount == 0` → `db.rollback()` + 409. Затем `db.refresh(deal_db)`. Так переход защищён и от параллельного запроса,
  и от фоновой задачи.
- Бронь: `db.query(Car).filter(Car.id == car_id, Car.status == CarStatus.available, Car.deleted_at.is_(None))
  .update({'status': CarStatus.reserved}, synchronize_session=False)` — ORM, без f-строк. Обновление статуса авто и сделки —
  в одной транзакции; при 409 по авто — `rollback`, сделка остаётся `in_progress`.
- Освобождение (`release_car`): `UPDATE car SET status='available' WHERE id=:id AND status='reserved'` (если авто уже не
  `reserved` — ничего не делаем, не ошибка).
- При отмене (любой: ручной, истечение, «продано», удаление) — все `pending` `DiscountRequest` сделки → `rejected`,
  `decided_at = now`, `decided_by_id = current_user.id` (или `None` для системы), уведомление продавцу **[дефолт]**.

---

## Скидки

Единственная точка изменения скидки — `POST /discount/create` **[дефолт]** (в `DealCreateSchema` скидки нет — сделка
создаётся с 0%; `PUT /deal/update` нет — см. «Эндпоинты»). Так одна ветка кода и полная история скидок.

`POST /discount/create` (`deal_id`, `requested_percent`, `comment`):
1. Сделка видима и своя (seller) / любая (admin), иначе 404; статус `new`/`in_progress`/`reserved`, иначе 409
   `'Скидку можно изменить только до оплаты'`.
2. Есть `pending` по сделке → 409 `'По сделке уже есть запрос на скидку на рассмотрении'`.
3. `requested_percent == deal.discount_percent` → 400 `'Эта скидка уже применена'`.
4. Процент — **абсолютный** (заменяет текущий, не суммируется) **[дефолт]**; можно и уменьшить.
5. Расчёт `new_final = calc_final_price(base_price, requested_percent)`; `<= 0` → 400.
6. `seller_id` записи = `deal.seller_id` (для admin — тоже продавец сделки).
7. **Ветка «в пределах лимита»**: seller и `requested_percent <= current_user.discount_limit`, **или** admin (без лимита) →
   запись создаётся сразу `approved`, `decided_by_id = current_user.id`, `decided_at = now`; у сделки
   `discount_percent`, `final_price` обновляются; AuditLog `discount_apply`; уведомление клиенту (`deal`):
   `'Цена по сделке #<id> изменена: <final_price> <currency>'`. Ответ — `DiscountRequestDetailSchema` (`status=approved`).
   Самоодобрение отличимо: `decided_by_id == seller_id`.
8. **Ветка «выше лимита»** (seller): запись `pending`, сделка **не меняется**; AuditLog `discount_request`;
   уведомление всем активным админам (`discount`): `'Запрос скидки <p>% по сделке #<id> (продавец <username>)'`.
   Ответ — `DiscountRequestDetailSchema` (`status=pending`). HTTP 200 в обоих случаях — клиент различает по `status`.

Решение админа:
- `POST /discount/approve/{discount_request_id}` (admin): только `pending` (иначе 409 `'Запрос уже рассмотрен'`);
  сделка должна быть в `new`/`in_progress`/`reserved` и не удалена (иначе 409). Пересчёт `final_price` от `deal.base_price`.
  `status=approved`, `decided_by_id`, `decided_at`. AuditLog `discount_approve` (old/new `discount_percent`, `final_price`).
  Уведомления: продавцу (`discount`) `'Скидка <p>% по сделке #<id> одобрена'`, клиенту (`deal`) — новая цена.
- `POST /discount/reject/{discount_request_id}` (admin): только `pending`; `status=rejected`; сделка не меняется.
  AuditLog `discount_reject` (`new_value` содержит `comment` админа). Уведомление продавцу: `'Скидка <p>% по сделке #<id>
  отклонена[: <comment>]'`.
- Тело обоих — `DiscountRequestDecisionSchema` (`comment: Text2000 | None = None`), необязательное.

Сделка во время `pending`: движется по машине состояний (`start`, `reserve`, `cancel` разрешены), **`pay` запрещён** (409),
пока запрос не рассмотрен **[дефолт]** — иначе цена изменилась бы после оплаты. Бронь при этом продолжает истекать.

Повторные запросы: пока есть `pending` — 409; после `approved`/`rejected` — новый запрос разрешён (новая запись).

Отзыв: `DELETE /discount/delete/{discount_request_id}` — продавец-автор (или admin) удаляет **только `pending`**
(физически; решённые — история, не удаляются → 409 `'Рассмотренный запрос удалить нельзя'`) **[дефолт]**.
AuditLog `discount_withdraw` (с `old_value` записи).

Лимит продавца меняется через существующий `PUT /user/discount-limit/{user_id}`; уже созданные `pending` по старому
лимиту не пересматриваются автоматически **[дефолт]**.

---

## Схемы

Новый тип: `DiscountPercent = Annotated[Decimal, Field(gt=0, lt=100, max_digits=5, decimal_places=2)]`
(`lt=100` — иначе `final_price = 0` нарушит CHECK; 100% → 422) **[дефолт]**.

| Схема | Было | Станет |
|---|---|---|
| `DealCreateSchema` | `car_id`, `client_id`, `discount_percent` | `car_id: int`, `client_id: int`, `seller_id: int \| None = None` (учитывается **только** у admin; у seller игнорируется — `seller_id = current_user.id`). `discount_percent` **убрать**. |
| `DealUpdateSchema` | `discount_percent`, `cancel_reason` | **удалить** (эндпоинта update нет). |
| `DealCancelSchema` | — | **новая**: `cancel_reason: Text2000` (обязательна). |
| `DealListSchema` | `created_at: datetime` | + `discount_percent: Decimal`; `created_at: UtcDatetimeOut`. |
| `DealDetailSchema` | datetime-поля | `reserved_until`, `paid_at`, `delivered_at`: `UtcDatetimeOut \| None`; `created_at: UtcDatetimeOut`. Без `deleted_at`. |
| `DiscountRequestCreateSchema` | `requested_percent` (gt 0, le 100), `comment: str \| None` | `deal_id: int`, `requested_percent: DiscountPercent`, `comment: Text2000 \| None = None`. |
| `DiscountRequestUpdateSchema` | `status`, `comment` | **удалить** (решение — action-эндпоинтами). |
| `DiscountRequestDecisionSchema` | — | **новая**: `comment: Text2000 \| None = None`. |
| `DiscountRequestListSchema` | — | + `decided_by_id: int \| None`. |
| `DiscountRequestDetailSchema` | `decided_at: datetime \| None` | `decided_at: UtcDatetimeOut \| None`. |
| `AuditLogListSchema/DetailSchema` | `created_at: datetime` | `created_at: UtcDatetimeOut` (используются только если автор захочет API журнала; на этапе — для sqladmin не нужны, правка дешёвая). |

**Не принимаются от клиента** (берёт сервер): `Deal.seller_id` (у seller), `base_price`, `discount_percent`, `final_price`,
`currency`, `status`, `reserved_until`, `paid_at`, `delivered_at`, `deleted_at`; `DiscountRequest.seller_id`, `status`,
`decided_by_id`, `decided_at`; `AuditLog` — целиком сервер. Лишние поля Pydantic игнорирует — тесты это проверяют.

---

## Эндпоинты

Общие правила (как этап 4): `response_model` всегда; пагинация `skip: int = Query(0, ge=0)`, `limit: int = Query(20, ge=1, le=100)`;
401 — нет/плохой токен; 403 — роль (`'Недостаточно прав'`); **чужой объект → 404** для client и seller; 409 — переход/конфликт;
400 — некорректные данные; 422 — валидация. Мягко удалённые сделки не видит никто (в т.ч. admin) → 404.

### `deal_router` — `/deal`, `tags=['Deal']`

Видимость (`visible_deals_query(db, current_user)` → `get_deal_or_404`): всегда `Deal.deleted_at.is_(None)`;
admin — все; seller — `seller_id == me`; client — `client_id == me`. Иначе 404 `'Сделка не найдена'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /deal/create` | seller, admin | `DealCreateSchema` → `DealDetailSchema` | 403 client; 404 `'Автомобиль не найден'` (нет/удалён), 404 `'Клиент не найден'` (нет, не `client`, заблокирован), 404 `'Продавец не найден'` (admin: нет/не seller/заблокирован); 400 `'Укажите продавца'` (admin без `seller_id`); 409 `'Автомобиль недоступен для сделки'` (`reserved`/`sold`/`withdrawn`); 409 `'У клиента уже есть активная сделка по этому автомобилю'` (`new`/`in_progress`/`reserved`/`paid`) |
| `GET /deal/list` | все роли | `status`, `car_id`, `client_id` (staff), `seller_id` (только admin, иначе игнор), `skip`, `limit` → `List[DealListSchema]`, `order_by(created_at.desc(), id.desc())` | 401, 422 |
| `GET /deal/detail?deal_id=` | все роли | → `DealDetailSchema` | 401, 404 |
| `POST /deal/start/{deal_id}` | seller, admin | → detail | 403 client, 404, 409 |
| `POST /deal/reserve/{deal_id}` | seller, admin | → detail | 403, 404, 409 (переход / авто занято / авто недоступно) |
| `POST /deal/pay/{deal_id}` | seller, admin | → detail | 403, 404, 409 (переход / pending-скидка / бронь истекла) |
| `POST /deal/deliver/{deal_id}` | seller, admin | → detail | 403, 404, 409 |
| `POST /deal/cancel/{deal_id}` | seller, admin | `DealCancelSchema` → detail | 403 client / seller на `paid`; 404; 409 (`delivered`/`cancelled`); 422 без причины |
| `DELETE /deal/delete/{deal_id}` | admin | → `{'message': 'Сделка удалена'}` (мягкое: `deleted_at = now`) | 403, 404, 409 `'Удалить можно только новую или отменённую сделку'` |

Детали:
- **create**: `seller_id = current_user.id` (seller) или `deal_data.seller_id` (admin, проверка активного seller).
  `base_price = car.price`, `currency = car.currency`, `discount_percent = 0`, `final_price = base_price`, `status = new`.
  Авто: `get_car_or_404(car_id, db)` (staff-видимость), статус `available`/`in_transit` **[дефолт]** (сделка на авто «в пути» —
  предзаказ; бронь всё равно только для `available`). Несколько активных сделок разных клиентов на одно авто допустимы
  **[дефолт]** — гонку решает атомарная бронь. Уведомление клиенту (`deal`): `'Создана сделка #<id> по автомобилю #<car_id>'`;
  если создал admin — ещё продавцу `'Вам назначена сделка #<id>'`. AuditLog `deal_create`.
- **reserve**: `reservation_hours` — из `SalonSettings` (`id=1`); нет записи → 48 **[дефолт]**. Уведомление клиенту
  (`reservation`): `'Автомобиль по сделке #<id> забронирован до <dd.mm.yyyy HH:MM> UTC'`. AuditLog `deal_reserve`
  (`new_value`: `status`, `reserved_until`, `car_status`).
- **pay**: уведомление клиенту (`deal`) `'Оплата по сделке #<id> получена'`.
- **deliver**: уведомление клиенту (`deal`) `'Сделка #<id> завершена, автомобиль выдан'`; по авто-отменённым чужим сделкам —
  их клиентам и продавцам (`deal`) `'Сделка #<id> отменена: автомобиль продан'`.
- **cancel**: уведомление клиенту и продавцу (кроме инициатора) (`deal`) `'Сделка #<id> отменена: <reason>'`.
- **delete**: только `new`/`cancelled` (иначе авто осталось бы в `reserved`, а `delivered` нужен для отзывов этапа 6);
  `pending`-скидки → `rejected`. Уведомлений нет. AuditLog `deal_delete`.
- `PUT /deal/update/{id}` **не делаем** **[дефолт]**: все изменяемые поля сделки меняются только через действия
  (статус) или `/discount/create` (скидка). Ошибочную сделку — отменить и создать заново.

### `discount_router` — `/discount`, `tags=['DiscountRequest']`

Видимость (`get_discount_request_or_404`): join `Deal` с `Deal.deleted_at.is_(None)`; admin — все; seller —
`Deal.seller_id == me` (через сделку, а не `DiscountRequest.seller_id`, чтобы при будущей передаче сделки доступ шёл за ней);
client → 403 (скидочные переговоры — внутренние) **[дефолт]**. Иначе 404 `'Запрос на скидку не найден'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /discount/create` | seller, admin | `DiscountRequestCreateSchema` → `DiscountRequestDetailSchema` | 403 client; 404 `'Сделка не найдена'` (чужая/удалённая); 409 статус сделки / уже есть pending; 400 та же скидка / цена ≤ 0; 422 (0, 100, >2 знаков) |
| `GET /discount/list` | seller, admin | `status`, `deal_id`, `seller_id` (только admin), `skip`, `limit` → `List[DiscountRequestListSchema]`, `order_by(id.desc())` | 401, 403 client |
| `GET /discount/detail?discount_request_id=` | seller, admin | → detail | 403, 404 |
| `POST /discount/approve/{discount_request_id}` | admin | `DiscountRequestDecisionSchema` (опц.) → detail | 403 seller, 404, 409 |
| `POST /discount/reject/{discount_request_id}` | admin | `DiscountRequestDecisionSchema` (опц.) → detail | 403, 404, 409 |
| `DELETE /discount/delete/{discount_request_id}` | seller-автор, admin | → `{'message': 'Запрос на скидку отозван'}` | 403, 404, 409 не `pending` |

### Уведомления этапа 5

| Событие | Кому | Тип |
|---|---|---|
| Сделка создана | клиенту; продавцу, если создал admin | `deal` |
| Бронь | клиенту | `reservation` |
| Оплата / выдача | клиенту | `deal` |
| Отмена (ручная, «авто продано») | клиенту и продавцу (кроме инициатора) | `deal` |
| Бронь истекла | продавцу и клиенту | `reservation` |
| Запрос скидки выше лимита | всем активным админам (`notify_active_admins`) | `discount` |
| Скидка применена / одобрена | клиенту (новая цена) + продавцу при одобрении | `deal` / `discount` |
| Скидка отклонена (в т.ч. авто-отклонение при отмене сделки) | продавцу | `discount` |

Правила как в этапе 4: без commit внутри `create_notification`, инициатору не шлём, заблокированным не шлём.

---

## Фоновая задача истечения брони

```python
# mysite/api/deal.py — вся логика, синхронно, тестируется напрямую
def expire_reservations(db: Session) -> int:
    now = datetime.now(timezone.utc)
    deals_db = db.query(Deal).filter(
        Deal.status == DealStatus.reserved, Deal.deleted_at.is_(None), Deal.reserved_until <= now
    ).all()
    # для каждой: условный UPDATE reserved→cancelled (rowcount 0 → пропустить: её уже оплатили/отменили),
    # cancel_reason='Срок брони истёк', release_car, reject_pending_discounts, уведомления reservation продавцу и клиенту,
    # AuditLog deal_expire (user_id=None); commit ПО ОДНОЙ сделке, ошибка → rollback + logger.exception и дальше.
    return count
```

```python
# main.py — по образцу game_scheduler (STYLE §9)
async def reservation_scheduler():
    while True:
        db = SessionLocal()
        try:
            expire_reservations(db)
        except Exception:
            logger.exception('Ошибка фоновой задачи истечения брони')
        finally:
            db.close()
        await asyncio.sleep(RESERVATION_CHECK_SECONDS)
```

- Запуск: `lifespan` (`@asynccontextmanager`), `FastAPI(title=..., lifespan=lifespan)`; при `RESERVATION_SCHEDULER_ENABLED`
  — `task = asyncio.create_task(reservation_scheduler())`, на выходе `task.cancel()` + `suppress(asyncio.CancelledError)`.
  **[дефолт]**: `lifespan` вместо устаревшего `@app.on_event('startup')` — это и есть «startup-обработчик» из STYLE §9,
  без DeprecationWarning (неблокирующий вопрос 1).
- Интервал — `RESERVATION_CHECK_SECONDS` (60 с). Точность истечения — до минуты; плюс `pay` сам проверяет истечение.
- SQLite + один воркер: задача живёт в том же event loop; её тело синхронное и не содержит `await` внутри транзакции,
  обработчики — `async def` без `await` между проверкой и `commit` → чередования внутри транзакции нет. Условные `UPDATE`
  дают защиту и при будущем переходе на `def`-обработчики (threadpool). `busy_timeout=5000` уже включён. При нескольких
  воркерах задача запустилась бы в каждом — условный `UPDATE` делает это безопасным, но это не поддерживаемый режим.
- Тесты: `RESERVATION_SCHEDULER_ENABLED=false` в `conftest.py` до импорта приложения (иначе `TestClient` запустит задачу,
  которая полезет в тестовый файл БД через отдельное соединение мимо SAVEPOINT). Логика тестируется вызовом
  `expire_reservations(db)` с `reserved_until` в прошлом. Отдельно — тест, что при выключенном флаге задача не создаётся
  (через `monkeypatch` на `asyncio.create_task` или проверка `asyncio.all_tasks()` не обязательна — достаточно unit-теста
  на `expire_reservations`) **[дефолт]**.

---

## AuditLog

Функции в `deal.py`:
```python
def to_audit_value(value):  # Decimal -> str ('1500000.00'), datetime -> isoformat UTC ('...+00:00'),
                            # Enum -> .value, None/int/str/bool как есть
def create_audit_log(db, user_id, action, entity_name, entity_id, old_value=None, new_value=None):
    # dict значений прогоняется через to_audit_value; db.add(AuditLog(...)) БЕЗ commit — в транзакции действия
```
- JSON-колонка SQLite сериализует через `json.dumps` — `Decimal`/`datetime` без конвертации упадут; поэтому только
  `to_audit_value`. В `old_value`/`new_value` — **только изменённые поля** (плоский dict).
- `user_id` — инициатор; для системы (истечение брони) — `None`.
- `action` ≤ 50 символов, `entity_name` — имя таблицы.

| action | entity_name | old_value → new_value |
|---|---|---|
| `deal_create` | `deal` | `None` → `{car_id, client_id, seller_id, base_price, final_price, currency, status}` |
| `deal_start` / `deal_pay` / `deal_deliver` | `deal` | `{status}` → `{status, paid_at / delivered_at, car_status}` |
| `deal_reserve` | `deal` | `{status, car_status: 'available'}` → `{status, reserved_until, car_status: 'reserved'}` |
| `deal_cancel` | `deal` | `{status, car_status?}` → `{status: 'cancelled', cancel_reason, car_status?}` |
| `deal_expire` | `deal` | `{status: 'reserved', reserved_until}` → `{status: 'cancelled', cancel_reason, car_status: 'available'}` |
| `deal_delete` | `deal` | `{deleted_at: None}` → `{deleted_at}` |
| `discount_apply` | `discount_request` | `{discount_percent, final_price}` (сделки) → новые значения + `deal_id` |
| `discount_request` | `discount_request` | `None` → `{deal_id, requested_percent, comment}` |
| `discount_approve` | `discount_request` | `{status, discount_percent, final_price}` → новые + `comment` админа |
| `discount_reject` | `discount_request` | `{status: 'pending'}` → `{status: 'rejected', comment}` |
| `discount_withdraw` | `discount_request` | `{deal_id, requested_percent, status}` → `None` |
| `user_discount_limit` | `user_profile` | `{discount_limit}` → `{discount_limit}` **[дефолт]** |

Чтение журнала — только sqladmin `AuditLogView` (read-only) **[дефолт]**; API `/audit-log/*` не делаем (файла нет в ROADMAP).
Блокировка пользователей и смена цены авто в AuditLog на этом этапе не пишутся (цена уже в `PriceHistory`) — неблокирующий вопрос 2.

---

## sqladmin

`view.py` — три класса, `can_create = can_edit = can_delete = False` (правка в панели обошла бы машину состояний,
атомарную бронь и расчёт цены):
- `DealView`: `id, car_id, client_id, seller_id, final_price, currency, status, reserved_until, created_at, deleted_at`.
- `DiscountRequestView`: `id, deal_id, seller_id, requested_percent, status, decided_by_id, decided_at`.
- `AuditLogView`: `id, user_id, action, entity_name, entity_id, created_at`; детали — с `old_value`/`new_value`;
  сортировка по умолчанию `column_default_sort = (AuditLog.id, True)`.

---

## Бизнес-правила этапа

| ТЗ | Правило | Как проверяется |
|---|---|---|
| §5.1 | Машина состояний, недопустимый переход → 409 | `DEAL_TRANSITIONS` + условный `UPDATE` по `status`; тесты на каждый запрещённый переход |
| §5.2 | Двойная бронь невозможна | `UPDATE car ... WHERE status='available'`, `rowcount 0` → 409 `'Авто уже забронировано'`; тест двух сделок на одно авто |
| §5.3 | Истечение брони → сделка `cancelled`, авто `available`, уведомления продавцу и клиенту | `expire_reservations` + `reservation_scheduler`; тесты с `reserved_until` в прошлом |
| §5.5 | Скидка ≤ лимита — сразу; выше — `DiscountRequest pending` | `/discount/create` ветвление по `discount_limit`; admin решает `/approve`, `/reject` |
| §5.6 | `final_price` считает сервер | нет поля во входных схемах; `calc_final_price` (Decimal, HALF_UP) |
| §5.7 | Важные действия → AuditLog | `create_audit_log` в каждом действии сделки/скидки + `discount-limit` |
| §5.8 | Мягкое удаление сделки | `deleted_at`, все выборки `deleted_at IS NULL` (deal и discount) |
| §3 seller | Только свои сделки; скидка до лимита | видимость `seller_id == me`, чужое → 404 |
| §3 client | Только свои сделки, чужое → 404 | `client_id == me`; client — только `list`/`detail` |
| §3 admin | Видит/меняет всё, решает скидки | admin проходит видимость; `approve`/`reject` только admin |
| §1, §7 | Деньги `Decimal`, время UTC | `calc_final_price`, `datetime.now(timezone.utc)`, `UtcDatetimeOut` |
| §6 | Пагинация | `skip`/`limit (le=100)` в `/deal/list`, `/discount/list` |

---

## Миграции

**Не требуются.** db-specialist: `alembic upgrade head` → `alembic check` (ожидается «No new upgrade operations detected»);
изменения `schema.py`/`config.py` на БД не влияют. Если автор выберет `decision_comment` / `DiscountRequest.created_at`
(вопрос 3) — новая миграция поверх `610fbbdbd05f` с `batch_alter_table`, `server_default` для NOT NULL.

---

## Тесты

`tests/conftest.py` — дополнить:
- `os.environ['RESERVATION_SCHEDULER_ENABLED'] = 'false'` рядом с `DATABASE_URL` (до импорта `main`).
- `seller2`, `client2` (через `make_user`), `make_deal(**overrides)` (по умолчанию `car=make_car()`, `client_user`, `seller`,
  `base_price=final_price=car.price`, `status=new`), `make_discount_request(**overrides)`.
- `DealView`, `DiscountRequestView`, `AuditLogView` — в кортеж `admin_session_local`.

`tests/test_deal.py`:
- create: `test_create_deal_seller_ok` (`seller_id == me`, `base_price == car.price`, `final_price == base_price`,
  `discount_percent == 0`, `currency` из авто, `status == new`, уведомление клиенту, AuditLog `deal_create`),
  `test_create_deal_ignores_server_fields` (`final_price`, `status`, `base_price`, `seller_id` от seller — игнор),
  `test_create_deal_admin_with_seller_ok`, `test_create_deal_admin_without_seller_400`, `test_create_deal_admin_blocked_seller_404`,
  `test_create_deal_as_client_403`, `test_create_deal_without_token_401`, `test_create_deal_unknown_car_404`,
  `test_create_deal_deleted_car_404`, `test_create_deal_client_is_seller_404`, `test_create_deal_blocked_client_404`,
  `test_create_deal_car_in_transit_ok`, parametrize `reserved`/`sold`/`withdrawn` → 409,
  `test_create_deal_duplicate_active_409`, `test_create_deal_after_cancelled_ok`, `test_create_deal_other_client_same_car_ok`.
- list/detail: `test_list_deal_client_sees_only_own`, `test_list_deal_seller_sees_only_own`, `test_list_deal_admin_sees_all`,
  `test_list_deal_admin_filter_seller_id`, `test_list_deal_seller_filter_seller_id_ignored`, фильтр `status`, пагинация,
  `limit=101` → 422, `test_list_deal_excludes_deleted`; **IDOR**: `test_detail_deal_other_client_404`,
  `test_detail_deal_other_seller_404`, `test_detail_deleted_deal_admin_404`, `test_detail_deal_datetime_utc_offset` (`+00:00`).
- переходы: `test_start_deal_ok`, `test_reserve_deal_ok` (авто `reserved`, `reserved_until ≈ now + reservation_hours`
  из `salon_settings`, уведомление `reservation`), `test_reserve_deal_default_48h_without_settings`,
  `test_pay_deal_ok` (`paid_at`, авто остаётся `reserved`), `test_deliver_deal_ok` (авто `sold`, `delivered_at`),
  parametrize запрещённых переходов → 409: `new→reserve`, `new→pay`, `in_progress→pay`, `reserved→deliver`, `reserved→start`,
  `paid→reserve`, `delivered→cancel`, `cancelled→start`, `cancelled→cancel`, повторный `start`.
  Права: `test_transition_as_client_403`, `test_transition_other_seller_404`.
- бронь: `test_reserve_car_already_reserved_409` (две сделки на одно авто: вторая → 409 `'Авто уже забронировано'`,
  сделка остаётся `in_progress`), `test_reserve_car_in_transit_409`, `test_reserve_car_withdrawn_409`,
  `test_reserve_deleted_car_409`, `test_reserve_after_cancel_other_ok` (после отмены первой брони вторая сделка бронирует).
- pay: `test_pay_with_pending_discount_409`, `test_pay_expired_reservation_409_and_cancelled` (сделка `cancelled`,
  авто `available`).
- deliver: `test_deliver_cancels_other_active_deals` (их статус, причина, уведомления, pending-скидки → rejected).
- cancel: `test_cancel_new_ok` (авто не меняется), `test_cancel_reserved_releases_car`, `test_cancel_paid_by_admin_releases_car`,
  `test_cancel_paid_by_seller_403`, `test_cancel_without_reason_422`, `test_cancel_blank_reason_422`,
  `test_cancel_rejects_pending_discounts`, `test_cancel_notifies_client_not_actor`, `test_cancel_delivered_409`.
- delete: `test_delete_deal_admin_new_ok` (`deleted_at` задан, в list/detail нет), `test_delete_deal_admin_cancelled_ok`,
  parametrize `in_progress`/`reserved`/`paid`/`delivered` → 409, `test_delete_deal_seller_403`, `test_delete_deal_client_403`,
  `test_delete_deal_not_found_404`, повторное удаление → 404.

`tests/test_discount.py`:
- `test_discount_within_limit_applied` (seller `discount_limit=5`, 5% → `approved`, `decided_by_id == seller.id`,
  `final_price` пересчитан, уведомление клиенту, AuditLog `discount_apply`), `test_discount_equal_limit_applied` (граница `==`),
  `test_discount_above_limit_pending` (сделка не изменилась, уведомления активным админам — заблокированному нет,
  AuditLog `discount_request`), `test_discount_zero_limit_always_pending`, `test_discount_admin_applies_any`.
- расчёт: `test_final_price_rounding_half_up` (100.30 × 5% → `95.29`), `test_final_price_decimal_string`
  (ответ `'1450050.00'`-подобный, без float-артефактов), `test_discount_replaces_not_accumulates`.
- валидация: parametrize `0`, `100`, `-1`, `5.555` → 422; `test_discount_same_as_current_400`.
- конфликты: `test_discount_second_pending_409`, `test_discount_after_rejected_ok`, parametrize статус сделки
  `paid`/`delivered`/`cancelled` → 409, `test_discount_on_reserved_deal_ok`, `test_discount_deleted_deal_404`.
- права/IDOR: `test_discount_create_as_client_403`, `test_discount_create_other_seller_deal_404`,
  `test_discount_list_seller_only_own`, `test_discount_list_client_403`, `test_discount_detail_other_seller_404`.
- решение: `test_approve_ok` (сделка пересчитана, `decided_by_id`, `decided_at` с `+00:00`, уведомления продавцу и клиенту,
  AuditLog), `test_reject_ok` (сделка не изменилась, комментарий в уведомлении и AuditLog, `comment` продавца сохранён),
  `test_approve_already_decided_409`, `test_reject_already_decided_409`, `test_approve_as_seller_403`,
  `test_approve_after_deal_cancelled_409` (pending к этому моменту уже `rejected` → 409), `test_approve_without_body_ok`.
- отзыв: `test_withdraw_pending_by_author_ok`, `test_withdraw_decided_409`, `test_withdraw_other_seller_404`.
- лимит: `test_update_discount_limit_writes_audit_log` (`user.py`).

`tests/test_reservation.py`:
- `test_expire_reservations_cancels_expired` (`expire_reservations(db)` → 1; сделка `cancelled`, `cancel_reason`, авто `available`,
  уведомления `reservation` продавцу и клиенту, AuditLog `deal_expire` с `user_id is None`).
- `test_expire_reservations_skips_not_expired`, `test_expire_reservations_skips_paid` (оплаченная с прошедшим `reserved_until`
  не трогается), `test_expire_reservations_skips_deleted`, `test_expire_reservations_rejects_pending_discounts`,
  `test_expire_reservations_multiple`, `test_expire_reservations_returns_zero_when_nothing`.
- `test_expire_reservations_aware_naive_compare` (значение из SQLite naive — сравнение корректно).
- `test_scheduler_disabled_in_tests` — `config.RESERVATION_SCHEDULER_ENABLED is False`.

`tests/test_audit_log.py`:
- `test_audit_values_json_serializable` (Decimal → `'1500000.00'`, datetime → строка с `+00:00`, Enum → значение).
- `test_audit_log_written_in_same_transaction` (при 409 на бронь записи `deal_reserve` нет).
- `test_audit_log_full_deal_flow` (create → start → reserve → pay → deliver: 5 записей с верными action, user_id).

`tests/test_admin.py` — дополнить: списки `DealView`, `DiscountRequestView`, `AuditLogView` → 200 под админом;
`/admin/<view>/create` и `/edit/<id>` недоступны; без логина → редирект.

---

## Риски и открытые вопросы

Неблокирующие, решены дефолтом (автор может переопределить):
1. **`lifespan` вместо `@app.on_event('startup')`** — STYLE §9 говорит «startup-обработчик»; `on_event` в FastAPI устарел.
   Логика та же (`asyncio.create_task` + `while True` + `SessionLocal()` + `sleep`).
2. **Объём AuditLog**: сделки, скидки и смена `discount_limit`. Блокировка/разблокировка пользователей, создание продавцов,
   удаление авто — не пишутся. Расширить — правка `user.py`/`car.py` (импорт `create_audit_log` из `deal.py`).
3. **Один `comment` у `DiscountRequest`**: хранит обоснование продавца; комментарий админа — в уведомлении и AuditLog.
   Нет `DiscountRequest.created_at`. Отдельные поля → миграция.
4. **Скидка во время `pending` блокирует только `pay`**; бронь может истечь, пока админ думает.
5. **Время в текстах уведомлений — UTC** (нет `tzdata` для `Asia/Bishkek` на Windows). Альтернатива — добавить `tzdata` в
   `requirements.txt` и форматировать в `SALON_TIMEZONE`.
6. **Отмена `paid` — только admin**; client сделки не отменяет вообще; seller — `new`/`in_progress`/`reserved` своих.
7. **Несколько активных сделок разных клиентов на одно авто** разрешены; при `deliver` остальные отменяются автоматически.
   Удаление авто в `car.py` не проверяет активные `new`/`in_progress` сделки (их бронь просто получит 409).
8. **`PUT /deal/update` отсутствует**; скидка только через `/discount/create`; в `DealCreateSchema` нет `discount_percent`.
   Отменить скидку до 0% нельзя (CHECK `requested_percent > 0`) — только уменьшить до 0.01% или пересоздать сделку.
9. **Межмодульные импорты**: `discount.py` и `user.py` импортируют хелперы из `deal.py` (как `lead.py` из `car.py`).
10. **Конкурентность** — один воркер, синхронные тела без `await`; переходы — условные `UPDATE`. При `--workers > 1`
    планировщик дублировался бы (безопасно за счёт условий, но не поддерживается).
11. **Удаление сделки — только `new`/`cancelled`**, только admin.
12. Фоновая задача коммитит по одной сделке; сбой одной не блокирует остальные (лог `logger.exception`).

---

## Не делаем в этом этапе

- Этап 6: `trade_in` + `TradeInImage`, `favorite`, `review` (в т.ч. проверка «отзыв только после `delivered`»), `credit`,
  `statistic` (в т.ч. «своя статистика» продавца по сделкам/скидкам).
- API журнала `/audit-log/*` (только sqladmin), API `SalonSettings`.
- Онлайн-оплата, документы/договоры, частичная оплата, связь сделки с заявкой (`lead_id`).
- Изменения `models.py` и миграции.
- Email/SMS/push/WebSocket — только записи `Notification`.
- Новые модули/утилиты, `services/`, отдельный `scheduler.py`.

---

## Порядок работы

1. **db-specialist** — без изменений моделей: `alembic upgrade head` + `alembic check`; подтвердить, что миграция не нужна.
2. **coder** (по порядку):
   1. `mysite/config.py` (+ `.env.example`) — `RESERVATION_CHECK_SECONDS`, `RESERVATION_SCHEDULER_ENABLED`.
   2. `mysite/db/schema.py` — `DiscountPercent`, правки `Deal*`/`DiscountRequest*`/`AuditLog*`, новые `DealCancelSchema`,
      `DiscountRequestDecisionSchema`, удаление `DealUpdateSchema`, `DiscountRequestUpdateSchema`.
   3. `mysite/api/notification.py` — `notify_active_admins`.
   4. `mysite/api/deal.py` — хелперы (`calc_final_price`, `to_audit_value`, `create_audit_log`, `change_deal_status`,
      `release_car`, `reject_pending_discounts`, `expire_reservations`) + `deal_router`.
   5. `mysite/api/discount.py` — `discount_router`.
   6. `mysite/api/user.py` — AuditLog в `update_discount_limit`.
   7. `main.py` — роутеры, `reservation_scheduler`, `lifespan`.
   8. `mysite/admin/view.py`, `setup.py` — три read-only view.
   9. Проверка: `.venv/Scripts/python.exe -c "import main"`, `uvicorn main:auto_app` → `/docs`, в логе нет ошибок планировщика.
3. **tester** — `conftest.py` (флаг планировщика, фикстуры, view) + `test_deal.py`, `test_discount.py`, `test_reservation.py`,
   `test_audit_log.py`, дополнение `test_admin.py`; `.venv/Scripts/python.exe -m pytest -q`.
4. **reviewer + security-auditor** — по `git diff`; особое внимание: IDOR (client/seller → 404 на чужие сделки и скидки,
   client → 403 на `/discount/*`), серверные поля не принимаются, `final_price` только `Decimal`, атомарность брони и
   переходов, мягко удалённые сделки не видны, AuditLog не содержит секретов, планировщик не стартует в тестах.
5. **coder** — исправления 🔴 critical.
6. Отметить чекбоксы в `docs/ROADMAP.md`, отчёт + предложенный коммит
   `feat(sales): add deals, discounts, reservation expiry and audit log (stage 5)` → **СТОП**.
