import os
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

# Переменные окружения нужно выставить ДО импорта приложения (config читается при импорте).
TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'sqlite:///./test_auto_salon.db')
assert 'test' in TEST_DATABASE_URL, 'TEST_DATABASE_URL должен указывать на тестовую БД'
os.environ['DATABASE_URL'] = TEST_DATABASE_URL
os.environ['SECRET_KEY'] = 'test-secret-key-for-pytest-only-0123456789'

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from main import auto_app  # noqa: E402
from mysite.admin.view import (  # noqa: E402
    BrandView,
    CarModelView,
    CarView,
    LeadView,
    PriceHistoryView,
    SalonSettingsView,
    TestDriveView,
    UserProfileView,
)
from mysite.api.auth import create_access_token, get_password_hash  # noqa: E402
from mysite.db.database import Base, engine, get_db  # noqa: E402
from mysite.db.models import (  # noqa: E402
    BodyType,
    Brand,
    Car,
    CarCondition,
    CarModel,
    DriveType,
    FuelType,
    Lead,
    LeadStatus,
    LeadType,
    Notification,
    NotificationType,
    SalonSettings,
    TestDrive,
    TestDriveStatus,
    Transmission,
    UserProfile,
    UserRole,
)

TestingSessionLocal = sessionmaker(bind=engine)


# Обходной путь для pysqlite: иначе SAVEPOINT/ROLLBACK не изолируют тесты (commit в тесте реально пишет в файл).
@event.listens_for(engine, 'connect')
def _disable_pysqlite_autobegin(dbapi_connection, connection_record):
    dbapi_connection.isolation_level = None


@event.listens_for(engine, 'begin')
def _emit_begin(connection):
    connection.exec_driver_sql('BEGIN')


PASSWORD = 'pass12345'


