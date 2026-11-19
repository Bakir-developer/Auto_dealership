# План: Этап 4 — CRM (заявки, заметки, тест-драйвы, уведомления)

## Открытые вопросы (блокирующие)

Нет. Всё, что помечено **[дефолт]**, — решение архитектора по умолчанию; автор может переопределить
до начала работы coder'а (сводка — в разделе «Риски и открытые вопросы»). Отдельно на подтверждение
вынесен п. 1 «Рисков» — новая зависимость `tzdata` (без неё `ZoneInfo('Asia/Bishkek')` не работает на Windows).

---

## Цель и границы

Цель: CRM салона — заявки клиентов (`Lead`) с взятием в работу продавцом и внутренними заметками
(`LeadNote`), запись на тест-драйв (`TestDrive`) с проверкой рабочих часов салона, пересечений, статуса авто
и «не в прошлое», машины состояний заявки и тест-драйва, внутренние уведомления (`Notification`), тесты.

Границы:
- Новые файлы в `mysite/` — **только** `mysite/api/lead.py`, `mysite/api/test_drive.py`, `mysite/api/notification.py`.
  Никаких `utils.py`/`services/`. Вспомогательные функции — внутри этих модулей
  (`create_notification` — в `notification.py`, импортируется из `lead.py` и `test_drive.py`).
- **Изменений моделей нет. Миграции нет.** Все поля, FK, индексы и `CHECK end_time > start_time`
  уже есть в `initial` (`f907a8edf483`).
- Ничего из этапов 5–6 (Deal, DiscountRequest, бронь, фоновая задача, AuditLog, TradeIn, Favorite, Review,
  credit, statistic).

Текущее состояние (проверено):
- `models.py`: `Lead`, `LeadNote` (`cascade='all, delete-orphan'` от Lead), `TestDrive`, `Notification`,
  `SalonSettings` (`work_start`/`work_end: Time`, `test_drive_minutes=60`, `CHECK id = 1`, `CHECK work_end > work_start`),
  все Enum (`LeadType`, `LeadStatus`, `TestDriveStatus`, `NotificationType`) — объявлены, связи двусторонние.
- `schema.py`: есть `Lead*`, `LeadNote*`, `TestDrive*`, `Notification*` схемы (требуют точечных правок, см. «Схемы»).
- `dependencies.py`: `get_current_user`, `get_optional_user`, `require_role`.
- `car.py`: `get_car_or_404(car_id, db, current_user, only_visible)`, `PUBLIC_CAR_STATUSES`, `is_staff`, `STAFF_ROLES` —
  переиспользуем импортом (`from mysite.api.car import get_car_or_404, is_staff`), не копируем.
- `config.py`: `SALON_TIMEZONE = 'Asia/Bishkek'` уже есть.
- `seed.py`: создаёт `SalonSettings(id=1, 09:00–18:00, 60 мин)`.
- `tests/conftest.py`: `db`, `client`, `make_user`, `auth_headers`, `admin`, `seller`, `client_user`, `brand`, `car_model`,
  `make_car`, `admin_session_local`. Фикстуры `SalonSettings` нет.
- `requirements.txt`: **нет `tzdata`**.

---

## Файлы (создать / изменить)

### Создать
| Путь | Что |
|---|---|
| `mysite/api/notification.py` | `notification_router` (`prefix='/notification'`, `tags=['Notification']`) + функции `create_notification(db, user_id, notification_type, text)`, `notify_active_sellers(db, notification_type, text, exclude_user_id=None)`. |
| `mysite/api/lead.py` | `lead_router` (`prefix='/lead'`, `tags=['Lead']`) и `lead_note_router` (`prefix='/lead-note'`, `tags=['LeadNote']`) — **оба в одном файле** (ROADMAP: «lead.py (+ LeadNote)») **[дефолт]**. |
| `mysite/api/test_drive.py` | `test_drive_router` (`prefix='/test-drive'`, `tags=['TestDrive']`). |
| `tests/test_lead.py`, `tests/test_lead_note.py`, `tests/test_test_drive.py`, `tests/test_notification.py` | тесты. |

### Изменить
| Путь | Что |
|---|---|
| `requirements.txt` | `tzdata==<актуальная>` (см. «Время»). Установить в `.venv`. |
| `mysite/db/schema.py` | точечно (см. «Схемы»): типы `UtcDatetime`, `UtcDatetimeOut`, `Text2000`, `Text5000`; правки `Lead*`, `LeadNote*`, `TestDrive*`; новые `LeadAssignSchema`, `TestDriveAssignSchema`. |
| `main.py` | `from mysite.api import ... lead, notification, test_drive`; `include_router` по строке: `lead.lead_router`, `lead.lead_note_router`, `test_drive.test_drive_router`, `notification.notification_router`. |
| `mysite/admin/view.py` | `LeadView`, `TestDriveView` — только чтение (`can_create = can_edit = can_delete = False`) **[дефолт]**. |
| `mysite/admin/setup.py` | `admin.add_view(LeadView)`, `admin.add_view(TestDriveView)`. |
| `tests/conftest.py` | фикстуры `salon_settings`, `make_lead`, `make_test_drive`, `future_slot`; новые view в кортеж `admin_session_local`. |
| `docs/ROADMAP.md` | чекбоксы этапа 4, строка «Текущий этап». |

---

## Модели / поля / связи / ограничения

**Изменений моделей нет, миграции нет.** Используются как есть:
- `Lead` — `client_id FK index`, `car_id FK nullable`, `lead_type Enum`, `status Enum default new`,
  `seller_id FK nullable index`, `comment Text`, `created_at`; связи `client`, `seller` (`foreign_keys` указаны), `car`,
  `notes` (cascade delete-orphan).
