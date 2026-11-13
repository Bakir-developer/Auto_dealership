from datetime import datetime, timezone

import pytest

from mysite.db.models import Brand, CarModel


def create(client, headers, brand_id, name):
    return client.post('/car-model/create', json={'brand_id': brand_id, 'model_name': name}, headers=headers)


def make_brand(db, name):
    brand_db = Brand(brand_name=name)
    db.add(brand_db)
    db.commit()
    return brand_db


def test_create_car_model_ok(client, admin, auth_headers, brand):
    response = create(client, auth_headers(admin), brand.id, '  Corolla ')
    assert response.status_code == 200
    assert response.json()['model_name'] == 'Corolla'
    assert response.json()['brand_id'] == brand.id


def test_create_car_model_unknown_brand_404(client, admin, auth_headers):
    assert create(client, auth_headers(admin), 9999, 'X').status_code == 404


@pytest.mark.parametrize('name', ['Camry', 'camry', 'CAMRY'])
def test_create_car_model_duplicate_409(client, admin, auth_headers, brand, car_model, name):
    assert create(client, auth_headers(admin), brand.id, name).status_code == 409


def test_create_car_model_duplicate_cyrillic_409(client, admin, auth_headers, db):
    brand_db = make_brand(db, 'Лада')
    headers = auth_headers(admin)
    assert create(client, headers, brand_db.id, 'Веста').status_code == 200
    assert create(client, headers, brand_db.id, 'веста').status_code == 409


def test_same_model_name_other_brand_ok(client, admin, auth_headers, car_model, db):
    other = make_brand(db, 'Honda')
    assert create(client, auth_headers(admin), other.id, 'Camry').status_code == 200


def test_create_car_model_blank_name_422(client, admin, auth_headers, brand):
    assert create(client, auth_headers(admin), brand.id, '   ').status_code == 422


@pytest.mark.parametrize('fixture_name', ['seller', 'client_user'])
def test_create_car_model_non_admin_403(client, auth_headers, brand, request, fixture_name):
    user = request.getfixturevalue(fixture_name)
    assert create(client, auth_headers(user), brand.id, 'X').status_code == 403


def test_create_car_model_without_token_401(client, brand):
    response = client.post('/car-model/create', json={'brand_id': brand.id, 'model_name': 'X'})
    assert response.status_code == 401


def test_list_car_model_public_ok(client, car_model):
    response = client.get('/car-model/list')
    assert response.status_code == 200
    assert [item['model_name'] for item in response.json()] == ['Camry']


def test_list_car_model_filter_brand_id(client, car_model, db):
    other = make_brand(db, 'Honda')
    db.add(CarModel(brand_id=other.id, model_name='Civic'))
    db.commit()
    response = client.get('/car-model/list', params={'brand_id': other.id})
    assert [item['model_name'] for item in response.json()] == ['Civic']
    response = client.get('/car-model/list', params={'brand_id': car_model.brand_id})
    assert [item['model_name'] for item in response.json()] == ['Camry']


def test_list_car_model_limit_over_100_422(client):
    assert client.get('/car-model/list', params={'limit': 101}).status_code == 422


def test_detail_car_model_ok(client, car_model):
    response = client.get('/car-model/detail', params={'car_model_id': car_model.id})
    assert response.status_code == 200
    assert response.json()['model_name'] == 'Camry'


def test_detail_car_model_not_found_404(client):
    assert client.get('/car-model/detail', params={'car_model_id': 9999}).status_code == 404


def test_update_car_model_name_ok(client, admin, auth_headers, car_model):
    response = client.put(
        f'/car-model/update/{car_model.id}', json={'model_name': 'Avalon'}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert response.json()['model_name'] == 'Avalon'


def test_update_car_model_duplicate_409(client, admin, auth_headers, car_model, db):
    db.add(CarModel(brand_id=car_model.brand_id, model_name='Corolla'))
    db.commit()
    response = client.put(
        f'/car-model/update/{car_model.id}', json={'model_name': 'corolla'}, headers=auth_headers(admin)
    )
    assert response.status_code == 409


def test_update_car_model_null_name_400(client, admin, auth_headers, car_model):
    response = client.put(f'/car-model/update/{car_model.id}', json={'model_name': None}, headers=auth_headers(admin))
    assert response.status_code == 400


def test_update_car_model_not_found_404(client, admin, auth_headers):
    response = client.put('/car-model/update/9999', json={'model_name': 'X'}, headers=auth_headers(admin))
    assert response.status_code == 404


def test_update_car_model_unknown_brand_404(client, admin, auth_headers, car_model):
    response = client.put(f'/car-model/update/{car_model.id}', json={'brand_id': 9999}, headers=auth_headers(admin))
    assert response.status_code == 404


def test_update_car_model_non_admin_403(client, seller, auth_headers, car_model):
    response = client.put(f'/car-model/update/{car_model.id}', json={'model_name': 'X'}, headers=auth_headers(seller))
    assert response.status_code == 403


def test_update_car_model_change_brand_with_cars_409(client, admin, auth_headers, car_model, make_car, db):
    make_car()
    other = make_brand(db, 'Honda')
    response = client.put(f'/car-model/update/{car_model.id}', json={'brand_id': other.id}, headers=auth_headers(admin))
    assert response.status_code == 409


def test_update_car_model_change_brand_without_cars_ok(client, admin, auth_headers, car_model, db):
    other = make_brand(db, 'Honda')
    response = client.put(f'/car-model/update/{car_model.id}', json={'brand_id': other.id}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['brand_id'] == other.id


def test_delete_car_model_ok(client, admin, auth_headers, car_model, db):
    response = client.delete(f'/car-model/delete/{car_model.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert db.query(CarModel).filter(CarModel.id == car_model.id).first() is None


def test_delete_car_model_with_cars_409(client, admin, auth_headers, car_model, make_car):
    make_car()
    assert client.delete(f'/car-model/delete/{car_model.id}', headers=auth_headers(admin)).status_code == 409


def test_delete_car_model_with_soft_deleted_car_409(client, admin, auth_headers, car_model, make_car):
    make_car(deleted_at=datetime.now(timezone.utc))
    assert client.delete(f'/car-model/delete/{car_model.id}', headers=auth_headers(admin)).status_code == 409


def test_delete_car_model_not_found_404(client, admin, auth_headers):
    assert client.delete('/car-model/delete/9999', headers=auth_headers(admin)).status_code == 404


def test_delete_car_model_non_admin_403(client, seller, auth_headers, car_model):
    assert client.delete(f'/car-model/delete/{car_model.id}', headers=auth_headers(seller)).status_code == 403


def test_delete_car_model_without_token_401(client, car_model):
    assert client.delete(f'/car-model/delete/{car_model.id}').status_code == 401
