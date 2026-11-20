# План: Этап 4 — CRM (заявки, заметки, уведомления)

> Тест-драйвы удалены из проекта по решению автора (2026-11-19, миграция `610fbbdbd05f_remove_test_drive`):
> нет модели `TestDrive`, Enum `TestDriveStatus`, значений `test_drive` в `LeadType`/`NotificationType`,
> поля `SalonSettings.test_drive_minutes`, роутера `test_drive.py`. Не возвращать без решения автора.

## Открытые вопросы (блокирующие)

Нет. Всё, что помечено **[дефолт]**, — решение архитектора по умолчанию; автор может переопределить
(сводка — в разделе «Риски и открытые вопросы»).

---

## Цель и границы

Цель: CRM салона — заявки клиентов (`Lead`) с взятием в работу продавцом и внутренними заметками
(`LeadNote`), машина состояний заявки, внутренние уведомления (`Notification`), тесты.

Границы:
- Новые файлы в `mysite/` — **только** `mysite/api/lead.py`, `mysite/api/notification.py`.
  Никаких `utils.py`/`services/`. Вспомогательные функции — внутри этих модулей
  (`create_notification` — в `notification.py`, импортируется из `lead.py`).
- **Изменений моделей нет. Миграции нет.** Все поля, FK и индексы уже есть в `initial` (`f907a8edf483`).
- Ничего из этапов 5–6 (Deal, DiscountRequest, бронь, фоновая задача, AuditLog, TradeIn, Favorite, Review,
  credit, statistic).

Текущее состояние (проверено):
- `models.py`: `Lead`, `LeadNote` (`cascade='all, delete-orphan'` от Lead), `Notification`,
  `SalonSettings` (`work_start`/`work_end: Time`, `CHECK id = 1`, `CHECK work_end > work_start`),
  все Enum (`LeadType`, `LeadStatus`, `NotificationType`) — объявлены, связи двусторонние.
- `schema.py`: есть `Lead*`, `LeadNote*`, `Notification*` схемы (требуют точечных правок, см. «Схемы»).
- `dependencies.py`: `get_current_user`, `get_optional_user`, `require_role`.
- `car.py`: `get_car_or_404(car_id, db, current_user, only_visible)`, `PUBLIC_CAR_STATUSES`, `is_staff`, `STAFF_ROLES` —
  переиспользуем импортом (`from mysite.api.car import get_car_or_404, is_staff`), не копируем.
- `tests/conftest.py`: `db`, `client`, `make_user`, `auth_headers`, `admin`, `seller`, `client_user`, `brand`, `car_model`,
  `make_car`, `admin_session_local`. Фикстуры `SalonSettings` нет.

---

## Файлы (создать / изменить)

### Создать
| Путь | Что |
|---|---|
| `mysite/api/notification.py` | `notification_router` (`prefix='/notification'`, `tags=['Notification']`) + функции `create_notification(db, user_id, notification_type, text)`, `notify_active_sellers(db, notification_type, text, exclude_user_id=None)`. |
| `mysite/api/lead.py` | `lead_router` (`prefix='/lead'`, `tags=['Lead']`) и `lead_note_router` (`prefix='/lead-note'`, `tags=['LeadNote']`) — **оба в одном файле** (ROADMAP: «lead.py (+ LeadNote)») **[дефолт]**. |
| `tests/test_lead.py`, `tests/test_lead_note.py`, `tests/test_notification.py` | тесты. |

### Изменить
| Путь | Что |
|---|---|
| `mysite/db/schema.py` | точечно (см. «Схемы»): типы `UtcDatetime`, `UtcDatetimeOut`, `Text2000`, `Text5000`; правки `Lead*`, `LeadNote*`, `Notification*`; новая `LeadAssignSchema`. |
| `main.py` | `from mysite.api import ... lead, notification`; `include_router` по строке: `lead.lead_router`, `lead.lead_note_router`, `notification.notification_router`. |
| `mysite/admin/view.py` | `LeadView` — только чтение (`can_create = can_edit = can_delete = False`) **[дефолт]**. |
| `mysite/admin/setup.py` | `admin.add_view(LeadView)`. |
| `tests/conftest.py` | фикстуры `salon_settings`, `make_lead`, `make_notification`; `LeadView` в кортеж `admin_session_local`. |
| `docs/ROADMAP.md` | чекбоксы этапа 4, строка «Текущий этап». |

---

## Модели / поля / связи / ограничения