- `LeadNote` — `lead_id FK index`, `seller_id FK` (автор заметки; для admin — id админа), `note Text`, `created_at`.
- `TestDrive` — `car_id`, `client_id`, `seller_id nullable` (все с index), `start_time`/`end_time DateTime(timezone=True)`,
  `status default scheduled`, `created_at`, `CHECK end_time > start_time`.
- `Notification` — `user_id FK index`, `notification_type`, `text Text`, `is_read default False`, `created_at`.
- `SalonSettings` — читается `db.query(SalonSettings).filter(SalonSettings.id == 1).first()`.

Осознанно **не добавляем**: индекс `(car_id, start_time)` у `test_drive`, `updated_at` у Lead/TestDrive,
статус `cancelled` у Lead, поле «причина отмены» у TestDrive — не требуются ТЗ; при объёмах одного салона
существующих индексов хватает.

---

## Время (UTC / SQLite / часовой пояс салона)

1. **Вход** (`start_time`, фильтры `date_from`/`date_to`) — тип `UtcDatetime` в `schema.py`:
   `Annotated[AwareDatetime, AfterValidator(to_utc)]`, где `to_utc(v) = v.astimezone(timezone.utc)`.
   `AwareDatetime` (Pydantic v2) отклоняет naive datetime → **422** автоматически. Строка `'2026-11-20T10:00:00+06:00'`
   превращается в `2026-11-20 04:00:00+00:00`. Для query-параметров — `date_from: UtcDatetime | None = None`
   (если FastAPI не применит `AfterValidator` к query — вызвать `astimezone(timezone.utc)` в роутере; tester проверяет).
2. **Запись**: в модель идут только UTC-значения. SQLite (SQLAlchemy `DATETIME`) хранит строку
   `YYYY-MM-DD HH:MM:SS.ffffff` без смещения → для сравнений в SQL (пересечения, фильтры) все bind-параметры
   **обязательно** предварительно в UTC; тогда лексикографическое сравнение строк корректно.
3. **Чтение**: SQLite возвращает naive → перед сравнением в Python `value.replace(tzinfo=timezone.utc)`
   (функция `as_utc(value)` в `test_drive.py`).
4. **Ответ**: в `TestDriveListSchema`/`TestDriveDetailSchema` поля `start_time`, `end_time`, `created_at` — тип
   `UtcDatetimeOut = Annotated[datetime, AfterValidator(lambda v: v if v.tzinfo else v.replace(tzinfo=timezone.utc))]`
   → клиент получает `...+00:00`/`Z`, а не naive **[дефолт]**. Для Lead/Notification — так же (`created_at`) **[дефолт]**,
   чтобы клиент мог корректно показать время. Остальные схемы прошлых этапов не трогаем.
5. **Рабочие часы** — в `ZoneInfo(SALON_TIMEZONE)` (`from zoneinfo import ZoneInfo`): `local_start = start.astimezone(tz)`,
   `local_end = end.astimezone(tz)`; условие: `local_start.date() == local_end.date()` и
   `settings.work_start <= local_start.time()` и `local_end.time() <= settings.work_end`.
   `ZoneInfo` на Windows требует пакет `tzdata` (в Docker `python:3.12` системная база есть, но ставим везде одинаково).
6. Текущее время — только `datetime.now(timezone.utc)`.
7. Тексты уведомлений показывают время **в часовом поясе салона**: `local_start.strftime('%d.%m.%Y %H:%M')`.

---

## Схемы

Добавить в `schema.py` (рядом с `Money`, `Year` …):
- `UtcDatetime`, `UtcDatetimeOut` (см. «Время»), функция `to_utc`.
- `Text2000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]`,
  `Text5000 = ... max_length=5000`.

| Схема | Было | Станет |
|---|---|---|
| `LeadCreateSchema` | `car_id`, `lead_type`, `comment: str \| None` | `comment: Text2000 \| None = None` |
| `LeadUpdateSchema` | `status`, `comment` | `status: LeadStatus \| None`, `comment: Text2000 \| None` (права на поля — в роутере) |
| `LeadAssignSchema` | — | **новая**: `seller_id: int` |
| `LeadListSchema`, `LeadDetailSchema` | `created_at: datetime` | `created_at: UtcDatetimeOut`. Заметки в `LeadDetailSchema` **не включаем** (их не должен видеть client). |
| `LeadNoteCreateSchema` | `lead_id`, `note: str (min_length=1)` | `note: Text5000` |
| `LeadNoteUpdateSchema` | `note: str \| None (min_length=1)` | `note: Text5000 \| None = None` |
| `LeadNoteList/DetailSchema` | — | `created_at: UtcDatetimeOut` |
| `TestDriveCreateSchema` | `car_id`, `start_time: datetime` | `start_time: UtcDatetime` |
| `TestDriveUpdateSchema` | `start_time`, `status` | **только** `start_time: UtcDatetime \| None = None` — статус меняется действиями (`confirm`/`complete`/`cancel`), не через update |
| `TestDriveAssignSchema` | — | **новая**: `seller_id: int` |
| `TestDriveList/DetailSchema` | `datetime` | `start_time`, `end_time`, `created_at`: `UtcDatetimeOut` |
| `NotificationUpdateSchema` | `is_read: bool \| None` | без изменений (явный `null` → 400 в роутере) |
| `NotificationList/DetailSchema` | — | `created_at: UtcDatetimeOut` |

