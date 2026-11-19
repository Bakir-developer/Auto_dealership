# План: Этап 3 — Справочники и авто

## Открытые вопросы (блокирующие)

Нет. Всё, что помечено **[дефолт]**, — решение архитектора по умолчанию; автор может переопределить
до начала работы coder'а (сводка — в разделе «Риски и открытые вопросы»).

---

## Цель и границы

Цель: справочники марок и моделей (CRUD только у admin, чтение публичное), каталог авто без входа
с фильтрами и пагинацией, создание/редактирование авто (admin, seller) с правилами new/used,
запись `PriceHistory` при смене цены, мягкое удаление, загрузка фото авто на диск с раздачей
через nginx `/media/`, представления в sqladmin, тесты.

Границы:
- Новые файлы в `mysite/` — **только** `mysite/api/brand.py`, `car_model.py`, `car.py`, `car_image.py`.
  Никаких новых модулей/утилит. Вспомогательные функции (`get_car_or_404`, проверка new/used,
  сохранение файла) — внутри соответствующих роутеров.
- **Изменений моделей нет. Миграции нет.** Все нужные поля, индексы и ограничения уже есть
  в `initial` (`f907a8edf483`).
- Ничего из этапов 4+ (Lead, Notification, Deal, DiscountRequest, бронь, AuditLog,
  TradeIn, Favorite, Review, credit, statistic).

Текущее состояние (проверено): этап 2 завершён — есть `mysite/api/{auth,dependencies,user}.py`,
`mysite/admin/{setup,view}.py`, `mysite/seed.py`, `tests/` (conftest, test_auth/user/admin/seed),
Docker/nginx. В `schema.py` уже есть `Brand*`, `CarModel*`, `Car*`, `CarImage*`, `PriceHistory*` схемы.
`python-multipart` уже в `requirements.txt` (нужен для `UploadFile`/`Form`). `media/` уже в
`.gitignore` и `.dockerignore`.

---

## Файлы (создать / изменить)

### Создать
| Путь | Что |
|---|---|
| `mysite/api/brand.py` | `brand_router` (`prefix='/brand'`, `tags=['Brand']`), CRUD. |
| `mysite/api/car_model.py` | `car_model_router` (`prefix='/car-model'`, `tags=['CarModel']`), CRUD. |
| `mysite/api/car.py` | `car_router` (`prefix='/car'`, `tags=['Car']`): каталог, CRUD, мягкое удаление, `price-history`. |
| `mysite/api/car_image.py` | `car_image_router` (`prefix='/car-image'`, `tags=['CarImage']`): загрузка/список/детально/изменение/удаление фото. |
| `tests/test_brand.py`, `tests/test_car_model.py`, `tests/test_car.py`, `tests/test_car_image.py` | тесты. |

### Изменить
| Путь | Что |
|---|---|
| `mysite/api/dependencies.py` | добавить `oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl='auth/login', auto_error=False)` и `get_optional_user` (см. «Эндпоинты → Каталог и видимость»). Существующие функции не менять. |
| `mysite/config.py` | одна константа: `MEDIA_DIR = os.getenv('MEDIA_DIR', 'media')`. |
| `mysite/db/schema.py` | точечно (см. «Схемы»): обрезка пробелов в `brand_name`/`model_name`/`color`. Новых схем нет. |
| `main.py` | импорт и `include_router` для `brand`, `car_model`, `car`, `car_image` (по строке); создание каталога `MEDIA_DIR/car_images` (`os.makedirs(..., exist_ok=True)`) и `auto_app.mount('/media', StaticFiles(directory=MEDIA_DIR), name='media')` — для локального запуска без nginx. `/health` оставить. |
| `mysite/admin/view.py` | `BrandView`, `CarModelView`, `CarView`, `PriceHistoryView` (см. «sqladmin»). |
| `mysite/admin/setup.py` | `admin.add_view(...)` для новых представлений. |
| `docker-compose.yml` | bind-mount `./media` (см. «Docker / nginx»). |
| `nginx/nginx.conf` | `location /media/` (см. «Docker / nginx»). |
| `.env.example` | строка `MEDIA_DIR=media` с комментарием (в docker переопределяется в compose). |
| `tests/conftest.py` | фикстуры `brand`, `car_model`, `make_car`, `media_dir`; добавить новые view в кортеж `admin_session_local`. |
| `docs/ROADMAP.md` | отметить чекбоксы этапа 3, строка «Текущий этап». |

---

## Модели / поля / связи / ограничения

**Изменений моделей нет, миграции нет.** Используются как есть:
- `Brand` — `brand_name String(50) unique`, `brand_logo String nullable`; связи `car_models`, `cars` (без cascade).
- `CarModel` — `brand_id FK`, `model_name String(50)`, `UniqueConstraint('brand_id', 'model_name')`.
- `Car` — все поля ТЗ §4.2; `vin String(17) unique` + `CHECK length(vin)=17`; `price Numeric(14,2)` + `CHECK price > 0`;
  `mileage >= 0`, `owners_count >= 0`, `engine_volume > 0`; индексы `brand_id`, `car_model_id`, `year`, `status`,
  `price`; `created_by_id FK`; `updated_at onupdate=func.now()`; `deleted_at` для мягкого удаления;
  `images` с `cascade='all, delete-orphan'`.
