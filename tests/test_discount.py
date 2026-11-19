from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from mysite.api.deal import calc_final_price
from mysite.db.models import (
    AuditLog,
    Deal,
    DealStatus,
    DiscountRequest,
    DiscountStatus,
    Notification,
    NotificationType,
    UserProfile,
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


def set_limit(db, user, limit):
    user.discount_limit = Decimal(str(limit))
    db.commit()


def create_discount(client, user_headers, deal_id, percent, **extra):
    return client.post(
        '/discount/create', json={'deal_id': deal_id, 'requested_percent': percent, **extra}, headers=user_headers
    )


# ---------- calc ----------


def test_final_price_rounding_half_up():
    assert calc_final_price(Decimal('100.30'), Decimal('5')) == Decimal('95.29')


def test_final_price_zero_percent_equals_base():
    assert calc_final_price(Decimal('1500000.00'), Decimal('0')) == Decimal('1500000.00')


# ---------- create: within limit ----------


def test_discount_within_limit_applied(client, db, seller, client_user, make_deal, auth_headers):
    set_limit(db, seller, 5)
    deal_db = make_deal()
    response = create_discount(client, auth_headers(seller), deal_db.id, '3', comment='Постоянный клиент')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'approved'
    assert data['decided_by_id'] == seller.id
    assert data['seller_id'] == seller.id
    assert data['decided_at'] is not None
    deal_after = reload(db, Deal, deal_db.id)
    assert deal_after.discount_percent == Decimal('3')
    assert deal_after.final_price == Decimal('1455000.00')
    assert notifications_of(db, client_user, NotificationType.deal)
    assert audit_of(db, 'discount_apply', data['id'])


def test_discount_equal_limit_applied(client, db, seller, make_deal, auth_headers):
    set_limit(db, seller, 5)
    deal_db = make_deal()
    response = create_discount(client, auth_headers(seller), deal_db.id, '5')
    assert response.json()['status'] == 'approved'


def test_discount_above_limit_pending(client, db, seller, admin, make_user, make_deal, auth_headers):
    set_limit(db, seller, 5)
    blocked_admin = make_user('blockedadmin', UserRole.admin, is_active=False)
    deal_db = make_deal()
    response = create_discount(client, auth_headers(seller), deal_db.id, '7')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'pending'
    assert data['decided_by_id'] is None
    deal_after = reload(db, Deal, deal_db.id)
    assert deal_after.discount_percent == 0
    assert deal_after.final_price == deal_db.base_price
    assert notifications_of(db, admin, NotificationType.discount)
    assert notifications_of(db, blocked_admin) == []
    assert audit_of(db, 'discount_request', data['id'])


def test_discount_zero_limit_always_pending(client, db, seller, make_deal, auth_headers):
    assert seller.discount_limit == 0
    deal_db = make_deal()
    response = create_discount(client, auth_headers(seller), deal_db.id, '0.01')
    assert response.json()['status'] == 'pending'


def test_discount_admin_applies_any(client, db, admin, make_deal, auth_headers):
    deal_db = make_deal()
    response = create_discount(client, auth_headers(admin), deal_db.id, '40')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'approved'
    assert data['decided_by_id'] == admin.id
    assert reload(db, Deal, deal_db.id).final_price == Decimal('900000.00')


def test_discount_seller_id_taken_from_deal_for_admin(client, admin, seller, make_deal, auth_headers):
    deal_db = make_deal()
    response = create_discount(client, auth_headers(admin), deal_db.id, '10', seller_id=admin.id, status='rejected')
    assert response.json()['seller_id'] == seller.id
    assert response.json()['status'] == 'approved'


def test_discount_ignores_status_and_decided_by(client, db, seller, admin, make_deal, auth_headers):
    deal_db = make_deal()
    response = create_discount(
        client, auth_headers(seller), deal_db.id, '50', status='approved', decided_by_id=admin.id, seller_id=admin.id
    )
    data = response.json()
    assert data['status'] == 'pending'
    assert data['decided_by_id'] is None
    assert data['seller_id'] == seller.id


def test_discount_on_reserved_deal_ok(client, db, seller, make_deal, make_car, auth_headers):
    set_limit(db, seller, 5)
    deal_db = make_deal(
        car=make_car(status='reserved'),
        status=DealStatus.reserved,
        reserved_until=datetime.now(timezone.utc) + timedelta(hours=5),
    )
    assert create_discount(client, auth_headers(seller), deal_db.id, '2').status_code == 200


# ---------- calc via API ----------


def test_final_price_rounding_half_up_via_api(client, db, admin, make_car, make_deal, auth_headers):
    car_db = make_car(price=Decimal('100.30'))
    deal_db = make_deal(car=car_db)
    response = create_discount(client, auth_headers(admin), deal_db.id, '5')
    assert response.status_code == 200
    assert reload(db, Deal, deal_db.id).final_price == Decimal('95.29')
    detail = client.get(f'/deal/detail?deal_id={deal_db.id}', headers=auth_headers(admin)).json()
    assert Decimal(detail['final_price']) == Decimal('95.29')


def test_final_price_decimal_string(client, admin, make_car, make_deal, auth_headers):
    car_db = make_car(price=Decimal('1500000.00'))
    deal_db = make_deal(car=car_db)
    create_discount(client, auth_headers(admin), deal_db.id, '3.33')
    detail = client.get(f'/deal/detail?deal_id={deal_db.id}', headers=auth_headers(admin)).json()
    assert Decimal(detail['final_price']) == Decimal('1450050.00')


def test_discount_replaces_not_accumulates(client, db, admin, make_deal, auth_headers):
    deal_db = make_deal()
    create_discount(client, auth_headers(admin), deal_db.id, '10')
    create_discount(client, auth_headers(admin), deal_db.id, '5')
    deal_after = reload(db, Deal, deal_db.id)
    assert deal_after.discount_percent == Decimal('5')
    assert deal_after.final_price == Decimal('1425000.00')


# ---------- validation ----------


@pytest.mark.parametrize('percent', ['0', '100', '-1', '5.555', '101'])
def test_discount_invalid_percent_422(client, seller, make_deal, auth_headers, percent):
    deal_db = make_deal()
    assert create_discount(client, auth_headers(seller), deal_db.id, percent).status_code == 422


def test_discount_missing_fields_422(client, seller, auth_headers):
    assert client.post('/discount/create', json={}, headers=auth_headers(seller)).status_code == 422


def test_discount_same_as_current_400(client, db, admin, make_deal, auth_headers):
    deal_db = make_deal()
    assert create_discount(client, auth_headers(admin), deal_db.id, '5').status_code == 200
    assert create_discount(client, auth_headers(admin), deal_db.id, '5').status_code == 400


# ---------- conflicts ----------


def test_discount_second_pending_409(client, seller, make_deal, auth_headers):
    deal_db = make_deal()
    assert create_discount(client, auth_headers(seller), deal_db.id, '10').status_code == 200
    assert create_discount(client, auth_headers(seller), deal_db.id, '12').status_code == 409


def test_discount_after_rejected_ok(client, db, seller, make_deal, make_discount_request, auth_headers):
    deal_db = make_deal()
    make_discount_request(deal_id=deal_db.id, status=DiscountStatus.rejected)
    assert create_discount(client, auth_headers(seller), deal_db.id, '10').status_code == 200


@pytest.mark.parametrize('deal_status', [DealStatus.paid, DealStatus.delivered, DealStatus.cancelled])
def test_discount_wrong_deal_status_409(client, seller, make_deal, auth_headers, deal_status):
    deal_db = make_deal(status=deal_status)
    assert create_discount(client, auth_headers(seller), deal_db.id, '10').status_code == 409


def test_discount_deleted_deal_404(client, seller, make_deal, auth_headers):
    deal_db = make_deal(deleted_at=datetime.now(timezone.utc))
    assert create_discount(client, auth_headers(seller), deal_db.id, '10').status_code == 404


def test_discount_unknown_deal_404(client, seller, auth_headers):
    assert create_discount(client, auth_headers(seller), 99999, '10').status_code == 404


# ---------- permissions ----------


def test_discount_create_as_client_403(client, client_user, make_deal, auth_headers):
    deal_db = make_deal()
    assert create_discount(client, auth_headers(client_user), deal_db.id, '10').status_code == 403


def test_discount_create_without_token_401(client, make_deal):
    deal_db = make_deal()
    assert client.post('/discount/create', json={'deal_id': deal_db.id, 'requested_percent': '10'}).status_code == 401


def test_discount_create_other_seller_deal_404(client, seller2, make_deal, auth_headers):
    deal_db = make_deal()
    assert create_discount(client, auth_headers(seller2), deal_db.id, '10').status_code == 404


def test_discount_list_seller_only_own(client, seller, seller2, make_deal, make_discount_request, auth_headers):
    own = make_discount_request(deal_id=make_deal().id)
    make_discount_request(deal_id=make_deal(seller_id=seller2.id).id, seller_id=seller2.id)
    response = client.get('/discount/list', headers=auth_headers(seller))
    assert response.status_code == 200
    assert [d['id'] for d in response.json()] == [own.id]


def test_discount_list_admin_sees_all(client, admin, seller2, make_deal, make_discount_request, auth_headers):
    first = make_discount_request(deal_id=make_deal().id)
    second = make_discount_request(deal_id=make_deal(seller_id=seller2.id).id, seller_id=seller2.id)
    response = client.get('/discount/list', headers=auth_headers(admin))
    assert {d['id'] for d in response.json()} == {first.id, second.id}


def test_discount_list_filters(client, admin, seller2, make_deal, make_discount_request, auth_headers):
    pending = make_discount_request(deal_id=make_deal().id)
    approved = make_discount_request(deal_id=make_deal().id, status=DiscountStatus.approved)
    other = make_discount_request(deal_id=make_deal(seller_id=seller2.id).id, seller_id=seller2.id)
    by_status = client.get('/discount/list?status=approved', headers=auth_headers(admin)).json()
    assert [d['id'] for d in by_status] == [approved.id]
    by_seller = client.get(f'/discount/list?seller_id={seller2.id}', headers=auth_headers(admin)).json()
    assert [d['id'] for d in by_seller] == [other.id]
    by_deal = client.get(f'/discount/list?deal_id={pending.deal_id}', headers=auth_headers(admin)).json()
    assert [d['id'] for d in by_deal] == [pending.id]


def test_discount_list_excludes_deleted_deals(client, admin, make_deal, make_discount_request, auth_headers):
    make_discount_request(deal_id=make_deal(deleted_at=datetime.now(timezone.utc)).id)
    assert client.get('/discount/list', headers=auth_headers(admin)).json() == []


def test_discount_list_client_403(client, client_user, auth_headers):
    assert client.get('/discount/list', headers=auth_headers(client_user)).status_code == 403


def test_discount_list_without_token_401(client):
    assert client.get('/discount/list').status_code == 401


def test_discount_list_limit_422(client, admin, auth_headers):
    assert client.get('/discount/list?limit=101', headers=auth_headers(admin)).status_code == 422


def test_discount_detail_ok(client, seller, admin, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    for user in (seller, admin):
        response = client.get(f'/discount/detail?discount_request_id={discount_db.id}', headers=auth_headers(user))
        assert response.status_code == 200
        assert response.json()['id'] == discount_db.id


def test_discount_detail_other_seller_404(client, seller2, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    response = client.get(f'/discount/detail?discount_request_id={discount_db.id}', headers=auth_headers(seller2))
    assert response.status_code == 404


def test_discount_detail_client_403(client, client_user, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    response = client.get(f'/discount/detail?discount_request_id={discount_db.id}', headers=auth_headers(client_user))
    assert response.status_code == 403


# ---------- approve / reject ----------


def test_approve_ok(client, db, admin, seller, client_user, make_deal, make_discount_request, auth_headers):
    deal_db = make_deal()
    discount_db = make_discount_request(deal_id=deal_db.id, requested_percent=Decimal('10'))
    response = client.post(f'/discount/approve/{discount_db.id}', json={'comment': 'ок'}, headers=auth_headers(admin))
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'approved'
    assert data['decided_by_id'] == admin.id
    assert data['decided_at'].endswith('+00:00') or data['decided_at'].endswith('Z')
    deal_after = reload(db, Deal, deal_db.id)
    assert deal_after.discount_percent == Decimal('10')
    assert deal_after.final_price == Decimal('1350000.00')
    assert notifications_of(db, seller, NotificationType.discount)
    assert notifications_of(db, client_user, NotificationType.deal)
    logs = audit_of(db, 'discount_approve', discount_db.id)
    assert len(logs) == 1
    assert logs[0].user_id == admin.id


def test_approve_without_body_ok(client, admin, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    assert client.post(f'/discount/approve/{discount_db.id}', headers=auth_headers(admin)).status_code == 200


def test_reject_ok(client, db, admin, seller, make_deal, make_discount_request, auth_headers):
    deal_db = make_deal()
    discount_db = make_discount_request(deal_id=deal_db.id, comment='Просьба продавца')
    response = client.post(
        f'/discount/reject/{discount_db.id}', json={'comment': 'Слишком много'}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'rejected'
    assert data['comment'] == 'Просьба продавца'
    assert data['decided_by_id'] == admin.id
    deal_after = reload(db, Deal, deal_db.id)
    assert deal_after.discount_percent == 0
    assert deal_after.final_price == deal_db.base_price
    notes = notifications_of(db, seller, NotificationType.discount)
    assert any('Слишком много' in n.text for n in notes)
    logs = audit_of(db, 'discount_reject', discount_db.id)
    assert len(logs) == 1
    assert logs[0].new_value['comment'] == 'Слишком много'


def test_reject_without_body_ok(client, admin, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    assert client.post(f'/discount/reject/{discount_db.id}', headers=auth_headers(admin)).status_code == 200


@pytest.mark.parametrize('first, second', [('approve', 'approve'), ('approve', 'reject'), ('reject', 'approve')])
def test_decide_already_decided_409(client, admin, make_discount_request, auth_headers, first, second):
    discount_db = make_discount_request()
    assert client.post(f'/discount/{first}/{discount_db.id}', headers=auth_headers(admin)).status_code == 200
    assert client.post(f'/discount/{second}/{discount_db.id}', headers=auth_headers(admin)).status_code == 409


def test_reject_already_decided_409(client, admin, make_discount_request, auth_headers):
    discount_db = make_discount_request(status=DiscountStatus.rejected)
    assert client.post(f'/discount/reject/{discount_db.id}', headers=auth_headers(admin)).status_code == 409


@pytest.mark.parametrize('action', ['approve', 'reject'])
def test_decide_as_seller_403(client, seller, make_discount_request, auth_headers, action):
    discount_db = make_discount_request()
    assert client.post(f'/discount/{action}/{discount_db.id}', headers=auth_headers(seller)).status_code == 403


@pytest.mark.parametrize('action', ['approve', 'reject'])
def test_decide_as_client_403(client, client_user, make_discount_request, auth_headers, action):
    discount_db = make_discount_request()
    assert client.post(f'/discount/{action}/{discount_db.id}', headers=auth_headers(client_user)).status_code == 403


@pytest.mark.parametrize('action', ['approve', 'reject'])
def test_decide_not_found_404(client, admin, auth_headers, action):
    assert client.post(f'/discount/{action}/99999', headers=auth_headers(admin)).status_code == 404


def test_approve_after_deal_cancelled_409(client, db, admin, make_deal, make_discount_request, auth_headers):
    deal_db = make_deal()
    discount_db = make_discount_request(deal_id=deal_db.id)
    cancel = client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'x'}, headers=auth_headers(admin))
    assert cancel.status_code == 200
    assert client.post(f'/discount/approve/{discount_db.id}', headers=auth_headers(admin)).status_code == 409
    assert reload(db, Deal, deal_db.id).final_price == deal_db.base_price


def test_approve_unblocks_pay(client, db, admin, seller, make_deal, make_car, make_discount_request, auth_headers):
    deal_db = make_deal(
        car=make_car(status='reserved'),
        status=DealStatus.reserved,
        reserved_until=datetime.now(timezone.utc) + timedelta(hours=5),
    )
    discount_db = make_discount_request(deal_id=deal_db.id)
    assert client.post(f'/deal/pay/{deal_db.id}', headers=auth_headers(seller)).status_code == 409
    client.post(f'/discount/reject/{discount_db.id}', headers=auth_headers(admin))
    assert client.post(f'/deal/pay/{deal_db.id}', headers=auth_headers(seller)).status_code == 200


# ---------- withdraw ----------


def test_withdraw_pending_by_author_ok(client, db, seller, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    response = client.delete(f'/discount/delete/{discount_db.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert reload(db, DiscountRequest, discount_db.id) is None
    assert audit_of(db, 'discount_withdraw', discount_db.id)


def test_withdraw_by_admin_ok(client, admin, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    assert client.delete(f'/discount/delete/{discount_db.id}', headers=auth_headers(admin)).status_code == 200


@pytest.mark.parametrize('decided', [DiscountStatus.approved, DiscountStatus.rejected])
def test_withdraw_decided_409(client, db, seller, make_discount_request, auth_headers, decided):
    discount_db = make_discount_request(status=decided)
    assert client.delete(f'/discount/delete/{discount_db.id}', headers=auth_headers(seller)).status_code == 409
    assert reload(db, DiscountRequest, discount_db.id) is not None


def test_withdraw_other_seller_404(client, seller2, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    assert client.delete(f'/discount/delete/{discount_db.id}', headers=auth_headers(seller2)).status_code == 404


def test_withdraw_as_client_403(client, client_user, make_discount_request, auth_headers):
    discount_db = make_discount_request()
    assert client.delete(f'/discount/delete/{discount_db.id}', headers=auth_headers(client_user)).status_code == 403


# ---------- discount limit (user.py) ----------


def test_update_discount_limit_writes_audit_log(client, db, admin, seller, auth_headers):
    response = client.put(
        f'/user/discount-limit/{seller.id}', json={'discount_limit': '7.5'}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert reload(db, UserProfile, seller.id).discount_limit == Decimal('7.5')
    logs = audit_of(db, 'user_discount_limit', seller.id)
    assert len(logs) == 1
    assert logs[0].user_id == admin.id
    assert logs[0].entity_name == 'user_profile'
    assert logs[0].old_value == {'discount_limit': '0.00'} or Decimal(logs[0].old_value['discount_limit']) == 0
    assert Decimal(logs[0].new_value['discount_limit']) == Decimal('7.5')