**Не принимаются от клиента** (берёт сервер): `Lead.client_id` (= `current_user.id`), `Lead.seller_id` (только через
`take`/`assign`), `Lead.status` при создании (`new`); `LeadNote.seller_id` (= автор); `TestDrive.client_id`,
`TestDrive.seller_id` (через `confirm`/`assign`), `TestDrive.end_time` (= `start_time + test_drive_minutes`),
`TestDrive.status`; `Notification` — целиком сервер (нет `NotificationCreateSchema` и эндпоинта создания).
Лишние поля в теле Pydantic игнорирует — тесты это проверяют.

---

## Эндпоинты

Общие правила: `response_model` всегда; пагинация `skip: int = Query(0, ge=0)`, `limit: int = Query(20, ge=1, le=100)`;
401 — нет/плохой токен, 403 — `'Недостаточно прав'` (роль), **чужой объект → 404** для client **и** seller **[дефолт]**
(не раскрываем существование), 409 — недопустимый переход/конфликт, 400 — некорректные данные.
Все ручки этапа требуют входа (`get_current_user` / `require_role`).

### `lead_router` — `/lead`, `tags=['Lead']`

Видимость заявки (`get_lead_or_404(lead_id, db, current_user)`):
- admin — любая;
- client — `client_id == current_user.id`;
- seller — `seller_id == current_user.id` **или** «свободная»: `seller_id IS NULL AND status == new` (чтобы её можно было
  взять) **[дефолт]**; иначе 404 `'Заявка не найдена'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /lead/create` | client | `LeadCreateSchema` → `LeadDetailSchema` | 401, 403 (admin/seller), 404 `'Автомобиль не найден'`, 400 `'Для заявки на тест-драйв укажите автомобиль'`, 409 `'У вас уже есть активная заявка по этому автомобилю'`, 422 |
| `GET /lead/list` | admin, seller, client | `status`, `lead_type`, `only_free: bool = False` (seller/admin: только свободные), `seller_id` (только admin), `skip`, `limit` → `List[LeadListSchema]`, `order_by(created_at.desc(), id.desc())` | 401, 422 |
| `GET /lead/detail?lead_id=` | все роли (видимость выше) | → `LeadDetailSchema` | 401, 404 |
| `POST /lead/take/{lead_id}` | seller | → `LeadDetailSchema` | 401, 403, 404, 409 `'Заявка уже взята в работу'` |
| `POST /lead/assign/{lead_id}` | admin | `LeadAssignSchema` → `LeadDetailSchema` | 401, 403, 404 `'Заявка не найдена'` / `'Продавец не найден'`, 409 `'Закрытую заявку нельзя переназначить'` |
| `PUT /lead/update/{lead_id}` | admin, seller, client | `LeadUpdateSchema` → `LeadDetailSchema` | 401, 404, 403 (поле не по роли), 400 явный `null`, 409 переход |
| `DELETE /lead/delete/{lead_id}` | admin; client (своя, `new`) | → `{'message': 'Заявка удалена'}` (жёсткое, заметки каскадом) | 401, 403 seller, 404, 409 `'Удалить можно только новую заявку'` (client) |

Детали:
- **create**: `client_id = current_user.id`, `status = new`, `seller_id = None`.
  - `car_id` задан → `get_car_or_404(car_id, db, current_user, only_visible=True)` (удалённые/скрытые от публики
    `sold`/`withdrawn` → 404).
  - `lead_type == test_drive` и `car_id is None` → 400 **[дефолт]**; для `purchase`/`trade_in`/`question` `car_id` необязателен.
  - Антидубль **[дефолт]**: у клиента уже есть заявка с тем же `lead_type` и тем же `car_id` (включая `IS NULL` ↔ `IS NULL`
    для `car_id` не проверяем — вопросов без авто может быть много; проверка только при `car_id is not None`)
    в статусе `new`/`in_progress` → 409.
  - Уведомление `lead` всем активным продавцам: `'Новая заявка #<id> (<тип>)'`.
- **list**: client — свои; seller — свои + свободные (`only_free=True` → только свободные); admin — все (+ фильтр `seller_id`).
  `seller_id`-фильтр от не-админа игнорируется **[дефолт]**.
- **take** (seller): заявка должна быть видна (иначе 404); условный атомарный `UPDATE`:
  `db.query(Lead).filter(Lead.id == lead_id, Lead.seller_id.is_(None), Lead.status == LeadStatus.new)
  .update({'seller_id': current_user.id, 'status': LeadStatus.in_progress}, synchronize_session=False)`;
  `rowcount == 0` → 409. Затем `refresh`. Уведомление клиенту: `'Ваша заявка #<id> взята в работу'`.
- **assign** (admin): продавец — `UserProfile.role == seller` и `is_active` → иначе 404 `'Продавец не найден'`.
  Статус `closed`/`rejected` → 409. Ставит `seller_id`; `new` → `in_progress`. Уведомления: новому продавцу
  (`'Вам назначена заявка #<id>'`), прежнему продавцу при переназначении (`'Заявка #<id> передана другому продавцу'`),
  клиенту — только если статус был `new`.
- **update** по ролям:
  - client: только `comment` и только пока `status == new` (иначе 409 `'Заявку в работе изменить нельзя'`);
    `status` в теле → 403 `'Клиент не может менять статус заявки'`.
  - seller (только своя, `seller_id == me`; свободная → 404 на update): только `status`; `comment` в теле → 403
    `'Комментарий клиента менять нельзя — используйте заметки'`.
  - admin: `status` и `comment`.
  - Машина состояний (`LEAD_TRANSITIONS`), иначе 409 `'Недопустимый переход статуса заявки'`:
    `new → rejected` (admin); `in_progress → closed | rejected` (admin, seller-владелец);
    `closed`, `rejected` — финальные. `new → in_progress` через update запрещён (только `take`/`assign`) → 409.
    Тот же статус → 409.
  - Явный `null` в `status` → 400 `'Поле не может быть пустым'`; `comment: null` (admin/client) — допустим (очистка).
  - Смена статуса на `closed`/`rejected` → уведомление клиенту `'Заявка #<id>: <закрыта|отклонена>'`.
