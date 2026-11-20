# План: Этап 6 — Остальное (trade-in, избранное, отзывы, кредит/сравнение, статистика)

## Открытые вопросы (блокирующие)

Нет. Всё, что помечено **[дефолт]**, — решение архитектора; автор может переопределить
(сводка — в разделе «Риски и открытые вопросы»).

---

## Цель и границы

Цель: оставшиеся функции ТЗ — trade-in (заявка клиента на оценку своего авто + фото), избранное, отзывы после выдачи
авто, кредитный калькулятор и сравнение до 4 авто, статистика (admin — общая, seller — своя), тесты.

Границы:
- Новые файлы в `mysite/` — **только** `mysite/api/trade_in.py`, `favorite.py`, `review.py`, `credit.py`,
  `statistic.py` (ROADMAP). `TradeInImage` — второй роутер **в том же** `trade_in.py` (`trade_in_image_router`,
  как `lead_note_router` в `lead.py`). Никаких `utils.py`, `services/`.
- **Изменений моделей нет. Миграции нет** (обоснование — в разделе «Модели»).
- Переиспользуем существующие функции (импорт между роутерами, как `discount.py` ← `deal.py`):
  - `car.py`: `get_car_or_404`, `is_staff`, `PUBLIC_CAR_STATUSES`;
  - `car_image.py`: `detect_image_extension`, `MAX_IMAGE_SIZE`, `ALLOWED_IMAGE_TYPES`, `IMAGE_TYPE_ERROR`;
  - `deal.py`: `visible_deals_query`, `create_audit_log`, `CENT`;
  - `notification.py`: `create_notification`, `notify_active_sellers`;
  - `dependencies.py`: `get_current_user`, `get_optional_user`, `require_role`.
- Ничего сверх ROADMAP: API `SalonSettings`, API журнала, курсы валют, банки/ставки в БД — не делаем.

Текущее состояние (проверено):
- `models.py`: `TradeIn` (`client_id` idx, `brand_name/model_name String(50)`, `year`, `mileage` CHECK `>= 0`,
  `description Text`, `estimated_price Numeric(14,2)` nullable CHECK `> 0`, `currency`, `status TradeInStatus`,
  `seller_id` nullable idx, `created_at`; `images` cascade `all, delete-orphan`), `TradeInImage` (`trade_in_id` idx,
  `trade_in_image`), `Favorite` (`user_id`, `car_id`, `UniqueConstraint uq_favorite_user_car`, без `created_at`),
  `Review` (`client_id`, `deal_id` **unique**, `seller_id` idx, `stars` CHECK `BETWEEN 1 AND 5`, `comment`, `created_at`),
  `Deal.review` (`uselist=False`). Все связи двусторонние. Enum `TradeInStatus`: new, evaluating, offered, accepted, rejected.
- `schema.py`: заготовки `TradeIn*`, `TradeInImage*`, `Favorite*`, `Review*` (этап 1, требуют правок — см. «Схемы»);
  типы `Money`, `Percent`, `Stars`, `Year`, `Mileage`, `Name50`, `Text2000`, `Text5000`, `UtcDatetimeOut`.
  Схем кредита и статистики нет.
- `main.py`: `os.makedirs(MEDIA_DIR/car_images)`, `/media` смонтирован через `StaticFiles`, 11 роутеров, `lifespan`.
- `conftest.py`: `db`, `client`, `make_user`, `auth_headers`, `admin`, `seller`, `seller2`, `client_user`, `client2`,
  `make_car`, `make_deal`, `make_discount_request`, `make_lead`, `salon_settings`, `media_dir` (патчит
  `mysite.api.car_image.MEDIA_DIR`), `JPEG_BYTES/PNG_BYTES/WEBP_BYTES`, `admin_session_local` (кортеж view).
- Alembic head: `610fbbdbd05f`.

---

## Файлы (создать / изменить)

### Создать
| Путь | Что |
|---|---|
| `mysite/api/trade_in.py` | `trade_in_router` (`/trade-in`, `tags=['TradeIn']`) + `trade_in_image_router` (`/trade-in-image`, `tags=['TradeInImage']`); хелперы `visible_trade_ins_query`, `get_trade_in_or_404`, `get_own_trade_in_or_404`, `change_trade_in_status`, `get_trade_in_images_dir`, `get_trade_in_image_or_404`, `remove_image_files`. |
| `mysite/api/favorite.py` | `favorite_router` (`/favorite`, `tags=['Favorite']`). |
| `mysite/api/review.py` | `review_router` (`/review`, `tags=['Review']`); `visible_reviews_query`, `get_review_or_404`. |
| `mysite/api/credit.py` | `credit_router` (`/credit`, `tags=['Credit']`); `calc_monthly_payment`, `build_credit_result`. |
| `mysite/api/statistic.py` | `statistic_router` (`/statistic`, `tags=['Statistic']`); `get_period_bounds`, `count_by_status`, `sum_money_by_currency`, `avg_stars`, `build_seller_statistic`. |
| `tests/test_trade_in.py`, `tests/test_trade_in_image.py`, `tests/test_favorite.py`, `tests/test_review.py`, `tests/test_credit.py`, `tests/test_statistic.py` | тесты. |

