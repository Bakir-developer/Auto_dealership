from datetime import datetime
from decimal import Decimal

import pytest

from mysite.db.models import (
    AuditLog,
    Notification,
    NotificationType,
    TradeIn,
    TradeInImage,
    TradeInStatus,
    UserRole,
)

PAYLOAD = {'brand_name': 'Toyota', 'model_name': 'Corolla', 'year': 2015, 'mileage': 120000}


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


def create(client, headers, **overrides):
    return client.post('/trade-in/create', json={**PAYLOAD, **overrides}, headers=headers)


# ---------- create ----------


def test_create_trade_in_ok(client, client_user, seller, auth_headers, db):
    response = create(client, auth_headers(client_user), description='Хорошее состояние')
    assert response.status_code == 200
    body = response.json()
    assert body['client_id'] == client_user.id
    assert body['status'] == 'new'
    assert body['seller_id'] is None
    assert body['estimated_price'] is None
    assert body['brand_name'] == 'Toyota'
    assert body['images'] == []
    notes = notifications_of(db, seller, NotificationType.lead)
    assert len(notes) == 1
    assert str(body['id']) in notes[0].text
    assert notifications_of(db, client_user) == []


def test_create_trade_in_ignores_server_fields(client, client_user, seller, auth_headers):
    response = create(
        client,
        auth_headers(client_user),
        status='accepted',
        seller_id=seller.id,
        estimated_price='500000.00',
        client_id=seller.id,
    )
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'new'
    assert body['seller_id'] is None
    assert body['estimated_price'] is None
    assert body['client_id'] == client_user.id


def test_create_trade_in_as_seller_403(client, seller, auth_headers):
    assert create(client, auth_headers(seller)).status_code == 403


def test_create_trade_in_as_admin_403(client, admin, auth_headers):
    assert create(client, auth_headers(admin)).status_code == 403


def test_create_trade_in_without_token_401(client):
    assert create(client, {}).status_code == 401


def test_create_trade_in_future_year_400(client, client_user, auth_headers):
    year = datetime.now().year + 2
    assert create(client, auth_headers(client_user), year=year).status_code == 400


def test_create_trade_in_next_year_ok(client, client_user, auth_headers):
    year = datetime.now().year + 1
    assert create(client, auth_headers(client_user), year=year).status_code == 200


def test_create_trade_in_negative_mileage_422(client, client_user, auth_headers):
    assert create(client, auth_headers(client_user), mileage=-1).status_code == 422


def test_create_trade_in_blank_brand_422(client, client_user, auth_headers):
    assert create(client, auth_headers(client_user), brand_name='   ').status_code == 422


def test_create_trade_in_missing_field_422(client, client_user, auth_headers):
    response = client.post('/trade-in/create', json={'brand_name': 'Toyota'}, headers=auth_headers(client_user))
    assert response.status_code == 422


def test_create_trade_in_cyrillic_ok(client, client_user, auth_headers):
    response = create(client, auth_headers(client_user), brand_name='Лада', model_name='Гранта')
    assert response.status_code == 200
    assert response.json()['brand_name'] == 'Лада'
    assert response.json()['model_name'] == 'Гранта'


def test_create_trade_in_active_limit_409(client, client_user, auth_headers, make_trade_in):
    for _ in range(5):
        make_trade_in()
    assert create(client, auth_headers(client_user)).status_code == 409


def test_create_trade_in_closed_not_counted_in_limit(client, client_user, auth_headers, make_trade_in):
    for _ in range(4):
        make_trade_in()
    for closed in (TradeInStatus.accepted, TradeInStatus.rejected):
        make_trade_in(status=closed)
    assert create(client, auth_headers(client_user)).status_code == 200
    assert create(client, auth_headers(client_user)).status_code == 409


# ---------- list / detail ----------


def test_list_client_sees_only_own(client, client_user, client2, auth_headers, make_trade_in):
    own = make_trade_in()
    make_trade_in(client_id=client2.id)
    response = client.get('/trade-in/list', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert [item['id'] for item in response.json()] == [own.id]


def test_list_seller_sees_own_and_free(client, seller, seller2, auth_headers, make_trade_in):
    free = make_trade_in()
    mine = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    make_trade_in(seller_id=seller2.id, status=TradeInStatus.evaluating)
    response = client.get('/trade-in/list', headers=auth_headers(seller))
    assert response.status_code == 200
    assert {item['id'] for item in response.json()} == {free.id, mine.id}


def test_list_seller_not_sees_other_taken(client, seller, seller2, auth_headers, make_trade_in):
    other = make_trade_in(seller_id=seller2.id, status=TradeInStatus.evaluating)
    response = client.get('/trade-in/list', headers=auth_headers(seller))
    assert other.id not in [item['id'] for item in response.json()]


def test_list_admin_sees_all(client, admin, seller, client2, auth_headers, make_trade_in):
    ids = {
        make_trade_in().id,
        make_trade_in(client_id=client2.id).id,
        make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating).id,
    }
    response = client.get('/trade-in/list', headers=auth_headers(admin))
    assert {item['id'] for item in response.json()} == ids