- `CarImage` — `car_id FK index`, `car_image String`, `is_main`, `position` (`CHECK >= 0`).
- `PriceHistory` — `car_id`, `old_price`, `new_price`, `changed_by_id`, `changed_at server_default`.

Осознанно **не меняем**:
- Порядок фото: у `Car.images` нет `order_by`. Сортировку делаем в роутере (см. `/car/detail`), а не
  правкой relationship.
- Регистронезависимая уникальность марок/моделей — `unique` в БД регистрозависим; дубли «Toyota»/«toyota»,
  «Лада»/«лада» ловим в Python (см. «Бизнес-правила»), отдельное поле `*_lower` не добавляем.

---

## Схемы

Все уже есть в `schema.py`. Изменения точечные **[дефолт]**:
- `BrandCreateSchema.brand_name`, `BrandUpdateSchema.brand_name`, `CarModelCreateSchema.model_name`,
  `CarModelUpdateSchema.model_name`, `CarCreateSchema.color`, `CarUpdateSchema.color` — через
  `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=N)]`
  (сейчас `'   '` проходит `min_length=1`, а `' Toyota'` и `'Toyota'` — разные значения).
  Можно объявить алиасы `Name50 = ...`, `Color = ...` рядом с `Money`, `Year`.
- `BrandUpdateSchema`, `CarModelUpdateSchema`, `CarUpdateSchema` — остаются «все поля `X | None = None`»;
  явный `null` в NOT NULL-полях ловит роутер → 400 (как в `user.py`), а не схема.

Используемые схемы:
| Сущность | Вход | Выход |
|---|---|---|
| Brand | `BrandCreateSchema`, `BrandUpdateSchema` | `BrandListSchema`, `BrandDetailSchema` |
| CarModel | `CarModelCreateSchema`, `CarModelUpdateSchema` | `CarModelListSchema`, `CarModelDetailSchema` |
| Car | `CarCreateSchema`, `CarUpdateSchema` | `CarListSchema`, `CarDetailSchema` (с `images: List[CarImageListSchema]`) |
| CarImage | `Form`/`UploadFile` (multipart), `CarImageUpdateSchema` | `CarImageListSchema`, `CarImageDetailSchema` |
| PriceHistory | — (создаёт сервер) | `PriceHistoryListSchema` |

`CarImageCreateSchema` (`car_image: str`) для загрузки **не используется** — путь к файлу формирует
сервер; клиент присылает файл, а не строку. Схему не удаляем (вне рамок этапа), см. «Риски».

Что **не принимается от клиента**:
- `Car`: `id`, `created_by_id` (= `current_user.id`), `created_at`, `updated_at`, `deleted_at`;
  статусы `reserved`/`sold` (уже запрещены `ManualCarStatus`). В update нет `vin`, `brand_id`,
  `car_model_id`, `condition` — их нельзя менять после создания **[дефолт]**.
- `CarImage`: `car_image` (имя/путь файла генерирует сервер), `id`.
- `PriceHistory`: целиком сервер (`changed_by_id = current_user.id`).

Деньги в ответах — `Decimal`; Pydantic v2 сериализует их в JSON **строкой** (`"1500000.00"`) — учитывать в тестах.

---

## Эндпоинты

Общие правила: `response_model` всегда; пагинация `skip: int = Query(0, ge=0)`,
`limit: int = Query(20, ge=1, le=100)`; ошибки — `HTTPException` с текстом на русском; 401 — нет/плохой токен,
403 — `'Недостаточно прав'` из `require_role`.

### `brand_router` — `/brand`, `tags=['Brand']`

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /brand/create` | admin | `BrandCreateSchema` → `BrandDetailSchema` | 401, 403, 409 `'Марка с таким названием уже существует'`, 422 |
| `GET /brand/list` | все (без входа) | `skip`, `limit` → `List[BrandListSchema]`, `order_by(Brand.brand_name, Brand.id)` | 422 |
| `GET /brand/detail?brand_id=` | все | → `BrandDetailSchema` | 404 `'Марка не найдена'` |
| `PUT /brand/update/{brand_id}` | admin | `BrandUpdateSchema` → `BrandDetailSchema` | 401, 403, 404, 409 дубль, 400 `'Поле не может быть пустым'` (явный `null` в `brand_name`) |
| `DELETE /brand/delete/{brand_id}` | admin | → `{'message': 'Марка удалена'}` (жёсткое удаление) | 401, 403, 404, 409 `'Нельзя удалить марку: к ней привязаны модели или автомобили'` |

### `car_model_router` — `/car-model`, `tags=['CarModel']`

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /car-model/create` | admin | `CarModelCreateSchema` → `CarModelDetailSchema` | 401, 403, 404 `'Марка не найдена'`, 409 `'Такая модель у этой марки уже существует'`, 422 |
| `GET /car-model/list` | все | `brand_id: int \| None`, `skip`, `limit` → `List[CarModelListSchema]`, сортировка `model_name, id` | 422 |
| `GET /car-model/detail?car_model_id=` | все | → `CarModelDetailSchema` | 404 `'Модель не найдена'` |
| `PUT /car-model/update/{car_model_id}` | admin | `CarModelUpdateSchema` → `CarModelDetailSchema` | 401, 403, 404 (модель / новая марка), 409 дубль, 409 `'Нельзя сменить марку: у модели есть автомобили'`, 400 явный `null` |
| `DELETE /car-model/delete/{car_model_id}` | admin | → `{'message': 'Модель удалена'}` | 401, 403, 404, 409 `'Нельзя удалить модель: к ней привязаны автомобили'` |