**Изменений моделей нет, миграции нет.** Используются как есть:
- `Lead` — `client_id FK index`, `car_id FK nullable`, `lead_type Enum`, `status Enum default new`,
  `seller_id FK nullable index`, `comment Text`, `created_at`; связи `client`, `seller` (`foreign_keys` указаны), `car`,
  `notes` (cascade delete-orphan).
- `LeadNote` — `lead_id FK index`, `seller_id FK` (автор заметки; для admin — id админа), `note Text`, `created_at`.
- `Notification` — `user_id FK index`, `notification_type`, `text Text`, `is_read default False`, `created_at`.

Осознанно **не добавляем**: `updated_at` у Lead, статус `cancelled` у Lead — не требуются ТЗ.

---

## Время (UTC / SQLite)

1. **Вход** (если есть datetime от клиента) — тип `UtcDatetime` в `schema.py`:
   `Annotated[AwareDatetime, AfterValidator(to_utc)]`, где `to_utc(v) = v.astimezone(timezone.utc)`.
   `AwareDatetime` (Pydantic v2) отклоняет naive datetime → **422** автоматически.
2. **Запись**: в модель идут только UTC-значения. SQLite хранит строку без смещения → для сравнений в SQL
   все bind-параметры **обязательно** предварительно в UTC.
3. **Чтение**: SQLite возвращает naive → перед сравнением в Python `value.replace(tzinfo=timezone.utc)`.
4. **Ответ**: в схемах Lead/LeadNote/Notification поле `created_at` — тип
   `UtcDatetimeOut = Annotated[datetime, AfterValidator(lambda v: v if v.tzinfo else v.replace(tzinfo=timezone.utc))]`
   → клиент получает `...+00:00`, а не naive **[дефолт]**. Остальные схемы прошлых этапов не трогаем.
5. Текущее время — только `datetime.now(timezone.utc)`.

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
| `NotificationUpdateSchema` | `is_read: bool \| None` | без изменений (явный `null` → 400 в роутере) |
| `NotificationList/DetailSchema` | — | `created_at: UtcDatetimeOut` |

**Не принимаются от клиента** (берёт сервер): `Lead.client_id` (= `current_user.id`), `Lead.seller_id` (только через
`take`/`assign`), `Lead.status` при создании (`new`); `LeadNote.seller_id` (= автор);
`Notification` — целиком сервер (нет `NotificationCreateSchema` и эндпоинта создания).
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
| `POST /lead/create` | client | `LeadCreateSchema` → `LeadDetailSchema` | 401, 403 (admin/seller), 404 `'Автомобиль не найден'`, 409 `'У вас уже есть активная заявка по этому автомобилю'`, 422 |
| `GET /lead/list` | admin, seller, client | `status`, `lead_type`, `only_free: bool = False` (seller/admin: только свободные), `seller_id` (только admin), `skip`, `limit` → `List[LeadListSchema]`, `order_by(created_at.desc(), id.desc())` | 401, 422 |
| `GET /lead/detail?lead_id=` | все роли (видимость выше) | → `LeadDetailSchema` | 401, 404 |
| `POST /lead/take/{lead_id}` | seller | → `LeadDetailSchema` | 401, 403, 404, 409 `'Заявка уже взята в работу'` |
| `POST /lead/assign/{lead_id}` | admin | `LeadAssignSchema` → `LeadDetailSchema` | 401, 403, 404 `'Заявка не найдена'` / `'Продавец не найден'`, 409 `'Закрытую заявку нельзя переназначить'` |
| `PUT /lead/update/{lead_id}` | admin, seller, client | `LeadUpdateSchema` → `LeadDetailSchema` | 401, 404, 403 (поле не по роли), 400 явный `null`, 409 переход |
| `DELETE /lead/delete/{lead_id}` | admin; client (своя, `new`) | → `{'message': 'Заявка удалена'}` (жёсткое, заметки каскадом) | 401, 403 seller, 404, 409 `'Удалить можно только новую заявку'` (client) |

Детали:
- **create**: `client_id = current_user.id`, `status = new`, `seller_id = None`.
  - `car_id` задан → `get_car_or_404(car_id, db, current_user, only_visible=True)` (удалённые/скрытые от публики
    `sold`/`withdrawn` → 404). Для `purchase`/`trade_in`/`question` `car_id` необязателен.
  - Антидубль **[дефолт]**: только при `car_id is not None` — у клиента уже есть заявка с тем же `lead_type` и тем же
    `car_id` в статусе `new`/`in_progress` → 409.
  - Уведомление `lead` всем активным продавцам: `'Новая заявка #<id> (<тип по-русски>)'` (`LEAD_TYPE_TEXT`).