### Изменить
| Путь | Что |
|---|---|
| `mysite/db/schema.py` | правки `TradeIn*`, `TradeInImage*`, `Favorite*`, `Review*`; новые `TradeInOfferSchema`, `TradeInAssignSchema`, `Credit*`, `Statistic*`, типы `CreditTerm`, `DownPayment`, `DownPaymentPercent` (см. «Схемы»). |
| `main.py` | импорт `trade_in, favorite, review, credit, statistic`; 6 `include_router` (`trade_in.trade_in_router`, `trade_in.trade_in_image_router`, `favorite.favorite_router`, `review.review_router`, `credit.credit_router`, `statistic.statistic_router`); `os.makedirs(os.path.join(MEDIA_DIR, 'trade_in_images'), exist_ok=True)`. |
| `mysite/admin/view.py` | `TradeInView`, `ReviewView` — только чтение **[дефолт]**. |
| `mysite/admin/setup.py` | `admin.add_view(TradeInView)`, `admin.add_view(ReviewView)`. |
| `tests/conftest.py` | `media_dir` — дополнительно патчит `mysite.api.trade_in.MEDIA_DIR` и создаёт `trade_in_images/`; фикстуры `make_trade_in`, `make_trade_in_image`, `make_review`, `make_favorite`; `TradeInView`, `ReviewView` в кортеж `admin_session_local`. |
| `tests/test_admin.py` | списки двух новых view → 200, create/edit недоступны. |
| `docs/ROADMAP.md` | чекбоксы этапа 6, строка «Текущий этап». |

`docker-compose.yml`, `nginx.conf` — **не меняем**: `./media` уже смонтирован, `location /media/` отдаёт любую подпапку.

---

## Модели / поля / связи / ограничения

**Изменений моделей нет, миграции нет.** Всё нужное есть в `initial` (`f907a8edf483`).

Рассмотрено и осознанно **не добавляем** **[дефолт]**:
| Кандидат | Почему не нужно сейчас |
|---|---|
| `Favorite.created_at` | сортировка по `Favorite.id.desc()` (autoincrement монотонен). |
| `TradeIn.updated_at`, `TradeIn.reject_reason`, `TradeIn.deal_id` | ТЗ не требует; причина отказа — в уведомлении и `AuditLog.new_value`. Зачёт trade-in в сделку — вне ТЗ. |
| `NotificationType.trade_in` / `review` | уведомления trade-in идут с типом `lead` (CRM), отзывов — `deal`. Новое значение Enum ⇒ правка модели. |
| Индексы `review.client_id`, `favorite.car_id`, `trade_in.status` | объёмы одного салона малы; `uq_favorite_user_car` уже покрывает выборки по `user_id`. |
| Модель «сравнение» | сравнение stateless — список `car_ids` в запросе (модели в ТЗ нет). |

Используемые ограничения БД как страховка: `uq_favorite_user_car` (гонка двойного добавления → `IntegrityError` → 409),
`review.deal_id UNIQUE` (гонка двух отзывов → 409), CHECK `stars BETWEEN 1 AND 5`, CHECK `estimated_price > 0`.

---

## SQLite: деньги, время, кириллица

- **Деньги.** `Numeric` в SQLite хранится как REAL; `SUM()`/`AVG()` в SQL вернули бы `float`. Поэтому в статистике
  денежные суммы **считаются в Python**: выбираем `(currency, final_price)` (SQLAlchemy отдаёт `Decimal`, уже
  округлённый до scale 2), суммируем `Decimal`, `quantize(CENT)`. В SQL — только `COUNT(*) ... GROUP BY`.
  Кредит — только `Decimal` (см. «Кредит»). `float` нигде.
- **Средняя оценка** — `SUM(stars)` и `COUNT` (целые) из SQL, деление в Python:
  `(Decimal(total) / Decimal(count)).quantize(CENT, ROUND_HALF_UP)`; нет отзывов → `None`.
- **Время.** Все ответы — `UtcDatetimeOut`. Период статистики — query `date_from: date | None`, `date_to: date | None`
  (включительно), границы — сутки **UTC** **[дефолт]** (`tzdata` нет в requirements): `start = datetime.combine(date_from,
  time.min, tzinfo=timezone.utc)`, `end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)`,
  фильтр `col >= start AND col < end` (bind aware UTC — как `reserved_until` в `deal.py`). `date_from > date_to` → 400.
  От клиента datetime на этапе не принимаются.
- **Кириллица.** Текстового поиска на этапе нет. `brand_name/model_name` trade-in — свободный текст (не справочник),
  `strip` через `Name50`; фильтров по ним нет **[дефолт]**.

---

## Схемы

Новые типы:
```python
CreditTerm = Annotated[int, Field(ge=1, le=120)]                                  # месяцев
DownPayment = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
DownPaymentPercent = Annotated[Decimal, Field(ge=0, lt=100, max_digits=5, decimal_places=2)]
```
Ставка — существующий `Percent` (0..100, 2 знака).

