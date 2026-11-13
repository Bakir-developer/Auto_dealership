# План: Этап 2 — Docker, Auth и роли

## Открытые вопросы (блокирующие)

Нет. Всё, что ниже помечено **[дефолт]**, — решение архитектора по умолчанию; автор может
переопределить до начала работы coder'а (см. раздел «Риски и открытые вопросы»).

---

## Цель и границы

Цель: приложение запускается в Docker (fast_web + nginx, SQLite-файл в `./data`), есть
регистрация/логин/логаут/обновление токенов, зависимости `get_current_user` / `require_role`,
управление профилем и продавцами, защищённая sqladmin-панель (только admin), seed первого админа
и `SalonSettings`, тесты auth и ролей.

Границы:
- Модели и миграции **не меняются** (всё нужное уже есть в `initial`: `UserProfile`, `RefreshToken`,
  `SalonSettings`, `UserRole`).
- Роутеры — только `auth.py` и `user.py`. Никаких роутеров/заглушек сущностей этапов 3+.
- sqladmin — только представления `UserProfile` и `SalonSettings`.

Текущее состояние (проверено): есть `main.py` (только `/health`), `mysite/config.py`,
`mysite/db/{database,models,schema}.py`, `alembic.ini`, `migrations/` (`45c6f4b7c659_initial.py`).
Нет: `mysite/api/`, `mysite/admin/`, `tests/`, `Dockerfile`, `docker-compose.yml`, `nginx/`,
`.dockerignore`.

---

## Файлы (создать / изменить)

### Создать
| Путь | Что |
|---|---|
| `Dockerfile` | `FROM python:3.12`, `ENV PYTHONUNBUFFERED=1`, `WORKDIR /app`, `COPY requirements.txt /app/`, `RUN pip install --no-cache-dir -r requirements.txt`, `COPY . /app/`. CMD не нужен (команда — в compose). |
| `.dockerignore` | **Обязателен**: `.env`, `.env.*` (кроме `.env.example`), `*.db`, `*.db-journal`, `.venv/`, `venv/`, `.git/`, `.idea/`, `__pycache__/`, `.pytest_cache/`, `.claude/`, `media/`. Иначе `COPY . /app/` утащит в образ `.env` с секретами и локальную `auto_salon.db`. |
| `docker-compose.yml` | см. раздел «Docker» ниже. |
| `nginx/Dockerfile` | `FROM nginx:latest` + `COPY nginx.conf /etc/nginx/conf.d/default.conf`. |
| `nginx/nginx.conf` | `server { listen 80; client_max_body_size 10M; location / { proxy_pass http://fast_web:8000; proxy_set_header Host $host; X-Real-IP; X-Forwarded-For; X-Forwarded-Proto $scheme; } }`. `/static/`, `/media/` — **не** добавляем (этап 3, см. «Не делаем»). |
| `mysite/api/__init__.py` | пустой. |
| `mysite/api/auth.py` | `pwd_context`, `get_password_hash`, `verify_password`, `create_access_token`, `create_refresh_token`, `decode_token`, `auth_router` с эндпоинтами `/auth/*`. |
| `mysite/api/dependencies.py` | `oauth2_scheme`, `get_current_user`, `require_role` — по STYLE_GUIDE §7 + проверка `type == 'access'`. |
| `mysite/api/user.py` | `user_router` (`prefix='/user'`, `tags=['UserProfile']`). |
| `mysite/admin/__init__.py` | пустой. |
| `mysite/admin/view.py` | `UserProfileView`, `SalonSettingsView`. |
| `mysite/admin/setup.py` | `AdminAuth(AuthenticationBackend)` + `setup_admin(app)`. |
| `mysite/seed.py` | seed-скрипт (запуск `python -m mysite.seed`). **[дефолт]** расположение. |
| `tests/__init__.py`, `tests/conftest.py`, `tests/test_auth.py`, `tests/test_user.py`, `tests/test_admin.py`, `tests/test_seed.py` | тесты. |

