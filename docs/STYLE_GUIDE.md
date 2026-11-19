# STYLE GUIDE — FastAPI Auto Salon

Главный эталон для всех агентов. Источник стиля — проект автора `mafia_app`
(+ `fastapi_booking`, `fastapi_wilberries`). Если что-то здесь противоречит
«общепринятым best practices» — **побеждает этот документ**.

Запрещено:
- добавлять слои `services/`, `repositories/`, `crud/`, `core/`, `utils/` и т.п.;
- разбивать `models.py` и `schema.py` на несколько файлов;
- переходить на async SQLAlchemy (`AsyncSession`, async-движки вроде `aiosqlite`);
- менять имена, пути и структуру, описанные ниже.

---

## 1. Структура проекта

```
Auto_salon/
├── main.py                  # FastAPI-приложение (в корне)
├── alembic.ini              # в корне
├── migrations/
│   ├── env.py               # from mysite.db.models import *; target_metadata = Base.metadata
│   └── versions/
├── Dockerfile
├── docker-compose.yml       # сервисы: fast_web (том с auto_salon.db), nginx
├── nginx/
│   ├── Dockerfile
│   └── nginx.conf
├── requirements.txt
├── .env                     # НЕ в git
├── .env.example             # в git, без реальных секретов
├── .gitignore
├── mysite/
│   ├── __init__.py
│   ├── config.py            # load_dotenv() + os.getenv(...) константами
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py      # engine, SessionLocal, Base, get_db
│   │   ├── models.py        # ВСЕ Enum и ВСЕ модели
│   │   └── schema.py        # ВСЕ Pydantic-схемы
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── dependencies.py  # get_current_user, require_role
│   │   └── <entity>.py      # по одному файлу на сущность: car.py, brand.py, deal.py ...
│   └── admin/
│       ├── __init__.py
│       ├── setup.py         # setup_admin(app)
│       └── view.py          # ModelView-классы
└── tests/
```

Имена файлов роутеров — snake_case по сущности: `car.py`, `car_model.py`,
`car_image.py`, `trade_in.py`.

---

## 2. config.py

Только `load_dotenv()` и константы через `os.getenv`. Никаких классов Settings.

```python
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./auto_salon.db')

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM', 'HS256')
ACCESS_EXPIRE_TOKEN = int(os.getenv('ACCESS_EXPIRE_TOKEN', 15))  # минуты
REFRESH_EXPIRE_TOKEN = int(os.getenv('REFRESH_EXPIRE_TOKEN', 7))  # дни

SALON_TIMEZONE = os.getenv('SALON_TIMEZONE', 'Asia/Bishkek')
```

Секреты — только в `.env`. В коде никаких дефолтных значений для `SECRET_KEY`.

---

## 3. db/database.py

Синхронный SQLAlchemy 2.x, база SQLite (`sqlite:///./auto_salon.db`). Для SQLite обязательны
`check_same_thread=False` и `PRAGMA foreign_keys=ON` (иначе FK не проверяются). `get_db` объявлен **ОДИН раз здесь** и импортируется
во все роутеры (в старых проектах он копировался в каждый файл — так больше не делаем).

```python
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from mysite.config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine)


@event.listens_for(engine, 'connect')
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.execute('PRAGMA busy_timeout=5000')
    cursor.close()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 4. db/models.py

Все Enum и все модели — в одном файле. Порядок: импорты → Enum'ы → модели
(сначала пользователь и токены, затем справочники, затем зависимые сущности).

### 4.1 Импорты и Enum

```python
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, SmallInteger,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, PyEnum):
    admin = 'admin'
    seller = 'seller'
    client = 'client'


class CarStatus(str, PyEnum):
    in_transit = 'in_transit'
    available = 'available'
    reserved = 'reserved'
    sold = 'sold'
    withdrawn = 'withdrawn'
```

Значения Enum — lower_case строки, совпадающие с именем (кроме `Currency`: `KGS`, `USD`).

### 4.2 Поля

```python
class UserProfile(Base):
    __tablename__ = 'user_profile'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(50))
    last_name: Mapped[Optional[str]] = mapped_column(String(50))
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    phone_number: Mapped[str] = mapped_column(String(13), default='+996')
    profile_image: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.client)
    password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    discount_limit: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    refresh_tokens: Mapped[List['RefreshToken']] = relationship(
        'RefreshToken', back_populates='user', cascade='all, delete-orphan'
    )
    created_cars: Mapped[List['Car']] = relationship(
        'Car', back_populates='created_by', foreign_keys='Car.created_by_id'
    )