def test_list_filter_status(client, admin, auth_headers, make_trade_in):
    make_trade_in()
    offered = make_trade_in(status=TradeInStatus.offered)
    response = client.get('/trade-in/list', params={'status': 'offered'}, headers=auth_headers(admin))
    assert [item['id'] for item in response.json()] == [offered.id]


def test_list_only_free(client, admin, seller, auth_headers, make_trade_in):
    free = make_trade_in()
    make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    response = client.get('/trade-in/list', params={'only_free': 'true'}, headers=auth_headers(admin))
    assert [item['id'] for item in response.json()] == [free.id]


def test_list_admin_filter_seller_id(client, admin, seller, seller2, auth_headers, make_trade_in):
    make_trade_in(seller_id=seller2.id, status=TradeInStatus.evaluating)
    mine = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    response = client.get('/trade-in/list', params={'seller_id': seller.id}, headers=auth_headers(admin))
    assert [item['id'] for item in response.json()] == [mine.id]


def test_list_pagination(client, client_user, auth_headers, make_trade_in):
    ids = [make_trade_in().id for _ in range(3)]
    response = client.get('/trade-in/list', params={'skip': 1, 'limit': 1}, headers=auth_headers(client_user))
    assert len(response.json()) == 1
    # сортировка по убыванию: id 3, 2, 1 (одинаковый created_at -> id desc)
    assert response.json()[0]['id'] == ids[1]


def test_list_limit_101_422(client, client_user, auth_headers):
    assert client.get('/trade-in/list', params={'limit': 101}, headers=auth_headers(client_user)).status_code == 422


def test_list_without_token_401(client):
    assert client.get('/trade-in/list').status_code == 401