### Изменить
| Путь | Что |
|---|---|
| `main.py` | `from mysite.admin.setup import setup_admin`, `from mysite.api import auth, user`; `auto_app.include_router(auth.auth_router)`, `auto_app.include_router(user.user_router)` (по строке); `setup_admin(auto_app)`. `/health` оставить. |
| `mysite/config.py` | добавить константы: `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PHONE`, `ADMIN_PASSWORD` — `os.getenv(...)` **без дефолтов**. Больше ничего. |
| `mysite/db/schema.py` | добавить одну схему `UserProfileDiscountLimitSchema(discount_limit: Percent)` в блок UserProfile. Остальные схемы уже есть. |
| `.env.example` | добавить `ADMIN_USERNAME=`, `ADMIN_EMAIL=`, `ADMIN_PHONE=+996XXXXXXXXX`, `ADMIN_PASSWORD=<не короче 8 символов>` (пустые/плейсхолдеры) и комментарий, что в docker `DATABASE_URL` переопределяется в compose. |
| `requirements.txt` | проверить `pip show itsdangerous` (нужен Starlette `SessionMiddleware`, который подключает sqladmin-аутентификация). Если не стоит транзитивно — добавить `itsdangerous` с пином. Больше ничего не трогать. |
| `docs/ROADMAP.md` | отметить чекбоксы этапа 2, обновить строку «Текущий этап». |

`.env` агенты менять не могут (хук) — автор вручную добавляет `ADMIN_*` в свой `.env`.

---

## Docker

`docker-compose.yml`:
```yaml
services:
  fast_web:
    build: .
    command: uvicorn main:auto_app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
    env_file: .env
    environment:
      DATABASE_URL: sqlite:////app/data/auto_salon.db
    volumes:
      - ./data:/app/data
    expose:
      - "8000"
  nginx:
    build: ./nginx
    ports:
      - "80:80"
    depends_on:
      - fast_web
```
- `environment` в compose имеет приоритет над `env_file`, а `load_dotenv()` не перезаписывает уже заданные
  переменные → в контейнере БД лежит в `./data` на хосте (bind-mount `/app/data`, переживает пересборку),
  локально — `./auto_salon.db` из `.env`. `data/` — в `.gitignore` и `.dockerignore`.
- Один процесс uvicorn, **без `--workers`** (SQLite: одна запись за раз).
- `--proxy-headers` — чтобы sqladmin строил ссылки/редиректы с правильной схемой/хостом за nginx.
- Порт 8000 наружу не публикуется — только nginx:80.
- Порядок первого запуска:
  ```
  docker compose up --build -d
  docker compose exec fast_web alembic upgrade head
  docker compose exec fast_web python -m mysite.seed
  ```

---

## Модели / поля / связи / ограничения

**Изменений моделей нет. Миграции нет.**

Используются существующие:
- `UserProfile` — `username` (unique), `email` (unique), `phone_number`, `role: Enum(UserRole)`,
  `password` (bcrypt-хеш), `is_active`, `discount_limit Numeric(5,2)` (CHECK 0..100), `created_at`;
  связь `refresh_tokens` с `cascade='all, delete-orphan'`.
- `RefreshToken` — `user_id` (FK, index), `token` (`String`, **unique**). Отдельного поля срока жизни
  нет и не нужно: срок проверяется по `exp` внутри JWT, а наличие строки в таблице — признак того,
  что токен не отозван (logout/ротация).
- `SalonSettings` — одна строка (`CHECK id = 1`), `work_start/work_end` обязательны, `CHECK work_end > work_start`.
- `UserRole` — `admin/seller/client`.

Важное следствие `unique` на `RefreshToken.token`: два логина одного пользователя в одну секунду дадут
одинаковый JWT → `IntegrityError`. Поэтому в refresh-токен обязательно кладём `jti = uuid4().hex`.

---

## Схемы

Существующие (не меняются): `RegisterSchema`, `LoginSchema`, `RefreshTokenSchema`, `TokenSchema`,
`UserProfileCreateSchema`, `UserProfileUpdateSchema`, `UserProfileListSchema`,
`UserProfileDetailSchema`, `SalonSettingsDetailSchema` (в API не используется на этом этапе).

Новая: `UserProfileDiscountLimitSchema` — `discount_limit: Percent` (0..100, 2 знака).

Что **не принимается от клиента**:
- `RegisterSchema` — нет `role`, `is_active`, `discount_limit`. Лишние поля Pydantic игнорирует
  (extra='ignore') → `role='admin'` в теле молча отбрасывается, роль всегда `client`.
- `UserProfileCreateSchema` (админ создаёт продавца) — нет `role` (сервер ставит `seller`), нет `is_active`.
- `UserProfileUpdateSchema` (свой профиль) — нет `username`, `role`, `is_active`, `discount_limit`, `password`.
- Ни одна схема ответа не содержит `password`; токены возвращаются только в `TokenSchema`
  (ответ login/access_generate) — это ожидаемо.