```

Правила:
- `id` всегда `mapped_column(primary_key=True, autoincrement=True)`.
- Optional-поля: `Mapped[Optional[str]]`.
- Деньги — `Mapped[Decimal] = mapped_column(Numeric(14, 2))`. Никогда `Float` для денег.
- Проценты — `Numeric(5, 2)`.
- Enum-поле — `mapped_column(Enum(CarStatus), default=CarStatus.available)`.
- Время — `DateTime(timezone=True)`, хранится в UTC. Создание — `server_default=func.now()`;
  изменения — `onupdate=func.now()`. SQLite не хранит часовой пояс и возвращает naive datetime —
  перед сравнением с `datetime.now(timezone.utc)` приводить: `value.replace(tzinfo=timezone.utc)`.
  При записи SQLite отбрасывает tzinfo без перевода в UTC — входящие aware datetime приводить
  `value.astimezone(timezone.utc)` до записи; naive от клиента — 422.
- JSON-поля — `JSON` (не `JSONB`).
- Деньги в коде — только `Decimal` (`Decimal('0.01')`, `quantize`), никаких `float`.
- Python-код использует `datetime.now(timezone.utc)`, а не `utcnow()`.
- Внешний ключ: `mapped_column(ForeignKey('car.id'))`; nullable — `Mapped[Optional[int]]`.
- Мягкое удаление: `deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)`.
- Составная уникальность — через `__table_args__`:

```python
class CarModel(Base):
    __tablename__ = 'car_model'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey('brand.id'))
    model_name: Mapped[str] = mapped_column(String(50))

    brand: Mapped['Brand'] = relationship('Brand', back_populates='car_models')
    cars: Mapped[List['Car']] = relationship('Car', back_populates='car_model')

    __table_args__ = (UniqueConstraint('brand_id', 'model_name', name='uq_brand_model_name'),)
```

### 4.3 Связи

- **Всегда двусторонние**: `back_populates` на обеих сторонах, имена совпадают.
- Родитель → дети: `Mapped[List['Child']] = relationship('Child', back_populates='parent', cascade='all, delete-orphan')`.
- Если к одной таблице несколько FK (например `Deal.client_id` и `Deal.seller_id` → `user_profile`),
  обязательно `foreign_keys=[...]` на стороне ребёнка и `foreign_keys='Deal.client_id'` на стороне родителя.
- `cascade='all, delete-orphan'` — только там, где ребёнок не имеет смысла без родителя
  (CarImage, LeadNote, TradeInImage, RefreshToken). Для Car/Deal (мягкое удаление) — без cascade delete.

### 4.4 Картинки — отдельная модель

```python
class CarImage(Base):
    __tablename__ = 'car_image'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(ForeignKey('car.id'))
    car_image: Mapped[str] = mapped_column(String)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)

    car: Mapped['Car'] = relationship('Car', back_populates='images')
```

### 4.5 RefreshToken — отдельная таблица

```python
class RefreshToken(Base):
    __tablename__ = 'refresh_token'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    token: Mapped[str] = mapped_column(String)

    user: Mapped['UserProfile'] = relationship('UserProfile', back_populates='refresh_tokens')
```

Имена полей: `brand_name`, `model_name`, `car_image`, `stars`, `comment`,
`profile_image`, `phone_number`. Имена таблиц — snake_case единственного числа
(`user_profile`, `car_model`, `price_history`, `trade_in`).

---

## 5. db/schema.py

Простые классы от `BaseModel`. Optional — через `str | None = None`.
Все схемы — в одном файле, сгруппированы по сущности.

```python
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr

from .models import BodyType, CarCondition, CarStatus, Currency, UserRole