- **delete**: admin — любую; client — свою в `new` (иначе 409; чужую — 404); seller → 403.

### `lead_note_router` — `/lead-note`, `tags=['LeadNote']` (в `lead.py`)

Доступ: admin, seller (`require_role(admin, seller)`); client → 403. Seller работает только с заметками **своих**
заявок (`Lead.seller_id == me`); заметки к чужой/свободной заявке → 404 `'Заявка не найдена'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /lead-note/create` | admin, seller | `LeadNoteCreateSchema` → `LeadNoteDetailSchema` | 401, 403, 404, 422 (пустая/пробелы/>5000) |
| `GET /lead-note/list?lead_id=` | admin, seller | `skip`, `limit` → `List[LeadNoteListSchema]`, `order_by(created_at.asc(), id.asc())` | 401, 403, 404 |
| `GET /lead-note/detail?lead_note_id=` | admin, seller | → `LeadNoteDetailSchema` | 401, 403, 404 `'Заметка не найдена'` |
| `PUT /lead-note/update/{lead_note_id}` | автор или admin | `LeadNoteUpdateSchema` → `LeadNoteDetailSchema` | 401, 403 `'Можно изменять только свои заметки'`, 404, 400 явный `null` |
| `DELETE /lead-note/delete/{lead_note_id}` | автор или admin | → `{'message': 'Заметка удалена'}` | 401, 403, 404 |

- `seller_id = current_user.id` (для admin — id админа) **[дефолт]**.
- Заметки к `closed`/`rejected` заявкам разрешены (итоговые комментарии) **[дефолт]**.
- Seller видит все заметки своей заявки (включая заметки прежнего продавца / админа); после переназначения прежний
  продавец теряет доступ к заявке и её заметкам (404).
- Уведомлений нет.

### `test_drive_router` — `/test-drive`, `tags=['TestDrive']`

Видимость (`get_test_drive_or_404`): admin — любой; client — `client_id == me`; seller — `seller_id == me` или свободный
(`seller_id IS NULL AND status == scheduled`) **[дефолт]**; иначе 404 `'Тест-драйв не найден'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /test-drive/create` | client | `TestDriveCreateSchema` → `TestDriveDetailSchema` | 401, 403, 404 авто, 409 статус авто, 400 прошлое/часы/горизонт, 409 пересечения, 503 нет настроек, 422 naive |
| `GET /test-drive/list` | все роли | `status`, `car_id`, `date_from`, `date_to` (`UtcDatetime`, по `start_time`), `only_free` (seller/admin), `skip`, `limit` → `List[TestDriveListSchema]`, `order_by(start_time.asc(), id.asc())` | 400 `'Некорректный диапазон фильтра'`, 422 |
| `GET /test-drive/detail?test_drive_id=` | все роли | → `TestDriveDetailSchema` | 404 |
| `PUT /test-drive/update/{test_drive_id}` | client (свой), seller (свой), admin | `TestDriveUpdateSchema` (перенос времени) → `TestDriveDetailSchema` | 400 `'Укажите новое время'` (нет/`null`), 404, 409 статус, + все проверки create |
| `POST /test-drive/assign/{test_drive_id}` | admin | `TestDriveAssignSchema` → detail | 404 тест-драйв/продавец, 409 статус, 409 пересечение по продавцу |
| `POST /test-drive/confirm/{test_drive_id}` | seller, admin | → detail | 404, 409 переход, 409 `'Сначала назначьте продавца'` (admin без продавца), 409 пересечение по продавцу, 409 статус авто, 400 `'Время тест-драйва уже прошло'` |
| `POST /test-drive/complete/{test_drive_id}` | seller (свой), admin | → detail | 404, 409 переход, 409 `'Тест-драйв ещё не начался'` |
| `POST /test-drive/cancel/{test_drive_id}` | client (свой), seller (свой), admin | → detail | 404, 409 переход |
| `DELETE /test-drive/delete/{test_drive_id}` | admin | → `{'message': 'Тест-драйв удалён'}` (жёсткое) | 401, 403, 404 |

**Машина состояний** (`TEST_DRIVE_TRANSITIONS`), иначе 409 `'Недопустимый переход статуса тест-драйва'`:
`scheduled → confirmed | cancelled`; `confirmed → completed | cancelled`; `completed`, `cancelled` — финальные.

**create** (порядок проверок):
1. Настройки: `SalonSettings id=1` нет → 503 `'Настройки салона не заданы, обратитесь к администратору'` **[дефолт]**.
2. Авто: `get_car_or_404(car_id, db, current_user, only_visible=True)` (удалено / `sold` / `withdrawn` → 404 для client);
   `car.status != available` → 409 `'Тест-драйв для этого автомобиля недоступен'` (`reserved` по ТЗ §5.4,
   `in_transit` — авто физически нет в салоне **[дефолт]**).
3. `start = start_time` (уже UTC), `end = start + timedelta(minutes=settings.test_drive_minutes)`.
4. Не в прошлое: `start <= now` → 400 `'Нельзя записаться на тест-драйв в прошлом'`.
5. Горизонт: `start > now + 30 дней` → 400 `'Запись возможна не более чем на 30 дней вперёд'`
   (константа `MAX_DAYS_AHEAD = 30` в модуле) **[дефолт]**.
6. Рабочие часы (см. «Время» п. 5) → 400 `'Тест-драйв возможен только в рабочие часы салона (09:00–18:00)'`
   (часы подставляются из настроек).