Смена `brand_id` у модели, на которую ссылаются авто (включая мягко удалённые), сломает согласованность
`Car.brand_id` ↔ `CarModel.brand_id` → 409 **[дефолт]**.

### `car_router` — `/car`, `tags=['Car']`

#### Каталог и видимость **[дефолт]**
- `dependencies.py`: `get_optional_user(token: str | None = Depends(oauth2_scheme_optional), db=Depends(get_db)) -> UserProfile | None` —
  нет токена → `None`; токен есть → та же проверка, что `get_current_user` (невалидный/просроченный/refresh/
  заблокированный → **401**, анонимом не считаем — иначе ошибка клиента маскируется). Реализация — вызов
  логики `get_current_user` (без дублирования кода).
- «Персонал» = `admin` или `seller`. Аноним и `client` — «публика».
- Публика видит статусы `PUBLIC_CAR_STATUSES = (available, in_transit, reserved)`; `sold`/`withdrawn` — только
  персонал. Мягко удалённые (`deleted_at IS NOT NULL`) не видит никто (ТЗ §5.8).
- Скрытое от публики авто в `/car/detail` → 404 (как несуществующее).

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `GET /car/list` | все (без входа); видимость по роли | фильтры (ниже) + `skip`, `limit` → `List[CarListSchema]` | 400 диапазоны, 401 плохой токен, 422 |
| `GET /car/detail?car_id=` | все; видимость по роли | → `CarDetailSchema` (фото отсортированы) | 404 `'Автомобиль не найден'`, 401 плохой токен |
| `POST /car/create` | admin, seller | `CarCreateSchema` → `CarDetailSchema` | 401, 403, 404 `'Марка не найдена'` / `'Модель не найдена'`, 400 `'Модель не принадлежит выбранной марке'`, 400 правила new/used, 400 год, 409 `'Автомобиль с таким VIN уже существует'`, 422 |
| `PUT /car/update/{car_id}` | admin, seller | `CarUpdateSchema` → `CarDetailSchema` | 401, 403, 404, 400 `'Поле не может быть пустым'`, 400 new/used, 409 (см. правила статусов) , 422 |
| `DELETE /car/delete/{car_id}` | admin | → `{'message': 'Автомобиль удалён'}` (мягкое) | 401, 403, 404 (нет / уже удалён), 409 `'Нельзя удалить забронированный автомобиль'` |
| `GET /car/price-history/{car_id}` | admin, seller **[дефолт]** | → `List[PriceHistoryListSchema]`, `order_by(changed_at.desc(), id.desc())`, `skip`/`limit` | 401, 403, 404 (нет / удалён) |

Фильтры `/car/list` (все необязательные, ТЗ §6): `brand_id: int`, `car_model_id: int`,
`year_min`/`year_max: int (ge=1900, le=2100)`, `price_min`/`price_max: Decimal (gt=0)`, `currency: Currency`,
`condition: CarCondition`, `body_type: BodyType`, `fuel_type: FuelType`, `transmission: Transmission`,
`drive_type: DriveType`, `status: CarStatus`.
- `year_min > year_max` или `price_min > price_max` → 400 `'Некорректный диапазон фильтра'`.
- Публика + `status=sold`/`withdrawn` → пустой список (фильтр применяется поверх ограничения видимости), не 403.
- Сортировка: `order_by(Car.created_at.desc(), Car.id.desc())` **[дефолт]**; параметр сортировки не вводим.
- Цена сравнивается «как есть» без конвертации валют; для осмысленного фильтра по цене клиент передаёт
  `currency` **[дефолт]**.
- Текстового поиска в каталоге нет — ТЗ §6 требует фильтры по марке/модели, они идут по `brand_id`/`car_model_id`
  (целые), проблема `ilike`/`lower()` с кириллицей здесь не возникает. Если автор захочет `q` — см. «Риски».
- Все Enum-фильтры — Pydantic-типы в query → невалидное значение 422 (CHECK в БД нет, валидирует Pydantic).

`/car/detail`: `options(selectinload(Car.images))`; ответ собирается
`CarDetailSchema.model_validate(car_db, from_attributes=True)`, затем
`images.sort(key=lambda i: (not i.is_main, i.position, i.id))` — главное фото первым. Модель не трогаем.

`/car/create`:
1. `brand` существует → иначе 404; `car_model` существует → иначе 404; `car_model.brand_id == brand_id` → иначе 400.
2. `year <= datetime.now(timezone.utc).year + 1` → иначе 400 `'Год выпуска не может быть больше следующего года'` **[дефолт]**.
3. Правила new/used (ниже) → 400.
4. VIN (уже `upper()` в `Vin`) — проверка `db.query(Car).filter(Car.vin == vin).first()` **без** фильтра `deleted_at`
   (unique в БД распространяется и на удалённые) → 409; страховка `IntegrityError` → `rollback` → 409.
5. `Car(**car_data.model_dump(), created_by_id=current_user.id)`; начальная цена в `PriceHistory` не пишется **[дефолт]**.