class RegisterSchema(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    username: str
    email: EmailStr
    phone_number: str
    password: str


class LoginSchema(BaseModel):
    username: str
    password: str


class UserProfileDetailSchema(BaseModel):  # БЕЗ password!
    id: int
    username: str
    email: EmailStr
    phone_number: str
    profile_image: str | None
    role: UserRole


class CarCreateSchema(BaseModel):
    vin: str
    brand_id: int
    car_model_id: int
    year: int
    body_type: BodyType
    condition: CarCondition
    price: Decimal
    currency: Currency = Currency.KGS
    mileage: int = 0


class CarUpdateSchema(BaseModel):
    price: Decimal | None = None
    status: CarStatus | None = None
    description: str | None = None


class CarListSchema(BaseModel):
    id: int
    year: int
    price: Decimal
    currency: Currency
    status: CarStatus


class CarDetailSchema(BaseModel):
    id: int
    vin: str
    year: int
    price: Decimal
    currency: Currency
    status: CarStatus
    created_at: datetime
```

Именование: `<Entity>CreateSchema`, `<Entity>UpdateSchema`, `<Entity>ListSchema`,
`<Entity>DetailSchema`. Плюс `RegisterSchema`, `LoginSchema`.
Схемы ответа **никогда** не содержат `password`, `token` и другие секреты.
Поля, которые считает сервер (`final_price`, `created_by_id`, `seller_id` у продавца,
`client_id` у клиента), **не принимаются** во входных схемах — берутся из `current_user`/расчёта.

---

## 6. Роутеры: api/<entity>.py

```python
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from mysite.db.database import get_db
from mysite.db.models import Brand
from mysite.db.schema import (BrandCreateSchema, BrandDetailSchema, BrandListSchema,
                              BrandUpdateSchema)

brand_router = APIRouter(prefix='/brand', tags=['Brand'])


@brand_router.post('/create', response_model=BrandDetailSchema)
async def create_brand(brand_data: BrandCreateSchema, db: Session = Depends(get_db)):
    brand_db = Brand(**brand_data.model_dump())
    db.add(brand_db)
    db.commit()
    db.refresh(brand_db)
    return brand_db


@brand_router.get('/list', response_model=List[BrandListSchema])
async def list_brand(db: Session = Depends(get_db)):
    return db.query(Brand).all()


@brand_router.get('/detail', response_model=BrandDetailSchema)
async def detail_brand(brand_id: int, db: Session = Depends(get_db)):
    brand_db = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')
    return brand_db


@brand_router.put('/update/{brand_id}', response_model=BrandDetailSchema)
async def update_brand(brand_id: int, brand_data: BrandUpdateSchema, db: Session = Depends(get_db)):
    brand_db = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')

    for key, value in brand_data.model_dump(exclude_unset=True).items():
        setattr(brand_db, key, value)

    db.commit()
    db.refresh(brand_db)
    return brand_db


@brand_router.delete('/delete/{brand_id}', response_model=dict)
async def delete_brand(brand_id: int, db: Session = Depends(get_db)):
    brand_db = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')
    db.delete(brand_db)
    db.commit()
    return {'message': 'Марка удалена'}
```

Правила:
- Имя роутера: `<entity>_router`; `prefix='/<entity>'` (kebab-case для составных: `/car-model`, `/lead-note`),
  `tags=['<Entity>']`.
- Пути строго: `POST /create`, `GET /list`, `GET /detail?<entity>_id=`, `PUT /update/{id}`,
  `DELETE /delete/{id}`. Дополнительные действия — глаголом: `POST /deal/reserve/{deal_id}`,
  `POST /deal/pay/{deal_id}`, `GET /car/price-history/{car_id}`.
- Переменные: `<entity>_db` — объект из БД, `<entity>_data` — входная схема.
- create: `Model(**data.model_dump())`; update: цикл `setattr` по `model_dump(exclude_unset=True)`.
  `.dict()` **не использовать**.
- Ошибки — `HTTPException(status_code=status.HTTP_..., detail='<текст на русском>')`.
  404 — не найдено (и чужой объект для client), 403 — нет прав, 409 — конфликт/недопустимый переход,
  400 — некорректные данные.
- `response_model` указывать всегда.
- Мягкое удаление (Car, Deal): `delete` ставит `deleted_at = datetime.now(timezone.utc)`; все выборки
  фильтруют `Model.deleted_at.is_(None)`.
- Против N+1 в списках — `options(joinedload(...))` / `selectinload(...)`.
- Права: `current_user: UserProfile = Depends(get_current_user)` или
  `Depends(require_role(UserRole.admin, UserRole.seller))` из `mysite.api.dependencies`.

---

## 7. api/dependencies.py

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from mysite.api.auth import decode_token
from mysite.db.database import get_db
from mysite.db.models import UserProfile, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/login')


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> UserProfile:
    payload = decode_token(token)
    user_id = payload.get('user_id')
    user_db = db.query(UserProfile).filter(UserProfile.id == user_id).first()
    if not user_db or not user_db.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Пользователь не найден или заблокирован')
    return user_db


def require_role(*roles: UserRole):
    async def checker(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Недостаточно прав')
        return current_user

    return checker
```

---

## 8. Auth (api/auth.py)

- `pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')`.
- `get_password_hash`, `verify_password`, `create_access_token`, `create_refresh_token`, `decode_token`.
- JWT — `python-jose`, payload: `{'sub': username, 'user_id': id}`, `exp` в UTC.
- Refresh-токены хранятся в `RefreshToken`; `/auth/logout` удаляет токен; `/auth/access_generate`
  ротирует пару токенов.
- `auth_router = APIRouter(prefix='/auth', tags=['Authorization'])`.
- `/auth/register` всегда создаёт `role=UserRole.client` — роль из запроса не принимается.
- Ответ логина: `{'access_token', 'refresh_token', 'user_id', 'type': 'bearer'}`.
- Совместимость: `passlib==1.7.4` + `bcrypt==4.0.1` (новые bcrypt ломают passlib).

---

## 9. main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mysite.admin.setup import setup_admin
from mysite.api import auth, brand, car

auto_app = FastAPI(title='FastAPI Auto Salon')
auto_app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

auto_app.include_router(auth.auth_router)
auto_app.include_router(brand.brand_router)
auto_app.include_router(car.car_router)

setup_admin(auto_app)
```

- Объект приложения — `auto_app`; uvicorn: `uvicorn main:auto_app`.
- `include_router` — по одному на строку.
- Фоновые задачи (истечение брони) — как `game_scheduler` в mafia_app: `async def reservation_scheduler()`
  с `while True` + `SessionLocal()` + `try/finally db.close()` + `await asyncio.sleep(...)`,
  запуск через `asyncio.create_task(...)` в startup-обработчике.

---

## 10. admin/ (sqladmin)

```python
# admin/view.py
from sqladmin import ModelView

from mysite.db.models import Car, UserProfile


class UserProfileView(ModelView, model=UserProfile):
    column_list = [UserProfile.id, UserProfile.username, UserProfile.email, UserProfile.role]
    column_exclude_list = [UserProfile.password]


class CarView(ModelView, model=Car):
    column_list = [Car.id, Car.vin, Car.year, Car.price, Car.status]
```

```python
# admin/setup.py
from fastapi import FastAPI
from sqladmin import Admin

from mysite.db.database import engine

from .view import CarView, UserProfileView


def setup_admin(app: FastAPI):
    admin = Admin(app, engine=engine)
    admin.add_view(UserProfileView)
    admin.add_view(CarView)
```

---

## 11. Alembic

- `alembic.ini` и `migrations/` в корне.
- `migrations/env.py`: `from mysite.db.models import *` и `target_metadata = Base.metadata`;
  URL берётся из `mysite.config.DATABASE_URL` (`config.set_main_option('sqlalchemy.url', DATABASE_URL)`),
  а не хардкодится в `alembic.ini`.
- Сообщения миграций осмысленные: `alembic revision --autogenerate -m "create car tables"`.
- Закоммиченные миграции не редактируются — только новая миграция поверх.

---

## 12. Docker / nginx

- `Dockerfile`: `FROM python:3.12`, `ENV PYTHONUNBUFFERED=1`, `WORKDIR /app`,
  `COPY requirements.txt`, `pip install -r requirements.txt`, `COPY . /app/`.
- `docker-compose.yml`: `fast_web` (uvicorn main:auto_app, env_file .env,
  `DATABASE_URL=sqlite:////app/data/auto_salon.db` в environment, bind-mount `./data:/app/data`),
  `nginx` (build ./nginx, порт 80). Отдельного сервиса БД нет. uvicorn — без `--workers`.
- `nginx/Dockerfile`: `FROM nginx:latest` + `COPY nginx.conf /etc/nginx/conf.d/default.conf`.
- `nginx/nginx.conf`: `proxy_pass http://fast_web:8000`, `location /static/`, `location /media/`.

---

## 13. Форматирование и качество

- black (line-length 120), isort (profile black), flake8 (max-line-length 120) — конфиги в
  `pyproject.toml` и `.flake8`.
- Строки — одинарные кавычки (black их не меняет: `skip-string-normalization = true`).
- Тесты — pytest + `fastapi.testclient.TestClient`.

---

## 14. Известные отличия от старых проектов

| Было в старых проектах | Как делаем здесь |
|---|---|
| `get_db` копируется в каждый файл | один `get_db` в `db/database.py` |
| `.dict()` | `.model_dump()` |
| `declarative_base()` | `class Base(DeclarativeBase): pass` |
| роль из запроса в register | register создаёт только `client` |
| `datetime.utcnow()` | `datetime.now(timezone.utc)` |
| `alembic.ini` с захардкоженным URL | URL из `.env` через `env.py` |
| ошибки на английском | ошибки для пользователя — на русском |
