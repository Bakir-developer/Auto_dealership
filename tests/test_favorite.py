from datetime import datetime, timezone

from mysite.db.models import CarStatus, Favorite


def add(client, headers, car_id, **extra):
    return client.post('/favorite/create', json={'car_id': car_id, **extra}, headers=headers)


# ---------- create ----------


def test_add_favorite_ok(client, client_user, auth_headers, make_car, db):
    car = make_car()
    response = add(client, auth_headers(client_user), car.id)
    assert response.status_code == 200
    body = response.json()
    assert body['user_id'] == client_user.id
    assert body['car_id'] == car.id
    assert body['car']['id'] == car.id
    assert db.query(Favorite).count() == 1


def test_add_favorite_reserved_car_ok(client, client_user, auth_headers, make_car):
    car = make_car(status=CarStatus.reserved)
    assert add(client, auth_headers(client_user), car.id).status_code == 200


def test_add_favorite_duplicate_409(client, client_user, auth_headers, make_car, make_favorite, db):
    car = make_car()
    make_favorite(client_user, car)
    assert add(client, auth_headers(client_user), car.id).status_code == 409
    assert db.query(Favorite).count() == 1


def test_add_favorite_sold_car_404(client, client_user, auth_headers, make_car):
    assert add(client, auth_headers(client_user), make_car(status=CarStatus.sold).id).status_code == 404


def test_add_favorite_withdrawn_car_404(client, client_user, auth_headers, make_car):
    assert add(client, auth_headers(client_user), make_car(status=CarStatus.withdrawn).id).status_code == 404


def test_add_favorite_deleted_car_404(client, client_user, auth_headers, make_car):
    car = make_car(deleted_at=datetime.now(timezone.utc))
    assert add(client, auth_headers(client_user), car.id).status_code == 404


def test_add_favorite_unknown_car_404(client, client_user, auth_headers):
    assert add(client, auth_headers(client_user), 9999).status_code == 404


def test_add_favorite_as_seller_403(client, seller, auth_headers, make_car):
    assert add(client, auth_headers(seller), make_car().id).status_code == 403


def test_add_favorite_as_admin_403(client, admin, auth_headers, make_car):
    assert add(client, auth_headers(admin), make_car().id).status_code == 403


def test_add_favorite_without_token_401(client, make_car):
    assert add(client, {}, make_car().id).status_code == 401


def test_add_favorite_missing_car_id_422(client, client_user, auth_headers):
    assert client.post('/favorite/create', json={}, headers=auth_headers(client_user)).status_code == 422


def test_add_favorite_ignores_user_id(client, client_user, client2, auth_headers, make_car, db):
    car = make_car()
    response = add(client, auth_headers(client_user), car.id, user_id=client2.id)
    assert response.status_code == 200
    assert response.json()['user_id'] == client_user.id
    assert db.query(Favorite).filter(Favorite.user_id == client2.id).count() == 0


# ---------- list ----------


def test_list_favorite_only_own(client, client_user, client2, auth_headers, make_car, make_favorite):
    own_car = make_car()
    make_favorite(client_user, own_car)
    make_favorite(client2, make_car())
    response = client.get('/favorite/list', headers=auth_headers(client_user))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]['car_id'] == own_car.id
    assert body[0]['car']['id'] == own_car.id


def test_list_favorite_ordered_newest_first(client, client_user, auth_headers, make_car, make_favorite):
    first = make_favorite(client_user, make_car())
    second = make_favorite(client_user, make_car())
    response = client.get('/favorite/list', headers=auth_headers(client_user))
    assert [item['id'] for item in response.json()] == [second.id, first.id]


def test_list_favorite_hides_sold_and_deleted(client, client_user, auth_headers, make_car, make_favorite):
    visible = make_favorite(client_user, make_car())
    make_favorite(client_user, make_car(status=CarStatus.sold))
    make_favorite(client_user, make_car(status=CarStatus.withdrawn))
    make_favorite(client_user, make_car(deleted_at=datetime.now(timezone.utc)))
    response = client.get('/favorite/list', headers=auth_headers(client_user))
    assert [item['id'] for item in response.json()] == [visible.id]


def test_list_favorite_pagination(client, client_user, auth_headers, make_car, make_favorite):
    for _ in range(3):
        make_favorite(client_user, make_car())
    response = client.get('/favorite/list', params={'skip': 1, 'limit': 1}, headers=auth_headers(client_user))
    assert len(response.json()) == 1
    assert client.get('/favorite/list', params={'limit': 101}, headers=auth_headers(client_user)).status_code == 422


def test_list_favorite_as_seller_403(client, seller, auth_headers):
    assert client.get('/favorite/list', headers=auth_headers(seller)).status_code == 403


def test_list_favorite_without_token_401(client):
    assert client.get('/favorite/list').status_code == 401


# ---------- detail / delete ----------


def test_detail_favorite_ok(client, client_user, auth_headers, make_car, make_favorite):
    favorite = make_favorite(client_user, make_car())
    response = client.get('/favorite/detail', params={'favorite_id': favorite.id}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['id'] == favorite.id


def test_detail_favorite_other_user_404(client, client_user, client2, auth_headers, make_car, make_favorite):
    favorite = make_favorite(client_user, make_car())
    response = client.get('/favorite/detail', params={'favorite_id': favorite.id}, headers=auth_headers(client2))
    assert response.status_code == 404


def test_detail_favorite_sold_car_404(client, client_user, auth_headers, make_car, make_favorite):
    favorite = make_favorite(client_user, make_car(status=CarStatus.sold))
    response = client.get('/favorite/detail', params={'favorite_id': favorite.id}, headers=auth_headers(client_user))
    assert response.status_code == 404


def test_delete_favorite_ok(client, client_user, auth_headers, make_car, make_favorite, db):
    favorite = make_favorite(client_user, make_car())
    response = client.delete(f'/favorite/delete/{favorite.id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json() == {'message': 'Автомобиль удалён из избранного'}
    assert db.query(Favorite).count() == 0


def test_delete_favorite_other_user_404(client, client_user, client2, auth_headers, make_car, make_favorite, db):
    favorite = make_favorite(client_user, make_car())
    assert client.delete(f'/favorite/delete/{favorite.id}', headers=auth_headers(client2)).status_code == 404
    assert db.query(Favorite).count() == 1


def test_delete_favorite_of_hidden_car_ok(client, client_user, auth_headers, make_car, make_favorite, db):
    favorite = make_favorite(client_user, make_car(status=CarStatus.sold))
    assert client.delete(f'/favorite/delete/{favorite.id}', headers=auth_headers(client_user)).status_code == 200
    assert db.query(Favorite).count() == 0


def test_delete_favorite_as_seller_403(client, seller, auth_headers, make_car, make_favorite, client_user):
    favorite = make_favorite(client_user, make_car())
    assert client.delete(f'/favorite/delete/{favorite.id}', headers=auth_headers(seller)).status_code == 403


def test_same_car_two_clients_ok(client, client_user, client2, auth_headers, make_car):
    car = make_car()
    assert add(client, auth_headers(client_user), car.id).status_code == 200
    assert add(client, auth_headers(client2), car.id).status_code == 200