`/car/update/{car_id}`:
1. Авто не найдено или удалено → 404 (персонал видит любые не удалённые статусы).
2. `update_data = model_dump(exclude_unset=True)`; явный `None` в NOT NULL-полях (`year`, `body_type`, `color`,
   `fuel_type`, `transmission`, `drive_type`, `steering`, `status`, `price`, `currency`, `mileage`,
   `customs_cleared`, `registered_in_kr`) → 400 `'Поле не может быть пустым'`.
3. `car_db.status == sold` → 409 `'Проданный автомобиль нельзя изменить'` **[дефолт]**.
4. `'status' in update_data` и `car_db.status == reserved` → 409 `'Статус забронированного автомобиля меняется только через сделку'`
   (переходы reserved/sold — этап 5).
5. Правила new/used проверяются на **итоговом** состоянии: `{f: update_data.get(f, getattr(car_db, f))}` → 400.
6. Если `'price' in update_data` и `update_data['price'] != car_db.price` (сравнение `Decimal`) —
   `db.add(PriceHistory(car_id, old_price=car_db.price, new_price=..., changed_by_id=current_user.id))` в той же
   транзакции, что и изменение цены. Одинаковая цена — записи нет.
7. `setattr` по `update_data`, `commit`, `refresh`, ответ как в detail.

`/car/delete/{car_id}`: `car_db.deleted_at = datetime.now(timezone.utc)`; фото и файлы не трогаем (история;
авто можно «вернуть» через БД). `reserved` → 409.

Права seller: редактирует **любое** авто (ТЗ ограничивает seller «своими» только по заявкам/сделкам) **[дефолт]**.
Удаление — только admin **[дефолт]** (ТЗ: seller «добавляет/редактирует»).

### `car_image_router` — `/car-image`, `tags=['CarImage']`

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /car-image/create` | admin, seller | multipart: `car_id: int = Form()`, `is_main: bool = Form(False)`, `position: int = Form(0, ge=0)`, `car_image: UploadFile = File()` → `CarImageDetailSchema` | 401, 403, 404 `'Автомобиль не найден'`, 400 `'Пустой файл'`, 400 `'Допустимы только изображения JPEG, PNG или WEBP'`, 413 `'Файл слишком большой (максимум 5 МБ)'`, 409 `'Достигнут лимит фотографий для автомобиля (20)'`, 422 |
| `GET /car-image/list?car_id=` | все; видимость авто как в каталоге | → `List[CarImageListSchema]` (главное первым, затем `position`, `id`) | 404 `'Автомобиль не найден'`, 401 плохой токен |
| `GET /car-image/detail?car_image_id=` | все; видимость авто как в каталоге | → `CarImageDetailSchema` | 404 `'Фотография не найдена'` |
| `PUT /car-image/update/{car_image_id}` | admin, seller | `CarImageUpdateSchema` → `CarImageDetailSchema` | 401, 403, 404, 400 явный `null` |
| `DELETE /car-image/delete/{car_image_id}` | admin, seller | → `{'message': 'Фотография удалена'}` | 401, 403, 404 |

Фото удалённого (мягко) авто — 404 во всех эндпоинтах.

#### Хранение и загрузка файлов **[дефолт]**
- Каталог: `Path(MEDIA_DIR) / 'car_images'` (`MEDIA_DIR` из `mysite.config`, дефолт `media` в корне проекта,
  в docker `/app/media`). Константы модуля `car_image.py`: `MAX_IMAGE_SIZE = 5 * 1024 * 1024`,
  `MAX_IMAGES_PER_CAR = 20`, `ALLOWED_IMAGE_TYPES = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}`.
- Тип: `UploadFile.content_type` ∈ `ALLOWED_IMAGE_TYPES` **и** сигнатура первых байт (JPEG `FF D8 FF`,
  PNG `89 50 4E 47 0D 0A 1A 0A`, WEBP `RIFF....WEBP`) — `content_type` присылает клиент, ему не верим.
  SVG/GIF/HTML не принимаются (SVG = XSS). Pillow не добавляем (новая зависимость) — см. «Риски».
- Размер: `data = await car_image.read(MAX_IMAGE_SIZE + 1)`; `len(data) > MAX_IMAGE_SIZE` → 413; `0` → 400.
  nginx уже ограничивает тело `client_max_body_size 10M`.
- Имя файла — только серверное: `f'{uuid4().hex}{ext}'`, расширение — из проверенного типа.
  `UploadFile.filename` **не используется нигде** (ни в пути, ни в БД) → path traversal невозможен.
- В БД `car_image = f'/media/car_images/{filename}'` — готовый URL для клиента.
- Порядок: проверки → запись файла (`open(path, 'wb')`) → `db.add` → `commit`; при исключении на БД — удалить
  записанный файл (`path.unlink(missing_ok=True)`) и пробросить ошибку.
- Удаление: путь на диске строится как `Path(MEDIA_DIR) / 'car_images' / Path(car_image_db.car_image).name`
  (только имя файла из БД, без директорий); сначала `db.delete` + `commit`, затем `unlink(missing_ok=True)`.
- Главное фото: в машине не больше одного `is_main=True`. При `is_main=True` (create/update) остальные фото
  этого авто получают `is_main=False` в той же транзакции. Первое фото авто становится главным автоматически.
  При удалении главного главным становится следующее по `(position, id)`.
- Модуль ссылается на `MEDIA_DIR` во время вызова (а не вычисляет путь при импорте), чтобы тесты могли
  подменить `mysite.api.car_image.MEDIA_DIR` на `tmp_path`.
- Запись файла синхронная внутри `async def` — допустимо для ≤5 МБ и одного воркера.

---

## Docker / nginx

`docker-compose.yml`:
```yaml
services:
  fast_web:
    ...
    environment:
      DATABASE_URL: sqlite:////app/data/auto_salon.db
      MEDIA_DIR: /app/media
    volumes:
      - ./data:/app/data
      - ./media:/app/media
  nginx:
    ...
    volumes:
      - ./media:/app/media:ro
