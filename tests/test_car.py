from datetime import datetime, timezone
from decimal import Decimal

import pytest

from mysite.db.models import (
    BodyType,
    Brand,
    Car,
    CarCondition,
    CarImage,
    CarModel,
    CarStatus,
    Currency,
    DriveType,
    FuelType,
    PriceHistory,
    Transmission,
)

VIN = 'WVWZZZ1JZXW000001'


@pytest.fixture
def payload(brand, car_model):
    def _payload(**overrides):
        data = {
            'vin': VIN,
            'brand_id': brand.id,
            'car_model_id': car_model.id,
            'year': 2023,
            'body_type': 'sedan',
            'color': 'Black',
            'fuel_type': 'petrol',
            'transmission': 'automatic',
            'drive_type': 'front',
            'condition': 'new',
            'price': '1500000.00',
            'mileage': 0,
        }
        data.update(overrides)
        return data

    return _payload


def used_payload(payload, **overrides):
    data = payload(condition='used', mileage=50000, owners_count=2, has_accidents=False)
    data.update(overrides)
    return data


def ids(response):
    return [item['id'] for item in response.json()]


# ---------- create ----------


def test_create_car_new_as_seller_ok(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=payload(), headers=auth_headers(seller))
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'available'
    assert body['vin'] == VIN
    assert Decimal(body['price']) == Decimal('1500000.00')


def test_create_car_sets_created_by_seller(client, seller, auth_headers, payload, db):
    response = client.post('/car/create', json=payload(), headers=auth_headers(seller))
    assert db.get(Car, response.json()['id']).created_by_id == seller.id


def test_create_car_as_admin_ok(client, admin, auth_headers, payload):
    assert client.post('/car/create', json=payload(), headers=auth_headers(admin)).status_code == 200


def test_create_car_as_client_403(client, client_user, auth_headers, payload):
    assert client.post('/car/create', json=payload(), headers=auth_headers(client_user)).status_code == 403


def test_create_car_without_token_401(client, payload):
    assert client.post('/car/create', json=payload()).status_code == 401


def test_create_car_ignores_created_by_id(client, seller, admin, auth_headers, payload, db):
    response = client.post('/car/create', json=payload(created_by_id=admin.id, id=777), headers=auth_headers(seller))
    assert response.status_code == 200
    car_db = db.get(Car, response.json()['id'])
    assert car_db.created_by_id == seller.id
    assert car_db.id != 777


@pytest.mark.parametrize('car_status', ['reserved', 'sold'])
def test_create_car_manual_status_422(client, seller, auth_headers, payload, car_status):
    response = client.post('/car/create', json=payload(status=car_status), headers=auth_headers(seller))
    assert response.status_code == 422


@pytest.mark.parametrize('vin', ['WVWZZZ1JZXW00001', 'WVWZZZ1JZXW00000O', 'WVWZZZ1JZXW0000012'])
def test_create_car_invalid_vin_422(client, seller, auth_headers, payload, vin):
    assert client.post('/car/create', json=payload(vin=vin), headers=auth_headers(seller)).status_code == 422


