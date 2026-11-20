from datetime import datetime, timedelta, timezone

import pytest

from mysite import config
from mysite.api.deal import expire_reservations, get_reservation_hours
from mysite.db.models import (
    AuditLog,
    Car,
    CarStatus,
    Deal,
    DealStatus,
    DiscountRequest,
    DiscountStatus,
    Notification,
    NotificationType,
)


def past():
    return datetime.now(timezone.utc) - timedelta(hours=1)


def future():
    return datetime.now(timezone.utc) + timedelta(hours=5)


def reserved_deal(make_deal, make_car, reserved_until, **overrides):
    car_db = make_car(status=CarStatus.reserved)
    return make_deal(car=car_db, status=DealStatus.reserved, reserved_until=reserved_until, **overrides)


def test_expire_reservations_cancels_expired(db, seller, client_user, make_deal, make_car):
    deal_db = reserved_deal(make_deal, make_car, past())
    assert expire_reservations(db) == 1
    db.expire_all()
    deal_after = db.get(Deal, deal_db.id)
    assert deal_after.status == DealStatus.cancelled
    assert deal_after.cancel_reason
    assert db.get(Car, deal_db.car_id).status == CarStatus.available
    for user in (seller, client_user):
        notes = (
            db.query(Notification)
            .filter(Notification.user_id == user.id, Notification.notification_type == NotificationType.reservation)
            .all()
        )
        assert len(notes) == 1
    logs = db.query(AuditLog).filter(AuditLog.action == 'deal_expire', AuditLog.entity_id == deal_db.id).all()
    assert len(logs) == 1
    assert logs[0].user_id is None


def test_expire_reservations_skips_not_expired(db, make_deal, make_car):
    deal_db = reserved_deal(make_deal, make_car, future())
    assert expire_reservations(db) == 0
    db.expire_all()
    assert db.get(Deal, deal_db.id).status == DealStatus.reserved
    assert db.get(Car, deal_db.car_id).status == CarStatus.reserved


def test_expire_reservations_skips_paid(db, make_deal, make_car):
    car_db = make_car(status=CarStatus.reserved)
    deal_db = make_deal(car=car_db, status=DealStatus.paid, reserved_until=past(), paid_at=past())
    assert expire_reservations(db) == 0
    db.expire_all()
    assert db.get(Deal, deal_db.id).status == DealStatus.paid
    assert db.get(Car, car_db.id).status == CarStatus.reserved


def test_expire_reservations_skips_deleted(db, make_deal, make_car):
    deal_db = reserved_deal(make_deal, make_car, past(), deleted_at=datetime.now(timezone.utc))
    assert expire_reservations(db) == 0
    db.expire_all()
    assert db.get(Deal, deal_db.id).status == DealStatus.reserved


def test_expire_reservations_rejects_pending_discounts(db, make_deal, make_car, make_discount_request):
    deal_db = reserved_deal(make_deal, make_car, past())
    discount_db = make_discount_request(deal_id=deal_db.id)
    assert expire_reservations(db) == 1
    db.expire_all()
    discount_after = db.get(DiscountRequest, discount_db.id)
    assert discount_after.status == DiscountStatus.rejected
    assert discount_after.decided_at is not None


def test_expire_reservations_multiple(db, make_deal, make_car):
    expired = [reserved_deal(make_deal, make_car, past()) for _ in range(3)]
    alive = reserved_deal(make_deal, make_car, future())
    assert expire_reservations(db) == 3
    db.expire_all()
    for deal_db in expired:
        assert db.get(Deal, deal_db.id).status == DealStatus.cancelled
    assert db.get(Deal, alive.id).status == DealStatus.reserved


def test_expire_reservations_returns_zero_when_nothing(db):
    assert expire_reservations(db) == 0


def test_expire_reservations_is_idempotent(db, make_deal, make_car):
    reserved_deal(make_deal, make_car, past())
    assert expire_reservations(db) == 1
    assert expire_reservations(db) == 0
    assert db.query(AuditLog).filter(AuditLog.action == 'deal_expire').count() == 1


def test_expire_reservations_aware_naive_compare(db, make_deal, make_car):
    deal_db = reserved_deal(make_deal, make_car, past())
    db.expire_all()
    stored = db.get(Deal, deal_db.id).reserved_until
    # SQLite возвращает naive datetime; сравнение с aware UTC не должно падать
    assert stored.tzinfo is None
    assert stored.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
    assert expire_reservations(db) == 1


def test_expire_reservations_only_releases_reserved_car(db, make_deal, make_car):
    car_db = make_car(status=CarStatus.available)
    deal_db = make_deal(car=car_db, status=DealStatus.reserved, reserved_until=past())
    assert expire_reservations(db) == 1
    db.expire_all()
    assert db.get(Deal, deal_db.id).status == DealStatus.cancelled
    assert db.get(Car, car_db.id).status == CarStatus.available


def test_scheduler_disabled_in_tests():
    assert config.RESERVATION_SCHEDULER_ENABLED is False


def test_expire_audit_without_car_status_if_car_not_released(db, make_deal, make_car):
    car_db = make_car(status=CarStatus.available)
    deal_db = make_deal(car=car_db, status=DealStatus.reserved, reserved_until=past())
    assert expire_reservations(db) == 1
    db.expire_all()
    audit_db = db.query(AuditLog).filter(AuditLog.action == 'deal_expire', AuditLog.entity_id == deal_db.id).one()
    assert 'car_status' not in audit_db.new_value


@pytest.mark.parametrize('hours', [0, 721, 1000])
def test_reservation_hours_out_of_range_default(db, salon_settings, hours):
    salon_settings.reservation_hours = hours
    db.commit()
    assert get_reservation_hours(db) == 48