| Схема | Было | Станет |
|---|---|---|
| `TradeInCreateSchema` | `brand_name/model_name: str(max 50)`, `description: str`, `currency` | `brand_name: Name50`, `model_name: Name50`, `year: Year`, `mileage: Mileage`, `description: Text5000 \| None = None`. **`currency` убрать** (валюту задаёт продавец в предложении). |
| `TradeInUpdateSchema` | `estimated_price`, `currency`, `status`, `description` | только поля клиента: `brand_name: Name50 \| None`, `model_name: Name50 \| None`, `year: Year \| None`, `mileage: Mileage \| None`, `description: Text5000 \| None` (все `= None`). Статус/цена — только action-эндпоинтами. |
| `TradeInOfferSchema` | — | **новая**: `estimated_price: Money`, `currency: Currency = Currency.KGS`. |
| `TradeInAssignSchema` | — | **новая**: `seller_id: int`. |
| `TradeInListSchema` | `created_at: datetime` | + `seller_id: int \| None`, `estimated_price: Decimal \| None`, `currency: Currency`; `created_at: UtcDatetimeOut`. |
| `TradeInDetailSchema` | `created_at: datetime` | `created_at: UtcDatetimeOut`; + `images: List[TradeInImageListSchema] = []`. |
| `TradeInImageCreateSchema`, `TradeInImageUpdateSchema` | есть | **удалить** (загрузка — multipart `Form`/`File`, как `car_image.py`; update нет). |
| `TradeInImageListSchema` / `DetailSchema` | ок | без изменений. |
| `FavoriteCreateSchema` | `car_id` | без изменений. |
| `FavoriteListSchema` | `id`, `car_id` | + `car: CarListSchema` (вложенный, `joinedload(Favorite.car)`). |
| `FavoriteDetailSchema` | `id`, `user_id`, `car_id` | + `car: CarListSchema`. |
| `ReviewCreateSchema` | `comment: str \| None` | `deal_id: int`, `stars: Stars`, `comment: Text2000 \| None = None`. |
| `ReviewUpdateSchema` | `comment: str \| None` | `stars: Stars \| None = None`, `comment: Text2000 \| None = None`. |
| `ReviewListSchema` | `created_at: datetime` | + `deal_id: int`; `created_at: UtcDatetimeOut`. |
| `ReviewDetailSchema` | `created_at: datetime` | `created_at: UtcDatetimeOut`. |
| `CreditCalculateSchema` | — | **новая**: `car_id: int \| None = None`, `price: Money \| None = None`, `currency: Currency = Currency.KGS` (только при `price`), `down_payment: DownPayment = 0`, `annual_rate: Percent`, `term_months: CreditTerm`. |
| `CreditResultSchema` | — | **новая**: `car_id: int \| None`, `price`, `currency`, `down_payment`, `loan_amount`, `annual_rate`, `term_months`, `monthly_payment`, `total_payment`, `overpayment` (деньги — `Decimal`). |
| `CreditCompareSchema` | — | **новая**: `car_ids: List[int] = Field(min_length=2, max_length=4)`, `annual_rate: Percent \| None = None`, `term_months: CreditTerm \| None = None`, `down_payment_percent: DownPaymentPercent = Decimal('0')`. |
| `CreditCompareItemSchema` | — | **новая**: `car: CarDetailSchema`, `credit: CreditResultSchema \| None`. |
| `StatisticSellerSchema` | — | **новая**: `seller_id: int`, `username: str`, `leads_by_status: dict[LeadStatus, int]`, `deals_by_status: dict[DealStatus, int]`, `discounts_by_status: dict[DiscountStatus, int]`, `trade_ins_by_status: dict[TradeInStatus, int]`, `revenue: dict[Currency, Decimal]`, `delivered_count: int`, `reviews_count: int`, `avg_stars: Decimal \| None`, `date_from: date \| None`, `date_to: date \| None`. |
| `StatisticGeneralSchema` | — | **новая**: `cars_by_status: dict[CarStatus, int]`, `leads_by_status`, `deals_by_status`, `trade_ins_by_status`, `discounts_pending: int`, `revenue: dict[Currency, Decimal]`, `delivered_count: int`, `avg_discount_percent: Decimal \| None`, `clients_count: int`, `reviews_count: int`, `avg_stars: Decimal \| None`, `sellers: List[StatisticSellerRowSchema]`, `date_from`, `date_to`. |
| `StatisticSellerRowSchema` | — | **новая**: `seller_id`, `username`, `is_active`, `deals_count`, `delivered_count`, `revenue: dict[Currency, Decimal]`, `avg_stars: Decimal \| None`. |

Во всех `*_by_status` и `revenue` — **все** ключи Enum, отсутствующие = `0` / `Decimal('0.00')` (стабильная форма ответа).

**Не принимаются от клиента** (берёт сервер): `TradeIn.client_id`, `seller_id` (кроме `assign` у admin), `status`,
`estimated_price` / `currency` (только `offer`), `created_at`; `TradeInImage.trade_in_image` (путь генерирует сервер);
`Favorite.user_id`; `Review.client_id`, `seller_id`, `created_at`; в кредите — все результаты расчёта.
Лишние поля Pydantic игнорирует — тесты это проверяют.

---

## Эндпоинты

Общие правила (как этапы 4–5): `response_model` всегда; пагинация `skip: int = Query(0, ge=0)`,
`limit: int = Query(20, ge=1, le=100)`; 401 — нет/плохой токен; 403 — роль (`'Недостаточно прав'`);
**чужой объект → 404** для client и seller; 409 — конфликт/недопустимый переход; 400 — некорректные данные; 422 — валидация.

### `trade_in_router` — `/trade-in`, `tags=['TradeIn']`

Машина состояний:
```
new ──take/assign──▶ evaluating ──offer──▶ offered ──accept (client)──▶ accepted
 │                       │                    └──reject (client)──▶ rejected
 └──reject (staff)───────┴──reject (staff)──▶ rejected
```
`TRADE_IN_TRANSITIONS = {new: (evaluating, rejected), evaluating: (offered, rejected), offered: (accepted, rejected)}`.
Каждый переход — условный `UPDATE trade_in SET ... WHERE id=:id AND status=:from` (`change_trade_in_status`, по образцу
`change_deal_status`); `rowcount == 0` → `rollback` + 409 `'Недопустимый переход статуса trade-in'`.