```
- Bind-mount (как `./data`), а не именованный том: файлы видны на хосте, переживают пересборку;
  nginx монтирует **только на чтение**.

`nginx/nginx.conf` — добавить перед `location /`:
```nginx
location /media/ {
    alias /app/media/;
    autoindex off;
    add_header X-Content-Type-Options nosniff always;
    add_header Content-Security-Policy "default-src 'none'" always;
    expires 7d;
}
```
- `add_header` внутри `location` **отменяет** заголовки уровня `server` — поэтому `nosniff` повторяем явно.
- `alias` с завершающим `/` у обоих путей (иначе путь склеится неверно).
- `/static/` не добавляем — статики у приложения нет (sqladmin отдаёт свою статику через FastAPI, это работает
  через `location /`).

`main.py` (локально без nginx): `os.makedirs(os.path.join(MEDIA_DIR, 'car_images'), exist_ok=True)` и
`auto_app.mount('/media', StaticFiles(directory=MEDIA_DIR), name='media')`. В docker запросы `/media/` до FastAPI
не доходят (их обслуживает nginx).

---

## sqladmin

STYLE_GUIDE §10 приводит `CarView`; в этапе 2 решили добавлять представления в этапе своей сущности. Добавляем
**[дефолт]**:
- `BrandView` — `column_list` (id, brand_name, brand_logo), создание/редактирование разрешены, `can_delete = False`
  (удаление с FK даёт 500 в панели; удаление — через API с понятным 409).
- `CarModelView` — (id, brand_id, model_name), `can_delete = False`.
- `CarView` — `column_list` (id, vin, brand_id, car_model_id, year, condition, status, price, currency, deleted_at);
  **только чтение**: `can_create = can_edit = can_delete = False` — правка через панель обошла бы `PriceHistory`,
  правила new/used и мягкое удаление.
- `PriceHistoryView` — только чтение (`can_create = can_edit = can_delete = False`).
- `CarImageView` — не добавляем (файл на диске + `is_main` управляются через API).
- `tests/conftest.py`: добавить новые view в кортеж в `admin_session_local`.

---

## Бизнес-правила этапа

| ТЗ | Правило | Как проверяется |
|---|---|---|
| §3 admin | Справочники марок и моделей — admin | `require_role(admin)` на create/update/delete brand/car-model; тесты 403 seller/client, 401 без токена |
| §3 client | Каталог доступен без входа | `/car/list`, `/car/detail`, `/brand/*`, `/car-model/*`, `/car-image/list|detail` без токена → 200 |
| §3 seller | Seller добавляет/редактирует авто и фото | `require_role(admin, seller)` на car create/update, car-image create/update/delete |
| §3 seller, §5.7 | Смена цены → `PriceHistory` | update: при `price != old` создаётся запись с `old_price`, `new_price`, `changed_by_id`; тест «та же цена — записи нет» |
| §5.8 | Мягкое удаление Car | `deleted_at = now(UTC)`; все выборки car/car-image/price-history с `Car.deleted_at.is_(None)` |
| §5.9 | used: обязательны поля б/у | `condition=used` → `mileage > 0`, `owners_count is not None and >= 1`, `has_accidents is not None`; если `has_accidents=True` → непустой `accident_notes` **[дефолт: конкретный набор]**; иначе 400 `'Для автомобиля с пробегом обязательны: пробег, число владельцев, наличие ДТП'` / `'Укажите описание ДТП'` |
| §5.9 | new: `mileage = 0` | `condition=new` → `mileage == 0` (иначе 400 `'У нового автомобиля пробег должен быть 0'`); `owners_count in (None, 0)`, `has_accidents in (None, False)`, `accident_notes` пусто (иначе 400 `'У нового автомобиля не может быть владельцев и ДТП'`) **[дефолт]** |
| §4.2 Car | VIN уникален, 17 символов | `Vin` в схеме (422), проверка дубля (409, включая удалённые) |
| §4.2 CarModel | `model_name` уникален в пределах марки | проверка в Python (`casefold`) → 409 + `UniqueConstraint` + `IntegrityError` → 409 |
| §4.2 Brand | `brand_name` уникален | проверка в Python (`casefold`) → 409 + `IntegrityError` → 409 |
| §6 | Фильтры каталога + пагинация | query-параметры `/car/list`, `skip/limit` с `le=100` |
| §6, SQLite | Регистр кириллицы | текстовых фильтров в каталоге нет; дубли справочников сравниваются `str.casefold()` в Python по выборке марок / моделей одной марки (таблицы маленькие) |
| §5.2 (подготовка) | `reserved`/`sold` ставит только сделка | `ManualCarStatus` в схемах (422) + 409 на смену статуса у reserved / любое изменение sold |
| CLAUDE.md SQLite | Деньги — `Decimal` | `Money`, фильтры цены `Decimal`; сравнение цены — `Decimal`, без `float` |
| CLAUDE.md SQLite | Время UTC | `deleted_at = datetime.now(timezone.utc)`; `created_at`/`updated_at`/`changed_at` — `server_default`/`onupdate` |

Проверка дублей справочников (`casefold`): `brand_name.casefold()` сравнивается со всеми
`db.query(Brand.id, Brand.brand_name)` (исключая текущую при update); для моделей — только в пределах `brand_id`.
`func.lower()`/`ilike` **не использовать** — для кириллицы в SQLite они не работают.

---

## Миграции

Не требуются. db-specialist: `alembic upgrade head` → `alembic check` (или пустой `--autogenerate`, который
удаляется). Изменения `schema.py`/`dependencies.py`/`config.py` на БД не влияют.

---

## Тесты

`tests/conftest.py` — дополнить:
- `brand` (Toyota), `car_model` (Camry, этой марки), `make_car(**overrides)` — создаёт `Car` напрямую в БД
  (валидный VIN генерируется из счётчика, `created_by_id` — seller/admin).
- `media_dir(tmp_path, monkeypatch)` — `monkeypatch.setattr('mysite.api.car_image.MEDIA_DIR', str(tmp_path))`,
  создать `tmp_path / 'car_images'`. Тесты не пишут в реальный `media/`.
- Хелперы байт: минимальные валидные заголовки JPEG/PNG/WEBP (`b'\xff\xd8\xff...'` и т.п.).
- Новые view в `admin_session_local`.

`tests/test_brand.py`:
- `test_create_brand_as_admin_ok`; `test_create_brand_as_seller_403`, `..._as_client_403`, `..._without_token_401`.
- `test_create_brand_duplicate_409`, `test_create_brand_duplicate_case_insensitive_409` (латиница и кириллица: «Лада»/«лада»).
- `test_create_brand_strips_spaces`, `test_create_brand_blank_name_422`.
- `test_list_brand_public_ok` (без токена), пагинация `skip/limit`, `limit=101` → 422.
- `test_detail_brand_ok`, `test_detail_brand_not_found_404`.
- `test_update_brand_ok`, `test_update_brand_duplicate_409`, `test_update_brand_null_name_400`, `test_update_brand_as_seller_403`.
- `test_delete_brand_ok`, `test_delete_brand_with_models_409`, `test_delete_brand_not_found_404`.

`tests/test_car_model.py`:
- `test_create_car_model_ok`, `..._unknown_brand_404`, `..._duplicate_409` (в т.ч. другой регистр),
  `test_same_model_name_other_brand_ok`, `..._as_seller_403`.
- `test_list_car_model_filter_brand_id`, `test_list_car_model_public_ok`.
- `test_detail_car_model_not_found_404`.
- `test_update_car_model_change_brand_with_cars_409`, `test_update_car_model_change_brand_without_cars_ok`.
- `test_delete_car_model_with_cars_409` (в т.ч. только мягко удалённое авто), `test_delete_car_model_ok`.

`tests/test_car.py`:
- Создание: `test_create_car_new_as_seller_ok` (`created_by_id == seller.id`, `status == 'available'`),
  `test_create_car_as_admin_ok`, `test_create_car_as_client_403`, `test_create_car_without_token_401`.
- `test_create_car_ignores_created_by_id` (поле в теле игнорируется).
- `test_create_car_status_reserved_422`, `test_create_car_status_sold_422`.
- `test_create_car_invalid_vin_422` (16 символов, буква `O`), `test_create_car_vin_lowercase_normalized`.
- `test_create_car_duplicate_vin_409`, `test_create_car_duplicate_vin_of_deleted_car_409`.
- `test_create_car_unknown_brand_404`, `test_create_car_unknown_model_404`, `test_create_car_model_of_other_brand_400`.
- `test_create_car_price_zero_422`, `test_create_car_price_three_decimals_422`, `test_create_car_future_year_400`.
- new/used: `test_create_new_car_with_mileage_400`, `test_create_new_car_with_owners_400`,
  `test_create_used_car_without_owners_400`, `test_create_used_car_without_has_accidents_400`,
  `test_create_used_car_zero_mileage_400`, `test_create_used_car_accident_without_notes_400`, `test_create_used_car_ok`.
- Каталог: `test_list_car_public_ok` (без токена), `test_list_car_hides_deleted`,
  `test_list_car_public_hides_sold_and_withdrawn`, `test_list_car_staff_sees_sold_and_withdrawn`,
  `test_list_car_client_hides_sold` (client = публика),
  фильтры — по одному тесту на `brand_id`, `car_model_id`, `year_min/year_max`, `price_min/price_max`, `condition`,
  `body_type`, `fuel_type`, `transmission`, `drive_type`, `status`, `currency`; комбинированный фильтр;
  `test_list_car_invalid_year_range_400`, `test_list_car_invalid_price_range_400`,
  `test_list_car_invalid_enum_422`, `test_list_car_pagination` (`skip/limit`, порядок новых первыми), `limit=0` → 422.
- `test_list_car_with_invalid_token_401` (плохой токен не превращается в анонима).
- Детально: `test_detail_car_public_ok` (без `created_by_id`/секретов), `test_detail_car_deleted_404`,
  `test_detail_car_sold_public_404`, `test_detail_car_sold_seller_ok`, `test_detail_car_images_main_first`.
- Обновление: `test_update_car_as_seller_ok`, `test_update_car_as_client_403`, `test_update_car_deleted_404`,
  `test_update_car_null_price_400`, `test_update_car_ignores_vin_and_condition`,
  `test_update_used_car_set_owners_null_400` (проверка итогового состояния), `test_update_new_car_set_mileage_400`,
  `test_update_car_status_withdrawn_ok`, `test_update_car_status_sold_422`,
  `test_update_reserved_car_status_409`, `test_update_sold_car_409` (статусы выставлены напрямую в БД).
- История цен: `test_update_price_creates_price_history` (`old_price`, `new_price`, `changed_by_id`),
  `test_update_same_price_no_history`, `test_update_other_fields_no_history`, `test_price_history_two_changes_order`,
  `test_price_history_as_client_403`, `test_price_history_without_token_401`, `test_price_history_deleted_car_404`.
- Удаление: `test_delete_car_as_admin_soft` (строка в БД есть, `deleted_at` не `None`),
  `test_delete_car_as_seller_403`, `test_delete_car_twice_404`, `test_delete_reserved_car_409`.

`tests/test_car_image.py` (все — с `media_dir`):
- `test_upload_jpeg_as_seller_ok` — файл в `tmp_path/car_images`, имя — uuid + `.jpg`, `car_image` начинается с
  `/media/car_images/`, первое фото `is_main=True`.
- `test_upload_png_ok`, `test_upload_webp_ok`.
- `test_upload_as_client_403`, `test_upload_without_token_401`.
- `test_upload_to_deleted_car_404`, `test_upload_to_unknown_car_404`.
- `test_upload_wrong_content_type_400` (`text/plain`), `test_upload_svg_400`,
  `test_upload_fake_jpeg_400` (`content_type=image/jpeg`, байты — HTML), `test_upload_empty_file_400`,
  `test_upload_too_large_413` (5 МБ + 1 байт).
- `test_upload_path_traversal_filename_ignored` — `filename='../../evil.py'` → файл только в `car_images`, имя uuid,
  вне `tmp_path` ничего не создано.
- `test_upload_limit_per_car_409` (константу `MAX_IMAGES_PER_CAR` можно подменить monkeypatch'ем на 2).
- `test_upload_is_main_resets_previous_main`.
- `test_list_images_public_ok` (порядок: главное, position), `test_list_images_deleted_car_404`,
  `test_list_images_sold_car_public_404`.
- `test_detail_image_not_found_404`.
- `test_update_image_set_main`, `test_update_image_position_negative_422`, `test_update_image_as_client_403`.
- `test_delete_image_ok` — строка и файл удалены; `test_delete_main_image_promotes_next`;
  `test_delete_image_file_already_missing_ok`; `test_delete_image_as_client_403`.

`tests/test_admin.py` — дополнить: залогиненный admin открывает `/admin/brand/list`, `/admin/car/list` → 200
(URL-идентификаторы сверить с sqladmin 0.32).

Ожидание «в ответе нет `password`» — проверить в одном тесте detail авто (ответ не содержит вложенного пользователя).

---

## Риски и открытые вопросы

Неблокирующие, решены дефолтом:
1. **Видимость в каталоге** — публика (аноним и client) видит `available`/`in_transit`/`reserved`; `sold`/`withdrawn`
   — только admin/seller. Требует `get_optional_user` в `dependencies.py`. Альтернатива — публичный каталог
   показывает всё, кроме удалённых (тогда `get_optional_user` не нужен).
2. **Плохой токен в публичном эндпоинте → 401**, а не «аноним». Если фронт хранит протухший access — он получит
   401 даже в каталоге; это ожидаемо (сигнал обновить токен).
3. **`/car/price-history/{car_id}` — только admin/seller.** Если история цен должна быть публичной («цена снижена») —
   снять `require_role`.
4. **Seller правит любое авто** (не только созданное им); удаление авто — только admin.
5. **Неизменяемые после создания** `vin`, `brand_id`, `car_model_id`, `condition` (их нет в `CarUpdateSchema`).
   Ошибку при вводе VIN исправить нельзя: удалённое авто держит VIN (unique) → нужен ручной фикс в БД.
   Если нужно — добавить эти поля в `CarUpdateSchema` (с теми же проверками), решает автор.
6. **Набор обязательных полей для used** (`mileage > 0`, `owners_count >= 1`, `has_accidents`, `accident_notes` при ДТП)
   — интерпретация «…» в ТЗ §5.9. `customs_cleared`/`registered_in_kr` имеют дефолт `False` и не проверяются.
7. **Смена `currency` без смены цены** в `PriceHistory` не пишется (в таблице нет валюты). Полноценный журнал — AuditLog, этап 5.
8. **Изменения sold/reserved** — sold полностью заморожен, у reserved нельзя менять статус; цену reserved менять можно
   (сделка фиксирует `base_price` у себя — этап 5).
9. **Проверка изображений — по сигнатуре байт, без Pillow.** Полиглот-файл (валидный заголовок + мусор) пройдёт;
   при отдаче nginx ставит `nosniff` и CSP `default-src 'none'`, расширение — только `.jpg/.png/.webp`, так что
   исполнения/XSS нет. Полная валидация/пересжатие — Pillow (новая зависимость) — по решению автора.
10. **Файлы фото мягко удалённого авто** остаются на диске и доступны по прямому URL `/media/...`
    (nginx не знает про `deleted_at`). Для этапа приемлемо.
11. **Сироты на диске**: если процесс упадёт между записью файла и `commit`, файл останется. Чистку не делаем.
12. **`CarImageCreateSchema` не используется** (multipart вместо JSON). Не удаляем — правка «на будущее» вне этапа.
13. **`brand_logo`** — остаётся строкой (URL), загрузку логотипа не делаем (в ROADMAP нет).
14. **Регистронезависимые дубли** проверяются в Python, БД защищает только точное совпадение. При гонке двух
    одновременных запросов «Toyota»/«toyota» обе вставки пройдут (один воркер uvicorn делает это маловероятным).
15. **Нет текстового поиска** в каталоге (ТЗ §6 его не требует). Если понадобится `q` по описанию/цвету — фильтровать
    в Python после выборки (`casefold`) или колонка `*_lower` (изменение моделей + миграция) — спросить автора.
16. **Фильтр цены без конвертации валют** — `price_min/max` сравнивают числа как есть.
17. **Naive datetime в ответах** (`created_at`, `updated_at`, `changed_at` без `+00:00`) — как в этапе 2;
    приведение к aware в ответах — отдельное решение.
18. **SQLite и `Decimal`**: SQLAlchemy хранит `Numeric` в SQLite как REAL-совместимое значение и может выдавать
    предупреждение о Decimal; для цен до 14 знаков с 2 знаками после запятой точность достаточна, но тест
    `test_update_same_price_no_history` с ценой вида `'1234567.89'` это проверит.
19. **Год `<= текущий + 1`** — дополнительная проверка сверх `Year (1900..2100)`.
20. **Сортировка каталога** — только «новые первыми»; параметр сортировки (по цене/году) не вводим.
21. **Количество в каталоге** (`total`) не возвращаем — ответ `List[...]`, как в `/user/list`.

---

## Не делаем в этом этапе

- `lead`, `notification` (этап 4); `deal`, `discount`, бронь атомарным `UPDATE`, фоновая задача
  истечения брони, `AuditLog` (этап 5); `trade_in` + `TradeInImage`, `favorite`, `review`, `credit` (кредитный
  калькулятор и сравнение до 4 авто), `statistic` (этап 6).
- Переходы `reserved`/`sold` у авто — только через сделку (этап 5).
- Загрузка `brand_logo` и `profile_image` файлами.
- Изменения `models.py` и новые миграции (в т.ч. `order_by` у `Car.images`, `*_lower` поля).
- Новые модули/утилиты (`utils.py`, `storage.py` и т.п.), Pillow, пересжатие/миниатюры, S3.
- Эндпоинт восстановления мягко удалённого авто.
- `/static/` в nginx.
- Текстовый поиск и сортировка каталога по параметру.

---

## Порядок работы

1. **db-specialist** — без изменений моделей: `alembic upgrade head` + `alembic check`, подтвердить, что миграция
   не нужна.
2. **coder** (по порядку):
   1. `mysite/config.py` (`MEDIA_DIR`), `.env.example`.
   2. `mysite/db/schema.py` — `StringConstraints(strip_whitespace=True, ...)` для `brand_name`, `model_name`, `color`.
   3. `mysite/api/dependencies.py` — `oauth2_scheme_optional`, `get_optional_user`.
   4. `mysite/api/brand.py`, `mysite/api/car_model.py` (по skill `crud-router`).
   5. `mysite/api/car.py` — каталог, фильтры, видимость, create/update (new/used, PriceHistory), мягкое удаление, price-history.
   6. `mysite/api/car_image.py` — загрузка, проверка типа/сигнатуры/размера, uuid-имена, is_main, удаление файла.
   7. `main.py` — роутеры, `os.makedirs`, `StaticFiles` на `/media`.
   8. `mysite/admin/view.py`, `mysite/admin/setup.py` — новые представления.
   9. `docker-compose.yml`, `nginx/nginx.conf` — `./media` и `location /media/`.
   10. Проверка: `python -c "import main"`, `uvicorn main:auto_app` → `/docs`, загрузка фото и открытие `/media/...`.
3. **tester** — `tests/conftest.py` (фикстуры) + `test_brand.py`, `test_car_model.py`, `test_car.py`,
   `test_car_image.py`, дополнение `test_admin.py`; `.venv/Scripts/python.exe -m pytest -q`.
4. **reviewer + security-auditor** — по `git diff`; особое внимание: загрузка файлов (тип, размер, имя, путь
   удаления), `nosniff`/CSP в `location /media/`, видимость sold/withdrawn и удалённых, отсутствие `func.lower`/`ilike`,
   `Decimal` без `float`, `created_by_id`/`changed_by_id` только с сервера.
5. **coder** — исправления 🔴 critical. Автор вручную: `docker compose up --build`, загрузка фото через nginx,
   открытие `http://localhost/media/car_images/<uuid>.jpg`.
6. Отметить чекбоксы в `docs/ROADMAP.md`, отчёт + предложенный коммит
   `feat(car): add brands, car models, car catalog with price history and image upload (stage 3)` → **СТОП**.
