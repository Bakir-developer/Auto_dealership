from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

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
    SalonSettings,
    UserRole,
)


def notifications_of(db, user, notification_type=None):
    db.expire_all()
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if notification_type is not None:
        query = query.filter(Notification.notification_type == notification_type)
    return query.all()


def audit_of(db, action, entity_id=None):
    db.expire_all()
    query = db.query(AuditLog).filter(AuditLog.action == action)
    if entity_id is not None:
        query = query.filter(AuditLog.entity_id == entity_id)
    return query.all()


def reload(db, model, pk):
    db.expire_all()
    return db.get(model, pk)


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def prepare(db, make_deal, make_car, deal_status, car_status=None, **deal_overrides):
    """Сделка в нужном статусе + согласованный статус авто."""
    if car_status is None:
        car_status = (
            CarStatus.available if deal_status in (DealStatus.new, DealStatus.in_progress) else CarStatus.reserved
        )
        if deal_status in (DealStatus.cancelled,):
            car_status = CarStatus.available
        if deal_status == DealStatus.delivered:
            car_status = CarStatus.sold
    car_db = make_car(status=car_status)
    extra = dict(deal_overrides)
    if deal_status == DealStatus.reserved:
        extra.setdefault('reserved_until', datetime.now(timezone.utc) + timedelta(hours=10))
    if deal_status in (DealStatus.paid, DealStatus.delivered):
        extra.setdefault('reserved_until', datetime.now(timezone.utc) + timedelta(hours=10))
        extra.setdefault('paid_at', datetime.now(timezone.utc))
    return make_deal(car=car_db, status=deal_status, **extra)


# ---------- create ----------


def test_create_deal_seller_ok(client, db, seller, client_user, make_car, auth_headers):
    car_db = make_car()
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['seller_id'] == seller.id
    assert data['client_id'] == client_user.id
    assert data['car_id'] == car_db.id
    assert Decimal(data['base_price']) == car_db.price
    assert Decimal(data['final_price']) == car_db.price
    assert Decimal(data['discount_percent']) == 0
    assert data['currency'] == car_db.currency.value
    assert data['status'] == 'new'
    assert 'password' not in response.text
    notes = notifications_of(db, client_user, NotificationType.deal)
    assert any(str(data['id']) in n.text for n in notes)
    logs = audit_of(db, 'deal_create', data['id'])
    assert len(logs) == 1
    assert logs[0].user_id == seller.id


def test_create_deal_ignores_server_fields(client, seller, make_user, client_user, make_car, auth_headers):
    car_db = make_car()
    other_seller = make_user('otherseller', UserRole.seller)
    response = client.post(
        '/deal/create',
        json={
            'car_id': car_db.id,
            'client_id': client_user.id,
            'seller_id': other_seller.id,
            'final_price': '1.00',
            'base_price': '2.00',
            'discount_percent': '50',
            'status': 'paid',
            'currency': 'USD',
        },
        headers=auth_headers(seller),
    )
    assert response.status_code == 200
    data = response.json()
    assert data['seller_id'] == seller.id
    assert data['status'] == 'new'
    assert Decimal(data['base_price']) == car_db.price
    assert Decimal(data['final_price']) == car_db.price
    assert Decimal(data['discount_percent']) == 0
    assert data['currency'] == car_db.currency.value