- **list**: client — свои; seller — свои + свободные (`only_free=True` → только свободные); admin — все (+ фильтр `seller_id`).
  `seller_id`-фильтр от не-админа игнорируется **[дефолт]**.
- **take** (seller): заявка должна быть видна (иначе 404); условный атомарный `UPDATE`:
  `db.query(Lead).filter(Lead.id == lead_id, Lead.seller_id.is_(None), Lead.status == LeadStatus.new)
  .update({'seller_id': current_user.id, 'status': LeadStatus.in_progress}, synchronize_session=False)`;
  `rowcount == 0` → 409. Затем `refresh`. Уведомление клиенту: `'Ваша заявка #<id> взята в работу'`.
  Заявку, уже взятую другим продавцом, второй продавец не видит → 404.
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

Конкурентность: обработчики `async def` выполняют синхронные запросы без `await` между проверкой и `commit`, uvicorn —
один воркер. `take` у заявки — дополнительно условный `UPDATE` (дёшево и надёжно).

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
  вызывающий роутер в той же транзакции, что и основное действие). Неактивному (заблокированному) получателю
  уведомление не создаётся.
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

---

## Бизнес-правила этапа

| ТЗ | Правило | Как проверяется |
|---|---|---|
| §3 seller | Берёт заявки в работу | `POST /lead/take` — условный `UPDATE` (`seller_id IS NULL AND status=new`), второй → 409 |
| §3 seller | Работает только со своими заявками | update/note/take-видимость по `seller_id == me`; чужая → 404 |
| §3 seller | Заметки по клиенту (`LeadNote`) | `/lead-note/*`, client → 403, автор — `current_user` |
| §3 client | Заявка на покупку | create только `client`; `client_id = current_user.id` |
| §3 client | Видит только свои; чужое → 404 | `get_lead_or_404`, notification по `user_id` |
| §3 admin | Видит и меняет всё | admin проходит видимость, `assign`, `delete` |
| §1, CLAUDE.md | Время в UTC; naive → 422; aware → `astimezone(utc)` | `UtcDatetime` (`AwareDatetime` + `to_utc`), ответы `UtcDatetimeOut` |
| §4.1 | Статусы `LeadStatus` | `LEAD_TRANSITIONS`, иначе 409 |
| §4.1 | `NotificationType` | `lead` используется на этом этапе |
| §6 | Пагинация списков | `skip`/`limit (le=100)` во всех `/list` |

---

## Миграции

Не требуются. db-specialist: `alembic upgrade head` → `alembic check` — подтвердить, что модели и БД совпадают.
Изменения `schema.py` на БД не влияют.

---

## Тесты

`tests/conftest.py` — дополнить:
- `salon_settings(db)` — `SalonSettings(id=1, work_start=time(9, 0), work_end=time(18, 0), ...)`.
- `make_lead(**overrides)`, `make_notification(**overrides)` — создание напрямую в БД.
- второй продавец/клиент — через `make_user('seller2', UserRole.seller)` и т.п.
- `LeadView` в кортеж `admin_session_local`.

`tests/test_lead.py`:
- create: `test_create_lead_as_client_ok` (`client_id == me`, `status == new`, `seller_id is None`),
  `test_create_lead_ignores_client_id_seller_id_status`, `test_create_lead_as_seller_403`, `..._as_admin_403`,
  `..._without_token_401`, `test_create_lead_unknown_car_404`, `test_create_lead_deleted_car_404`,
  `test_create_lead_sold_car_404`, `test_create_lead_question_without_car_ok`,
  `test_create_lead_duplicate_active_409`, `test_create_lead_duplicate_after_closed_ok`,
  `test_create_lead_comment_too_long_422`, `test_create_lead_invalid_type_422`,
  `test_create_lead_notifies_active_sellers` (заблокированному — нет).
- list: `test_list_lead_client_sees_only_own`, `test_list_lead_seller_sees_own_and_free`,
  `test_list_lead_seller_not_sees_other_sellers`, `test_list_lead_only_free`, `test_list_lead_admin_sees_all`,
  `test_list_lead_admin_filter_seller_id`, фильтры `status`/`lead_type`, пагинация, `limit=101` → 422.
- detail: свой → 200; **IDOR**: `test_detail_lead_other_client_404`, `test_detail_lead_other_seller_404`,
  `test_detail_free_lead_seller_ok`, `test_detail_lead_not_found_404`.
