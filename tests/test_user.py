from datetime import time
from decimal import Decimal

import pytest

from mysite.db.models import RefreshToken, SalonSettings, UserProfile, UserRole

CREATE_DATA = {
    'username': 'newseller',
    'email': 'newseller@test.kg',
    'phone_number': '+996700555666',
    'password': 'password123',
}


@pytest.fixture
def salon_settings(db):
    settings_db = SalonSettings(
        id=1,
        salon_name='Auto Salon',
        address='г. Бишкек',
        phone_number='+996700000000',
        work_start=time(9, 0),
        work_end=time(18, 0),
        default_discount_limit=Decimal('3'),
    )
    db.add(settings_db)
    db.commit()
    return settings_db


def login(client, username):
    return client.post('/auth/login', json={'username': username, 'password': 'pass12345'})


def set_limit(client, headers, user_id, value):
    return client.put(f'/user/discount-limit/{user_id}', headers=headers, json={'discount_limit': value})


# ---------- profile ----------


@pytest.mark.parametrize('fixture_name', ['admin', 'seller', 'client_user'])
def test_profile_ok_each_role(client, auth_headers, request, fixture_name):
    user_db = request.getfixturevalue(fixture_name)
    response = client.get('/user/profile', headers=auth_headers(user_db))
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == user_db.id
    assert data['username'] == user_db.username
    assert data['role'] == user_db.role.value
    assert 'password' not in data