7. Пересечение по авто: существует `TestDrive` с `car_id == car_id`, `status IN (scheduled, confirmed)`,
   `start_time < end AND end_time > start` (интервалы полуоткрытые: стык 10:00–11:00 и 11:00–12:00 — **не** пересечение)
   → 409 `'Автомобиль уже занят на это время'`.
8. Пересечение по клиенту **[дефолт]**: то же условие по `client_id == me` → 409 `'У вас уже есть тест-драйв на это время'`.
9. `TestDrive(car_id, client_id=me, seller_id=None, start_time=start, end_time=end, status=scheduled)`; commit.
10. Уведомление `test_drive` всем активным продавцам: `'Новая запись на тест-драйв #<id> на <дд.мм.гггг чч:мм>'`.

Функция `check_slot(db, car_id, client_id, seller_id, start, end, exclude_id=None)` — проверки 7, 8 и по продавцу
(если `seller_id` задан): `seller_id == seller_id`, активные статусы, пересечение → 409
`'У продавца уже есть тест-драйв на это время'`. `exclude_id` — исключить текущую запись при переносе.

**update (перенос)**: статус `scheduled`/`confirmed`, иначе 409 `'Перенести можно только запланированный тест-драйв'`;
повторяются проверки 1–8 + по продавцу (если назначен), с `exclude_id`; client переносит только свой, seller — только
свой (свободный → 404 на update); после переноса `status = scheduled` (повторное подтверждение) **[дефолт]**, `seller_id`
сохраняется. Уведомление другой стороне: client перенёс → продавцу (если назначен); seller/admin перенёс → клиенту.

**assign** (admin): продавец — активный `seller` (иначе 404 `'Продавец не найден'`); статус `scheduled`/`confirmed`
(иначе 409); проверка пересечения по продавцу (`exclude_id`); ставит `seller_id`. Уведомления: продавцу; прежнему
продавцу при переназначении.

**confirm**: seller — если `seller_id is None` → становится `me`; если `seller_id != me` → 404. Admin — нужен назначенный
продавец (иначе 409). Проверки: переход `scheduled → confirmed`; `start_time > now` (иначе 400); авто не удалено и
`status == available` (иначе 409 — авто могли перевести в `withdrawn`); пересечение по продавцу (`exclude_id`).
Уведомление клиенту `'Тест-драйв #<id> на <время> подтверждён'`.

**complete**: `confirmed → completed`; `now >= start_time` иначе 409. Уведомлений нет.

**cancel**: из `scheduled`/`confirmed`. Client — свой; seller — свой (свободный → 404); admin — любой.
Отменять прошедшие разрешено (неявка) **[дефолт]**. Уведомление другой стороне (как при переносе).

**list/detail**: `date_from > date_to` → 400. Seller по умолчанию видит свои + свободные; `only_free=True` — только свободные.

Конкурентность: обработчики `async def` выполняют синхронные запросы без `await` между проверкой и `commit`, uvicorn —
один воркер → проверки пересечений и `commit` не перемежаются. Coder **не добавляет `await`** внутри этих блоков.
`take` у заявки — дополнительно условный `UPDATE` (дёшево и надёжно).

### `notification_router` — `/notification`, `tags=['Notification']`

Все роли, только **свои** уведомления (admin — тоже только свои, это личный ящик **[дефолт]**); чужое → 404
`'Уведомление не найдено'`.

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `GET /notification/list` | любой вошедший | `is_read: bool \| None`, `skip`, `limit` → `List[NotificationListSchema]`, `order_by(created_at.desc(), id.desc())` | 401, 422 |
| `GET /notification/detail?notification_id=` | любой | → `NotificationDetailSchema` | 401, 404 |
| `GET /notification/unread-count` | любой | → `{'count': n}` | 401 |
| `PUT /notification/update/{notification_id}` | любой | `NotificationUpdateSchema` → detail | 401, 404, 400 явный `null` |
| `POST /notification/read-all` | любой | → `{'message': 'Уведомления прочитаны', 'count': n}` (bulk `update` по своим непрочитанным) | 401 |
| `DELETE /notification/delete/{notification_id}` | любой | → `{'message': 'Уведомление удалено'}` | 401, 404 |

Эндпоинта создания нет. Функции модуля:
- `create_notification(db, user_id, notification_type, text)` — `db.add(Notification(...))` **без commit** (commit делает
  вызывающий роутер в той же транзакции, что и основное действие).
- `notify_active_sellers(db, notification_type, text, exclude_user_id=None)` — по одному уведомлению каждому
  `UserProfile.role == seller AND is_active`.
- Уведомления не создаются самому инициатору действия и заблокированным пользователям.

**Когда создаются уведомления (этап 4)**:

| Событие | Кому | Тип |
|---|---|---|
| Заявка создана | всем активным продавцам | `lead` |
| Заявка взята (`take`) | клиенту | `lead` |
| Заявка назначена (`assign`) | новому продавцу; прежнему продавцу; клиенту, если была `new` | `lead` |
| Заявка `closed`/`rejected` | клиенту | `lead` |
| Тест-драйв создан | всем активным продавцам | `test_drive` |
| Тест-драйв назначен (`assign`) | новому продавцу; прежнему продавцу | `test_drive` |
| Тест-драйв подтверждён | клиенту | `test_drive` |
| Тест-драйв перенесён / отменён | другой стороне (клиенту или назначенному продавцу) | `test_drive` |

---

## Бизнес-правила этапа