- take: `test_take_lead_ok` (status `in_progress`, seller = me, уведомление клиенту), второй продавец → 404,
  повторный take тем же продавцом → 409, `test_take_lead_as_client_403`, `test_take_closed_lead_404`.
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

`tests/test_notification.py`:
- `test_list_only_own`, `test_list_filter_is_read`, `test_list_order_newest_first`, `test_list_without_token_401`.
- `test_detail_other_user_404` (IDOR, в т.ч. admin → чужое 404), `test_unread_count`.
- `test_update_mark_read_ok`, `test_update_null_400`, `test_update_other_user_404`.
- `test_read_all_marks_only_own` (чужие остаются непрочитанными).
- `test_delete_own_ok`, `test_delete_other_user_404`.
- `test_no_create_endpoint` (`POST /notification/create` → 404/405).
- `test_notification_not_sent_to_actor_and_blocked`.

`tests/test_admin.py` — дополнить: admin открывает список `LeadView` → 200, view только для чтения.

---

## Риски и открытые вопросы

Неблокирующие, решены дефолтом:
1. **Seller видит свободные заявки** (иначе «взять в работу» невозможно). Чужие (назначенные другому) — 404.
2. **Чужой объект для seller → 404**, а не 403 (как для client; STYLE §6 допускает 403 «нет прав», но так не раскрываем
   существование).
3. **Lead без статуса «отменён клиентом»**: client может только удалить свою `new`-заявку; после взятия — нет.
4. **Конкурентность** держится на одном воркере и отсутствии `await` между проверкой и `commit`; `take` — условный `UPDATE`.
5. **`UtcDatetimeOut` в ответах** Lead/LeadNote/Notification — ответы этапа 4 отдают aware UTC, ответы
   прошлых этапов — naive (как было). Унификация — отдельное решение.
6. **Два роутера в `lead.py`** (`lead_router`, `lead_note_router`) — ROADMAP не выделяет файл для LeadNote. Альтернатива —
   пути `/lead/note/...` внутри `lead_router`.
7. **Уведомления «всем продавцам»** о новых заявках — при большом штате будет шумно; можно переключить на
   «только админам». Хранение уведомлений бессрочное, очистки нет.
8. **`get_car_or_404`/`is_staff` импортируются из `mysite/api/car.py`** — межроутерный импорт вместо дублирования.

---

## Не делаем в этом этапе

- `deal`, `discount`, бронь атомарным `UPDATE`, фоновая задача истечения брони, `AuditLog`, уведомления типов
  `deal`/`discount`/`reservation` (этап 5); `trade_in` + `TradeInImage`, `favorite`, `review`, `credit`, `statistic`
  (этап 6) — в т.ч. «своя статистика» продавца по заявкам.
- API для `SalonSettings` (правится в sqladmin / seed).
- Изменения `models.py` и миграции (`updated_at`, причина отмены).
- Email/SMS/push/WebSocket — только записи `Notification` в БД.
- Новые модули/утилиты, `services/`.

---

## Порядок работы

1. **db-specialist** — без изменений моделей: `alembic upgrade head` + `alembic check`; подтвердить, что миграция не нужна.
2. **coder** (по порядку):
   1. `mysite/db/schema.py` — `UtcDatetime`, `UtcDatetimeOut`, `Text2000`, `Text5000`, правки `Lead*`/`LeadNote*`/
      `Notification*`, новая `LeadAssignSchema`.
   2. `mysite/api/notification.py` — `create_notification`, `notify_active_sellers`, роутер.
   3. `mysite/api/lead.py` — `lead_router` (create/list/detail/take/assign/update/delete) + `lead_note_router`.
   4. `main.py` — три `include_router`.
   5. `mysite/admin/view.py`, `setup.py` — `LeadView` (только чтение).
   6. Проверка: `python -c "import main"`, `uvicorn main:auto_app` → `/docs`.
3. **tester** — `conftest.py` (фикстуры) + `test_lead.py`, `test_lead_note.py`, `test_notification.py`,
   дополнение `test_admin.py`; `.venv/Scripts/python.exe -m pytest -q`.
4. **reviewer + security-auditor** — по `git diff`; особое внимание: IDOR (client/seller → 404 на чужое во всех ручках,
   включая `/lead-note/*` и `/notification/*`), серверные поля (`client_id`, `seller_id`, `status`) не
   принимаются, заметки не утекают клиенту.
5. **coder** — исправления 🔴 critical.
6. Отметить чекбоксы в `docs/ROADMAP.md`, отчёт + предложенный коммит
   `feat(crm): add leads with notes and notifications (stage 4)` → **СТОП**.
