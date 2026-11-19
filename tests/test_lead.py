from datetime import datetime, timezone

import pytest

from mysite.db.models import Lead, LeadNote, LeadStatus, LeadType, Notification, NotificationType, UserRole


def ids(response):
    return [item['id'] for item in response.json()]


def notifications_of(db, user):
    db.expire_all()
    return db.query(Notification).filter(Notification.user_id == user.id).all()


# ---------- create ----------


def test_create_lead_as_client_ok(client, client_user, auth_headers, make_car):
    car_db = make_car()
    response = client.post(
        '/lead/create',
        json={'car_id': car_db.id, 'lead_type': 'purchase', 'comment': 'Хочу купить'},
        headers=auth_headers(client_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data['client_id'] == client_user.id
    assert data['status'] == 'new'
    assert data['seller_id'] is None
    assert data['car_id'] == car_db.id
    assert 'password' not in response.text


def test_create_lead_ignores_client_id_seller_id_status(client, client_user, seller, make_user, auth_headers):
    other = make_user('other', UserRole.client)
    response = client.post(
        '/lead/create',
        json={
            'lead_type': 'question',
            'client_id': other.id,
            'seller_id': seller.id,
            'status': 'closed',
        },
        headers=auth_headers(client_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data['client_id'] == client_user.id
    assert data['seller_id'] is None
    assert data['status'] == 'new'


def test_create_lead_response_created_at_is_aware(client, client_user, auth_headers):
    response = client.post('/lead/create', json={'lead_type': 'question'}, headers=auth_headers(client_user))
    created_at = datetime.fromisoformat(response.json()['created_at'].replace('Z', '+00:00'))
    assert created_at.tzinfo is not None
    assert created_at.utcoffset().total_seconds() == 0


def test_create_lead_as_seller_403(client, seller, auth_headers):
    response = client.post('/lead/create', json={'lead_type': 'question'}, headers=auth_headers(seller))
    assert response.status_code == 403


def test_create_lead_as_admin_403(client, admin, auth_headers):
    response = client.post('/lead/create', json={'lead_type': 'question'}, headers=auth_headers(admin))
    assert response.status_code == 403


def test_create_lead_without_token_401(client):
    assert client.post('/lead/create', json={'lead_type': 'question'}).status_code == 401


def test_create_lead_unknown_car_404(client, client_user, auth_headers):
    response = client.post(
        '/lead/create', json={'car_id': 99999, 'lead_type': 'purchase'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 404


def test_create_lead_deleted_car_404(client, db, client_user, auth_headers, make_car):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    response = client.post(
        '/lead/create', json={'car_id': car_db.id, 'lead_type': 'purchase'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 404


def test_create_lead_sold_car_404(client, client_user, auth_headers, make_car):
    from mysite.db.models import CarStatus

    car_db = make_car(status=CarStatus.sold)
    response = client.post(
        '/lead/create', json={'car_id': car_db.id, 'lead_type': 'purchase'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 404


def test_create_lead_test_drive_without_car_400(client, client_user, auth_headers):
    response = client.post('/lead/create', json={'lead_type': 'test_drive'}, headers=auth_headers(client_user))
    assert response.status_code == 400


def test_create_lead_question_without_car_ok(client, client_user, auth_headers):
    response = client.post('/lead/create', json={'lead_type': 'question'}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['car_id'] is None


def test_create_lead_duplicate_active_409(client, client_user, auth_headers, make_car):
    car_db = make_car()
    body = {'car_id': car_db.id, 'lead_type': 'purchase'}
    assert client.post('/lead/create', json=body, headers=auth_headers(client_user)).status_code == 200
    assert client.post('/lead/create', json=body, headers=auth_headers(client_user)).status_code == 409


def test_create_lead_duplicate_after_closed_ok(client, client_user, auth_headers, make_car, make_lead):
    car_db = make_car()
    make_lead(car_id=car_db.id, status=LeadStatus.closed)
    response = client.post(
        '/lead/create', json={'car_id': car_db.id, 'lead_type': 'purchase'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 200


def test_create_lead_other_type_same_car_ok(client, client_user, auth_headers, make_car, make_lead):
    car_db = make_car()
    make_lead(car_id=car_db.id, lead_type=LeadType.purchase)
    response = client.post(
        '/lead/create', json={'car_id': car_db.id, 'lead_type': 'test_drive'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 200


def test_create_lead_comment_too_long_422(client, client_user, auth_headers):
    response = client.post(
        '/lead/create', json={'lead_type': 'question', 'comment': 'a' * 2001}, headers=auth_headers(client_user)
    )
    assert response.status_code == 422


def test_create_lead_invalid_type_422(client, client_user, auth_headers):
    response = client.post('/lead/create', json={'lead_type': 'bogus'}, headers=auth_headers(client_user))
    assert response.status_code == 422


def test_create_lead_notifies_active_sellers(client, db, client_user, seller, make_user, auth_headers):
    blocked = make_user('blockedseller', UserRole.seller, is_active=False)
    seller2 = make_user('seller2', UserRole.seller)
    admin_db = make_user('adm', UserRole.admin)
    response = client.post('/lead/create', json={'lead_type': 'question'}, headers=auth_headers(client_user))
    assert response.status_code == 200
    lead_id = response.json()['id']
    for user in (seller, seller2):
        items = notifications_of(db, user)
        assert len(items) == 1
        assert items[0].notification_type == NotificationType.lead
        assert str(lead_id) in items[0].text
    assert notifications_of(db, blocked) == []
    assert notifications_of(db, admin_db) == []
    assert notifications_of(db, client_user) == []


# ---------- list ----------


def test_list_lead_without_token_401(client):
    assert client.get('/lead/list').status_code == 401


def test_list_lead_client_sees_only_own(client, client_user, make_user, auth_headers, make_lead):
    other = make_user('other', UserRole.client)
    mine = make_lead()
    make_lead(client_id=other.id)
    response = client.get('/lead/list', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert ids(response) == [mine.id]


def test_list_lead_seller_sees_own_and_free(client, seller, make_user, auth_headers, make_lead):
    seller2 = make_user('seller2', UserRole.seller)
    own = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    free = make_lead()
    other = make_lead(seller_id=seller2.id, status=LeadStatus.in_progress)
    response = client.get('/lead/list', headers=auth_headers(seller))
    assert response.status_code == 200
    assert set(ids(response)) == {own.id, free.id}
    assert other.id not in ids(response)


def test_list_lead_seller_not_sees_closed_unassigned(client, seller, auth_headers, make_lead):
    make_lead(status=LeadStatus.rejected)
    assert client.get('/lead/list', headers=auth_headers(seller)).json() == []


def test_list_lead_only_free(client, seller, auth_headers, make_lead):
    make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    free = make_lead()
    response = client.get('/lead/list', params={'only_free': True}, headers=auth_headers(seller))
    assert ids(response) == [free.id]


def test_list_lead_admin_sees_all(client, admin, seller, auth_headers, make_lead):
    a = make_lead()
    b = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    c = make_lead(status=LeadStatus.closed)
    response = client.get('/lead/list', headers=auth_headers(admin))
    assert set(ids(response)) == {a.id, b.id, c.id}


def test_list_lead_admin_filter_seller_id(client, admin, seller, auth_headers, make_lead):
    make_lead()
    b = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.get('/lead/list', params={'seller_id': seller.id}, headers=auth_headers(admin))
    assert ids(response) == [b.id]


def test_list_lead_seller_id_filter_ignored_for_seller(client, seller, make_user, auth_headers, make_lead):
    seller2 = make_user('seller2', UserRole.seller)
    make_lead(seller_id=seller2.id, status=LeadStatus.in_progress)
    response = client.get('/lead/list', params={'seller_id': seller2.id}, headers=auth_headers(seller))
    assert response.json() == []


def test_list_lead_filter_status_and_type(client, admin, auth_headers, make_lead):
    a = make_lead(lead_type=LeadType.question)
    make_lead(lead_type=LeadType.purchase, status=LeadStatus.closed)
    assert ids(client.get('/lead/list', params={'status': 'new'}, headers=auth_headers(admin))) == [a.id]
    assert ids(client.get('/lead/list', params={'lead_type': 'question'}, headers=auth_headers(admin))) == [a.id]


def test_list_lead_order_newest_first_and_pagination(client, admin, auth_headers, make_lead):
    first = make_lead()
    second = make_lead()
    third = make_lead()
    response = client.get('/lead/list', headers=auth_headers(admin))
    assert ids(response) == [third.id, second.id, first.id]
    page = client.get('/lead/list', params={'skip': 1, 'limit': 1}, headers=auth_headers(admin))
    assert ids(page) == [second.id]


@pytest.mark.parametrize('params', [{'limit': 101}, {'limit': 0}, {'skip': -1}])
def test_list_lead_invalid_pagination_422(client, admin, auth_headers, params):
    assert client.get('/lead/list', params=params, headers=auth_headers(admin)).status_code == 422


# ---------- detail ----------


def test_detail_lead_own_ok(client, client_user, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.get('/lead/detail', params={'lead_id': lead_db.id}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['id'] == lead_db.id


def test_detail_lead_other_client_404(client, make_user, auth_headers, make_lead):
    lead_db = make_lead()
    other = make_user('other', UserRole.client)
    response = client.get('/lead/detail', params={'lead_id': lead_db.id}, headers=auth_headers(other))
    assert response.status_code == 404


def test_detail_lead_other_seller_404(client, make_user, auth_headers, make_lead):
    seller1 = make_user('s1', UserRole.seller)
    seller2 = make_user('s2', UserRole.seller)
    lead_db = make_lead(seller_id=seller1.id, status=LeadStatus.in_progress)
    response = client.get('/lead/detail', params={'lead_id': lead_db.id}, headers=auth_headers(seller2))
    assert response.status_code == 404


def test_detail_free_lead_seller_ok(client, seller, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.get('/lead/detail', params={'lead_id': lead_db.id}, headers=auth_headers(seller))
    assert response.status_code == 200


def test_detail_lead_admin_ok(client, admin, seller, auth_headers, make_lead):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.get('/lead/detail', params={'lead_id': lead_db.id}, headers=auth_headers(admin))
    assert response.status_code == 200


def test_detail_lead_not_found_404(client, admin, auth_headers):
    assert client.get('/lead/detail', params={'lead_id': 9999}, headers=auth_headers(admin)).status_code == 404


def test_detail_lead_without_token_401(client):
    assert client.get('/lead/detail', params={'lead_id': 1}).status_code == 401


# ---------- take ----------


def test_take_lead_ok(client, db, seller, client_user, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'in_progress'
    assert data['seller_id'] == seller.id
    items = notifications_of(db, client_user)
    assert len(items) == 1
    assert items[0].notification_type == NotificationType.lead


def test_take_lead_twice_by_same_seller_409(client, seller, auth_headers, make_lead):
    lead_db = make_lead()
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(seller)).status_code == 200
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(seller)).status_code == 409


def test_take_lead_taken_by_other_seller_404(client, make_user, auth_headers, make_lead):
    seller1 = make_user('s1', UserRole.seller)
    seller2 = make_user('s2', UserRole.seller)
    lead_db = make_lead()
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(seller1)).status_code == 200
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(seller2)).status_code == 404


def test_take_lead_as_client_403(client, client_user, auth_headers, make_lead):
    lead_db = make_lead()
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(client_user)).status_code == 403


def test_take_lead_as_admin_403(client, admin, auth_headers, make_lead):
    lead_db = make_lead()
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(admin)).status_code == 403


def test_take_lead_without_token_401(client, make_lead):
    lead_db = make_lead()
    assert client.post(f'/lead/take/{lead_db.id}').status_code == 401


def test_take_closed_lead_404(client, seller, auth_headers, make_lead):
    lead_db = make_lead(status=LeadStatus.closed)
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(seller)).status_code in (404, 409)


def test_take_unknown_lead_404(client, seller, auth_headers):
    assert client.post('/lead/take/9999', headers=auth_headers(seller)).status_code == 404


# ---------- assign ----------


def test_assign_lead_admin_ok(client, db, admin, seller, client_user, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.post(f'/lead/assign/{lead_db.id}', json={'seller_id': seller.id}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller.id
    assert response.json()['status'] == 'in_progress'
    assert len(notifications_of(db, seller)) == 1
    assert len(notifications_of(db, client_user)) == 1


def test_assign_lead_to_client_404(client, admin, client_user, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.post(
        f'/lead/assign/{lead_db.id}', json={'seller_id': client_user.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 404


def test_assign_lead_to_blocked_seller_404(client, admin, make_user, auth_headers, make_lead):
    blocked = make_user('blocked', UserRole.seller, is_active=False)
    lead_db = make_lead()
    response = client.post(f'/lead/assign/{lead_db.id}', json={'seller_id': blocked.id}, headers=auth_headers(admin))
    assert response.status_code == 404


def test_reassign_lead_notifies_old_seller(client, db, admin, seller, make_user, auth_headers, make_lead):
    seller2 = make_user('seller2', UserRole.seller)
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.post(f'/lead/assign/{lead_db.id}', json={'seller_id': seller2.id}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller2.id
    assert len(notifications_of(db, seller2)) == 1
    assert len(notifications_of(db, seller)) == 1


def test_assign_closed_lead_409(client, admin, seller, auth_headers, make_lead):
    lead_db = make_lead(status=LeadStatus.closed)
    response = client.post(f'/lead/assign/{lead_db.id}', json={'seller_id': seller.id}, headers=auth_headers(admin))
    assert response.status_code == 409


def test_assign_lead_as_seller_403(client, seller, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.post(f'/lead/assign/{lead_db.id}', json={'seller_id': seller.id}, headers=auth_headers(seller))
    assert response.status_code == 403


def test_assign_unknown_lead_404(client, admin, seller, auth_headers):
    response = client.post('/lead/assign/9999', json={'seller_id': seller.id}, headers=auth_headers(admin))
    assert response.status_code == 404


# ---------- update ----------


def test_update_lead_client_comment_new_ok(client, client_user, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.put(
        f'/lead/update/{lead_db.id}', json={'comment': 'Новый комментарий'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 200
    assert response.json()['comment'] == 'Новый комментарий'


def test_update_lead_client_comment_in_progress_409(client, client_user, seller, auth_headers, make_lead):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.put(f'/lead/update/{lead_db.id}', json={'comment': 'x'}, headers=auth_headers(client_user))
    assert response.status_code == 409


def test_update_lead_client_status_403(client, client_user, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'closed'}, headers=auth_headers(client_user))
    assert response.status_code == 403


def test_update_lead_other_client_404(client, make_user, auth_headers, make_lead):
    other = make_user('other', UserRole.client)
    lead_db = make_lead()
    response = client.put(f'/lead/update/{lead_db.id}', json={'comment': 'x'}, headers=auth_headers(other))
    assert response.status_code == 404


@pytest.mark.parametrize('new_status, word', [('closed', 'закрыта'), ('rejected', 'отклонена')])
def test_update_lead_seller_close_ok(client, db, seller, client_user, auth_headers, make_lead, new_status, word):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': new_status}, headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['status'] == new_status
    items = notifications_of(db, client_user)
    assert len(items) == 1
    assert word in items[0].text


def test_update_lead_seller_comment_403(client, seller, auth_headers, make_lead):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.put(f'/lead/update/{lead_db.id}', json={'comment': 'x'}, headers=auth_headers(seller))
    assert response.status_code == 403


def test_update_lead_other_seller_404(client, make_user, auth_headers, make_lead):
    seller1 = make_user('s1', UserRole.seller)
    seller2 = make_user('s2', UserRole.seller)
    lead_db = make_lead(seller_id=seller1.id, status=LeadStatus.in_progress)
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'closed'}, headers=auth_headers(seller2))
    assert response.status_code == 404


def test_update_lead_free_lead_seller_404(client, seller, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'rejected'}, headers=auth_headers(seller))
    assert response.status_code == 404


def test_update_lead_new_to_in_progress_409(client, admin, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'in_progress'}, headers=auth_headers(admin))
    assert response.status_code == 409


@pytest.mark.parametrize('final', [LeadStatus.closed, LeadStatus.rejected])
@pytest.mark.parametrize('target', ['in_progress', 'closed', 'rejected', 'new'])
def test_update_lead_from_final_status_409(client, admin, auth_headers, make_lead, final, target):
    lead_db = make_lead(status=final)
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': target}, headers=auth_headers(admin))
    assert response.status_code == 409


def test_update_lead_same_status_409(client, admin, seller, auth_headers, make_lead):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'in_progress'}, headers=auth_headers(admin))
    assert response.status_code == 409


def test_update_lead_in_progress_back_to_new_409(client, admin, seller, auth_headers, make_lead):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'new'}, headers=auth_headers(admin))
    assert response.status_code == 409


def test_update_lead_null_status_400(client, admin, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': None}, headers=auth_headers(admin))
    assert response.status_code == 400


def test_update_lead_admin_reject_new_ok(client, admin, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'rejected'}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['status'] == 'rejected'


def test_update_lead_admin_comment_null_ok(client, admin, auth_headers, make_lead):
    lead_db = make_lead(comment='old')
    response = client.put(f'/lead/update/{lead_db.id}', json={'comment': None}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['comment'] is None


def test_update_lead_invalid_status_422(client, admin, auth_headers, make_lead):
    lead_db = make_lead()
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'bogus'}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_update_lead_without_token_401(client, make_lead):
    lead_db = make_lead()
    assert client.put(f'/lead/update/{lead_db.id}', json={'comment': 'x'}).status_code == 401


# ---------- delete ----------


def test_delete_lead_client_new_ok(client, db, client_user, auth_headers, make_lead):
    lead_db = make_lead()
    lead_id = lead_db.id
    response = client.delete(f'/lead/delete/{lead_id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    db.expire_all()
    assert db.get(Lead, lead_id) is None


def test_delete_lead_client_in_progress_409(client, client_user, seller, auth_headers, make_lead):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    assert client.delete(f'/lead/delete/{lead_db.id}', headers=auth_headers(client_user)).status_code == 409


def test_delete_lead_other_client_404(client, make_user, auth_headers, make_lead):
    other = make_user('other', UserRole.client)
    lead_db = make_lead()
    assert client.delete(f'/lead/delete/{lead_db.id}', headers=auth_headers(other)).status_code == 404


def test_delete_lead_seller_403(client, seller, auth_headers, make_lead):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    assert client.delete(f'/lead/delete/{lead_db.id}', headers=auth_headers(seller)).status_code == 403


def test_delete_lead_admin_cascades_notes(client, db, admin, seller, auth_headers, make_lead):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.in_progress)
    lead_id = lead_db.id
    db.add(LeadNote(lead_id=lead_id, seller_id=seller.id, note='заметка'))
    db.commit()
    response = client.delete(f'/lead/delete/{lead_id}', headers=auth_headers(admin))
    assert response.status_code == 200
    db.expire_all()
    assert db.get(Lead, lead_id) is None
    assert db.query(LeadNote).filter(LeadNote.lead_id == lead_id).count() == 0


def test_delete_lead_without_token_401(client, make_lead):
    lead_db = make_lead()
    assert client.delete(f'/lead/delete/{lead_db.id}').status_code == 401


# ---------- уведомления: заблокированные получатели, текст типа ----------


def test_take_lead_blocked_client_not_notified(client, db, seller, make_user, auth_headers, make_lead):
    blocked_client = make_user('blockedclient', UserRole.client, is_active=False)
    lead_db = make_lead(client_id=blocked_client.id)
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(seller)).status_code == 200
    assert notifications_of(db, blocked_client) == []


def test_reassign_lead_blocked_old_seller_not_notified(client, db, admin, make_user, auth_headers, make_lead):
    old_seller = make_user('oldseller', UserRole.seller, is_active=False)
    new_seller = make_user('newseller', UserRole.seller)
    lead_db = make_lead(seller_id=old_seller.id, status=LeadStatus.in_progress)
    response = client.post(f'/lead/assign/{lead_db.id}', json={'seller_id': new_seller.id}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert len(notifications_of(db, new_seller)) == 1
    assert notifications_of(db, old_seller) == []


def test_close_lead_blocked_client_not_notified(client, db, seller, make_user, auth_headers, make_lead):
    blocked_client = make_user('blockedclient', UserRole.client, is_active=False)
    lead_db = make_lead(client_id=blocked_client.id, seller_id=seller.id, status=LeadStatus.in_progress)
    response = client.put(f'/lead/update/{lead_db.id}', json={'status': 'closed'}, headers=auth_headers(seller))
    assert response.status_code == 200
    assert notifications_of(db, blocked_client) == []


def test_create_lead_notification_uses_russian_type(client, db, client_user, seller, auth_headers):
    response = client.post('/lead/create', json={'lead_type': 'purchase'}, headers=auth_headers(client_user))
    assert response.status_code == 200
    text = notifications_of(db, seller)[0].text
    assert 'покупка' in text
    assert 'purchase' not in text