def test_create_deal_admin_with_seller_ok(client, db, admin, seller, client_user, make_car, auth_headers):
    car_db = make_car()
    response = client.post(
        '/deal/create',
        json={'car_id': car_db.id, 'client_id': client_user.id, 'seller_id': seller.id},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller.id
    assert notifications_of(db, seller, NotificationType.deal)
    assert notifications_of(db, client_user, NotificationType.deal)


def test_create_deal_admin_without_seller_400(client, admin, client_user, make_car, auth_headers):
    car_db = make_car()
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 400


def test_create_deal_admin_blocked_seller_404(client, admin, make_user, client_user, make_car, auth_headers):
    blocked = make_user('blockedseller', UserRole.seller, is_active=False)
    car_db = make_car()
    response = client.post(
        '/deal/create',
        json={'car_id': car_db.id, 'client_id': client_user.id, 'seller_id': blocked.id},
        headers=auth_headers(admin),
    )
    assert response.status_code == 404


def test_create_deal_admin_seller_id_not_seller_404(client, admin, client_user, client2, make_car, auth_headers):
    car_db = make_car()
    response = client.post(
        '/deal/create',
        json={'car_id': car_db.id, 'client_id': client_user.id, 'seller_id': client2.id},
        headers=auth_headers(admin),
    )
    assert response.status_code == 404


def test_create_deal_as_client_403(client, client_user, make_car, auth_headers):
    car_db = make_car()
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(client_user)
    )
    assert response.status_code == 403