def test_create_car_vin_lowercase_normalized(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=payload(vin=VIN.lower()), headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['vin'] == VIN


def test_create_car_duplicate_vin_409(client, seller, auth_headers, payload, make_car):
    make_car(vin=VIN)
    assert client.post('/car/create', json=payload(), headers=auth_headers(seller)).status_code == 409


def test_create_car_duplicate_vin_of_deleted_car_409(client, seller, auth_headers, payload, make_car):
    make_car(vin=VIN, deleted_at=datetime.now(timezone.utc))
    assert client.post('/car/create', json=payload(), headers=auth_headers(seller)).status_code == 409


def test_create_car_unknown_brand_404(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=payload(brand_id=9999), headers=auth_headers(seller))
    assert response.status_code == 404


def test_create_car_unknown_model_404(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=payload(car_model_id=9999), headers=auth_headers(seller))
    assert response.status_code == 404


def test_create_car_model_of_other_brand_400(client, seller, auth_headers, payload, db):
    other = Brand(brand_name='Honda')
    db.add(other)
    db.commit()
    response = client.post('/car/create', json=payload(brand_id=other.id), headers=auth_headers(seller))
    assert response.status_code == 400


@pytest.mark.parametrize('price', ['0', '-5'])
def test_create_car_non_positive_price_422(client, seller, auth_headers, payload, price):
    assert client.post('/car/create', json=payload(price=price), headers=auth_headers(seller)).status_code == 422


def test_create_car_price_three_decimals_422(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=payload(price='100.123'), headers=auth_headers(seller))
    assert response.status_code == 422


def test_create_car_future_year_400(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=payload(year=2100), headers=auth_headers(seller))
    assert response.status_code == 400


def test_create_car_next_year_ok(client, seller, auth_headers, payload):
    year = datetime.now(timezone.utc).year + 1
    response = client.post('/car/create', json=payload(year=year), headers=auth_headers(seller))
    assert response.status_code == 200


def test_create_car_invalid_enum_422(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=payload(drive_type='sideways'), headers=auth_headers(seller))
    assert response.status_code == 422


def test_create_car_blank_color_422(client, seller, auth_headers, payload):
    assert client.post('/car/create', json=payload(color='   '), headers=auth_headers(seller)).status_code == 422


def test_create_new_car_with_mileage_400(client, seller, auth_headers, payload):
    assert client.post('/car/create', json=payload(mileage=10), headers=auth_headers(seller)).status_code == 400


def test_create_new_car_with_owners_400(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=payload(owners_count=1), headers=auth_headers(seller))
    assert response.status_code == 400


def test_create_used_car_ok(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=used_payload(payload), headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['condition'] == 'used'


def test_create_used_car_without_owners_400(client, seller, auth_headers, payload):
    data = used_payload(payload)
    del data['owners_count']
    assert client.post('/car/create', json=data, headers=auth_headers(seller)).status_code == 400


def test_create_used_car_without_has_accidents_400(client, seller, auth_headers, payload):
    data = used_payload(payload)
    del data['has_accidents']
    assert client.post('/car/create', json=data, headers=auth_headers(seller)).status_code == 400


def test_create_used_car_zero_mileage_400(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=used_payload(payload, mileage=0), headers=auth_headers(seller))
    assert response.status_code == 400


def test_create_used_car_accident_without_notes_400(client, seller, auth_headers, payload):
    response = client.post('/car/create', json=used_payload(payload, has_accidents=True), headers=auth_headers(seller))
    assert response.status_code == 400


def test_create_used_car_accident_with_notes_ok(client, seller, auth_headers, payload):
    response = client.post(
        '/car/create',
        json=used_payload(payload, has_accidents=True, accident_notes='Bumper'),
        headers=auth_headers(seller),
    )
    assert response.status_code == 200


# ---------- list ----------


def test_list_car_public_ok(client, make_car):
    car_db = make_car()
    response = client.get('/car/list')
    assert response.status_code == 200
    assert ids(response) == [car_db.id]


def test_list_car_hides_deleted(client, make_car, seller, auth_headers):
    make_car(deleted_at=datetime.now(timezone.utc))
    assert client.get('/car/list').json() == []
    assert client.get('/car/list', headers=auth_headers(seller)).json() == []


def test_list_car_public_hides_sold_and_withdrawn(client, make_car):
    visible = [make_car(status=s).id for s in (CarStatus.available, CarStatus.in_transit, CarStatus.reserved)]
    make_car(status=CarStatus.sold)
    make_car(status=CarStatus.withdrawn)
    assert sorted(ids(client.get('/car/list'))) == sorted(visible)


def test_list_car_client_hides_sold(client, make_car, client_user, auth_headers):
    available = make_car()
    make_car(status=CarStatus.sold)
    make_car(status=CarStatus.withdrawn)
    assert ids(client.get('/car/list', headers=auth_headers(client_user))) == [available.id]


@pytest.mark.parametrize('role_fixture', ['seller', 'admin'])
def test_list_car_staff_sees_sold_and_withdrawn(client, make_car, auth_headers, request, role_fixture):
    user = request.getfixturevalue(role_fixture)
    make_car()
    make_car(status=CarStatus.sold)
    make_car(status=CarStatus.withdrawn)
    assert len(client.get('/car/list', headers=auth_headers(user)).json()) == 3


def test_list_car_public_status_sold_filter_empty(client, make_car):
    make_car(status=CarStatus.sold)
    response = client.get('/car/list', params={'status': 'sold'})
    assert response.status_code == 200
    assert response.json() == []


def test_list_car_staff_status_sold_filter(client, make_car, seller, auth_headers):
    make_car()
    sold = make_car(status=CarStatus.sold)
    response = client.get('/car/list', params={'status': 'sold'}, headers=auth_headers(seller))
    assert ids(response) == [sold.id]


def test_list_car_filter_brand_id(client, make_car, db, brand):
    other = Brand(brand_name='Honda')
    db.add(other)
    db.commit()
    other_model = CarModel(brand_id=other.id, model_name='Civic')
    db.add(other_model)
    db.commit()
    make_car()
    honda = make_car(brand_id=other.id, car_model_id=other_model.id)
    assert ids(client.get('/car/list', params={'brand_id': other.id})) == [honda.id]


def test_list_car_filter_car_model_id(client, make_car, db, brand):
    other_model = CarModel(brand_id=brand.id, model_name='Corolla')
    db.add(other_model)
    db.commit()
    make_car()
    corolla = make_car(car_model_id=other_model.id)
    assert ids(client.get('/car/list', params={'car_model_id': other_model.id})) == [corolla.id]


def test_list_car_filter_year_range(client, make_car):
    make_car(year=2010)
    middle = make_car(year=2015)
    make_car(year=2020)
    response = client.get('/car/list', params={'year_min': 2012, 'year_max': 2018})
    assert ids(response) == [middle.id]
    assert len(client.get('/car/list', params={'year_min': 2015}).json()) == 2
    assert len(client.get('/car/list', params={'year_max': 2015}).json()) == 2


def test_list_car_filter_price_range(client, make_car):
    make_car(price=Decimal('1000.00'))
    middle = make_car(price=Decimal('2000.00'))
    make_car(price=Decimal('3000.00'))
    response = client.get('/car/list', params={'price_min': '1500', 'price_max': '2500'})
    assert ids(response) == [middle.id]
    assert len(client.get('/car/list', params={'price_min': '2000'}).json()) == 2
    assert len(client.get('/car/list', params={'price_max': '2000'}).json()) == 2


@pytest.mark.parametrize(
    'param, value, overrides',
    [
        ('currency', 'USD', {'currency': Currency.USD}),
        ('condition', 'used', {'condition': CarCondition.used, 'mileage': 100, 'owners_count': 1}),
        ('body_type', 'suv', {'body_type': BodyType.suv}),
        ('fuel_type', 'diesel', {'fuel_type': FuelType.diesel}),
        ('transmission', 'manual', {'transmission': Transmission.manual}),
        ('drive_type', 'full', {'drive_type': DriveType.full}),
        ('status', 'in_transit', {'status': CarStatus.in_transit}),
    ],
)
def test_list_car_filter_enum(client, make_car, param, value, overrides):
    make_car()
    expected = make_car(**overrides)
    assert ids(client.get('/car/list', params={param: value})) == [expected.id]


def test_list_car_combined_filters(client, make_car):
    make_car(body_type=BodyType.suv, price=Decimal('1000.00'))
    make_car(body_type=BodyType.sedan, price=Decimal('1000.00'))
    expected = make_car(body_type=BodyType.suv, price=Decimal('5000.00'))
    response = client.get('/car/list', params={'body_type': 'suv', 'price_min': '2000'})
    assert ids(response) == [expected.id]


def test_list_car_invalid_year_range_400(client):
    assert client.get('/car/list', params={'year_min': 2020, 'year_max': 2010}).status_code == 400


def test_list_car_invalid_price_range_400(client):
    assert client.get('/car/list', params={'price_min': '200', 'price_max': '100'}).status_code == 400


def test_list_car_invalid_enum_422(client):
    assert client.get('/car/list', params={'body_type': 'spaceship'}).status_code == 422


def test_list_car_limit_zero_422(client):
    assert client.get('/car/list', params={'limit': 0}).status_code == 422


def test_list_car_limit_over_100_422(client):
    assert client.get('/car/list', params={'limit': 101}).status_code == 422


def test_list_car_pagination_newest_first(client, make_car):
    first = make_car()
    second = make_car()
    third = make_car()
    assert ids(client.get('/car/list')) == [third.id, second.id, first.id]
    assert ids(client.get('/car/list', params={'skip': 1, 'limit': 1})) == [second.id]


def test_list_car_with_invalid_token_401(client, make_car):
    make_car()
    response = client.get('/car/list', headers={'Authorization': 'Bearer garbage'})
    assert response.status_code == 401


# ---------- detail ----------


def test_detail_car_public_ok(client, make_car):
    car_db = make_car()
    response = client.get('/car/detail', params={'car_id': car_db.id})
    assert response.status_code == 200
    assert response.json()['id'] == car_db.id
    assert 'created_by_id' not in response.json()
    assert 'password' not in response.text


def test_detail_car_not_found_404(client):
    assert client.get('/car/detail', params={'car_id': 9999}).status_code == 404


def test_detail_car_deleted_404(client, make_car, admin, auth_headers):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    assert client.get('/car/detail', params={'car_id': car_db.id}).status_code == 404
    assert client.get('/car/detail', params={'car_id': car_db.id}, headers=auth_headers(admin)).status_code == 404


@pytest.mark.parametrize('car_status', [CarStatus.sold, CarStatus.withdrawn])
def test_detail_car_hidden_status_public_404(client, make_car, car_status):
    car_db = make_car(status=car_status)
    assert client.get('/car/detail', params={'car_id': car_db.id}).status_code == 404


def test_detail_car_sold_client_404(client, make_car, client_user, auth_headers):
    car_db = make_car(status=CarStatus.sold)
    response = client.get('/car/detail', params={'car_id': car_db.id}, headers=auth_headers(client_user))
    assert response.status_code == 404


def test_detail_car_sold_seller_ok(client, make_car, seller, auth_headers):
    car_db = make_car(status=CarStatus.sold)
    response = client.get('/car/detail', params={'car_id': car_db.id}, headers=auth_headers(seller))
    assert response.status_code == 200


def test_detail_car_invalid_token_401(client, make_car):
    car_db = make_car()
    response = client.get('/car/detail', params={'car_id': car_db.id}, headers={'Authorization': 'Bearer garbage'})
    assert response.status_code == 401


def test_detail_car_images_main_first(client, make_car, db):
    car_db = make_car()
    db.add_all(
        [
            CarImage(car_id=car_db.id, car_image='/media/car_images/a.jpg', is_main=False, position=0),
            CarImage(car_id=car_db.id, car_image='/media/car_images/b.jpg', is_main=True, position=5),
            CarImage(car_id=car_db.id, car_image='/media/car_images/c.jpg', is_main=False, position=1),
        ]
    )
    db.commit()
    images = client.get('/car/detail', params={'car_id': car_db.id}).json()['images']
    assert [image['car_image'][-5:] for image in images] == ['b.jpg', 'a.jpg', 'c.jpg']


# ---------- update ----------


def update(client, headers, car_id, **data):
    return client.put(f'/car/update/{car_id}', json=data, headers=headers)


def test_update_car_as_seller_ok(client, seller, auth_headers, make_car):
    car_db = make_car()
    response = update(client, auth_headers(seller), car_db.id, color='Red', description='Nice')
    assert response.status_code == 200
    assert response.json()['color'] == 'Red'
    assert response.json()['description'] == 'Nice'


def test_update_car_as_client_403(client, client_user, auth_headers, make_car):
    car_db = make_car()
    assert update(client, auth_headers(client_user), car_db.id, color='Red').status_code == 403


def test_update_car_without_token_401(client, make_car):
    car_db = make_car()
    assert client.put(f'/car/update/{car_db.id}', json={'color': 'Red'}).status_code == 401


def test_update_car_not_found_404(client, seller, auth_headers):
    assert update(client, auth_headers(seller), 9999, color='Red').status_code == 404


def test_update_car_deleted_404(client, seller, auth_headers, make_car):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    assert update(client, auth_headers(seller), car_db.id, color='Red').status_code == 404


def test_update_car_null_price_400(client, seller, auth_headers, make_car):
    car_db = make_car()
    assert update(client, auth_headers(seller), car_db.id, price=None).status_code == 400


def test_update_car_ignores_vin_and_condition(client, seller, auth_headers, make_car):
    car_db = make_car()
    old_vin = car_db.vin
    response = update(client, auth_headers(seller), car_db.id, vin='AAAAAAAAAAAAAAAAA', condition='used', color='Red')
    assert response.status_code == 200
    assert response.json()['vin'] == old_vin
    assert response.json()['condition'] == 'new'


def test_update_used_car_set_owners_null_400(client, seller, auth_headers, make_car):
    car_db = make_car(condition=CarCondition.used, mileage=1000, owners_count=1, has_accidents=False)
    assert update(client, auth_headers(seller), car_db.id, owners_count=None).status_code == 400


def test_update_used_car_set_accident_without_notes_400(client, seller, auth_headers, make_car):
    car_db = make_car(condition=CarCondition.used, mileage=1000, owners_count=1, has_accidents=False)
    assert update(client, auth_headers(seller), car_db.id, has_accidents=True).status_code == 400


def test_update_used_car_zero_mileage_400(client, seller, auth_headers, make_car):
    car_db = make_car(condition=CarCondition.used, mileage=1000, owners_count=1, has_accidents=False)
    assert update(client, auth_headers(seller), car_db.id, mileage=0).status_code == 400


def test_update_new_car_set_mileage_400(client, seller, auth_headers, make_car):
    car_db = make_car()
    assert update(client, auth_headers(seller), car_db.id, mileage=500).status_code == 400


def test_update_car_future_year_400(client, seller, auth_headers, make_car):
    car_db = make_car()
    assert update(client, auth_headers(seller), car_db.id, year=2100).status_code == 400


def test_update_car_status_withdrawn_ok(client, seller, auth_headers, make_car):
    car_db = make_car()
    response = update(client, auth_headers(seller), car_db.id, status='withdrawn')
    assert response.status_code == 200
    assert response.json()['status'] == 'withdrawn'


@pytest.mark.parametrize('car_status', ['sold', 'reserved'])
def test_update_car_manual_status_422(client, seller, auth_headers, make_car, car_status):
    car_db = make_car()
    assert update(client, auth_headers(seller), car_db.id, status=car_status).status_code == 422


def test_update_reserved_car_status_409(client, seller, auth_headers, make_car):
    car_db = make_car(status=CarStatus.reserved)
    assert update(client, auth_headers(seller), car_db.id, status='available').status_code == 409


def test_update_sold_car_409(client, seller, auth_headers, make_car):
    car_db = make_car(status=CarStatus.sold)
    assert update(client, auth_headers(seller), car_db.id, color='Red').status_code == 409


# ---------- price history ----------


def test_update_price_creates_price_history(client, seller, auth_headers, make_car, db):
    car_db = make_car(price=Decimal('1500000.00'))
    response = update(client, auth_headers(seller), car_db.id, price='1400000.50')
    assert response.status_code == 200
    assert Decimal(response.json()['price']) == Decimal('1400000.50')
    history = db.query(PriceHistory).filter(PriceHistory.car_id == car_db.id).all()
    assert len(history) == 1
    assert history[0].old_price == Decimal('1500000.00')
    assert history[0].new_price == Decimal('1400000.50')
    assert isinstance(history[0].new_price, Decimal)
    assert history[0].changed_by_id == seller.id


def test_update_same_price_no_history(client, seller, auth_headers, make_car, db):
    car_db = make_car(price=Decimal('1234567.89'))
    response = update(client, auth_headers(seller), car_db.id, price='1234567.89')
    assert response.status_code == 200
    assert db.query(PriceHistory).filter(PriceHistory.car_id == car_db.id).count() == 0


def test_update_other_fields_no_history(client, seller, auth_headers, make_car, db):
    car_db = make_car()
    update(client, auth_headers(seller), car_db.id, color='Red')
    assert db.query(PriceHistory).filter(PriceHistory.car_id == car_db.id).count() == 0


def test_price_history_two_changes_order(client, seller, admin, auth_headers, make_car):
    car_db = make_car(price=Decimal('100.00'))
    update(client, auth_headers(seller), car_db.id, price='200.00')
    update(client, auth_headers(admin), car_db.id, price='300.00')
    response = client.get(f'/car/price-history/{car_db.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    body = response.json()
    assert [(Decimal(i['old_price']), Decimal(i['new_price'])) for i in body] == [
        (Decimal('200.00'), Decimal('300.00')),
        (Decimal('100.00'), Decimal('200.00')),
    ]


def test_price_history_as_admin_ok(client, admin, auth_headers, make_car):
    car_db = make_car()
    response = client.get(f'/car/price-history/{car_db.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json() == []


def test_price_history_as_client_403(client, client_user, auth_headers, make_car):
    car_db = make_car()
    assert client.get(f'/car/price-history/{car_db.id}', headers=auth_headers(client_user)).status_code == 403


def test_price_history_without_token_401(client, make_car):
    car_db = make_car()
    assert client.get(f'/car/price-history/{car_db.id}').status_code == 401


def test_price_history_deleted_car_404(client, seller, auth_headers, make_car):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    assert client.get(f'/car/price-history/{car_db.id}', headers=auth_headers(seller)).status_code == 404


def test_price_history_unknown_car_404(client, seller, auth_headers):
    assert client.get('/car/price-history/9999', headers=auth_headers(seller)).status_code == 404


# ---------- delete ----------


def test_delete_car_as_admin_soft(client, admin, auth_headers, make_car, db):
    car_db = make_car()
    response = client.delete(f'/car/delete/{car_db.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    db.refresh(car_db)
    assert car_db.deleted_at is not None
    assert client.get('/car/detail', params={'car_id': car_db.id}).status_code == 404
    assert client.get('/car/list').json() == []


def test_delete_car_as_seller_403(client, seller, auth_headers, make_car):
    car_db = make_car()
    assert client.delete(f'/car/delete/{car_db.id}', headers=auth_headers(seller)).status_code == 403


def test_delete_car_as_client_403(client, client_user, auth_headers, make_car):
    car_db = make_car()
    assert client.delete(f'/car/delete/{car_db.id}', headers=auth_headers(client_user)).status_code == 403


def test_delete_car_without_token_401(client, make_car):
    car_db = make_car()
    assert client.delete(f'/car/delete/{car_db.id}').status_code == 401


def test_delete_car_twice_404(client, admin, auth_headers, make_car):
    car_db = make_car()
    client.delete(f'/car/delete/{car_db.id}', headers=auth_headers(admin))
    assert client.delete(f'/car/delete/{car_db.id}', headers=auth_headers(admin)).status_code == 404


def test_delete_reserved_car_409(client, admin, auth_headers, make_car):
    car_db = make_car(status=CarStatus.reserved)
    assert client.delete(f'/car/delete/{car_db.id}', headers=auth_headers(admin)).status_code == 409