---

## Эндпоинты

### `auth_router` — `prefix='/auth'`, `tags=['Authorization']`

| Метод, путь | Доступ | Вход → выход | Ошибки |
|---|---|---|---|
| `POST /auth/register` | все | `RegisterSchema` → `UserProfileDetailSchema` **[дефолт]: токены не выдаём, клиент логинится отдельно** | 409 `'Пользователь с таким username уже существует'`, 409 `'Пользователь с таким email уже существует'`, 422 валидация |
| `POST /auth/login` | все | `LoginSchema` (JSON) → `TokenSchema` | 401 `'Неверный логин или пароль'` (одинаково для «нет пользователя» и «неверный пароль»), 403 `'Пользователь заблокирован'` (только после успешной проверки пароля) |
| `POST /auth/logout` | все (access-токен не требуется — он мог истечь) | `RefreshTokenSchema` → `{'message': 'Вы вышли из системы'}` | 401 `'Недействительный refresh-токен'` (невалиден/истёк/не refresh/нет в БД) |
| `POST /auth/access_generate` | все | `RefreshTokenSchema` → `TokenSchema` (новая пара) | 401 `'Недействительный refresh-токен'`, 401 `'Пользователь не найден или заблокирован'` |

Логика:
- `register`: проверка дублей username и email (`db.query(...).first()`) → 409; затем
  `UserProfile(**data.model_dump(exclude={'password'}), password=get_password_hash(...), role=UserRole.client)`;
  страховка — `IntegrityError` → `db.rollback()` → 409.
- `login`: найти по `username`; `verify_password`; `is_active`; создать access + refresh; сохранить
  `RefreshToken(user_id, token=refresh)`; вернуть `{'access_token', 'refresh_token', 'user_id', 'type': 'bearer'}`.
- `logout`: `decode_token` → `type == 'refresh'` → найти строку `RefreshToken.token == token` → удалить.
- `access_generate` (ротация): decode → `type == 'refresh'` → строка есть в БД → пользователь есть и
  `is_active` → удалить старую строку, создать новую пару, сохранить новый refresh, `commit`.

Функции `auth.py`:
- `pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')`.
- `create_access_token(data: dict)` — копия `data` + `exp = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE_TOKEN)` + `'type': 'access'`.
- `create_refresh_token(data: dict)` — `exp` через `REFRESH_EXPIRE_TOKEN` дней + `'type': 'refresh'` + `'jti': uuid4().hex`.
- payload: `{'sub': username, 'user_id': id}` (STYLE_GUIDE §8) + `type`/`exp` (+`jti`).
- `decode_token(token: str) -> dict` — `jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])`;
  `JWTError` (включая истёкший) → `HTTPException(401, 'Недействительный или просроченный токен', headers={'WWW-Authenticate': 'Bearer'})`.
  Проверку `type` делают вызывающие.
- Если `SECRET_KEY` пуст — `auth.py` при импорте поднимает `RuntimeError('SECRET_KEY не задан')`
  (fail fast; `config.py` остаётся только с константами, alembic не ломается).
- `auth.py` **не импортирует** `dependencies.py` (иначе цикл: dependencies импортирует `decode_token` из auth).

### `dependencies.py`
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/login')`.
- `get_current_user`: `decode_token` → `type != 'access'` → 401; `user_id` нет → 401; пользователь не
  найден или `is_active=False` → 401 `'Пользователь не найден или заблокирован'`. Без токена — 401 (сам `OAuth2PasswordBearer`).
- `require_role(*roles)` — как в STYLE_GUIDE §7, чужая роль → 403 `'Недостаточно прав'`.

### `user_router` — `prefix='/user'`, `tags=['UserProfile']`

