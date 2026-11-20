import os
from datetime import time
from decimal import Decimal

# Переменные окружения нужно выставить ДО импорта приложения (config читается при импорте).
TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'sqlite:///./test_auto_salon.db')
assert 'test' in TEST_DATABASE_URL, 'TEST_DATABASE_URL должен указывать на тестовую БД'
os.environ['DATABASE_URL'] = TEST_DATABASE_URL
os.environ['RESERVATION_SCHEDULER_ENABLED'] = 'false'
os.environ['SECRET_KEY'] = 'test-secret-key-for-pytest-only-0123456789'

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from main import auto_app  # noqa: E402
from mysite.admin.view import (  # noqa: E402
    AuditLogView,
    BrandView,
    CarModelView,
    CarView,
    DealView,
    DiscountRequestView,
    LeadView,
    PriceHistoryView,
    ReviewView,
    SalonSettingsView,
    TradeInView,
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
    Deal,
    DealStatus,
    DiscountRequest,
    DiscountStatus,
    DriveType,
    Favorite,
    FuelType,
    Lead,
    LeadStatus,
    LeadType,
    Notification,
    NotificationType,
    Review,
    SalonSettings,
    TradeIn,
    TradeInImage,
    TradeInStatus,
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
def seller2(make_user):
    return make_user('seller2', UserRole.seller)


@pytest.fixture
def client2(make_user):
    return make_user('client2', UserRole.client)


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
        DealView,
        DiscountRequestView,
        AuditLogView,
        TradeInView,
        ReviewView,
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
    monkeypatch.setattr('mysite.api.trade_in.MEDIA_DIR', str(tmp_path))
    (tmp_path / 'car_images').mkdir()
    (tmp_path / 'trade_in_images').mkdir()
    return tmp_path


@pytest.fixture
def salon_settings(db):
    settings_db = SalonSettings(
        id=1,
        salon_name='Test Salon',
        address='Bishkek',
        phone_number='+996700000000',
        work_start=time(9, 0),
        work_end=time(18, 0),
    )
    db.add(settings_db)
    db.commit()
    db.refresh(settings_db)
    return settings_db


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
def make_notification(db):
    def _make_notification(user, text='Тест', is_read=False, notification_type=NotificationType.system):
        notification_db = Notification(user_id=user.id, notification_type=notification_type, text=text, is_read=is_read)
        db.add(notification_db)
        db.commit()
        db.refresh(notification_db)
        return notification_db

    return _make_notification


@pytest.fixture
def make_deal(db, make_car, client_user, seller):
    def _make_deal(**overrides):
        if 'car' in overrides:
            car_db = overrides.pop('car')
        elif 'car_id' in overrides:
            car_db = db.get(Car, overrides['car_id'])
        else:
            car_db = make_car()
        data = dict(
            car_id=car_db.id,
            client_id=client_user.id,
            seller_id=seller.id,
            base_price=car_db.price,
            discount_percent=Decimal('0'),
            final_price=car_db.price,
            currency=car_db.currency,
            status=DealStatus.new,
        )
        data.update(overrides)
        if 'base_price' in overrides and 'final_price' not in overrides:
            data['final_price'] = data['base_price']
        deal_db = Deal(**data)
        db.add(deal_db)
        db.commit()
        db.refresh(deal_db)
        return deal_db

    return _make_deal


@pytest.fixture
def make_discount_request(db, make_deal, seller):
    def _make_discount_request(**overrides):
        if 'deal_id' not in overrides:
            overrides['deal_id'] = make_deal().id
        data = dict(
            seller_id=seller.id,
            requested_percent=Decimal('10'),
            status=DiscountStatus.pending,
        )
        data.update(overrides)
        discount_db = DiscountRequest(**data)
        db.add(discount_db)
        db.commit()
        db.refresh(discount_db)
        return discount_db

    return _make_discount_request


@pytest.fixture
def make_trade_in(db, client_user):
    def _make_trade_in(**overrides):
        data = dict(
            client_id=client_user.id,
            brand_name='Toyota',
            model_name='Corolla',
            year=2015,
            mileage=120000,
            status=TradeInStatus.new,
        )
        data.update(overrides)
        trade_in_db = TradeIn(**data)
        db.add(trade_in_db)
        db.commit()
        db.refresh(trade_in_db)
        return trade_in_db

    return _make_trade_in


@pytest.fixture
def make_trade_in_image(db):
    def _make_trade_in_image(trade_in, name='x.jpg'):
        image_db = TradeInImage(trade_in_id=trade_in.id, trade_in_image=f'/media/trade_in_images/{name}')
        db.add(image_db)
        db.commit()
        db.refresh(image_db)
        return image_db

    return _make_trade_in_image


@pytest.fixture
def make_favorite(db):
    def _make_favorite(user, car):
        favorite_db = Favorite(user_id=user.id, car_id=car.id)
        db.add(favorite_db)
        db.commit()
        db.refresh(favorite_db)
        return favorite_db

    return _make_favorite


@pytest.fixture
def make_review(db, make_deal):
    def _make_review(deal=None, **overrides):
        if deal is None:
            deal = make_deal(status=DealStatus.delivered)
        data = dict(client_id=deal.client_id, deal_id=deal.id, seller_id=deal.seller_id, stars=5)
        data.update(overrides)
        review_db = Review(**data)
        db.add(review_db)
        db.commit()
        db.refresh(review_db)
        return review_db

    return _make_review
