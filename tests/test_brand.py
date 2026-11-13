import pytest

from mysite.db.models import Brand


def create(client, headers, name):
    return client.post('/brand/create', json={'brand_name': name}, headers=headers)


def test_create_brand_as_admin_ok(client, admin, auth_headers):
    response = create(client, auth_headers(admin), 'Toyota')
    assert response.status_code == 200
    assert response.json()['brand_name'] == 'Toyota'
    assert 'password' not in response.text


@pytest.mark.parametrize('fixture_name', ['seller', 'client_user'])
def test_create_brand_non_admin_403(client, auth_headers, request, fixture_name):
    user = request.getfixturevalue(fixture_name)
    assert create(client, auth_headers(user), 'Toyota').status_code == 403


def test_create_brand_without_token_401(client):
    assert client.post('/brand/create', json={'brand_name': 'Toyota'}).status_code == 401


def test_create_brand_duplicate_409(client, admin, auth_headers):
    headers = auth_headers(admin)
    create(client, headers, 'Toyota')
    assert create(client, headers, 'Toyota').status_code == 409


@pytest.mark.parametrize('first, second', [('Toyota', 'toyota'), ('Лада', 'лада'), ('Лада', 'ЛАДА')])
def test_create_brand_duplicate_case_insensitive_409(client, admin, auth_headers, first, second):
    headers = auth_headers(admin)
    assert create(client, headers, first).status_code == 200
    assert create(client, headers, second).status_code == 409


def test_create_brand_strips_spaces(client, admin, auth_headers):
    response = create(client, auth_headers(admin), '  Honda  ')
    assert response.status_code == 200
    assert response.json()['brand_name'] == 'Honda'


def test_create_brand_duplicate_after_strip_409(client, admin, auth_headers):
    headers = auth_headers(admin)
    create(client, headers, 'Honda')
    assert create(client, headers, ' Honda ').status_code == 409


@pytest.mark.parametrize('name', ['', '   '])
def test_create_brand_blank_name_422(client, admin, auth_headers, name):
    assert create(client, auth_headers(admin), name).status_code == 422


def test_create_brand_too_long_422(client, admin, auth_headers):
    assert create(client, auth_headers(admin), 'a' * 51).status_code == 422


def test_list_brand_public_ok(client, brand):
    response = client.get('/brand/list')
    assert response.status_code == 200
    assert [item['brand_name'] for item in response.json()] == ['Toyota']


def test_list_brand_pagination(client, db):
    for name in ('Audi', 'BMW', 'Citroen'):
        db.add(Brand(brand_name=name))
    db.commit()
    response = client.get('/brand/list', params={'skip': 1, 'limit': 1})
    assert [item['brand_name'] for item in response.json()] == ['BMW']


def test_list_brand_limit_over_100_422(client):
    assert client.get('/brand/list', params={'limit': 101}).status_code == 422


def test_detail_brand_ok(client, brand):
    response = client.get('/brand/detail', params={'brand_id': brand.id})
    assert response.status_code == 200
    assert response.json()['id'] == brand.id


def test_detail_brand_not_found_404(client):
    assert client.get('/brand/detail', params={'brand_id': 9999}).status_code == 404


def test_update_brand_ok(client, admin, auth_headers, brand):
    response = client.put(f'/brand/update/{brand.id}', json={'brand_name': 'Lexus'}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['brand_name'] == 'Lexus'


def test_update_brand_same_name_other_case_ok(client, admin, auth_headers, brand):
    response = client.put(f'/brand/update/{brand.id}', json={'brand_name': 'TOYOTA'}, headers=auth_headers(admin))
    assert response.status_code == 200


def test_update_brand_duplicate_409(client, admin, auth_headers, brand, db):
    db.add(Brand(brand_name='Honda'))
    db.commit()
    response = client.put(f'/brand/update/{brand.id}', json={'brand_name': 'honda'}, headers=auth_headers(admin))
    assert response.status_code == 409


def test_update_brand_null_name_400(client, admin, auth_headers, brand):
    response = client.put(f'/brand/update/{brand.id}', json={'brand_name': None}, headers=auth_headers(admin))
    assert response.status_code == 400


def test_update_brand_not_found_404(client, admin, auth_headers):
    response = client.put('/brand/update/9999', json={'brand_name': 'X'}, headers=auth_headers(admin))
    assert response.status_code == 404


@pytest.mark.parametrize('fixture_name', ['seller', 'client_user'])
def test_update_brand_non_admin_403(client, auth_headers, brand, request, fixture_name):
    user = request.getfixturevalue(fixture_name)
    response = client.put(f'/brand/update/{brand.id}', json={'brand_name': 'X'}, headers=auth_headers(user))
    assert response.status_code == 403


def test_update_brand_without_token_401(client, brand):
    assert client.put(f'/brand/update/{brand.id}', json={'brand_name': 'X'}).status_code == 401


def test_delete_brand_ok(client, admin, auth_headers, brand, db):
    response = client.delete(f'/brand/delete/{brand.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert db.query(Brand).filter(Brand.id == brand.id).first() is None


def test_delete_brand_with_models_409(client, admin, auth_headers, car_model):
    response = client.delete(f'/brand/delete/{car_model.brand_id}', headers=auth_headers(admin))
    assert response.status_code == 409


def test_delete_brand_with_cars_409(client, admin, auth_headers, make_car, brand):
    make_car()
    assert client.delete(f'/brand/delete/{brand.id}', headers=auth_headers(admin)).status_code == 409


def test_delete_brand_not_found_404(client, admin, auth_headers):
    assert client.delete('/brand/delete/9999', headers=auth_headers(admin)).status_code == 404


@pytest.mark.parametrize('fixture_name', ['seller', 'client_user'])
def test_delete_brand_non_admin_403(client, auth_headers, brand, request, fixture_name):
    user = request.getfixturevalue(fixture_name)
    assert client.delete(f'/brand/delete/{brand.id}', headers=auth_headers(user)).status_code == 403


def test_delete_brand_without_token_401(client, brand):
    assert client.delete(f'/brand/delete/{brand.id}').status_code == 401