| Метод, путь | Роль | Вход → выход | Ошибки |
|---|---|---|---|
| `GET /user/profile` | любая авторизованная | → `UserProfileDetailSchema` (свой) | 401 |
| `PUT /user/profile` | любая авторизованная | `UserProfileUpdateSchema` → `UserProfileDetailSchema` | 401; 409 email занят другим; 400 `'Поле не может быть пустым'` при явном `null` в `email`/`phone_number`; 422 |
| `POST /user/create` | admin | `UserProfileCreateSchema` → `UserProfileDetailSchema` (создаёт **seller**) | 401, 403, 409 username/email |
| `GET /user/list` | admin | query: `role: UserRole \| None`, `is_active: bool \| None`, `skip: int = 0 (ge=0)`, `limit: int = 20 (ge=1, le=100)` → `List[UserProfileListSchema]`, сортировка по `id` | 401, 403 |
| `GET /user/detail?user_id=` | admin | → `UserProfileDetailSchema` | 401, 403, 404 `'Пользователь не найден'` |
| `POST /user/block/{user_id}` | admin | → `UserProfileDetailSchema` | 401, 403; 404; 400 `'Нельзя заблокировать самого себя'`; 403 `'Нельзя заблокировать администратора'`; 409 `'Пользователь уже заблокирован'` |
| `POST /user/unblock/{user_id}` | admin | → `UserProfileDetailSchema` | 401, 403, 404, 409 `'Пользователь не заблокирован'` |
| `PUT /user/discount-limit/{user_id}` | admin | `UserProfileDiscountLimitSchema` → `UserProfileDetailSchema` | 401, 403, 404, 400 `'Лимит скидки задаётся только продавцу'`, 422 вне 0..100 |

Детали:
- `create` продавца: `discount_limit` не передан (`'discount_limit' not in data.model_fields_set`) →
  берётся `SalonSettings.default_discount_limit` (если записи нет — `0`). `role=UserRole.seller`, пароль — хеш.
- `block`: `is_active=False` + удалить все `RefreshToken` пользователя. Access-токен перестаёт работать
  сразу — `get_current_user` проверяет `is_active` на каждом запросе.
- Удаление пользователей через API — **нет** (вместо удаления — блокировка; на пользователей ссылаются FK).
- Для этих эндпоинтов IDOR неприменим в форме «чужой → 404»: свой профиль берётся только из
  `current_user`, `user_id` в путях доступен только admin.

### sqladmin (`/admin`) — только admin

`admin/setup.py`:
- `class AdminAuth(AuthenticationBackend)`:
  - `login(request)`: форма `username`/`password`; пользователь найден, `verify_password`, `role == admin`,
    `is_active` → `request.session.update({'user_id': user.id})`, `True`; иначе `False`.
  - `authenticate(request)`: `user_id` из сессии; **на каждом запросе** перечитать пользователя из БД
    и проверить `role == admin` и `is_active` (так блокировка/смена роли действуют сразу).
  - `logout(request)`: `request.session.clear()`.
  - БД — `db = SessionLocal()` + `try/finally db.close()`; `SessionLocal` импортируется в модуль
    `mysite.admin.setup` (тесты подменяют его через monkeypatch).
- `setup_admin(app)`: `Admin(app, engine=engine, authentication_backend=AdminAuth(secret_key=SECRET_KEY))`,
  `add_view(UserProfileView)`, `add_view(SalonSettingsView)`. Cookie сессии подписывается `SECRET_KEY`.

`admin/view.py`:
- `UserProfileView`: `column_list` (id, username, email, role, is_active, discount_limit, created_at),
  `column_exclude_list`/`column_details_exclude_list = [UserProfile.password]`,
  `form_columns = [first_name, last_name, email, phone_number, role, is_active, discount_limit]`
  (без `password` и без коллекций-связей), `can_create = False` (иначе пароль сохранится
  открытым текстом — пользователей создаём через API/seed), `can_delete = False`.
- `SalonSettingsView`: все поля, `can_create = False`, `can_delete = False` (запись создаёт seed).

---

## Seed-скрипт

`mysite/seed.py`, запуск: `python -m mysite.seed` (локально) /
`docker compose exec fast_web python -m mysite.seed`.

- Данные админа — **только** из окружения через `mysite.config`: `ADMIN_USERNAME`, `ADMIN_EMAIL`,
  `ADMIN_PHONE`, `ADMIN_PASSWORD`. Никаких хардкод-значений. Если хоть одна пуста →
  сообщение `'Заполните ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PHONE, ADMIN_PASSWORD в .env'` и `sys.exit(1)`.
- Валидация входа — через `UserProfileCreateSchema(...)` (формат телефона, email, длина пароля 8..72);
  `ValidationError` → понятное сообщение и `sys.exit(1)`. Пароль в вывод не печатать.