| ТЗ | Правило | Как проверяется |
|---|---|---|
| §3 seller | Берёт заявки в работу | `POST /lead/take` — условный `UPDATE` (`seller_id IS NULL AND status=new`), второй → 409 |
| §3 seller | Работает только со своими заявками | update/note/take-видимость по `seller_id == me`; чужая → 404 |
| §3 seller | Заметки по клиенту (`LeadNote`) | `/lead-note/*`, client → 403, автор — `current_user` |
| §3 client | Заявка на покупку, запись на тест-драйв | create только `client`; `client_id = current_user.id` |
| §3 client | Видит только свои; чужое → 404 | `get_lead_or_404`, `get_test_drive_or_404`, notification по `user_id` |
| §3 admin | Видит и меняет всё | admin проходит видимость, `assign`, `delete` |
| §5.4 | Только в рабочие часы (Asia/Bishkek) | `ZoneInfo(SALON_TIMEZONE)`, `work_start`/`work_end` из `SalonSettings`; конец ≤ `work_end`, тот же день |
| §5.4 | Без пересечений по авто | `check_slot`: активные статусы, `start < end' AND end > start'` |
| §5.4 | Без пересечений по продавцу | `check_slot` при `assign`/`confirm`/переносе с назначенным продавцом |
| §5.4 | Не на reserved/sold | `car.status == available` (create, update, confirm), иначе 409; sold/withdrawn для client — 404 |
| §5.4 | Не в прошлое | `start_time > now(UTC)` (create, update, confirm) |
| §5.4 | Длительность — `test_drive_minutes` | `end_time` считает сервер, от клиента не принимается |
| §1, CLAUDE.md | Время в UTC; naive → 422; aware → `astimezone(utc)` | `UtcDatetime` (`AwareDatetime` + `to_utc`), ответы `UtcDatetimeOut` |
| §4.1 | Статусы `LeadStatus` / `TestDriveStatus` | `LEAD_TRANSITIONS`, `TEST_DRIVE_TRANSITIONS`, иначе 409 |
| §4.1 | `NotificationType` | `lead`, `test_drive` используются на этом этапе |
| §6 | Пагинация списков | `skip`/`limit (le=100)` во всех `/list` |

---

## Миграции

Не требуются. db-specialist: `alembic upgrade head` → `alembic check` (или пустой `--autogenerate`, который удаляется) —
подтвердить, что модели и БД совпадают. Изменения `schema.py` на БД не влияют.

---

## Тесты

`tests/conftest.py` — дополнить:
- `salon_settings(db)` — `SalonSettings(id=1, work_start=time(9, 0), work_end=time(18, 0), test_drive_minutes=60, ...)`.
- `future_slot(days=1, hour=10, minute=0)` — хелпер: `datetime.combine(today_bishkek + days, time(hour, minute),
  tzinfo=ZoneInfo('Asia/Bishkek'))` → ISO-строка с `+06:00`. Тесты не зависят от текущего часа.
- `make_lead(**overrides)`, `make_test_drive(**overrides)` — создание напрямую в БД (UTC-значения).
- второй продавец/клиент — через `make_user('seller2', UserRole.seller)` и т.п.
- `LeadView`, `TestDriveView` в кортеж `admin_session_local`.

`tests/test_lead.py`:
- create: `test_create_lead_as_client_ok` (`client_id == me`, `status == new`, `seller_id is None`),
  `test_create_lead_ignores_client_id_seller_id_status`, `test_create_lead_as_seller_403`, `..._as_admin_403`,
  `..._without_token_401`, `test_create_lead_unknown_car_404`, `test_create_lead_deleted_car_404`,
  `test_create_lead_sold_car_404`, `test_create_lead_test_drive_without_car_400`, `test_create_lead_question_without_car_ok`,
  `test_create_lead_duplicate_active_409`, `test_create_lead_duplicate_after_closed_ok`,
  `test_create_lead_comment_too_long_422`, `test_create_lead_invalid_type_422`,
  `test_create_lead_notifies_active_sellers` (заблокированному — нет).
- list: `test_list_lead_client_sees_only_own`, `test_list_lead_seller_sees_own_and_free`,
  `test_list_lead_seller_not_sees_other_sellers`, `test_list_lead_only_free`, `test_list_lead_admin_sees_all`,
  `test_list_lead_admin_filter_seller_id`, фильтры `status`/`lead_type`, пагинация, `limit=101` → 422.
- detail: свой → 200; **IDOR**: `test_detail_lead_other_client_404`, `test_detail_lead_other_seller_404`,
  `test_detail_free_lead_seller_ok`, `test_detail_lead_not_found_404`.
- take: `test_take_lead_ok` (status `in_progress`, seller = me, уведомление клиенту), `test_take_lead_twice_409`
  (второй продавец), `test_take_lead_as_client_403`, `test_take_closed_lead_409/404`.
- assign: `test_assign_lead_admin_ok`, `test_assign_lead_to_client_404`, `test_assign_lead_to_blocked_seller_404`,
  `test_reassign_lead_notifies_old_seller`, `test_assign_closed_lead_409`, `test_assign_lead_as_seller_403`.
- update: `test_update_lead_client_comment_new_ok`, `test_update_lead_client_comment_in_progress_409`,
  `test_update_lead_client_status_403`, `test_update_lead_seller_close_ok` (уведомление клиенту),
  `test_update_lead_seller_comment_403`, `test_update_lead_other_seller_404`, `test_update_lead_free_lead_seller_404`,
  `test_update_lead_new_to_in_progress_409`, `test_update_lead_closed_to_in_progress_409`,
  `test_update_lead_same_status_409`, `test_update_lead_null_status_400`, `test_update_lead_admin_reject_new_ok`.
- delete: `test_delete_lead_client_new_ok` (заметки удалены каскадом — для admin-кейса), `test_delete_lead_client_in_progress_409`,
  `test_delete_lead_other_client_404`, `test_delete_lead_seller_403`, `test_delete_lead_admin_ok`.