Видимость (`visible_trade_ins_query`, по образцу `visible_leads_query`): admin — все; client — `client_id == me`;
seller — `seller_id == me` **или** свободные (`seller_id IS NULL AND status = new`). Иначе 404 `'Заявка на trade-in не найдена'`.
Для действий продавца (`offer`, `reject`) — `get_own_trade_in_or_404`: seller — только `seller_id == me`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /trade-in/create` | client | `TradeInCreateSchema` → `TradeInDetailSchema` | 403 staff; 400 `'Год выпуска не может быть больше следующего года'`; 409 `'У вас уже есть 5 активных заявок на trade-in'` (лимит 5 в `new`/`evaluating`/`offered`) **[дефолт]** |
| `GET /trade-in/list` | все роли | `status`, `only_free` (staff), `seller_id` (только admin), `skip`, `limit` → `List[TradeInListSchema]`, `order_by(created_at.desc(), id.desc())` | 401, 422 |
| `GET /trade-in/detail?trade_in_id=` | все роли | → `TradeInDetailSchema` (`selectinload(TradeIn.images)`, сортировка по `id`) | 401, 404 |
| `PUT /trade-in/update/{trade_in_id}` | client-владелец | `TradeInUpdateSchema` → detail | 403 staff; 404; 409 `'Заявку на trade-in в работе изменить нельзя'` (не `new`); 400 `null` в обязательном поле / год |
| `POST /trade-in/take/{trade_in_id}` | seller | → detail | 404; 409 `'Заявка на trade-in уже взята в работу'` (атомарно `WHERE seller_id IS NULL AND status='new'`, как `lead.take`) |
| `POST /trade-in/assign/{trade_in_id}` | admin | `TradeInAssignSchema` → detail | 404 заявка / `'Продавец не найден'` (не seller/заблокирован); 409 `'Закрытую заявку на trade-in нельзя переназначить'` (`accepted`/`rejected`). `new` → `evaluating` |
| `POST /trade-in/offer/{trade_in_id}` | seller-владелец, admin | `TradeInOfferSchema` → detail | 403 client; 404; 409 переход (только из `evaluating`) |
| `POST /trade-in/accept/{trade_in_id}` | client-владелец | → detail | 403 staff; 404; 409 (только из `offered`) |
| `POST /trade-in/reject/{trade_in_id}` | client-владелец (из `offered`); seller-владелец (из `evaluating`); admin (из `new`/`evaluating`/`offered`) | → detail | 404; 409 недопустимый для роли/статуса переход |
| `DELETE /trade-in/delete/{trade_in_id}` | client-владелец (только `new`), admin (любой) | → `{'message': 'Заявка на trade-in удалена'}` | 403 seller; 404; 409 `'Удалить можно только новую заявку на trade-in'` |

Детали:
- **create**: `TradeIn(**data.model_dump(), client_id=me, status=new, seller_id=None)`; `flush`;
  `notify_active_sellers(db, NotificationType.lead, f'Новая заявка на trade-in #{id}', current_user.id)`.
- **take / assign**: уведомление клиенту (`lead`) `'Ваша заявка на trade-in #<id> взята в оценку'`; assign — ещё новому
  продавцу `'Вам назначена заявка на trade-in #<id>'` и прежнему (если был) `'Заявка на trade-in #<id> передана другому продавцу'`.
- **offer**: `estimated_price`, `currency`, `status=offered` одним условным `UPDATE`. Уведомление клиенту (`lead`)
  `'Предложение по trade-in #<id>: <estimated_price> <currency>'`. AuditLog `trade_in_offer`
  (`{status}` → `{status, estimated_price, currency}`).
- **accept / reject**: уведомление второй стороне (клиенту, если отклонил staff; продавцу, если решил клиент; admin-решение —
  обеим, кроме инициатора) (`lead`). AuditLog `trade_in_accept` / `trade_in_reject` (`{status}` → `{status}`).
- **update** (client): цикл `setattr`; `year` > текущий+1 → 400; `null` для `brand_name/model_name/year/mileage` → 400
  `'Поле не может быть пустым'`.
- **delete**: физическое (cascade удалит `TradeInImage`); пути файлов собрать **до** `db.delete`, удалить с диска **после**
  `commit` (`unlink(missing_ok=True)`, только `Path(...).name`). Admin-удаление — AuditLog `trade_in_delete`.

### `trade_in_image_router` — `/trade-in-image`, `tags=['TradeInImage']`

Видимость фото — через видимость родительской заявки (`get_trade_in_or_404` / join `TradeIn` + те же условия).
Иначе 404 `'Фотография не найдена'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /trade-in-image/create` | client-владелец | multipart: `trade_in_id: int = Form()`, `trade_in_image: UploadFile = File()` → `TradeInImageDetailSchema` | 403 staff; 404 заявка; 409 `'Фото можно добавлять только к новой заявке или заявке на оценке'` (не `new`/`evaluating`); 413 > 5 МБ; 400 пустой файл / тип; 409 лимит `MAX_IMAGES_PER_TRADE_IN = 10` |
| `GET /trade-in-image/list?trade_in_id=` | все роли (по видимости заявки) | → `List[TradeInImageListSchema]`, `order_by(id)` | 401, 404 |
| `GET /trade-in-image/detail?trade_in_image_id=` | все роли | → detail | 401, 404 |
| `DELETE /trade-in-image/delete/{trade_in_image_id}` | client-владелец (заявка `new`/`evaluating`), admin | → `{'message': 'Фотография удалена'}` | 403 seller; 404; 409 статус |

Загрузка — **строго по образцу `create_car_image`**: `await file.read(MAX_IMAGE_SIZE + 1)`, сигнатура
`detect_image_extension` + совпадение с `ALLOWED_IMAGE_TYPES[content_type]`, имя `uuid4().hex + ext` (клиентское
`filename` не используется), запись файла → `db.add` → `commit`, при исключении `rollback` + `unlink`. Каталог —
`get_trade_in_images_dir()` = `Path(MEDIA_DIR) / 'trade_in_images'` (читать `MEDIA_DIR` в момент вызова — для тестов),
URL в БД — `/media/trade_in_images/<имя>`. Удаление файла — только `Path(db_value).name`. `PUT /update` нет.

### `favorite_router` — `/favorite`, `tags=['Favorite']`

Только **client** **[дефолт]** (ТЗ §3: избранное — функция клиента). Свои записи: `Favorite.user_id == me`, иначе 404
`'Запись избранного не найдена'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /favorite/create` | client | `FavoriteCreateSchema` → `FavoriteDetailSchema` | 403 staff; 404 авто (`get_car_or_404(..., current_user, only_visible=True)` — нет/удалено/`sold`/`withdrawn`); 409 `'Автомобиль уже в избранном'` (предпроверка + `IntegrityError` → `rollback` + 409) |
| `GET /favorite/list` | client | `skip`, `limit` → `List[FavoriteListSchema]`; join `Car`: `deleted_at IS NULL` и `status IN PUBLIC_CAR_STATUSES` **[дефолт]** (проданные/снятые скрываются, запись не удаляется); `joinedload(Favorite.car)`; `order_by(Favorite.id.desc())` | 401, 403 |
| `GET /favorite/detail?favorite_id=` | client | → detail (тот же фильтр по авто) | 404 |
| `DELETE /favorite/delete/{favorite_id}` | client | → `{'message': 'Автомобиль удалён из избранного'}` (физически; запись удаляется, даже если авто уже скрыто) | 404 чужая/нет |

`PUT /update` нет (менять нечего).

### `review_router` — `/review`, `tags=['Review']`

Видимость (`visible_reviews_query`) **[дефолт]**: join `Deal` с `Deal.deleted_at IS NULL`; admin — все; client — свои
(`client_id == me`); seller — о себе (`Review.seller_id == me`). Иначе 404 `'Отзыв не найден'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /review/create` | client | `ReviewCreateSchema` → `ReviewDetailSchema` | 403 staff; 404 `'Сделка не найдена'` (чужая/удалённая — через `visible_deals_query`); 409 `'Отзыв можно оставить только после выдачи автомобиля'` (статус ≠ `delivered`); 409 `'Отзыв по этой сделке уже оставлен'` (предпроверка + `IntegrityError`); 422 `stars` вне 1..5 |
| `GET /review/list` | все роли | `seller_id` (только admin, иначе игнор), `stars`, `skip`, `limit` → `List[ReviewListSchema]`, `order_by(created_at.desc(), id.desc())` | 401 |
| `GET /review/detail?review_id=` | все роли | → detail | 404 |
| `PUT /review/update/{review_id}` | client-автор | `ReviewUpdateSchema` → detail | 403 staff; 404; 400 `stars: null` |
| `DELETE /review/delete/{review_id}` | client-автор, admin | → `{'message': 'Отзыв удалён'}` (физически) | 403 seller; 404 |

Детали:
- create: `Review(**data.model_dump(), client_id=me, seller_id=deal.seller_id)`; уведомление продавцу (`deal`)
  `'Новый отзыв по сделке #<deal_id>: <stars>★'` **[дефолт]**.
- После удаления клиент может оставить отзыв заново (уникальность `deal_id` освобождается).
- Удаление админом (модерация) — AuditLog `review_delete` (`old_value`: `deal_id`, `stars`, `comment`).

### `credit_router` — `/credit`, `tags=['Credit']`

Доступ — **без входа** (`get_optional_user`, как каталог) **[дефолт]**: калькулятор не раскрывает данных, авто —
с публичной видимостью (`get_car_or_404(car_id, db, current_user, only_visible=True)`).

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /credit/calculate` | все / аноним | `CreditCalculateSchema` → `CreditResultSchema` | 400 `'Укажите автомобиль или цену'` (оба/ни одного из `car_id`/`price`); 404 авто; 400 `'Первоначальный взнос должен быть меньше цены'`; 422 валидация |
| `POST /credit/compare` | все / аноним | `CreditCompareSchema` → `List[CreditCompareItemSchema]` (в порядке `car_ids`) | 422 меньше 2 / больше 4 авто; 400 `'Автомобили в сравнении не должны повторяться'`; 404 любое авто; 400 `'Укажите ставку и срок вместе'` (только одно из двух) |