- Функции (чтобы тестировать без env):
  - `create_admin(db, username, email, phone_number, password) -> UserProfile` — если пользователь с таким
    `username` или `email` уже есть → ничего не менять (пароль **не** перезаписывается), вернуть существующего
    и вывести `'Администратор уже существует'`; иначе создать `role=admin`, `is_active=True`, пароль — `get_password_hash`.
    Если существующий пользователь с этим username не admin — `sys.exit(1)` с сообщением (не повышать роль молча).
  - `create_salon_settings(db) -> SalonSettings` — если записи `id=1` нет, создать с дефолтами:
    `salon_name='Auto Salon'`, `address='г. Бишкек'`, `phone_number=ADMIN_PHONE`,
    `work_start=time(9, 0)`, `work_end=time(18, 0)`, `test_drive_minutes=60`, `reservation_hours=48`,
    `default_discount_limit=3`. Существующую запись не трогать. **[дефолт]** значения — правятся в sqladmin.
  - `main()` — `SessionLocal()`, обе функции, `commit`, `finally db.close()`; `if __name__ == '__main__': main()`.
- Идемпотентен: повторный запуск ничего не дублирует.

---

## Бизнес-правила этапа

| ТЗ | Правило | Как проверяется |
|---|---|---|
| §3 client | Открытая регистрация — только client | `/auth/register` жёстко ставит `role=client`; тест с `role='admin'` в теле |
| §3 admin, seller | Продавцов создаёт только admin | `POST /user/create` → `require_role(admin)`; тесты 403 для seller/client |
| §3 admin | Блокировка `is_active=False` | `/user/block`; заблокированный: login 403, access 401, refresh 401 |
| §3 admin | Лимит скидки продавца | `/user/discount-limit/{id}`, 0..100, только seller |
| §3 admin | Первый админ — seed | `mysite/seed.py`, тест идемпотентности |
| §4.2 SalonSettings | Одна запись, `default_discount_limit=3` | seed; дефолт лимита для нового seller |
| §6 | Пароль — bcrypt, в ответах нет пароля/токенов из БД | хеш `$2b$`, тест «нет `password` в ответе» |
| CLAUDE.md | Секреты только из `.env` через config | `SECRET_KEY`, `ADMIN_*` без дефолтов; `.dockerignore` |

---

## Миграции

Не требуются. db-specialist только проверяет, что модели и БД совпадают:
`alembic upgrade head` → `alembic check` (или `alembic revision --autogenerate` даёт пустую
миграцию — тогда её удалить, не коммитить).

---

## Тесты

`tests/conftest.py` — по skill `testing`, плюс:
- **до** `from main import auto_app`: `os.environ['DATABASE_URL'] = TEST_DATABASE_URL` и
  `os.environ.setdefault('SECRET_KEY', 'test-secret-key-...')` — чтобы ни приложение, ни sqladmin
  не трогали рабочую `auto_salon.db`, а тесты не зависели от локального `.env`.
- фикстуры `admin`, `seller`, `client_user`, `make_user`, `auth_headers` — как в skill.
- фикстура `admin_session_local(monkeypatch, db)` — подменяет `mysite.admin.setup.SessionLocal`
  на фабрику, возвращающую тестовую `db` (с no-op `close`), чтобы sqladmin видел данные теста.

`tests/test_auth.py`:
- `test_register_ok` — 200, `role == 'client'`, нет `password` в ответе; в БД пароль — bcrypt-хеш, не открытый текст.
- `test_register_ignores_role_admin` — `role='admin'` в теле → создан client.
- `test_register_duplicate_username_409`, `test_register_duplicate_email_409`.
- `test_register_invalid_phone_422`, `test_register_short_password_422`, `test_register_invalid_email_422`.
- `test_login_ok` — есть `access_token`, `refresh_token`, `user_id`, `type == 'bearer'`; строка `RefreshToken` создана.
- `test_login_twice_creates_distinct_refresh_tokens` — два логина подряд не падают (jti).
- `test_login_wrong_password_401`, `test_login_unknown_user_401` (одинаковый текст ошибки).
- `test_login_blocked_user_403`.
- `test_access_generate_ok` — новая пара; старый refresh удалён из БД.
- `test_access_generate_old_refresh_after_rotation_401`.
- `test_access_generate_with_access_token_401` (тип не refresh).
- `test_access_generate_expired_refresh_401` (токен с прошедшим `exp`, собран через `jose.jwt.encode`).
- `test_access_generate_garbage_token_401`.
- `test_access_generate_blocked_user_401`.
- `test_logout_ok` — строка удалена; затем `access_generate` с этим токеном → 401.
- `test_logout_unknown_token_401`.
- `test_protected_without_token_401` (`GET /user/profile`).
- `test_protected_with_refresh_token_as_access_401`.
- `test_protected_expired_access_401`.
- `test_protected_blocked_user_access_401`.

