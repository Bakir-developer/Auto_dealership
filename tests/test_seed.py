from datetime import time
from decimal import Decimal

import pytest

from mysite import seed
from mysite.api.auth import verify_password
from mysite.db.models import SalonSettings, UserProfile, UserRole
from tests.conftest import SessionProxy


def set_env(monkeypatch, username='boss', email='boss@test.kg', phone='+996700123456', password='password123'):
    monkeypatch.setattr(seed, 'ADMIN_USERNAME', username)
    monkeypatch.setattr(seed, 'ADMIN_EMAIL', email)
    monkeypatch.setattr(seed, 'ADMIN_PHONE', phone)
    monkeypatch.setattr(seed, 'ADMIN_PASSWORD', password)


def test_create_admin_ok(db):
    user_db = seed.create_admin(db, 'boss', 'boss@test.kg', '+996700123456', 'password123')
    assert user_db.role == UserRole.admin
    assert user_db.is_active is True
    assert user_db.password != 'password123'
    assert user_db.password.startswith('$2')
    assert verify_password('password123', user_db.password)


def test_create_admin_idempotent(db):
    first = seed.create_admin(db, 'boss', 'boss@test.kg', '+996700123456', 'password123')
    second = seed.create_admin(db, 'boss', 'boss@test.kg', '+996700123456', 'other-password-456')
    assert first.id == second.id
    assert db.query(UserProfile).filter(UserProfile.username == 'boss').count() == 1
    assert verify_password('password123', second.password)
    assert not verify_password('other-password-456', second.password)


def test_create_admin_existing_non_admin_exits(db, make_user):
    make_user('boss', UserRole.client)
    with pytest.raises(SystemExit) as exc_info:
        seed.create_admin(db, 'boss', 'boss@test.kg', '+996700123456', 'password123')
    assert exc_info.value.code == 1
    assert db.query(UserProfile).filter(UserProfile.username == 'boss').one().role == UserRole.client


def test_create_salon_settings_once(db, monkeypatch):
    set_env(monkeypatch)
    first = seed.create_salon_settings(db)
    assert first.id == 1
    assert first.default_discount_limit == Decimal('3')
    assert first.work_start == time(9, 0)
    assert first.work_end == time(18, 0)
    assert first.reservation_hours == 48

    first.salon_name = 'Changed'
    db.flush()
    second = seed.create_salon_settings(db)
    assert second.id == 1
    assert second.salon_name == 'Changed'
    assert db.query(SalonSettings).count() == 1


def test_seed_main_without_env_exits(monkeypatch):
    set_env(monkeypatch, '', '', '', '')
    with pytest.raises(SystemExit) as exc_info:
        seed.main()
    assert exc_info.value.code == 1


def test_seed_main_partial_env_exits(monkeypatch):
    set_env(monkeypatch, password=None)
    with pytest.raises(SystemExit) as exc_info:
        seed.main()
    assert exc_info.value.code == 1


def test_seed_main_invalid_phone_exits(monkeypatch):
    set_env(monkeypatch, phone='bad-phone')
    with pytest.raises(SystemExit) as exc_info:
        seed.main()
    assert exc_info.value.code == 1


def test_seed_main_twice_is_idempotent(monkeypatch, db):
    set_env(monkeypatch)
    monkeypatch.setattr(seed, 'SessionLocal', lambda: SessionProxy(db))
    seed.main()
    seed.main()
    assert db.query(UserProfile).filter(UserProfile.role == UserRole.admin).count() == 1
    assert db.query(SalonSettings).count() == 1