def test_profile_update_ok(client, auth_headers, client_user):
    response = client.put(
        '/user/profile',
        headers=auth_headers(client_user),
        json={'first_name': 'Иван', 'last_name': 'Иванов', 'phone_number': '+996555123456'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['first_name'] == 'Иван'
    assert data['last_name'] == 'Иванов'
    assert data['phone_number'] == '+996555123456'
    assert 'password' not in data


def test_profile_update_email_taken_409(client, auth_headers, client_user, seller):
    response = client.put('/user/profile', headers=auth_headers(client_user), json={'email': seller.email})
    assert response.status_code == 409


def test_profile_update_own_email_ok(client, auth_headers, client_user):
    response = client.put('/user/profile', headers=auth_headers(client_user), json={'email': client_user.email})
    assert response.status_code == 200


def test_profile_update_cannot_change_role_or_discount_limit(client, db, auth_headers, client_user):
    response = client.put(
        '/user/profile',
        headers=auth_headers(client_user),
        json={
            'first_name': 'Иван',
            'role': 'admin',
            'discount_limit': '50',
            'is_active': False,
            'username': 'hacker',
            'password': 'newpassword123',
        },
    )
    assert response.status_code == 200
    db.expire_all()
    user_db = db.get(UserProfile, client_user.id)
    assert user_db.role == UserRole.client
    assert user_db.discount_limit == 0
    assert user_db.is_active is True
    assert user_db.username == 'client1'
    assert user_db.first_name == 'Иван'


def test_profile_update_null_email_400(client, auth_headers, client_user):
    response = client.put('/user/profile', headers=auth_headers(client_user), json={'email': None})
    assert response.status_code == 400


def test_profile_update_invalid_phone_422(client, auth_headers, client_user):
    response = client.put('/user/profile', headers=auth_headers(client_user), json={'phone_number': '123'})
    assert response.status_code == 422


def test_profile_update_without_token_401(client):
    assert client.put('/user/profile', json={'first_name': 'X'}).status_code == 401


# ---------- create seller ----------


def test_create_seller_as_admin_ok(client, auth_headers, admin, salon_settings):
    response = client.post('/user/create', headers=auth_headers(admin), json=CREATE_DATA)
    assert response.status_code == 200
    data = response.json()
    assert data['role'] == 'seller'
    assert Decimal(str(data['discount_limit'])) == salon_settings.default_discount_limit
    assert data['is_active'] is True
    assert 'password' not in data


def test_create_seller_without_salon_settings_limit_zero(client, auth_headers, admin):
    response = client.post('/user/create', headers=auth_headers(admin), json=CREATE_DATA)
    assert response.status_code == 200
    assert Decimal(str(response.json()['discount_limit'])) == 0


def test_create_seller_explicit_discount_limit(client, auth_headers, admin, salon_settings):
    response = client.post('/user/create', headers=auth_headers(admin), json={**CREATE_DATA, 'discount_limit': '7.5'})
    assert response.status_code == 200
    assert Decimal(str(response.json()['discount_limit'])) == Decimal('7.5')


def test_create_seller_ignores_role_in_body(client, auth_headers, admin):
    response = client.post('/user/create', headers=auth_headers(admin), json={**CREATE_DATA, 'role': 'admin'})
    assert response.status_code == 200
    assert response.json()['role'] == 'seller'


def test_create_seller_password_is_hashed(client, db, auth_headers, admin):
    client.post('/user/create', headers=auth_headers(admin), json=CREATE_DATA)
    user_db = db.query(UserProfile).filter(UserProfile.username == 'newseller').one()
    assert user_db.password != CREATE_DATA['password']
    assert user_db.password.startswith('$2')


def test_create_seller_as_seller_403(client, auth_headers, seller):
    assert client.post('/user/create', headers=auth_headers(seller), json=CREATE_DATA).status_code == 403


def test_create_seller_as_client_403(client, auth_headers, client_user):
    assert client.post('/user/create', headers=auth_headers(client_user), json=CREATE_DATA).status_code == 403


def test_create_seller_without_token_401(client):
    assert client.post('/user/create', json=CREATE_DATA).status_code == 401


def test_create_seller_duplicate_username_409(client, auth_headers, admin, seller):
    data = {**CREATE_DATA, 'username': seller.username}
    assert client.post('/user/create', headers=auth_headers(admin), json=data).status_code == 409


def test_create_seller_duplicate_email_409(client, auth_headers, admin, seller):
    data = {**CREATE_DATA, 'email': seller.email}
    assert client.post('/user/create', headers=auth_headers(admin), json=data).status_code == 409


def test_create_seller_invalid_data_422(client, auth_headers, admin):
    data = {**CREATE_DATA, 'phone_number': 'abc'}
    assert client.post('/user/create', headers=auth_headers(admin), json=data).status_code == 422


# ---------- list / detail ----------


def test_list_users_as_admin_ok(client, auth_headers, admin, seller, client_user):
    response = client.get('/user/list', headers=auth_headers(admin))
    assert response.status_code == 200
    data = response.json()
    assert [item['id'] for item in data] == sorted(item['id'] for item in data)
    assert {item['username'] for item in data} == {'admin', 'seller', 'client1'}
    assert all('password' not in item for item in data)


def test_list_users_filter_role(client, auth_headers, admin, seller, client_user):
    response = client.get('/user/list', headers=auth_headers(admin), params={'role': 'seller'})
    assert response.status_code == 200
    assert [item['username'] for item in response.json()] == ['seller']


def test_list_users_filter_is_active(client, auth_headers, admin, make_user):
    make_user('blocked', is_active=False)
    response = client.get('/user/list', headers=auth_headers(admin), params={'is_active': False})
    assert [item['username'] for item in response.json()] == ['blocked']


def test_list_users_pagination(client, auth_headers, admin, seller, client_user):
    first = client.get('/user/list', headers=auth_headers(admin), params={'limit': 2}).json()
    second = client.get('/user/list', headers=auth_headers(admin), params={'skip': 2, 'limit': 2}).json()
    assert len(first) == 2
    assert len(second) == 1
    assert second[0]['id'] > first[-1]['id']


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': 101}, {'skip': -1}])
def test_list_users_invalid_pagination_422(client, auth_headers, admin, params):
    assert client.get('/user/list', headers=auth_headers(admin), params=params).status_code == 422


def test_list_users_as_client_403(client, auth_headers, client_user):
    assert client.get('/user/list', headers=auth_headers(client_user)).status_code == 403


def test_list_users_as_seller_403(client, auth_headers, seller):
    assert client.get('/user/list', headers=auth_headers(seller)).status_code == 403


def test_list_users_without_token_401(client):
    assert client.get('/user/list').status_code == 401


def test_detail_user_as_admin_ok(client, auth_headers, admin, seller):
    response = client.get('/user/detail', headers=auth_headers(admin), params={'user_id': seller.id})
    assert response.status_code == 200
    assert response.json()['id'] == seller.id
    assert 'password' not in response.json()


def test_detail_user_not_found_404(client, auth_headers, admin):
    assert client.get('/user/detail', headers=auth_headers(admin), params={'user_id': 99999}).status_code == 404


def test_detail_user_as_seller_403(client, auth_headers, seller, client_user):
    response = client.get('/user/detail', headers=auth_headers(seller), params={'user_id': client_user.id})
    assert response.status_code == 403


def test_detail_user_as_client_403(client, auth_headers, seller, client_user):
    response = client.get('/user/detail', headers=auth_headers(client_user), params={'user_id': seller.id})
    assert response.status_code == 403


# ---------- block / unblock ----------


def test_block_seller_ok(client, db, auth_headers, admin, seller):
    tokens = login(client, seller.username).json()
    access_headers = {'Authorization': f'Bearer {tokens["access_token"]}'}
    assert client.get('/user/profile', headers=access_headers).status_code == 200

    response = client.post(f'/user/block/{seller.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['is_active'] is False
    assert db.query(RefreshToken).filter(RefreshToken.user_id == seller.id).count() == 0
    assert client.get('/user/profile', headers=access_headers).status_code == 401
    assert login(client, seller.username).status_code == 403
    refresh_response = client.post('/auth/access_generate', json={'refresh_token': tokens['refresh_token']})
    assert refresh_response.status_code == 401


def test_block_does_not_touch_other_users_tokens(client, db, auth_headers, admin, seller, client_user):
    login(client, seller.username)
    login(client, client_user.username)
    client.post(f'/user/block/{seller.id}', headers=auth_headers(admin))
    assert db.query(RefreshToken).filter(RefreshToken.user_id == client_user.id).count() == 1


def test_block_self_400(client, auth_headers, admin):
    assert client.post(f'/user/block/{admin.id}', headers=auth_headers(admin)).status_code == 400


def test_block_admin_403(client, auth_headers, admin, make_user):
    other_admin = make_user('admin2', UserRole.admin)
    assert client.post(f'/user/block/{other_admin.id}', headers=auth_headers(admin)).status_code == 403


def test_block_already_blocked_409(client, auth_headers, admin, make_user):
    blocked = make_user('blocked', UserRole.seller, is_active=False)
    assert client.post(f'/user/block/{blocked.id}', headers=auth_headers(admin)).status_code == 409


def test_block_not_found_404(client, auth_headers, admin):
    assert client.post('/user/block/99999', headers=auth_headers(admin)).status_code == 404


def test_block_as_seller_403(client, auth_headers, seller, client_user):
    assert client.post(f'/user/block/{client_user.id}', headers=auth_headers(seller)).status_code == 403


def test_block_as_client_403(client, auth_headers, seller, client_user):
    assert client.post(f'/user/block/{seller.id}', headers=auth_headers(client_user)).status_code == 403


def test_block_without_token_401(client, seller):
    assert client.post(f'/user/block/{seller.id}').status_code == 401


def test_unblock_ok(client, auth_headers, admin, make_user):
    blocked = make_user('blocked', UserRole.seller, is_active=False)
    response = client.post(f'/user/unblock/{blocked.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['is_active'] is True
    assert login(client, 'blocked').status_code == 200


def test_unblock_not_blocked_409(client, auth_headers, admin, seller):
    assert client.post(f'/user/unblock/{seller.id}', headers=auth_headers(admin)).status_code == 409


def test_unblock_not_found_404(client, auth_headers, admin):
    assert client.post('/user/unblock/99999', headers=auth_headers(admin)).status_code == 404


def test_unblock_as_seller_403(client, auth_headers, seller, make_user):
    blocked = make_user('blocked', is_active=False)
    assert client.post(f'/user/unblock/{blocked.id}', headers=auth_headers(seller)).status_code == 403


# ---------- discount-limit ----------


def test_discount_limit_ok(client, auth_headers, admin, seller):
    response = set_limit(client, auth_headers(admin), seller.id, '10.5')
    assert response.status_code == 200
    assert Decimal(str(response.json()['discount_limit'])) == Decimal('10.5')


@pytest.mark.parametrize('value', ['0', '100'])
def test_discount_limit_boundaries_ok(client, auth_headers, admin, seller, value):
    assert set_limit(client, auth_headers(admin), seller.id, value).status_code == 200


@pytest.mark.parametrize('value', ['101', '-1'])
def test_discount_limit_out_of_range_422(client, auth_headers, admin, seller, value):
    assert set_limit(client, auth_headers(admin), seller.id, value).status_code == 422


def test_discount_limit_for_client_400(client, auth_headers, admin, client_user):
    assert set_limit(client, auth_headers(admin), client_user.id, '5').status_code == 400


def test_discount_limit_for_admin_400(client, auth_headers, admin):
    assert set_limit(client, auth_headers(admin), admin.id, '5').status_code == 400


def test_discount_limit_not_found_404(client, auth_headers, admin):
    assert set_limit(client, auth_headers(admin), 99999, '5').status_code == 404


def test_discount_limit_as_seller_403(client, auth_headers, seller):
    assert set_limit(client, auth_headers(seller), seller.id, '5').status_code == 403


def test_discount_limit_as_client_403(client, auth_headers, seller, client_user):
    assert set_limit(client, auth_headers(client_user), seller.id, '5').status_code == 403


def test_discount_limit_without_token_401(client, seller):
    assert set_limit(client, {}, seller.id, '5').status_code == 401