`tests/test_user.py`:
- `test_profile_ok_each_role` (admin/seller/client), нет `password`.
- `test_profile_update_ok` (имя, телефон).
- `test_profile_update_email_taken_409`.
- `test_profile_update_cannot_change_role_or_discount_limit` — поля в теле игнорируются.
- `test_profile_update_null_email_400`.
- `test_create_seller_as_admin_ok` — `role == 'seller'`, `discount_limit` = `SalonSettings.default_discount_limit` (если запись есть) / 0 (если нет); явный `discount_limit` применяется.
- `test_create_seller_as_seller_403`, `test_create_seller_as_client_403`, `test_create_seller_without_token_401`.
- `test_create_seller_duplicate_username_409`.
- `test_list_users_as_admin_ok`, фильтр `role=seller`, пагинация `skip/limit`; `test_list_users_as_client_403`, `..._as_seller_403`.
- `test_detail_user_as_admin_ok`, `test_detail_user_not_found_404`, `test_detail_user_as_seller_403`.
- `test_block_seller_ok` — `is_active=False`, refresh-токены удалены, после этого его access → 401, login → 403.
- `test_block_self_400`, `test_block_admin_403`, `test_block_already_blocked_409`, `test_block_not_found_404`, `test_block_as_seller_403`.
- `test_unblock_ok`, `test_unblock_not_blocked_409`.
- `test_discount_limit_ok`, `test_discount_limit_out_of_range_422` (101, -1), `test_discount_limit_for_client_400`, `test_discount_limit_as_seller_403`.

`tests/test_admin.py` (sqladmin):
- `test_admin_panel_without_login_redirects` — `GET /admin/` → редирект на `/admin/login` (`follow_redirects=False`).
- `test_admin_login_as_admin_ok` — `POST /admin/login` (form) → редирект в панель; затем `GET /admin/` → 200.
- `test_admin_login_as_seller_denied`, `test_admin_login_as_client_denied`, `test_admin_login_wrong_password_denied`,
  `test_admin_login_blocked_admin_denied` — нет доступа к `/admin/` (код ответа сверить с sqladmin 0.32: форма логина с ошибкой, не 302 в панель).
- `test_admin_session_revoked_after_block` — залогиненный admin, затем `is_active=False` → `GET /admin/` снова редирект на логин.

`tests/test_seed.py`:
- `test_create_admin_ok` — role admin, хеш пароля, `is_active=True`.
- `test_create_admin_idempotent` — второй вызов не создаёт дубль и не меняет пароль.
- `test_create_salon_settings_once` — одна запись `id=1`, повторный вызов не меняет её.
- `test_seed_main_without_env_exits` — пустые `ADMIN_*` (monkeypatch атрибутов `mysite.seed`/`mysite.config`) → `SystemExit`.

---

## Риски и открытые вопросы

Неблокирующие, решены дефолтом:
1. **Swagger «Authorize».** STYLE_GUIDE: `OAuth2PasswordBearer(tokenUrl='auth/login')` + JSON `LoginSchema`.
   Кнопка Authorize в `/docs` шлёт form-data → с JSON-логином не сработает (запросы из Swagger придётся
   делать с ручным заголовком / через Postman). **[дефолт]** оставляем по STYLE_GUIDE. Альтернатива —
   `OAuth2PasswordRequestForm` в `/auth/login` (ломает JSON-контракт) — решает автор.
2. **`type` и `jti` в JWT** — дополнение к payload из STYLE_GUIDE §8: без `type` refresh-токен (живёт 7 дней)
   можно использовать как access; без `jti` — коллизия по `unique` в `refresh_token.token`.
3. **Refresh-токены хранятся в БД открытым текстом** (как STYLE_GUIDE §4.5). Утечка БД = утечка
   действующих refresh-токенов. Можно хранить SHA-256 без изменения схемы — **[дефолт]** не делаем,
   решение за автором/security-auditor.
4. **Рост таблицы `refresh_token`**: просроченные, но не отозванные токены не удаляются (нет `expires_at`).
   Для этапа приемлемо; чистку можно добавить позже (потребует поле → миграцию).
