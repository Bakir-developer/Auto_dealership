---
name: testing
description: Применяй при написании и запуске pytest-тестов — структура tests/, фикстуры, тестовая SQLite-БД, переопределение get_db, TestClient, токены для ролей admin/seller/client.
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
SQLite, отдельный файл `test_auto_salon.db` (URL — `TEST_DATABASE_URL`, по умолчанию `sqlite:///./test_auto_salon.db`).
- `DATABASE_URL` и `SECRET_KEY` выставляются в `os.environ` **ДО** `from main import auto_app` — иначе
  `engine` приложения (и sqladmin) смотрит на рабочую `auto_salon.db`.
- Движок — тот же `engine` из `mysite.db.database` (с `check_same_thread=False` и `PRAGMA foreign_keys=ON`).
- Обход pysqlite (`isolation_level=None` + `BEGIN` в событии `begin`) — без него SAVEPOINT не изолирует
  тесты и `commit()` в тесте реально пишет в файл.
- Таблицы: `drop_all` + `create_all` в начале сессии, `drop_all` в конце.
- Каждый тест — в транзакции с откатом (данные не протекают между тестами).

## conftest.py (шаблон — как в `tests/conftest.py`)
```python
import os

TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'sqlite:///./test_auto_salon.db')
assert 'test' in TEST_DATABASE_URL, 'TEST_DATABASE_URL должен указывать на тестовую БД'
os.environ['DATABASE_URL'] = TEST_DATABASE_URL
os.environ['SECRET_KEY'] = 'test-secret-key-for-pytest-only-0123456789'

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from main import auto_app  # noqa: E402
from mysite.api.auth import create_access_token, get_password_hash  # noqa: E402
from mysite.db.database import Base, engine, get_db  # noqa: E402
from mysite.db.models import UserProfile, UserRole  # noqa: E402

TestingSessionLocal = sessionmaker(bind=engine)


@event.listens_for(engine, 'connect')
def _disable_pysqlite_autobegin(dbapi_connection, connection_record):
    dbapi_connection.isolation_level = None


@event.listens_for(engine, 'begin')
def _emit_begin(connection):
    connection.exec_driver_sql('BEGIN')


@pytest.fixture(scope='session', autouse=True)
def create_tables():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


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
Тестовая БД — SQLite-файл `test_auto_salon.db`, создаётся автоматически (`create_all` в conftest).

## Принцип
Тест фиксирует поведение по ТЗ. Если код ведёт себя иначе — это баг кода, а не теста.
Никогда не меняй ожидание теста, чтобы он «позеленел».
