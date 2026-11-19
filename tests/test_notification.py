from datetime import datetime, timezone

from mysite.db.models import LeadStatus, Notification, UserRole


def ids(response):
    return [item['id'] for item in response.json()]


def test_list_without_token_401(client):
    assert client.get('/notification/list').status_code == 401


def test_list_only_own(client, client_user, seller, auth_headers, make_notification):
    mine = make_notification(client_user)
    make_notification(seller)
    response = client.get('/notification/list', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert ids(response) == [mine.id]


def test_list_admin_sees_only_own(client, admin, client_user, auth_headers, make_notification):
    make_notification(client_user)
    assert client.get('/notification/list', headers=auth_headers(admin)).json() == []


def test_list_filter_is_read(client, client_user, auth_headers, make_notification):
    unread = make_notification(client_user)
    read = make_notification(client_user, is_read=True)
    assert ids(client.get('/notification/list', params={'is_read': False}, headers=auth_headers(client_user))) == [
        unread.id
    ]
    assert ids(client.get('/notification/list', params={'is_read': True}, headers=auth_headers(client_user))) == [
        read.id
    ]


def test_list_order_newest_first(client, client_user, auth_headers, make_notification):
    first = make_notification(client_user)
    second = make_notification(client_user)
    assert ids(client.get('/notification/list', headers=auth_headers(client_user))) == [second.id, first.id]


def test_list_pagination_and_invalid_limit(client, client_user, auth_headers, make_notification):
    for _ in range(3):
        make_notification(client_user)
    page = client.get('/notification/list', params={'skip': 1, 'limit': 1}, headers=auth_headers(client_user))
    assert len(page.json()) == 1
    assert client.get('/notification/list', params={'limit': 101}, headers=auth_headers(client_user)).status_code == 422


def test_detail_own_ok(client, client_user, auth_headers, make_notification):
    note = make_notification(client_user, 'Привет')
    response = client.get(
        '/notification/detail', params={'notification_id': note.id}, headers=auth_headers(client_user)
    )
    assert response.status_code == 200
    assert response.json()['text'] == 'Привет'


def test_detail_other_user_404(client, client_user, admin, auth_headers, make_notification):
    note = make_notification(client_user)
    response = client.get('/notification/detail', params={'notification_id': note.id}, headers=auth_headers(admin))
    assert response.status_code == 404


def test_detail_other_client_404(client, client_user, make_user, auth_headers, make_notification):
    other = make_user('other', UserRole.client)
    note = make_notification(client_user)
    response = client.get('/notification/detail', params={'notification_id': note.id}, headers=auth_headers(other))
    assert response.status_code == 404


def test_unread_count(client, client_user, seller, auth_headers, make_notification):
    make_notification(client_user)
    make_notification(client_user)
    make_notification(client_user, is_read=True)
    make_notification(seller)
    response = client.get('/notification/unread-count', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json() == {'count': 2}


def test_unread_count_without_token_401(client):
    assert client.get('/notification/unread-count').status_code == 401


def test_update_mark_read_ok(client, client_user, auth_headers, make_notification):
    note = make_notification(client_user)
    response = client.put(f'/notification/update/{note.id}', json={'is_read': True}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['is_read'] is True
    count = client.get('/notification/unread-count', headers=auth_headers(client_user))
    assert count.json()['count'] == 0


def test_update_null_400(client, client_user, auth_headers, make_notification):
    note = make_notification(client_user)
    response = client.put(f'/notification/update/{note.id}', json={'is_read': None}, headers=auth_headers(client_user))
    assert response.status_code == 400


def test_update_other_user_404(client, client_user, seller, auth_headers, make_notification):
    note = make_notification(client_user)
    response = client.put(f'/notification/update/{note.id}', json={'is_read': True}, headers=auth_headers(seller))
    assert response.status_code == 404


def test_read_all_marks_only_own(client, db, client_user, seller, auth_headers, make_notification):
    make_notification(client_user)
    make_notification(client_user)
    foreign = make_notification(seller)
    response = client.post('/notification/read-all', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['count'] == 2
    assert client.get('/notification/unread-count', headers=auth_headers(client_user)).json() == {'count': 0}
    db.expire_all()
    assert db.get(Notification, foreign.id).is_read is False


def test_read_all_without_token_401(client):
    assert client.post('/notification/read-all').status_code == 401


def test_delete_own_ok(client, db, client_user, auth_headers, make_notification):
    note = make_notification(client_user)
    note_id = note.id
    assert client.delete(f'/notification/delete/{note_id}', headers=auth_headers(client_user)).status_code == 200
    db.expire_all()
    assert db.get(Notification, note_id) is None


def test_delete_other_user_404(client, client_user, seller, auth_headers, make_notification):
    note = make_notification(client_user)
    assert client.delete(f'/notification/delete/{note.id}', headers=auth_headers(seller)).status_code == 404


def test_no_create_endpoint(client, client_user, auth_headers):
    response = client.post(
        '/notification/create',
        json={'user_id': client_user.id, 'notification_type': 'system', 'text': 'x'},
        headers=auth_headers(client_user),
    )
    assert response.status_code in (404, 405)


def test_notification_response_created_at_is_aware(client, client_user, auth_headers, make_notification):
    make_notification(client_user)
    item = client.get('/notification/list', headers=auth_headers(client_user)).json()[0]
    created_at = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
    assert created_at.tzinfo is not None
    assert created_at.astimezone(timezone.utc).utcoffset().total_seconds() == 0


def test_notification_not_sent_to_actor_and_blocked(
    client, db, client_user, seller, make_user, auth_headers, make_notification
):
    blocked = make_user('blockedseller', UserRole.seller, is_active=False)
    response = client.post('/lead/create', json={'lead_type': 'question'}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert client.get('/notification/unread-count', headers=auth_headers(seller)).json() == {'count': 1}
    assert client.get('/notification/unread-count', headers=auth_headers(client_user)).json() == {'count': 0}
    assert client.get('/notification/unread-count', headers=auth_headers(blocked)).status_code in (401, 403)
    assert db.query(Notification).filter(Notification.user_id == blocked.id).count() == 0


def test_lead_taken_notification_visible_only_to_client(client, client_user, seller, auth_headers, make_lead):
    lead_db = make_lead()
    assert client.post(f'/lead/take/{lead_db.id}', headers=auth_headers(seller)).status_code == 200
    assert client.get('/notification/unread-count', headers=auth_headers(client_user)).json() == {'count': 1}
    assert client.get('/notification/unread-count', headers=auth_headers(seller)).json() == {'count': 0}
    assert lead_db.status == LeadStatus.in_progress