5. **Расположение seed** — `mysite/seed.py` (в STYLE_GUIDE не описано). Альтернатива — `seed.py` в корне.
6. **register возвращает профиль, а не токены** — **[дефолт]**.
7. **Блокировка/лимит — отдельными действиями** (`/user/block`, `/user/unblock`, `/user/discount-limit`)
   вместо общего `PUT /user/update/{id}` для админа.
8. **sqladmin обходит API-валидацию**: правки через панель не проверяют формат телефона и не удаляют
   refresh-токены при блокировке. Смягчение: `get_current_user` и `access_generate` проверяют `is_active`
   на каждом запросе, так что блокировка через панель всё равно действует сразу.
9. **Контейнер работает от root** (минимальный Dockerfile из STYLE_GUIDE). Non-root — улучшение
   на потом, отметить security-auditor.
10. **SQLite + один воркер uvicorn**: масштабировать `--workers` нельзя (блокировки записи).
11. **Подбор пароля**: rate-limit на `/auth/login` и `/admin/login` не делаем (нет в ТЗ/этапе).
12. **Версия Python**: локально `.venv` на 3.14, образ — `python:3.12`. Пины `requirements.txt` должны
    ставиться на 3.12 — проверить сборкой. `passlib 1.7.4 + bcrypt 4.0.1` — не обновлять.
14. Смена пароля пользователем и сброс пароля — в ТЗ нет; не делаем (см. ниже). Нужно ли — вопрос автору.

---

## Не делаем в этом этапе

- Роутеры `brand`, `car_model`, `car`, `car_image` (этап 3); `lead`, `test_drive`, `notification` (этап 4);
  `deal`, `discount`, фоновая задача брони, `AuditLog` (этап 5); `trade_in`, `favorite`, `review`,
  `credit`, `statistic` (этап 6).
- API для `SalonSettings` (детально/изменение) — только seed + sqladmin. Если нужен эндпоинт — спросить автора.
- sqladmin-представления для остальных моделей (Brand, Car, Deal, …) — добавляются в своих этапах.
- `/static/`, `/media/` в nginx и тома `static_volume`/`media_volume`, загрузка файлов
  (`profile_image` пока просто строка) — этап 3 (фото авто).
- Запуск `alembic upgrade head` автоматически при старте контейнера — только вручную через `exec`.
- Изменения моделей и новые миграции.
- Смена/сброс пароля, подтверждение email, rate-limit, удаление пользователей через API.
- Запись в `AuditLog` о блокировке/изменении лимита (AuditLog — этап 5).

---

## Порядок работы

1. **db-specialist** — без изменений моделей: `alembic upgrade head` + `alembic check` на `auto_salon.db`,
   подтвердить, что миграция не нужна. Проверить `pip show itsdangerous`.
2. **coder** (по порядку):
   1. `mysite/config.py` (`ADMIN_*`), `.env.example`, `requirements.txt` (при необходимости `itsdangerous`).
   2. `mysite/db/schema.py` — `UserProfileDiscountLimitSchema`.
   3. `mysite/api/__init__.py`, `mysite/api/auth.py`, `mysite/api/dependencies.py`, `mysite/api/user.py`.
   4. `mysite/admin/__init__.py`, `mysite/admin/view.py`, `mysite/admin/setup.py`.
   5. `main.py` — подключение роутеров и `setup_admin`.
   6. `mysite/seed.py`.
   7. `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `nginx/Dockerfile`, `nginx/nginx.conf`.
   8. Проверка: `python -c "import main"`, `uvicorn main:auto_app` локально → `/docs`, `/admin`.
3. **tester** — `tests/` по списку выше; `.venv/Scripts/python.exe -m pytest -q`.
4. **reviewer + security-auditor** — по `git diff` (особое внимание: `.dockerignore`, отсутствие `password`
   в ответах, тип токена, 401 vs 403, защита `/admin`, отсутствие хардкода секретов в seed).
5. **coder** — исправления 🔴 critical. Автор вручную: добавить `ADMIN_*` в `.env`, проверить
   `docker compose up --build`, `exec alembic upgrade head`, `exec python -m mysite.seed`, вход в `/admin` через nginx.
6. Отметить чекбоксы в `docs/ROADMAP.md`, отчёт + предложенный коммит
   `feat(auth): add docker, auth, roles, user management and sqladmin (stage 2)` → **СТОП**.