def test_create_deal_without_token_401(client, client_user, make_car):
    car_db = make_car()
    assert client.post('/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}).status_code == 401


def test_create_deal_unknown_car_404(client, seller, client_user, auth_headers):
    response = client.post(
        '/deal/create', json={'car_id': 99999, 'client_id': client_user.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 404


def test_create_deal_deleted_car_404(client, seller, client_user, make_car, auth_headers):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 404


def test_create_deal_client_is_seller_404(client, seller, make_user, make_car, auth_headers):
    car_db = make_car()
    other = make_user('otherseller', UserRole.seller)
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': other.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 404


def test_create_deal_unknown_client_404(client, seller, make_car, auth_headers):
    car_db = make_car()
    response = client.post('/deal/create', json={'car_id': car_db.id, 'client_id': 99999}, headers=auth_headers(seller))
    assert response.status_code == 404


def test_create_deal_blocked_client_404(client, seller, make_user, make_car, auth_headers):
    blocked = make_user('blockedclient', UserRole.client, is_active=False)
    car_db = make_car()
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': blocked.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 404


def test_create_deal_missing_fields_422(client, seller, auth_headers):
    assert client.post('/deal/create', json={}, headers=auth_headers(seller)).status_code == 422


def test_create_deal_car_in_transit_ok(client, seller, client_user, make_car, auth_headers):
    car_db = make_car(status=CarStatus.in_transit)
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 200


@pytest.mark.parametrize('car_status', [CarStatus.reserved, CarStatus.sold, CarStatus.withdrawn])
def test_create_deal_car_unavailable_409(client, seller, client_user, make_car, auth_headers, car_status):
    car_db = make_car(status=car_status)
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 409


def test_create_deal_duplicate_active_409(client, seller, client_user, make_car, make_deal, auth_headers):
    car_db = make_car()
    make_deal(car=car_db)
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 409


def test_create_deal_after_cancelled_ok(client, seller, client_user, make_car, make_deal, auth_headers):
    car_db = make_car()
    make_deal(car=car_db, status=DealStatus.cancelled)
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 200


def test_create_deal_other_client_same_car_ok(client, seller, client2, client_user, make_car, make_deal, auth_headers):
    car_db = make_car()
    make_deal(car=car_db)
    response = client.post(
        '/deal/create', json={'car_id': car_db.id, 'client_id': client2.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 200


# ---------- list / detail ----------


def test_list_deal_client_sees_only_own(client, client_user, client2, make_deal, auth_headers):
    own = make_deal()
    make_deal(client_id=client2.id)
    response = client.get('/deal/list', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert [d['id'] for d in response.json()] == [own.id]


def test_list_deal_seller_sees_only_own(client, seller, seller2, make_deal, auth_headers):
    own = make_deal()
    make_deal(seller_id=seller2.id)
    response = client.get('/deal/list', headers=auth_headers(seller))
    assert [d['id'] for d in response.json()] == [own.id]


def test_list_deal_admin_sees_all(client, admin, seller2, make_deal, auth_headers):
    first = make_deal()
    second = make_deal(seller_id=seller2.id)
    response = client.get('/deal/list', headers=auth_headers(admin))
    assert {d['id'] for d in response.json()} == {first.id, second.id}


def test_list_deal_admin_filter_seller_id(client, admin, seller, seller2, make_deal, auth_headers):
    make_deal()
    other = make_deal(seller_id=seller2.id)
    response = client.get(f'/deal/list?seller_id={seller2.id}', headers=auth_headers(admin))
    assert [d['id'] for d in response.json()] == [other.id]


def test_list_deal_seller_filter_seller_id_ignored(client, seller, seller2, make_deal, auth_headers):
    own = make_deal()
    make_deal(seller_id=seller2.id)
    response = client.get(f'/deal/list?seller_id={seller2.id}', headers=auth_headers(seller))
    assert [d['id'] for d in response.json()] == [own.id]


def test_list_deal_client_filter_client_id_ignored(client, client_user, client2, make_deal, auth_headers):
    own = make_deal()
    make_deal(client_id=client2.id)
    response = client.get(f'/deal/list?client_id={client2.id}', headers=auth_headers(client_user))
    assert [d['id'] for d in response.json()] == [own.id]


def test_list_deal_filter_status(client, admin, make_deal, auth_headers):
    make_deal()
    cancelled = make_deal(status=DealStatus.cancelled)
    response = client.get('/deal/list?status=cancelled', headers=auth_headers(admin))
    assert [d['id'] for d in response.json()] == [cancelled.id]


def test_list_deal_pagination(client, admin, make_deal, auth_headers):
    for _ in range(3):
        make_deal()
    response = client.get('/deal/list?skip=1&limit=1', headers=auth_headers(admin))
    assert len(response.json()) == 1


def test_list_deal_limit_over_100_422(client, admin, auth_headers):
    assert client.get('/deal/list?limit=101', headers=auth_headers(admin)).status_code == 422


def test_list_deal_without_token_401(client):
    assert client.get('/deal/list').status_code == 401


def test_list_deal_excludes_deleted(client, admin, make_deal, auth_headers):
    make_deal(deleted_at=datetime.now(timezone.utc))
    visible = make_deal()
    response = client.get('/deal/list', headers=auth_headers(admin))
    assert [d['id'] for d in response.json()] == [visible.id]


def test_detail_deal_other_client_404(client, client2, make_deal, auth_headers):
    deal_db = make_deal()
    assert client.get(f'/deal/detail?deal_id={deal_db.id}', headers=auth_headers(client2)).status_code == 404


def test_detail_deal_other_seller_404(client, seller2, make_deal, auth_headers):
    deal_db = make_deal()
    assert client.get(f'/deal/detail?deal_id={deal_db.id}', headers=auth_headers(seller2)).status_code == 404


def test_detail_deal_own_ok(client, client_user, seller, admin, make_deal, auth_headers):
    deal_db = make_deal()
    for user in (client_user, seller, admin):
        response = client.get(f'/deal/detail?deal_id={deal_db.id}', headers=auth_headers(user))
        assert response.status_code == 200
        assert response.json()['id'] == deal_db.id
        assert 'password' not in response.text


def test_detail_deleted_deal_admin_404(client, admin, make_deal, auth_headers):
    deal_db = make_deal(deleted_at=datetime.now(timezone.utc))
    assert client.get(f'/deal/detail?deal_id={deal_db.id}', headers=auth_headers(admin)).status_code == 404


def test_detail_deal_not_found_404(client, admin, auth_headers):
    assert client.get('/deal/detail?deal_id=99999', headers=auth_headers(admin)).status_code == 404


def test_detail_deal_without_token_401(client, make_deal):
    deal_db = make_deal()
    assert client.get(f'/deal/detail?deal_id={deal_db.id}').status_code == 401


def test_detail_deal_datetime_utc_offset(client, admin, db, make_deal, make_car, auth_headers):
    deal_db = prepare(db, make_deal, make_car, DealStatus.reserved)
    response = client.get(f'/deal/detail?deal_id={deal_db.id}', headers=auth_headers(admin))
    data = response.json()
    assert data['created_at'].endswith('+00:00') or data['created_at'].endswith('Z')
    assert data['reserved_until'].endswith('+00:00') or data['reserved_until'].endswith('Z')


# ---------- transitions ----------


def test_start_deal_ok(client, db, seller, make_deal, auth_headers):
    deal_db = make_deal()
    response = client.post(f'/deal/start/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['status'] == 'in_progress'
    assert audit_of(db, 'deal_start', deal_db.id)


def test_start_deal_admin_ok(client, admin, make_deal, auth_headers):
    deal_db = make_deal()
    assert client.post(f'/deal/start/{deal_db.id}', headers=auth_headers(admin)).status_code == 200


def test_reserve_deal_ok(client, db, seller, client_user, salon_settings, make_deal, auth_headers):
    salon_settings.reservation_hours = 24
    db.commit()
    deal_db = make_deal(status=DealStatus.in_progress)
    before = datetime.now(timezone.utc)
    response = client.post(f'/deal/reserve/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'reserved'
    until = datetime.fromisoformat(data['reserved_until'].replace('Z', '+00:00'))
    expected = before + timedelta(hours=24)
    assert abs((until - expected).total_seconds()) < 60
    assert reload(db, Car, deal_db.car_id).status == CarStatus.reserved
    notes = notifications_of(db, client_user, NotificationType.reservation)
    assert len(notes) == 1
    assert audit_of(db, 'deal_reserve', deal_db.id)


def test_reserve_deal_default_48h_without_settings(client, db, seller, make_deal, auth_headers):
    assert db.query(SalonSettings).count() == 0
    deal_db = make_deal(status=DealStatus.in_progress)
    before = datetime.now(timezone.utc)
    response = client.post(f'/deal/reserve/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    until = datetime.fromisoformat(response.json()['reserved_until'].replace('Z', '+00:00'))
    assert abs((until - (before + timedelta(hours=48))).total_seconds()) < 60


def test_pay_deal_ok(client, db, seller, client_user, make_deal, make_car, auth_headers):
    deal_db = prepare(db, make_deal, make_car, DealStatus.reserved)
    response = client.post(f'/deal/pay/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'paid'
    assert data['paid_at'] is not None
    assert reload(db, Car, deal_db.car_id).status == CarStatus.reserved
    assert notifications_of(db, client_user, NotificationType.deal)
    assert audit_of(db, 'deal_pay', deal_db.id)


def test_deliver_deal_ok(client, db, seller, client_user, make_deal, make_car, auth_headers):
    deal_db = prepare(db, make_deal, make_car, DealStatus.paid)
    response = client.post(f'/deal/deliver/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'delivered'
    assert data['delivered_at'] is not None
    assert reload(db, Car, deal_db.car_id).status == CarStatus.sold
    assert notifications_of(db, client_user, NotificationType.deal)
    assert audit_of(db, 'deal_deliver', deal_db.id)


def test_full_flow_car_statuses(client, db, seller, make_deal, make_car, auth_headers):
    car_db = make_car()
    deal_db = make_deal(car=car_db)
    headers = auth_headers(seller)
    assert client.post(f'/deal/start/{deal_db.id}', headers=headers).status_code == 200
    assert reload(db, Car, car_db.id).status == CarStatus.available
    assert client.post(f'/deal/reserve/{deal_db.id}', headers=headers).status_code == 200
    assert reload(db, Car, car_db.id).status == CarStatus.reserved
    assert client.post(f'/deal/pay/{deal_db.id}', headers=headers).status_code == 200
    assert reload(db, Car, car_db.id).status == CarStatus.reserved
    assert client.post(f'/deal/deliver/{deal_db.id}', headers=headers).status_code == 200
    assert reload(db, Car, car_db.id).status == CarStatus.sold


FORBIDDEN_TRANSITIONS = [
    (DealStatus.new, 'reserve'),
    (DealStatus.new, 'pay'),
    (DealStatus.new, 'deliver'),
    (DealStatus.in_progress, 'pay'),
    (DealStatus.in_progress, 'start'),
    (DealStatus.in_progress, 'deliver'),
    (DealStatus.reserved, 'deliver'),
    (DealStatus.reserved, 'start'),
    (DealStatus.reserved, 'reserve'),
    (DealStatus.paid, 'reserve'),
    (DealStatus.paid, 'pay'),
    (DealStatus.paid, 'start'),
    (DealStatus.delivered, 'start'),
    (DealStatus.delivered, 'reserve'),
    (DealStatus.delivered, 'pay'),
    (DealStatus.delivered, 'deliver'),
    (DealStatus.cancelled, 'start'),
    (DealStatus.cancelled, 'reserve'),
    (DealStatus.cancelled, 'pay'),
    (DealStatus.cancelled, 'deliver'),
]


@pytest.mark.parametrize('deal_status, action', FORBIDDEN_TRANSITIONS)
def test_forbidden_transition_409(client, db, seller, make_deal, make_car, auth_headers, deal_status, action):
    deal_db = prepare(db, make_deal, make_car, deal_status)
    car_status_before = reload(db, Car, deal_db.car_id).status
    response = client.post(f'/deal/{action}/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 409
    assert reload(db, Deal, deal_db.id).status == deal_status
    assert reload(db, Car, deal_db.car_id).status == car_status_before


@pytest.mark.parametrize('deal_status', [DealStatus.delivered, DealStatus.cancelled])
def test_cancel_final_status_409(client, db, admin, make_deal, make_car, auth_headers, deal_status):
    deal_db = prepare(db, make_deal, make_car, deal_status)
    response = client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'причина'}, headers=auth_headers(admin))
    assert response.status_code == 409


@pytest.mark.parametrize('action', ['start', 'reserve', 'pay', 'deliver'])
def test_transition_as_client_403(client, client_user, make_deal, auth_headers, action):
    deal_db = make_deal()
    assert client.post(f'/deal/{action}/{deal_db.id}', headers=auth_headers(client_user)).status_code == 403


def test_cancel_as_client_403(client, client_user, make_deal, auth_headers):
    deal_db = make_deal()
    response = client.post(
        f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'не хочу'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 403


@pytest.mark.parametrize('action', ['start', 'reserve', 'pay', 'deliver'])
def test_transition_other_seller_404(client, seller2, make_deal, auth_headers, action):
    deal_db = make_deal()
    assert client.post(f'/deal/{action}/{deal_db.id}', headers=auth_headers(seller2)).status_code == 404


def test_cancel_other_seller_404(client, seller2, make_deal, auth_headers):
    deal_db = make_deal()
    response = client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'x'}, headers=auth_headers(seller2))
    assert response.status_code == 404


def test_transition_without_token_401(client, make_deal):
    deal_db = make_deal()
    assert client.post(f'/deal/start/{deal_db.id}').status_code == 401


def test_transition_unknown_deal_404(client, admin, auth_headers):
    assert client.post('/deal/start/99999', headers=auth_headers(admin)).status_code == 404


# ---------- reservation ----------


def test_reserve_car_already_reserved_409(client, db, seller, make_car, make_deal, auth_headers):
    car_db = make_car()
    first = make_deal(car=car_db, status=DealStatus.in_progress)
    second = make_deal(car=car_db, status=DealStatus.in_progress, client_id=_other_client(db).id)
    assert client.post(f'/deal/reserve/{first.id}', headers=auth_headers(seller)).status_code == 200
    response = client.post(f'/deal/reserve/{second.id}', headers=auth_headers(seller))
    assert response.status_code == 409
    assert response.json()['detail'] == 'Авто уже забронировано'
    second_db = reload(db, Deal, second.id)
    assert second_db.status == DealStatus.in_progress
    assert second_db.reserved_until is None
    assert reload(db, Car, car_db.id).status == CarStatus.reserved


def _other_client(db):
    from mysite.db.models import UserProfile

    user_db = UserProfile(username='clientx', email='clientx@test.kg', phone_number='+996700000099', password='x')
    db.add(user_db)
    db.commit()
    db.refresh(user_db)
    return user_db


def test_reserve_car_not_available_409(client, db, seller, make_car, make_deal, auth_headers):
    car_db = make_car(status=CarStatus.reserved)
    deal_db = make_deal(car=car_db, status=DealStatus.in_progress)
    response = client.post(f'/deal/reserve/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 409
    assert response.json()['detail'] == 'Авто уже забронировано'
    assert reload(db, Deal, deal_db.id).status == DealStatus.in_progress


@pytest.mark.parametrize('car_status', [CarStatus.in_transit, CarStatus.withdrawn, CarStatus.sold])
def test_reserve_car_wrong_status_409(client, db, seller, make_car, make_deal, auth_headers, car_status):
    car_db = make_car(status=car_status)
    deal_db = make_deal(car=car_db, status=DealStatus.in_progress)
    response = client.post(f'/deal/reserve/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 409
    assert reload(db, Deal, deal_db.id).status == DealStatus.in_progress
    assert reload(db, Car, car_db.id).status == car_status


def test_reserve_deleted_car_409(client, db, seller, make_car, make_deal, auth_headers):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    deal_db = make_deal(car=car_db, status=DealStatus.in_progress)
    assert client.post(f'/deal/reserve/{deal_db.id}', headers=auth_headers(seller)).status_code == 409
    assert reload(db, Deal, deal_db.id).status == DealStatus.in_progress


def test_reserve_after_cancel_other_ok(client, db, seller, make_car, make_deal, auth_headers):
    car_db = make_car()
    first = make_deal(car=car_db, status=DealStatus.in_progress)
    second = make_deal(car=car_db, status=DealStatus.in_progress, client_id=_other_client(db).id)
    headers = auth_headers(seller)
    assert client.post(f'/deal/reserve/{first.id}', headers=headers).status_code == 200
    assert client.post(f'/deal/reserve/{second.id}', headers=headers).status_code == 409
    cancel = client.post(f'/deal/cancel/{first.id}', json={'cancel_reason': 'передумал'}, headers=headers)
    assert cancel.status_code == 200
    assert reload(db, Car, car_db.id).status == CarStatus.available
    assert client.post(f'/deal/reserve/{second.id}', headers=headers).status_code == 200


def test_reserve_409_does_not_write_audit(client, db, seller, make_car, make_deal, auth_headers):
    car_db = make_car(status=CarStatus.reserved)
    deal_db = make_deal(car=car_db, status=DealStatus.in_progress)
    client.post(f'/deal/reserve/{deal_db.id}', headers=auth_headers(seller))
    assert audit_of(db, 'deal_reserve', deal_db.id) == []


# ---------- pay ----------


def test_pay_with_pending_discount_409(client, db, seller, make_deal, make_car, make_discount_request, auth_headers):
    deal_db = prepare(db, make_deal, make_car, DealStatus.reserved)
    make_discount_request(deal_id=deal_db.id)
    response = client.post(f'/deal/pay/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 409
    assert reload(db, Deal, deal_db.id).status == DealStatus.reserved


def test_pay_expired_reservation_409_and_cancelled(client, db, seller, make_deal, make_car, auth_headers):
    deal_db = prepare(
        db, make_deal, make_car, DealStatus.reserved, reserved_until=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    response = client.post(f'/deal/pay/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 409
    deal_after = reload(db, Deal, deal_db.id)
    assert deal_after.status == DealStatus.cancelled
    assert reload(db, Car, deal_db.car_id).status == CarStatus.available


# ---------- deliver ----------


def test_deliver_cancels_other_active_deals(
    client, db, seller, seller2, client2, make_deal, make_car, make_discount_request, auth_headers
):
    car_db = make_car(status=CarStatus.reserved)
    paid = make_deal(
        car=car_db,
        status=DealStatus.paid,
        reserved_until=datetime.now(timezone.utc) + timedelta(hours=5),
        paid_at=datetime.now(timezone.utc),
    )
    other_new = make_deal(car=car_db, status=DealStatus.new, client_id=client2.id, seller_id=seller2.id)
    other_progress = make_deal(car=car_db, status=DealStatus.in_progress, client_id=_other_client(db).id)
    discount_db = make_discount_request(deal_id=other_new.id, seller_id=seller2.id)

    response = client.post(f'/deal/deliver/{paid.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert reload(db, Car, car_db.id).status == CarStatus.sold
    for other in (other_new, other_progress):
        other_after = reload(db, Deal, other.id)
        assert other_after.status == DealStatus.cancelled
        assert other_after.cancel_reason
    assert reload(db, DiscountRequest, discount_db.id).status == DiscountStatus.rejected
    assert notifications_of(db, client2, NotificationType.deal)
    assert any(str(other_new.id) in n.text for n in notifications_of(db, seller2, NotificationType.deal))


# ---------- cancel ----------


def test_cancel_new_ok(client, db, seller, client_user, make_deal, auth_headers):
    deal_db = make_deal()
    response = client.post(
        f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'клиент передумал'}, headers=auth_headers(seller)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'cancelled'
    assert data['cancel_reason'] == 'клиент передумал'
    assert reload(db, Car, deal_db.car_id).status == CarStatus.available
    assert audit_of(db, 'deal_cancel', deal_db.id)


def test_cancel_reserved_releases_car(client, db, seller, make_deal, make_car, auth_headers):
    deal_db = prepare(db, make_deal, make_car, DealStatus.reserved)
    response = client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'x'}, headers=auth_headers(seller))
    assert response.status_code == 200
    assert reload(db, Car, deal_db.car_id).status == CarStatus.available


def test_cancel_paid_by_admin_releases_car(client, db, admin, make_deal, make_car, auth_headers):
    deal_db = prepare(db, make_deal, make_car, DealStatus.paid)
    response = client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'возврат'}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['status'] == 'cancelled'
    assert reload(db, Car, deal_db.car_id).status == CarStatus.available


def test_cancel_paid_by_seller_403(client, db, seller, make_deal, make_car, auth_headers):
    deal_db = prepare(db, make_deal, make_car, DealStatus.paid)
    response = client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'x'}, headers=auth_headers(seller))
    assert response.status_code == 403
    assert reload(db, Deal, deal_db.id).status == DealStatus.paid
    assert reload(db, Car, deal_db.car_id).status == CarStatus.reserved


def test_cancel_without_reason_422(client, seller, make_deal, auth_headers):
    deal_db = make_deal()
    assert client.post(f'/deal/cancel/{deal_db.id}', json={}, headers=auth_headers(seller)).status_code == 422


def test_cancel_blank_reason_422(client, seller, make_deal, auth_headers):
    deal_db = make_deal()
    response = client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': '   '}, headers=auth_headers(seller))
    assert response.status_code == 422


def test_cancel_rejects_pending_discounts(client, db, seller, admin, make_deal, make_discount_request, auth_headers):
    deal_db = make_deal()
    discount_db = make_discount_request(deal_id=deal_db.id)
    response = client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'x'}, headers=auth_headers(admin))
    assert response.status_code == 200
    discount_after = reload(db, DiscountRequest, discount_db.id)
    assert discount_after.status == DiscountStatus.rejected
    assert discount_after.decided_at is not None
    assert notifications_of(db, seller, NotificationType.discount)


def test_cancel_notifies_client_not_actor(client, db, seller, client_user, make_deal, auth_headers):
    deal_db = make_deal()
    client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'причина-отмены'}, headers=auth_headers(seller))
    client_notes = notifications_of(db, client_user, NotificationType.deal)
    assert any('причина-отмены' in n.text for n in client_notes)
    assert not any('причина-отмены' in n.text for n in notifications_of(db, seller))


def test_cancel_by_admin_notifies_seller_and_client(client, db, admin, seller, client_user, make_deal, auth_headers):
    deal_db = make_deal()
    client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'adm'}, headers=auth_headers(admin))
    assert any('adm' in n.text for n in notifications_of(db, seller, NotificationType.deal))
    assert any('adm' in n.text for n in notifications_of(db, client_user, NotificationType.deal))
    assert not notifications_of(db, admin)


# ---------- delete ----------


def test_delete_deal_admin_new_ok(client, db, admin, make_deal, auth_headers):
    deal_db = make_deal()
    response = client.delete(f'/deal/delete/{deal_db.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert reload(db, Deal, deal_db.id).deleted_at is not None
    assert client.get('/deal/list', headers=auth_headers(admin)).json() == []
    assert client.get(f'/deal/detail?deal_id={deal_db.id}', headers=auth_headers(admin)).status_code == 404
    assert audit_of(db, 'deal_delete', deal_db.id)


def test_delete_deal_admin_cancelled_ok(client, admin, make_deal, auth_headers):
    deal_db = make_deal(status=DealStatus.cancelled)
    assert client.delete(f'/deal/delete/{deal_db.id}', headers=auth_headers(admin)).status_code == 200


@pytest.mark.parametrize(
    'deal_status', [DealStatus.in_progress, DealStatus.reserved, DealStatus.paid, DealStatus.delivered]
)
def test_delete_deal_wrong_status_409(client, db, admin, make_deal, make_car, auth_headers, deal_status):
    deal_db = prepare(db, make_deal, make_car, deal_status)
    assert client.delete(f'/deal/delete/{deal_db.id}', headers=auth_headers(admin)).status_code == 409
    assert reload(db, Deal, deal_db.id).deleted_at is None


def test_delete_deal_seller_403(client, seller, make_deal, auth_headers):
    deal_db = make_deal()
    assert client.delete(f'/deal/delete/{deal_db.id}', headers=auth_headers(seller)).status_code == 403


def test_delete_deal_client_403(client, client_user, make_deal, auth_headers):
    deal_db = make_deal()
    assert client.delete(f'/deal/delete/{deal_db.id}', headers=auth_headers(client_user)).status_code == 403


def test_delete_deal_not_found_404(client, admin, auth_headers):
    assert client.delete('/deal/delete/99999', headers=auth_headers(admin)).status_code == 404


def test_delete_deal_twice_404(client, admin, make_deal, auth_headers):
    deal_db = make_deal()
    assert client.delete(f'/deal/delete/{deal_db.id}', headers=auth_headers(admin)).status_code == 200
    assert client.delete(f'/deal/delete/{deal_db.id}', headers=auth_headers(admin)).status_code == 404


def test_delete_deal_rejects_pending_discounts(client, db, admin, make_deal, make_discount_request, auth_headers):
    deal_db = make_deal()
    discount_db = make_discount_request(deal_id=deal_db.id)
    client.delete(f'/deal/delete/{deal_db.id}', headers=auth_headers(admin))
    assert reload(db, DiscountRequest, discount_db.id).status == DiscountStatus.rejected


def test_delete_deal_without_token_401(client, make_deal):
    deal_db = make_deal()
    assert client.delete(f'/deal/delete/{deal_db.id}').status_code == 401


def test_deliver_skips_other_deal_changed_concurrently(
    client, db, seller, make_deal, make_car, auth_headers, monkeypatch
):
    from mysite.api import deal as deal_module

    car_db = make_car(status=CarStatus.reserved)
    paid = make_deal(
        car=car_db,
        status=DealStatus.paid,
        reserved_until=datetime.now(timezone.utc) + timedelta(hours=5),
        paid_at=datetime.now(timezone.utc),
    )
    other = make_deal(car=car_db, status=DealStatus.new, client_id=_other_client(db).id)
    original = deal_module.update_deal_status

    def fake_update(db_, deal_id, from_status, to_status, *args, **fields):
        if deal_id == other.id:
            return 0  # сделку уже перевели другим действием
        return original(db_, deal_id, from_status, to_status, *args, **fields)

    monkeypatch.setattr(deal_module, 'update_deal_status', fake_update)
    response = client.post(f'/deal/deliver/{paid.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert reload(db, Car, car_db.id).status == CarStatus.sold
    assert reload(db, Deal, other.id).status == DealStatus.new