Расчёт (аннуитет, всё в `Decimal`):
```python
def calc_monthly_payment(loan: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    if loan == 0: return Decimal('0.00')
    if annual_rate == 0: return (loan / term_months).quantize(CENT, rounding=ROUND_HALF_UP)
    r = annual_rate / Decimal('1200')
    k = (1 + r) ** term_months          # Decimal ** int — точно в контексте prec=28
    return (loan * r * k / (k - 1)).quantize(CENT, rounding=ROUND_HALF_UP)
```
- `price` = `car.price` и `currency` = `car.currency` (при `car_id`) или из запроса; `loan_amount = price - down_payment`;
  `total_payment = monthly_payment * term_months + down_payment`? — **нет** **[дефолт]**: `total_payment = monthly_payment *
  term_months` (сумма выплат по кредиту), `overpayment = total_payment - loan_amount`. Всё `quantize(CENT)`.
- `down_payment == price` → 400 (кредит не нужен); `down_payment_percent` в сравнении — от цены каждого авто:
  `(price * percent / 100).quantize(CENT, ROUND_HALF_UP)`.
- В сравнении `credit = None`, если не переданы ставка и срок; валюты авто могут различаться — конвертации нет,
  у каждого результата своя `currency` **[дефолт]**.
- Ставку задаёт клиент **[дефолт]** (банков/ставок в модели нет).

