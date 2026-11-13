---
name: testing
description: Применяй при написании и запуске pytest-тестов — структура tests/, фикстуры, тестовая PostgreSQL-БД, переопределение get_db, TestClient, токены для ролей admin/seller/client.
---

# Тестирование

## Структура
```
tests/
├── __init__.py
├── conftest.py          # движок тестовой БД, сессия, client, пользователи и токены
├── test_auth.py
├── test_car.py
└── test_deal.py
```
Файлы `test_<entity>.py`, функции `test_<действие>_<ожидание>`:
`test_create_car_as_client_forbidden`, `test_detail_foreign_deal_returns_404`.

## Тестовая БД
PostgreSQL (не SQLite!): нужны `Enum`, `Numeric`, `SELECT ... FOR UPDATE`, `JSON`.
- Отдельная база `auto_salon_test`, URL — в переменной `TEST_DATABASE_URL` (в `.env`, пример — в `.env.example`).
- Таблицы: `Base.metadata.create_all` в начале сессии, `drop_all` в конце.
- Каждый тест — в транзакции с откатом (данные не протекают между тестами).

## conftest.py (шаблон)
```python
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import auto_app
from mysite.api.auth import create_access_token, get_password_hash
from mysite.db.database import Base, get_db
from mysite.db.models import UserProfile, UserRole

TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL')
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine)


@pytest.fixture(scope='session', autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection, join_transaction_mode='create_savepoint')
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    auto_app.dependency_overrides[get_db] = override_get_db
    with TestClient(auto_app) as test_client:
        yield test_client
    auto_app.dependency_overrides.clear()


def make_user(db, username, role):
    user_db = UserProfile(username=username, email=f'{username}@test.kg', phone_number='+996700000000',
                          role=role, password=get_password_hash('pass12345'))
    db.add(user_db)
    db.commit()
    db.refresh(user_db)
    return user_db


def auth_headers(user_db):
    token = create_access_token({'sub': user_db.username, 'user_id': user_db.id})
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def admin(db):
    return make_user(db, 'admin', UserRole.admin)


@pytest.fixture
def seller(db):
    return make_user(db, 'seller', UserRole.seller)


@pytest.fixture
def client_user(db):
    return make_user(db, 'client1', UserRole.client)
```
Фоновые задачи (scheduler) в тестах не запускать — тестировать функцию обработки истёкших броней напрямую.

## Обязательные виды кейсов
- позитивный сценарий;
- без токена → 401; чужая роль → 403;
- client к чужому объекту → 404 (IDOR);
- невалидные данные → 422;
- бизнес-правило → 409/400 (по ТЗ);
- в ответе нет `password`.

## Запуск (Windows)
```bash
.venv/Scripts/python.exe -m pytest -q          # все
.venv/Scripts/python.exe -m pytest -q -x -vv tests/test_car.py::test_create_car_ok
```
Тестовая БД должна быть поднята: `docker compose up -d fast_db` и создана база `auto_salon_test`.

## Принцип
Тест фиксирует поведение по ТЗ. Если код ведёт себя иначе — это баг кода, а не теста.
Никогда не меняй ожидание теста, чтобы он «позеленел».