class SessionProxy:
    """Обертка над тестовой сессией: close() ничего не делает, чтобы код с SessionLocal() не рвал тестовую сессию."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


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


@pytest.fixture
def make_user(db):
    counter = {'n': 0}

    def _make_user(username, role=UserRole.client, is_active=True, email=None, phone_number=None):
        counter['n'] += 1
        user_db = UserProfile(
            username=username,
            email=email or f'{username}@test.kg',
            phone_number=phone_number or f'+9967000000{counter["n"]:02d}',
            role=role,
            is_active=is_active,
            password=get_password_hash(PASSWORD),
        )
        db.add(user_db)
        db.commit()
        db.refresh(user_db)
        return user_db

    return _make_user


@pytest.fixture
def auth_headers():
    def _auth_headers(user_db):
        token = create_access_token({'sub': user_db.username, 'user_id': user_db.id})
        return {'Authorization': f'Bearer {token}'}

    return _auth_headers


@pytest.fixture
def admin(make_user):
    return make_user('admin', UserRole.admin)


@pytest.fixture
def seller(make_user):
    return make_user('seller', UserRole.seller)


@pytest.fixture
def client_user(make_user):
    return make_user('client1', UserRole.client)


@pytest.fixture
def admin_session_local(monkeypatch, db):
    """sqladmin ходит в БД через mysite.admin.setup.SessionLocal - отдаем ему тестовую сессию."""
    monkeypatch.setattr('mysite.admin.setup.SessionLocal', lambda: SessionProxy(db))
    for view in (
        UserProfileView,
        SalonSettingsView,
        BrandView,
        CarModelView,
        CarView,
        PriceHistoryView,
        LeadView,
        TestDriveView,
    ):
        monkeypatch.setattr(view, 'session_maker', staticmethod(lambda **kwargs: SessionProxy(db)))
    return db


JPEG_BYTES = bytes.fromhex('ffd8ffe0') + bytes(16)
PNG_BYTES = bytes.fromhex('89') + b'PNG' + bytes.fromhex('0d0a1a0a') + bytes(16)
WEBP_BYTES = b'RIFF' + (20).to_bytes(4, 'little') + b'WEBP' + bytes(16)


@pytest.fixture
def brand(db):
    brand_db = Brand(brand_name='Toyota')
    db.add(brand_db)
    db.commit()
    db.refresh(brand_db)
    return brand_db


@pytest.fixture
def car_model(db, brand):
    car_model_db = CarModel(brand_id=brand.id, model_name='Camry')
    db.add(car_model_db)
    db.commit()
    db.refresh(car_model_db)
    return car_model_db


@pytest.fixture
def make_car(db, brand, car_model, seller):
    counter = {'n': 0}

    def _make_car(**overrides):
        counter['n'] += 1
        data = dict(
            vin=f'JTDBR32E{counter["n"]:09d}',
            brand_id=brand.id,
            car_model_id=car_model.id,
            year=2022,
            body_type=BodyType.sedan,
            color='Black',
            fuel_type=FuelType.petrol,
            transmission=Transmission.automatic,
            drive_type=DriveType.front,
            condition=CarCondition.new,
            price=Decimal('1500000.00'),
            mileage=0,
            created_by_id=seller.id,
        )
        data.update(overrides)
        car_db = Car(**data)
        db.add(car_db)
        db.commit()
        db.refresh(car_db)
        return car_db

    return _make_car


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr('mysite.api.car_image.MEDIA_DIR', str(tmp_path))
    (tmp_path / 'car_images').mkdir()
    return tmp_path


SALON_TZ = ZoneInfo('Asia/Bishkek')


@pytest.fixture
def salon_settings(db):
    settings_db = SalonSettings(
        id=1,
        salon_name='Test Salon',
        address='Bishkek',
        phone_number='+996700000000',
        work_start=time(9, 0),
        work_end=time(18, 0),
        test_drive_minutes=60,
    )
    db.add(settings_db)
    db.commit()
    db.refresh(settings_db)
    return settings_db


@pytest.fixture
def slot_dt():
    """slot_dt(days, hour, minute) -> aware datetime в Asia/Bishkek (дата относительно сегодняшней даты в Бишкеке)."""

    def _slot_dt(days=1, hour=10, minute=0):
        today = datetime.now(SALON_TZ).date()
        return datetime.combine(today + timedelta(days=days), time(hour, minute), tzinfo=SALON_TZ)

    return _slot_dt


@pytest.fixture
def future_slot(slot_dt):
    """future_slot(days, hour, minute) -> ISO-строка с +06:00."""

    def _future_slot(days=1, hour=10, minute=0):
        return slot_dt(days, hour, minute).isoformat()

    return _future_slot


@pytest.fixture
def make_lead(db, client_user):
    def _make_lead(**overrides):
        data = dict(client_id=client_user.id, lead_type=LeadType.purchase, status=LeadStatus.new)
        data.update(overrides)
        lead_db = Lead(**data)
        db.add(lead_db)
        db.commit()
        db.refresh(lead_db)
        return lead_db

    return _make_lead


@pytest.fixture
def make_test_drive(db, client_user, slot_dt):
    def _make_test_drive(car, **overrides):
        start = overrides.pop('start', None) or slot_dt(1, 10, 0)
        start = start.astimezone(timezone.utc)
        data = dict(
            car_id=car.id,
            client_id=client_user.id,
            start_time=start,
            end_time=start + timedelta(minutes=60),
            status=TestDriveStatus.scheduled,
        )
        data.update(overrides)
        test_drive_db = TestDrive(**data)
        db.add(test_drive_db)
        db.commit()
        db.refresh(test_drive_db)
        return test_drive_db

    return _make_test_drive


@pytest.fixture
def make_notification(db):
    def _make_notification(user, text='Тест', is_read=False, notification_type=NotificationType.system):
        notification_db = Notification(user_id=user.id, notification_type=notification_type, text=text, is_read=is_read)
        db.add(notification_db)
        db.commit()
        db.refresh(notification_db)
        return notification_db

    return _make_notification