### `statistic_router` — `/statistic`, `tags=['Statistic']`

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `GET /statistic/general` | admin | `date_from`, `date_to` → `StatisticGeneralSchema` | 401; 403 seller/client; 400 период |
| `GET /statistic/my` | seller | `date_from`, `date_to` → `StatisticSellerSchema` (для `current_user`) | 401; 403 admin/client; 400 |
| `GET /statistic/seller/{seller_id}` | admin | `date_from`, `date_to` → `StatisticSellerSchema` | 403; 404 `'Продавец не найден'` (нет или не seller); 400 |

Содержимое (период фильтрует по дате события, без периода — всё время):
- Сделки — `Deal.deleted_at IS NULL`; `deals_by_status` — по `created_at`; `revenue`, `delivered_count`,
  `avg_discount_percent` — по `delivered` с `delivered_at` в периоде; выручка = `final_price`, **раздельно по валютам**.
- Заявки (`leads_by_status`) — по `Lead.created_at`; trade-in — по `TradeIn.created_at`; скидки
  (`discounts_by_status`) — `DiscountRequest.seller_id`, без периода (нет `created_at`) **[дефолт]**;
  `discounts_pending` (general) — текущее количество `pending`.
- Отзывы — по `Review.created_at`; `avg_stars` см. «SQLite».
- `cars_by_status` (general) — текущее состояние склада (`Car.deleted_at IS NULL`), без периода.
- `clients_count` (general) — активные клиенты, без периода.
- `sellers` (general) — все продавцы (в т.ч. заблокированные, с `is_active`), сортировка по `delivered_count desc, id`.
- Seller-статистика: заявки/сделки/trade-in — `seller_id == продавец`; отзывы — `Review.seller_id`.
- Всё — `COUNT ... GROUP BY` (без N+1: одна групповая выборка на метрику, для `sellers` — `GROUP BY seller_id`),
  деньги — суммирование `Decimal` в Python.

---

## Бизнес-правила этапа

| ТЗ | Правило | Как проверяется |
|---|---|---|
| §5.10 | Отзыв только после `delivered`, один на сделку | `deal.status == delivered` иначе 409; предпроверка + `UNIQUE(deal_id)` → 409 |
| §3 client | Видит только свои объекты, чужой → 404 | trade-in, фото, избранное, отзывы — фильтр по `client_id/user_id == me` |
| §3 seller | Только свои (trade-in, отзывы о себе, своя статистика) | `seller_id == me`; `/statistic/general` → 403 |
| §3 admin | Видит/меняет всё, аналитика | admin проходит видимость, `general`, `seller/{id}`, удаление чужих отзывов/trade-in |
| §3 client | Сравнение — до 4 авто | `car_ids` `min_length=2, max_length=4` → 422 |
| §3 client | Кредитный калькулятор | `/credit/calculate`, аннуитет в `Decimal` |
| §1, §7 | Деньги `Decimal`, время UTC | калькулятор и выручка — `Decimal` + `quantize`; `UtcDatetimeOut`; сутки периода — UTC |
| §5.8 | Мягко удалённые не попадают в выборки | избранное/сравнение/кредит — `get_car_or_404`; отзывы и статистика — `Deal.deleted_at IS NULL`, `Car.deleted_at IS NULL` |
| §5.7 | Важные действия → AuditLog | `trade_in_offer/accept/reject/delete`, `review_delete` (`create_audit_log` из `deal.py`) |
| §6 | Пагинация | `skip`/`limit (le=100)` во всех `list` |
| CLAUDE.md | Загрузка файлов безопасна | сигнатура файла, лимит размера, серверное имя, `Path(...).name` при удалении |

---

## Миграции

**Не требуются.** db-specialist: `alembic upgrade head` → `alembic check` (ожидается «No new upgrade operations
detected»). Изменения `schema.py` на БД не влияют.

---

## Тесты

`tests/conftest.py` — дополнить:
- `media_dir`: ещё `monkeypatch.setattr('mysite.api.trade_in.MEDIA_DIR', str(tmp_path))` и `(tmp_path / 'trade_in_images').mkdir()`.
- `make_trade_in(**overrides)` (по умолчанию `client_user`, `Toyota`/`Corolla`, 2015, 120000 км, `status=new`),
  `make_trade_in_image(trade_in, name='x.jpg')`, `make_favorite(user, car)`, `make_review(deal, **overrides)`.
- `TradeInView`, `ReviewView` в кортеж `admin_session_local`.

`tests/test_trade_in.py`:
- create: `test_create_trade_in_ok` (`client_id == me`, `status new`, `seller_id None`, уведомления активным продавцам),
  `test_create_trade_in_ignores_server_fields` (`status`, `seller_id`, `estimated_price`, `client_id`),
  `test_create_trade_in_as_seller_403`, `test_create_trade_in_without_token_401`, `test_create_trade_in_future_year_400`,
  `test_create_trade_in_negative_mileage_422`, `test_create_trade_in_blank_brand_422`, `test_create_trade_in_cyrillic_ok`
  (`'Лада'` сохраняется как есть), `test_create_trade_in_active_limit_409`.
- list/detail: `test_list_client_sees_only_own`, `test_list_seller_sees_own_and_free`, `test_list_seller_not_sees_other_taken`,
  `test_list_admin_sees_all`, фильтр `status`, `only_free`, пагинация, `limit=101` → 422;
  **IDOR**: `test_detail_other_client_404`, `test_detail_other_seller_taken_404`, `test_detail_includes_images`,
  `test_detail_datetime_utc_offset`.