def test_detail_own_ok(client, client_user, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.get('/trade-in/detail', params={'trade_in_id': trade_in.id}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['id'] == trade_in.id


def test_detail_other_client_404(client, client2, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.get('/trade-in/detail', params={'trade_in_id': trade_in.id}, headers=auth_headers(client2))
    assert response.status_code == 404


def test_detail_other_seller_taken_404(client, seller, seller2, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller2.id, status=TradeInStatus.evaluating)
    response = client.get('/trade-in/detail', params={'trade_in_id': trade_in.id}, headers=auth_headers(seller))
    assert response.status_code == 404


def test_detail_free_visible_to_seller(client, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.get('/trade-in/detail', params={'trade_in_id': trade_in.id}, headers=auth_headers(seller))
    assert response.status_code == 200


def test_detail_unknown_404(client, admin, auth_headers):
    assert client.get('/trade-in/detail', params={'trade_in_id': 9999}, headers=auth_headers(admin)).status_code == 404


def test_detail_includes_images(client, client_user, auth_headers, make_trade_in, make_trade_in_image):
    trade_in = make_trade_in()
    first = make_trade_in_image(trade_in, 'a.jpg')
    second = make_trade_in_image(trade_in, 'b.jpg')
    response = client.get('/trade-in/detail', params={'trade_in_id': trade_in.id}, headers=auth_headers(client_user))
    assert [image['id'] for image in response.json()['images']] == [first.id, second.id]


def test_detail_datetime_utc_offset(client, client_user, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.get('/trade-in/detail', params={'trade_in_id': trade_in.id}, headers=auth_headers(client_user))
    created_at = datetime.fromisoformat(response.json()['created_at'].replace('Z', '+00:00'))
    assert created_at.utcoffset().total_seconds() == 0


# ---------- transitions ----------


def test_take_ok(client, seller, client_user, auth_headers, make_trade_in, db):
    trade_in = make_trade_in()
    response = client.post(f'/trade-in/take/{trade_in.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['status'] == 'evaluating'
    assert response.json()['seller_id'] == seller.id
    notes = notifications_of(db, client_user, NotificationType.lead)
    assert len(notes) == 1
    assert str(trade_in.id) in notes[0].text


def test_take_already_taken_409(client, seller, seller2, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    assert client.post(f'/trade-in/take/{trade_in.id}', headers=auth_headers(seller)).status_code == 200
    # у второго продавца заявка уже не видна (взята) -> 404 по видимости, 409 по гонке
    assert client.post(f'/trade-in/take/{trade_in.id}', headers=auth_headers(seller2)).status_code in (404, 409)
    # повторное взятие своим же продавцом -> 409
    assert client.post(f'/trade-in/take/{trade_in.id}', headers=auth_headers(seller)).status_code == 409


def test_take_as_client_403(client, client_user, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    assert client.post(f'/trade-in/take/{trade_in.id}', headers=auth_headers(client_user)).status_code == 403


def test_take_as_admin_403(client, admin, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    assert client.post(f'/trade-in/take/{trade_in.id}', headers=auth_headers(admin)).status_code == 403


def test_take_without_token_401(client, make_trade_in):
    assert client.post(f'/trade-in/take/{make_trade_in().id}').status_code == 401


def test_assign_admin_ok(client, admin, seller, client_user, auth_headers, make_trade_in, db):
    trade_in = make_trade_in()
    response = client.post(
        f'/trade-in/assign/{trade_in.id}', json={'seller_id': seller.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller.id
    assert response.json()['status'] == 'evaluating'
    assert len(notifications_of(db, seller, NotificationType.lead)) == 1
    assert len(notifications_of(db, client_user, NotificationType.lead)) == 1


def test_assign_reassign_notifies_old_seller(client, admin, seller, seller2, auth_headers, make_trade_in, db):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    response = client.post(
        f'/trade-in/assign/{trade_in.id}', json={'seller_id': seller2.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller2.id
    assert response.json()['status'] == 'evaluating'
    assert len(notifications_of(db, seller, NotificationType.lead)) == 1


@pytest.mark.parametrize('current', [TradeInStatus.offered, TradeInStatus.evaluating])
def test_assign_keeps_status_for_in_work(client, admin, seller, seller2, auth_headers, make_trade_in, current):
    trade_in = make_trade_in(seller_id=seller.id, status=current)
    response = client.post(
        f'/trade-in/assign/{trade_in.id}', json={'seller_id': seller2.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller2.id
    assert response.json()['status'] == current.value


def test_assign_old_seller_loses_access_offer_reject(client, admin, seller, seller2, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    client.post(f'/trade-in/assign/{trade_in.id}', json={'seller_id': seller2.id}, headers=auth_headers(admin))
    assert offer(client, auth_headers(seller), trade_in.id).status_code in (404, 409)
    assert client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(seller)).status_code in (404, 409)
    assert offer(client, auth_headers(seller2), trade_in.id).status_code == 200


def test_assign_blocked_seller_404(client, admin, make_user, auth_headers, make_trade_in):
    blocked = make_user('blockedseller', is_active=False, role=UserRole.seller)
    trade_in = make_trade_in()
    response = client.post(
        f'/trade-in/assign/{trade_in.id}', json={'seller_id': blocked.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 404


def test_assign_not_seller_404(client, admin, client2, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.post(
        f'/trade-in/assign/{trade_in.id}', json={'seller_id': client2.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 404


@pytest.mark.parametrize('closed', [TradeInStatus.accepted, TradeInStatus.rejected])
def test_assign_closed_409(client, admin, seller, auth_headers, make_trade_in, closed):
    trade_in = make_trade_in(status=closed)
    response = client.post(
        f'/trade-in/assign/{trade_in.id}', json={'seller_id': seller.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 409


def test_assign_as_seller_403(client, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.post(
        f'/trade-in/assign/{trade_in.id}', json={'seller_id': seller.id}, headers=auth_headers(seller)
    )
    assert response.status_code == 403


def offer(client, headers, trade_in_id, **overrides):
    return client.post(
        f'/trade-in/offer/{trade_in_id}',
        json={'estimated_price': '450000.50', 'currency': 'KGS', **overrides},
        headers=headers,
    )


def test_offer_ok(client, seller, client_user, auth_headers, make_trade_in, db):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    response = offer(client, auth_headers(seller), trade_in.id, currency='USD', estimated_price='12345.60')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'offered'
    assert body['estimated_price'] == '12345.60'
    assert body['currency'] == 'USD'
    stored = reload(db, TradeIn, trade_in.id)
    assert stored.estimated_price == Decimal('12345.60')
    notes = notifications_of(db, client_user, NotificationType.lead)
    assert len(notes) == 1
    assert '12345.60' in notes[0].text and 'USD' in notes[0].text
    logs = audit_of(db, 'trade_in_offer', trade_in.id)
    assert len(logs) == 1
    assert logs[0].user_id == seller.id
    assert logs[0].new_value['status'] == 'offered'


def test_offer_by_admin_ok(client, admin, auth_headers, make_trade_in):
    trade_in = make_trade_in(status=TradeInStatus.evaluating)
    assert offer(client, auth_headers(admin), trade_in.id).status_code == 200


def test_offer_from_new_409(client, admin, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    assert offer(client, auth_headers(admin), trade_in.id).status_code == 409


def test_offer_other_seller_404(client, seller, seller2, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    assert offer(client, auth_headers(seller2), trade_in.id).status_code == 404


def test_offer_as_client_403(client, client_user, auth_headers, make_trade_in):
    trade_in = make_trade_in(status=TradeInStatus.evaluating)
    assert offer(client, auth_headers(client_user), trade_in.id).status_code == 403


@pytest.mark.parametrize('price', ['0', '-5', '0.00'])
def test_offer_non_positive_price_422(client, seller, auth_headers, make_trade_in, price):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    assert offer(client, auth_headers(seller), trade_in.id, estimated_price=price).status_code == 422


def test_offer_too_many_decimals_422(client, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    assert offer(client, auth_headers(seller), trade_in.id, estimated_price='100.555').status_code == 422


def test_accept_ok(client, client_user, seller, auth_headers, make_trade_in, db):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.offered, estimated_price=Decimal('100000'))
    response = client.post(f'/trade-in/accept/{trade_in.id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['status'] == 'accepted'
    assert len(notifications_of(db, seller, NotificationType.lead)) == 1
    logs = audit_of(db, 'trade_in_accept', trade_in.id)
    assert len(logs) == 1
    assert logs[0].user_id == client_user.id


@pytest.mark.parametrize('current', [TradeInStatus.new, TradeInStatus.evaluating])
def test_accept_not_offered_409(client, client_user, auth_headers, make_trade_in, current):
    trade_in = make_trade_in(status=current)
    assert client.post(f'/trade-in/accept/{trade_in.id}', headers=auth_headers(client_user)).status_code == 409


def test_accept_as_seller_403(client, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.offered)
    assert client.post(f'/trade-in/accept/{trade_in.id}', headers=auth_headers(seller)).status_code == 403


def test_accept_other_client_404(client, client2, auth_headers, make_trade_in):
    trade_in = make_trade_in(status=TradeInStatus.offered)
    assert client.post(f'/trade-in/accept/{trade_in.id}', headers=auth_headers(client2)).status_code == 404


def test_reject_by_client_offered_ok(client, client_user, seller, auth_headers, make_trade_in, db):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.offered)
    response = client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['status'] == 'rejected'
    assert len(notifications_of(db, seller, NotificationType.lead)) == 1
    assert notifications_of(db, client_user) == []
    assert len(audit_of(db, 'trade_in_reject', trade_in.id)) == 1


@pytest.mark.parametrize('current', [TradeInStatus.new, TradeInStatus.evaluating])
def test_reject_by_client_not_offered_409(client, client_user, auth_headers, make_trade_in, current):
    trade_in = make_trade_in(status=current)
    assert client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(client_user)).status_code == 409


def test_reject_by_seller_evaluating_ok(client, seller, client_user, auth_headers, make_trade_in, db):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    response = client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['status'] == 'rejected'
    assert len(notifications_of(db, client_user, NotificationType.lead)) == 1


def test_reject_by_seller_offered_409(client, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.offered)
    assert client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(seller)).status_code == 409


def test_reject_by_other_seller_404(client, seller, seller2, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    assert client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(seller2)).status_code == 404


def test_reject_by_admin_new_ok(client, admin, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['status'] == 'rejected'


def test_reject_other_client_404(client, client2, auth_headers, make_trade_in):
    trade_in = make_trade_in(status=TradeInStatus.offered)
    assert client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(client2)).status_code == 404


@pytest.mark.parametrize('closed', [TradeInStatus.accepted, TradeInStatus.rejected])
def test_actions_on_closed_trade_in_409(client, admin, client_user, seller, auth_headers, make_trade_in, closed):
    trade_in = make_trade_in(seller_id=seller.id, status=closed)
    admin_headers = auth_headers(admin)
    assert offer(client, admin_headers, trade_in.id).status_code == 409
    assert client.post(f'/trade-in/reject/{trade_in.id}', headers=admin_headers).status_code == 409
    assert client.post(f'/trade-in/accept/{trade_in.id}', headers=auth_headers(client_user)).status_code == 409
    assert client.post(f'/trade-in/reject/{trade_in.id}', headers=auth_headers(client_user)).status_code == 409
    assert (
        client.post(f'/trade-in/assign/{trade_in.id}', json={'seller_id': seller.id}, headers=admin_headers).status_code
        == 409
    )


# ---------- update ----------


def test_update_client_new_ok(client, client_user, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.put(
        f'/trade-in/update/{trade_in.id}',
        json={'brand_name': 'Honda', 'mileage': 100, 'description': 'new text'},
        headers=auth_headers(client_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body['brand_name'] == 'Honda'
    assert body['mileage'] == 100
    assert body['description'] == 'new text'
    assert body['model_name'] == 'Corolla'


def test_update_client_evaluating_409(client, client_user, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    response = client.put(
        f'/trade-in/update/{trade_in.id}', json={'brand_name': 'Honda'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 409


def test_update_other_client_404(client, client2, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.put(f'/trade-in/update/{trade_in.id}', json={'brand_name': 'H'}, headers=auth_headers(client2))
    assert response.status_code == 404


def test_update_as_seller_403(client, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.put(f'/trade-in/update/{trade_in.id}', json={'brand_name': 'H'}, headers=auth_headers(seller))
    assert response.status_code == 403


@pytest.mark.parametrize('field', ['brand_name', 'model_name', 'year', 'mileage'])
def test_update_null_field_400(client, client_user, auth_headers, make_trade_in, field):
    trade_in = make_trade_in()
    response = client.put(f'/trade-in/update/{trade_in.id}', json={field: None}, headers=auth_headers(client_user))
    assert response.status_code == 400


def test_update_future_year_400(client, client_user, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    response = client.put(
        f'/trade-in/update/{trade_in.id}', json={'year': datetime.now().year + 2}, headers=auth_headers(client_user)
    )
    assert response.status_code == 400


def test_update_ignores_status_and_price(client, client_user, seller, auth_headers, make_trade_in, db):
    trade_in = make_trade_in()
    response = client.put(
        f'/trade-in/update/{trade_in.id}',
        json={'brand_name': 'Honda', 'status': 'accepted', 'estimated_price': '1.00', 'seller_id': seller.id},
        headers=auth_headers(client_user),
    )
    assert response.status_code == 200
    stored = reload(db, TradeIn, trade_in.id)
    assert stored.status == TradeInStatus.new
    assert stored.estimated_price is None
    assert stored.seller_id is None


def test_update_without_token_401(client, make_trade_in):
    assert client.put(f'/trade-in/update/{make_trade_in().id}', json={'brand_name': 'H'}).status_code == 401


# ---------- delete ----------


def test_delete_client_new_ok(client, client_user, auth_headers, make_trade_in, make_trade_in_image, media_dir, db):
    trade_in = make_trade_in()
    trade_in_id = trade_in.id
    file_path = media_dir / 'trade_in_images' / 'a.jpg'
    file_path.write_bytes(b'x')
    make_trade_in_image(trade_in, 'a.jpg')
    response = client.delete(f'/trade-in/delete/{trade_in_id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json() == {'message': 'Заявка на trade-in удалена'}
    assert reload(db, TradeIn, trade_in_id) is None
    assert db.query(TradeInImage).count() == 0
    assert not file_path.exists()
    assert audit_of(db, 'trade_in_delete', trade_in_id) == []


@pytest.mark.parametrize('current', [TradeInStatus.evaluating, TradeInStatus.offered, TradeInStatus.accepted])
def test_delete_client_not_new_409(client, client_user, seller, auth_headers, make_trade_in, current):
    trade_in = make_trade_in(seller_id=seller.id, status=current)
    assert client.delete(f'/trade-in/delete/{trade_in.id}', headers=auth_headers(client_user)).status_code == 409


def test_delete_admin_any_ok(client, admin, seller, auth_headers, make_trade_in, db):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.offered)
    response = client.delete(f'/trade-in/delete/{trade_in.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert reload(db, TradeIn, trade_in.id) is None
    logs = audit_of(db, 'trade_in_delete', trade_in.id)
    assert len(logs) == 1
    assert logs[0].user_id == admin.id


def test_delete_seller_403(client, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    assert client.delete(f'/trade-in/delete/{trade_in.id}', headers=auth_headers(seller)).status_code == 403


def test_delete_other_client_404(client, client2, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    assert client.delete(f'/trade-in/delete/{trade_in.id}', headers=auth_headers(client2)).status_code == 404


def test_delete_without_token_401(client, make_trade_in):
    assert client.delete(f'/trade-in/delete/{make_trade_in().id}').status_code == 401
