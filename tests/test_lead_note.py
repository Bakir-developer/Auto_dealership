import pytest

from mysite.db.models import LeadNote, LeadStatus, UserRole


@pytest.fixture
def own_lead(seller, make_lead):
    return make_lead(seller_id=seller.id, status=LeadStatus.in_progress)


@pytest.fixture
def make_note(db):
    def _make_note(lead, author, note='заметка'):
        note_db = LeadNote(lead_id=lead.id, seller_id=author.id, note=note)
        db.add(note_db)
        db.commit()
        db.refresh(note_db)
        return note_db

    return _make_note


def test_create_note_own_lead_ok(client, seller, own_lead, auth_headers):
    response = client.post(
        '/lead-note/create', json={'lead_id': own_lead.id, 'note': 'Перезвонить'}, headers=auth_headers(seller)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['seller_id'] == seller.id
    assert data['note'] == 'Перезвонить'


def test_create_note_ignores_seller_id(client, seller, admin, own_lead, auth_headers):
    response = client.post(
        '/lead-note/create',
        json={'lead_id': own_lead.id, 'note': 'x', 'seller_id': admin.id},
        headers=auth_headers(seller),
    )
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller.id


def test_create_note_other_seller_lead_404(client, make_user, make_lead, auth_headers):
    seller1 = make_user('s1', UserRole.seller)
    seller2 = make_user('s2', UserRole.seller)
    lead_db = make_lead(seller_id=seller1.id, status=LeadStatus.in_progress)
    response = client.post(
        '/lead-note/create', json={'lead_id': lead_db.id, 'note': 'x'}, headers=auth_headers(seller2)
    )
    assert response.status_code == 404


def test_create_note_free_lead_404(client, seller, make_lead, auth_headers):
    lead_db = make_lead()
    response = client.post('/lead-note/create', json={'lead_id': lead_db.id, 'note': 'x'}, headers=auth_headers(seller))
    assert response.status_code == 404


def test_create_note_as_client_403(client, client_user, own_lead, auth_headers):
    response = client.post(
        '/lead-note/create', json={'lead_id': own_lead.id, 'note': 'x'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 403


def test_create_note_without_token_401(client, own_lead):
    assert client.post('/lead-note/create', json={'lead_id': own_lead.id, 'note': 'x'}).status_code == 401


@pytest.mark.parametrize('note', ['', '   ', 'a' * 5001])
def test_create_note_invalid_422(client, seller, own_lead, auth_headers, note):
    response = client.post(
        '/lead-note/create', json={'lead_id': own_lead.id, 'note': note}, headers=auth_headers(seller)
    )
    assert response.status_code == 422


def test_create_note_admin_ok(client, admin, own_lead, auth_headers):
    response = client.post(
        '/lead-note/create', json={'lead_id': own_lead.id, 'note': 'от админа'}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert response.json()['seller_id'] == admin.id


def test_create_note_closed_lead_ok(client, seller, make_lead, auth_headers):
    lead_db = make_lead(seller_id=seller.id, status=LeadStatus.closed)
    response = client.post(
        '/lead-note/create', json={'lead_id': lead_db.id, 'note': 'итог'}, headers=auth_headers(seller)
    )
    assert response.status_code == 200


def test_create_note_unknown_lead_404(client, admin, auth_headers):
    response = client.post('/lead-note/create', json={'lead_id': 9999, 'note': 'x'}, headers=auth_headers(admin))
    assert response.status_code == 404


def test_list_notes_own_lead_ok(client, seller, own_lead, make_note, auth_headers):
    first = make_note(own_lead, seller, 'первая')
    second = make_note(own_lead, seller, 'вторая')
    response = client.get('/lead-note/list', params={'lead_id': own_lead.id}, headers=auth_headers(seller))
    assert response.status_code == 200
    assert [item['id'] for item in response.json()] == [first.id, second.id]


def test_list_notes_other_lead_404(client, make_user, own_lead, auth_headers):
    seller2 = make_user('s2', UserRole.seller)
    response = client.get('/lead-note/list', params={'lead_id': own_lead.id}, headers=auth_headers(seller2))
    assert response.status_code == 404


def test_list_notes_as_client_403(client, client_user, own_lead, auth_headers):
    response = client.get('/lead-note/list', params={'lead_id': own_lead.id}, headers=auth_headers(client_user))
    assert response.status_code == 403


def test_list_notes_admin_ok(client, admin, seller, own_lead, make_note, auth_headers):
    make_note(own_lead, seller)
    response = client.get('/lead-note/list', params={'lead_id': own_lead.id}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_detail_note_ok_and_other_seller_404(client, seller, make_user, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, seller)
    ok = client.get('/lead-note/detail', params={'lead_note_id': note_db.id}, headers=auth_headers(seller))
    assert ok.status_code == 200
    seller2 = make_user('s2', UserRole.seller)
    denied = client.get('/lead-note/detail', params={'lead_note_id': note_db.id}, headers=auth_headers(seller2))
    assert denied.status_code == 404


def test_update_note_author_ok(client, seller, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, seller)
    response = client.put(f'/lead-note/update/{note_db.id}', json={'note': 'новая'}, headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['note'] == 'новая'


def test_update_note_not_author_403(client, seller, admin, own_lead, make_note, auth_headers):
    admin_note = make_note(own_lead, admin)
    response = client.put(f'/lead-note/update/{admin_note.id}', json={'note': 'x'}, headers=auth_headers(seller))
    assert response.status_code == 403


def test_update_note_admin_can_edit_any(client, admin, seller, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, seller)
    response = client.put(f'/lead-note/update/{note_db.id}', json={'note': 'правка'}, headers=auth_headers(admin))
    assert response.status_code == 200


def test_update_note_null_400(client, seller, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, seller)
    response = client.put(f'/lead-note/update/{note_db.id}', json={'note': None}, headers=auth_headers(seller))
    assert response.status_code == 400


def test_update_note_blank_422(client, seller, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, seller)
    response = client.put(f'/lead-note/update/{note_db.id}', json={'note': '  '}, headers=auth_headers(seller))
    assert response.status_code == 422


def test_update_note_as_client_403(client, client_user, seller, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, seller)
    response = client.put(f'/lead-note/update/{note_db.id}', json={'note': 'x'}, headers=auth_headers(client_user))
    assert response.status_code == 403


def test_delete_note_author_ok(client, db, seller, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, seller)
    note_id = note_db.id
    assert client.delete(f'/lead-note/delete/{note_id}', headers=auth_headers(seller)).status_code == 200
    db.expire_all()
    assert db.get(LeadNote, note_id) is None


def test_delete_note_admin_ok(client, admin, seller, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, seller)
    assert client.delete(f'/lead-note/delete/{note_db.id}', headers=auth_headers(admin)).status_code == 200


def test_delete_note_not_author_403(client, seller, admin, own_lead, make_note, auth_headers):
    note_db = make_note(own_lead, admin)
    assert client.delete(f'/lead-note/delete/{note_db.id}', headers=auth_headers(seller)).status_code == 403


def test_old_seller_loses_access_after_reassign(client, admin, seller, make_user, own_lead, make_note, auth_headers):
    seller2 = make_user('seller2', UserRole.seller)
    note_db = make_note(own_lead, seller)
    response = client.post(f'/lead/assign/{own_lead.id}', json={'seller_id': seller2.id}, headers=auth_headers(admin))
    assert response.status_code == 200
    params = {'lead_id': own_lead.id}
    assert client.get('/lead-note/list', params=params, headers=auth_headers(seller)).status_code == 404
    assert client.get('/lead-note/list', params=params, headers=auth_headers(seller2)).status_code == 200
    update = client.put(f'/lead-note/update/{note_db.id}', json={'note': 'x'}, headers=auth_headers(seller))
    assert update.status_code == 404
    new_seller_edit = client.put(f'/lead-note/update/{note_db.id}', json={'note': 'x'}, headers=auth_headers(seller2))
    assert new_seller_edit.status_code == 403


def test_lead_detail_has_no_notes(client, client_user, seller, own_lead, make_note, auth_headers):
    make_note(own_lead, seller, 'секретная заметка')
    detail = client.get('/lead/detail', params={'lead_id': own_lead.id}, headers=auth_headers(client_user))
    assert detail.status_code == 200
    assert 'секретная заметка' not in detail.text
    assert 'notes' not in detail.json()
    listing = client.get('/lead/list', headers=auth_headers(client_user))
    assert 'секретная заметка' not in listing.text