- переходы: `test_take_ok` (`evaluating`, уведомление клиенту), `test_take_already_taken_409`, `test_take_as_client_403`,
  `test_assign_admin_ok`, `test_assign_blocked_seller_404`, `test_assign_closed_409`, `test_offer_ok` (`estimated_price`
  Decimal-строкой, валюта, уведомление, AuditLog `trade_in_offer`), `test_offer_from_new_409`, `test_offer_other_seller_404`,
  `test_offer_zero_price_422`, `test_accept_ok`, `test_accept_not_offered_409`, `test_accept_as_seller_403`,
  `test_reject_by_client_offered_ok`, `test_reject_by_client_evaluating_409`, `test_reject_by_seller_evaluating_ok`,
  `test_reject_by_admin_new_ok`, parametrize переходы из `accepted`/`rejected` → 409.
- update: `test_update_client_new_ok`, `test_update_client_evaluating_409`, `test_update_other_client_404`,
  `test_update_as_seller_403`, `test_update_null_field_400`, `test_update_ignores_status_and_price`.
- delete: `test_delete_client_new_ok` (файлы фото удалены с диска), `test_delete_client_evaluating_409`,
  `test_delete_admin_any_ok` (AuditLog), `test_delete_seller_403`, `test_delete_other_client_404`.

`tests/test_trade_in_image.py` (с `media_dir`):
- `test_upload_jpeg_ok` (файл в `trade_in_images/`, URL `/media/trade_in_images/<hex>.jpg`, клиентское имя не используется),
  `test_upload_png_ok`, `test_upload_webp_ok`, `test_upload_fake_content_type_400`, `test_upload_empty_400`,
  `test_upload_too_large_413`, `test_upload_limit_409`, `test_upload_offered_409`, `test_upload_other_client_404`,
  `test_upload_as_seller_403`, `test_upload_path_traversal_filename_ignored` (`../../x.jpg`).
- `test_list_images_seller_owner_ok`, `test_list_images_seller_free_ok`, `test_list_images_other_client_404`,
  `test_detail_image_other_client_404`.
- `test_delete_image_owner_ok` (файл удалён), `test_delete_image_offered_409`, `test_delete_image_admin_ok`,
  `test_delete_image_seller_403`.

`tests/test_favorite.py`:
- `test_add_favorite_ok`, `test_add_favorite_duplicate_409`, `test_add_favorite_sold_car_404`, `test_add_favorite_deleted_car_404`,
  `test_add_favorite_unknown_car_404`, `test_add_favorite_as_seller_403`, `test_add_favorite_without_token_401`,
  `test_add_favorite_ignores_user_id`.
- `test_list_favorite_only_own` (вложенный `car`), `test_list_favorite_hides_sold_and_deleted`, пагинация,
  `test_detail_favorite_other_user_404`, `test_delete_favorite_ok`, `test_delete_favorite_other_user_404`,
  `test_delete_favorite_of_hidden_car_ok`, `test_same_car_two_clients_ok`.

`tests/test_review.py`:
- `test_create_review_delivered_ok` (`seller_id == deal.seller_id`, `client_id == me`, уведомление продавцу),
  parametrize `new`/`in_progress`/`reserved`/`paid`/`cancelled` → 409, `test_create_review_twice_409`,
  `test_create_review_other_client_deal_404`, `test_create_review_deleted_deal_404`, `test_create_review_as_seller_403`,
  parametrize `stars` `0`/`6` → 422, `test_create_review_ignores_seller_id`.
- `test_list_review_client_own`, `test_list_review_seller_about_self`, `test_list_review_admin_all`,
  `test_list_review_admin_filter_seller`, `test_detail_review_other_client_404`, `test_detail_review_other_seller_404`.
- `test_update_review_author_ok`, `test_update_review_other_client_404`, `test_update_review_seller_403`,
  `test_update_review_null_stars_400`.
- `test_delete_review_author_ok` (затем повторный create → ok), `test_delete_review_admin_ok` (AuditLog),
  `test_delete_review_seller_403`.

`tests/test_credit.py`:
- `test_calculate_known_annuity` (1 000 000, 12%, 12 мес → `monthly_payment '88848.79'`, `total '1066185.48'`,
  `overpayment '66185.48'`), `test_calculate_zero_rate` (1 200 000 / 12 → `'100000.00'`), `test_calculate_rounding_half_up`
  (1000, 0%, 3 → `'333.33'`), `test_calculate_by_car_id_uses_car_price_and_currency`, `test_calculate_anonymous_ok`,
  `test_calculate_down_payment_ok`, `test_calculate_down_payment_equal_price_400`, `test_calculate_both_car_and_price_400`,
  `test_calculate_neither_400`, `test_calculate_sold_car_404`, `test_calculate_deleted_car_404`,
  parametrize `term_months` `0`/`121`, `annual_rate` `-1`/`101`/`5.555` → 422, `test_calculate_no_float_artifacts`
  (строки денег с 2 знаками).
- `test_compare_two_ok`, `test_compare_four_ok` (порядок как в `car_ids`), `test_compare_five_422`, `test_compare_one_422`,
  `test_compare_duplicates_400`, `test_compare_hidden_car_404`, `test_compare_with_credit` (`down_payment_percent` от цены
  каждого авто), `test_compare_without_credit_null`, `test_compare_rate_without_term_400`, `test_compare_mixed_currency`.

`tests/test_statistic.py`:
- `test_general_as_admin_ok` (все ключи статусов присутствуют, нули), `test_general_as_seller_403`, `test_general_as_client_403`,
  `test_general_without_token_401`.