`tests/test_lead_note.py`:
- `test_create_note_own_lead_ok` (`seller_id == me`), `test_create_note_other_seller_lead_404`, `test_create_note_free_lead_404`,
  `test_create_note_as_client_403`, `test_create_note_blank_422`, `test_create_note_admin_ok`.
- `test_list_notes_own_lead_ok` (порядок по времени), `test_list_notes_other_lead_404`, `test_list_notes_as_client_403`.
- `test_update_note_author_ok`, `test_update_note_not_author_403` (другой продавец той же заявки после переназначения → 404,
  админская заметка у продавца → 403), `test_update_note_null_400`, `test_delete_note_author_ok`, `test_delete_note_admin_ok`.
- `test_old_seller_loses_access_after_reassign`.
- `test_lead_detail_has_no_notes` (client не видит заметок ни в одном ответе).

`tests/test_test_drive.py`:
- create: `test_create_test_drive_ok` (`end_time - start_time == 60 мин`, `status scheduled`, `seller_id None`,
  ответ с `+00:00`, в БД 10:00 Бишкек = 04:00 UTC), `test_create_ignores_end_time_client_id_status`,
  `test_create_naive_datetime_422`, `test_create_utc_input_ok` (`Z` → тот же слот), `test_create_as_seller_403`,
  `..._without_token_401`.
- статусы авто: `test_create_reserved_car_409`, `test_create_in_transit_car_409`, `test_create_sold_car_404`,
  `test_create_withdrawn_car_404`, `test_create_deleted_car_404`, `test_create_unknown_car_404`.
- время: `test_create_in_past_400`, `test_create_now_400`, `test_create_beyond_30_days_400`,
  `test_create_before_work_start_400` (08:59), `test_create_at_work_start_ok` (09:00),
  `test_create_ending_after_work_end_400` (17:30 + 60), `test_create_ending_exactly_work_end_ok` (17:00),
  `test_create_respects_salon_timezone` (09:00 UTC = 15:00 Бишкек → ok; 04:00 UTC+6-эквивалент проверки),
  `test_create_custom_test_drive_minutes` (настройки 30 мин), `test_create_without_salon_settings_503`.
- пересечения: `test_overlap_same_car_409`, `test_adjacent_slots_same_car_ok` (10:00 и 11:00),
  `test_overlap_same_car_cancelled_ignored_ok`, `test_overlap_same_car_completed_ignored_ok`,
  `test_overlap_other_car_ok`, `test_overlap_same_client_other_car_409`,
  `test_overlap_seller_on_confirm_409`, `test_overlap_seller_on_assign_409`.
- видимость/IDOR: `test_list_client_sees_only_own`, `test_list_seller_own_and_free`, `test_detail_other_client_404`,
  `test_detail_other_seller_404`, `test_list_filter_date_range`, `test_list_invalid_date_range_400`,
  `test_list_naive_date_from_422`.
- переходы: `test_confirm_free_by_seller_assigns_self`, `test_confirm_other_seller_404`, `test_confirm_admin_without_seller_409`,
  `test_confirm_twice_409`, `test_confirm_past_400`, `test_confirm_car_withdrawn_409`, `test_complete_confirmed_after_start_ok`
  (запись с прошлым временем — напрямую в БД), `test_complete_before_start_409`, `test_complete_scheduled_409`,
  `test_cancel_by_client_ok` (уведомление продавцу), `test_cancel_by_seller_ok` (уведомление клиенту),
  `test_cancel_completed_409`, `test_cancel_other_client_404`.
- перенос: `test_update_reschedule_ok` (статус → `scheduled`, новый `end_time`), `test_update_reschedule_overlap_self_ok`
  (сдвиг на 30 мин внутри своего слота — `exclude_id`), `test_update_reschedule_past_400`, `test_update_no_start_time_400`,
  `test_update_completed_409`, `test_update_other_client_404`, `test_update_status_field_ignored`.
- `test_assign_as_seller_403`, `test_assign_to_client_404`, `test_delete_as_admin_ok`, `test_delete_as_seller_403`.

`tests/test_notification.py`:
- `test_list_only_own`, `test_list_filter_is_read`, `test_list_order_newest_first`, `test_list_without_token_401`.
- `test_detail_other_user_404` (IDOR, в т.ч. admin → чужое 404), `test_unread_count`.
- `test_update_mark_read_ok`, `test_update_null_400`, `test_update_other_user_404`.
- `test_read_all_marks_only_own` (чужие остаются непрочитанными).
- `test_delete_own_ok`, `test_delete_other_user_404`.
- `test_no_create_endpoint` (`POST /notification/create` → 404/405).
- `test_notification_not_sent_to_actor_and_blocked`.

`tests/test_admin.py` — дополнить: admin открывает списки `LeadView`, `TestDriveView` → 200.

---

## Риски и открытые вопросы

Неблокирующие, решены дефолтом:
1. **Новая зависимость `tzdata`** — нужна `zoneinfo` на Windows (на Linux/Docker работает и без неё). Альтернатива без
   зависимости — фиксированное смещение `timezone(timedelta(hours=6))` (в Кыргызстане нет перехода на летнее время с 2005 г.),
   но тогда `SALON_TIMEZONE` из конфига фактически игнорируется. Выбран `tzdata` — **подтвердите**.
2. **Тест-драйв создаёт только client.** Продавец не может записать клиента «по телефону» (в `TestDriveCreateSchema`
   нет `client_id`). Если нужно — добавить `client_id` для персонала (отдельное решение).
3. **Тест-драйв только для `available`**; `in_transit` тоже запрещён (авто нет в салоне). ТЗ явно называет только
   `reserved`/`sold`.