- `test_general_revenue_decimal_sum` (`100000.10 + 200000.20` → `'300000.30'`), `test_general_revenue_split_by_currency`,
  `test_general_excludes_deleted_deals_and_cars`, `test_general_avg_stars` (4 и 5 → `'4.50'`), `test_general_no_reviews_null`,
  `test_general_sellers_rows`.
- период: `test_period_filters_delivered_at`, `test_period_inclusive_date_to`, `test_period_invalid_400`.
- `test_my_as_seller_only_own` (данные `seller2` не попадают), `test_my_as_admin_403`, `test_seller_stat_admin_ok`,
  `test_seller_stat_not_seller_404`, `test_seller_stat_as_seller_403`.

`tests/test_admin.py` — `TradeInView`, `ReviewView`: список → 200 под админом, `/create` и `/edit/<id>` недоступны.

---

## Риски и открытые вопросы

Неблокирующие, решены дефолтом (автор может переопределить):
1. **Фото trade-in доступны по прямой ссылке** `/media/trade_in_images/<uuid>` без авторизации (nginx/StaticFiles отдают
   весь `/media/`). Защита — неугадываемое имя `uuid4` (122 бита). Строгая альтернатива — отдельная папка вне `/media`
   + эндпоинт выдачи с проверкой прав (+ правка nginx) — отдельная задача.
2. **Отзывы не публичные**: client — свои, seller — о себе, admin — все. Если нужен публичный блок отзывов — добавить
   анонимный `list` без `client_id`/`deal_id` в ответе.
3. **Сравнение stateless** (`POST /credit/compare` с `car_ids`), «список сравнения» не хранится (нет модели в ТЗ).
   Сравнение совмещено с кредитом (общий файл `credit.py` по ROADMAP).
4. **Ставку кредита вводит клиент**; срок 1–120 мес.; `total_payment` — только выплаты по кредиту (без взноса).
5. **Уведомления trade-in — тип `lead`, отзывов — `deal`** (новых значений `NotificationType` нет).
6. **Избранное — только client**; проданные/снятые/удалённые авто скрываются из списка, записи не удаляются.
7. **Trade-in**: лимит 5 активных на клиента; фото — только клиент-владелец, до 10 шт., пока заявка `new`/`evaluating`;
   `accepted` trade-in не связывается со сделкой (зачёт стоимости — вне ТЗ). `Lead` с `lead_type=trade_in` остаётся
   независимым (вопрос клиента), сущность trade-in — `/trade-in`.
8. **Статистика**: сутки периода в UTC (нет `tzdata`); `discounts_by_status` без периода (у `DiscountRequest` нет
   `created_at`); выручка не конвертируется между KGS и USD.
9. **SQLite `Numeric` = REAL** — денежные суммы только в Python через `Decimal`; при росте объёмов — хранить копейки
   `Integer` (миграция) или перейти на PostgreSQL.
10. **Межмодульные импорты**: `trade_in.py` ← `car_image.py`, `deal.py`, `notification.py`; `review.py`, `statistic.py` ←
    `deal.py`; `favorite.py`, `credit.py` ← `car.py`. Циклов нет (новые модули никто не импортирует, кроме `main.py`).

---

## Не делаем в этом этапе

- Изменения `models.py` и миграции; новые значения Enum.
- API `SalonSettings`, API журнала `/audit-log/*`, публичные отзывы, хранимый список сравнения.
- Банки/кредитные программы, график платежей, конвертация валют, экспорт статистики (CSV/Excel), графики по дням.
- Связь trade-in со сделкой/заявкой, зачёт стоимости trade-in в `final_price`.
- Защищённая выдача медиафайлов, правки nginx/docker-compose.
- Email/SMS/push — только записи `Notification`.
- Новые модули/утилиты, `services/`.

---

## Порядок работы

1. **db-specialist** — без изменений моделей: `alembic upgrade head` + `alembic check`; подтвердить, что миграция не нужна.
2. **coder** (по порядку):
   1. `mysite/db/schema.py` — новые типы, правки `TradeIn*`/`TradeInImage*`/`Favorite*`/`Review*`, новые `TradeInOfferSchema`,
      `TradeInAssignSchema`, `Credit*`, `Statistic*`; удалить `TradeInImageCreateSchema`, `TradeInImageUpdateSchema`.
   2. `mysite/api/favorite.py`.
   3. `mysite/api/review.py`.
   4. `mysite/api/trade_in.py` — `trade_in_router` + `trade_in_image_router`.
   5. `mysite/api/credit.py`.
   6. `mysite/api/statistic.py`.
   7. `main.py` — импорты, 6 `include_router`, `os.makedirs(.../trade_in_images)`.
   8. `mysite/admin/view.py`, `setup.py` — `TradeInView`, `ReviewView` (read-only).
   9. Проверка: `.venv/Scripts/python.exe -c "import main"`, `uvicorn main:auto_app` → `/docs`.
3. **tester** — `conftest.py` (media_dir, фикстуры, view) + 6 новых файлов тестов, дополнение `test_admin.py`;
   `.venv/Scripts/python.exe -m pytest -q`.
4. **reviewer + security-auditor** — по `git diff`; особое внимание: IDOR (trade-in, фото, избранное, отзывы → 404 на чужое),
   загрузка файлов (сигнатура, размер, серверное имя, удаление только по `name`), серверные поля не принимаются,
   деньги только `Decimal` (калькулятор, выручка), `/statistic/general` недоступна seller, мягко удалённые сделки/авто
   не попадают в отзывы и статистику.
5. **coder** — исправления 🔴 critical.
6. Отметить чекбоксы в `docs/ROADMAP.md`, отчёт + предложенный коммит
   `feat(api): add trade-in, favorites, reviews, credit calculator and statistics (stage 6)` → **СТОП**.