4. **Пересечение по клиенту** и **горизонт 30 дней** — правила сверх ТЗ (защита от спама/ошибок).
5. **Перенос сбрасывает `confirmed → scheduled`** (продавец должен подтвердить заново).
6. **Seller видит свободные заявки/тест-драйвы** (иначе «взять в работу» невозможно). Чужие (назначенные другому) — 404.
7. **Чужой объект для seller → 404**, а не 403 (как для client; STYLE §6 допускает 403 «нет прав», но так не раскрываем
   существование).
8. **Lead без статуса «отменён клиентом»**: client может только удалить свою `new`-заявку; после взятия — нет.
9. **Нет связи Lead ↔ TestDrive** (в моделях нет FK). Заявка `test_drive` и запись `TestDrive` независимы;
   автоматического создания одного из другого нет.
10. **Рабочие дни**: в `SalonSettings` нет выходных — тест-драйв возможен в любой день недели. Праздники/выходные —
    изменение модели (вне этапа).
11. **Тест-драйв не может переходить через полночь** (`local_start.date() == local_end.date()`) — при `work_end ≤ 24:00`
    это следует из рабочих часов.
12. **Будущие тест-драйвы на авто, которое позже забронировали/продали** (этап 5), не отменяются автоматически;
    `confirm` проверяет статус авто. Автоотмена — этап 5.
13. **Нет настроек салона → 503**. В проде `seed` создаёт их; в тестах — фикстура.
14. **Конкурентность** держится на одном воркере и отсутствии `await` между проверкой и `commit`. При переходе на несколько
    воркеров проверки пересечений станут гонкой (SQLite без row lock) — тогда нужен условный `INSERT ... SELECT WHERE NOT EXISTS`.
15. **`UtcDatetimeOut` в ответах** Lead/LeadNote/TestDrive/Notification — ответы этапа 4 отдают aware UTC, ответы
    прошлых этапов — naive (как было). Унификация — отдельное решение.
16. **Два роутера в `lead.py`** (`lead_router`, `lead_note_router`) — ROADMAP не выделяет файл для LeadNote. Альтернатива —
    пути `/lead/note/...` внутри `lead_router`.
17. **Уведомления «всем продавцам»** о новых заявках/тест-драйвах — при большом штате будет шумно; можно переключить на
    «только админам». Хранение уведомлений бессрочное, очистки нет.
18. **`get_car_or_404`/`is_staff` импортируются из `mysite/api/car.py`** — межроутерный импорт вместо дублирования.

---

## Не делаем в этом этапе

- `deal`, `discount`, бронь атомарным `UPDATE`, фоновая задача истечения брони, `AuditLog`, уведомления типов
  `deal`/`discount`/`reservation` (этап 5); `trade_in` + `TradeInImage`, `favorite`, `review`, `credit`, `statistic`
  (этап 6) — в т.ч. «своя статистика» продавца по заявкам.
- API для `SalonSettings` (правится в sqladmin / seed; на этом этапе только чтение в `test_drive.py`).
- Изменения `models.py` и миграции (выходные дни, FK Lead ↔ TestDrive, `updated_at`, причина отмены).
- Автоотмена тест-драйвов при брони/продаже авто; напоминания о тест-драйвах по расписанию (фоновые задачи).
- Email/SMS/push/WebSocket — только записи `Notification` в БД.
- Запись на тест-драйв персоналом от имени клиента; поиск свободных слотов (`/test-drive/slots`).
- Новые модули/утилиты, `services/`.

---

## Порядок работы

1. **db-specialist** — без изменений моделей: `alembic upgrade head` + `alembic check`; подтвердить, что миграция не нужна.
2. **coder** (по порядку):
   1. `requirements.txt` — `tzdata`; `.venv/Scripts/python.exe -m pip install tzdata`; проверить
      `python -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Bishkek')"`.
   2. `mysite/db/schema.py` — `UtcDatetime`, `UtcDatetimeOut`, `Text2000`, `Text5000`, правки `Lead*`/`LeadNote*`/
      `TestDrive*`/`Notification*`, новые `LeadAssignSchema`, `TestDriveAssignSchema`.
   3. `mysite/api/notification.py` — `create_notification`, `notify_active_sellers`, роутер.
   4. `mysite/api/lead.py` — `lead_router` (create/list/detail/take/assign/update/delete) + `lead_note_router`.
   5. `mysite/api/test_drive.py` — `get_salon_settings_or_503`, `as_utc`, `check_working_hours`, `check_slot`,
      `TEST_DRIVE_TRANSITIONS`, эндпоинты.
   6. `main.py` — четыре `include_router`.
   7. `mysite/admin/view.py`, `setup.py` — `LeadView`, `TestDriveView` (только чтение).
   8. Проверка: `python -c "import main"`, `uvicorn main:auto_app` → `/docs`.
3. **tester** — `conftest.py` (фикстуры) + `test_lead.py`, `test_lead_note.py`, `test_test_drive.py`, `test_notification.py`,
   дополнение `test_admin.py`; `.venv/Scripts/python.exe -m pytest -q`.
4. **reviewer + security-auditor** — по `git diff`; особое внимание: IDOR (client/seller → 404 на чужое во всех ручках,
   включая `/lead-note/*` и `/notification/*`), серверные поля (`client_id`, `seller_id`, `end_time`, `status`) не
   принимаются, naive datetime → 422, все bind-параметры времени в UTC, отсутствие `await` между проверкой пересечений
   и `commit`, заметки не утекают клиенту.
5. **coder** — исправления 🔴 critical.
6. Отметить чекбоксы в `docs/ROADMAP.md`, отчёт + предложенный коммит
   `feat(crm): add leads with notes, test drives and notifications (stage 4)` → **СТОП**.
