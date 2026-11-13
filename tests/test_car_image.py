import re
from datetime import datetime, timezone

import pytest

from mysite.db.models import CarImage, CarStatus
from tests.conftest import JPEG_BYTES, PNG_BYTES, WEBP_BYTES

URL_RE = re.compile(r'^/media/car_images/[0-9a-f]{32}\.(jpg|png|webp)$')


def upload(client, headers, car_id, content=JPEG_BYTES, content_type='image/jpeg', filename='photo.jpg', **form):
    data = {'car_id': str(car_id)}
    data.update({key: str(value) for key, value in form.items()})
    return client.post(
        '/car-image/create',
        data=data,
        files={'car_image': (filename, content, content_type)},
        headers=headers,
    )


def stored_files(media_dir):
    return [path for path in (media_dir / 'car_images').iterdir()]


def add_image(db, car_id, name, is_main=False, position=0):
    image = CarImage(car_id=car_id, car_image=f'/media/car_images/{name}', is_main=is_main, position=position)
    db.add(image)
    db.commit()
    return image


# ---------- upload ----------


def test_upload_jpeg_as_seller_ok(client, seller, auth_headers, make_car, media_dir):
    car_db = make_car()
    response = upload(client, auth_headers(seller), car_db.id)
    assert response.status_code == 200
    body = response.json()
    assert URL_RE.match(body['car_image'])
    assert body['car_image'].endswith('.jpg')
    assert body['is_main'] is True
    files = stored_files(media_dir)
    assert len(files) == 1
    assert files[0].name == body['car_image'].rsplit('/', 1)[1]
    assert files[0].read_bytes() == JPEG_BYTES


def test_upload_png_ok(client, admin, auth_headers, make_car, media_dir):
    response = upload(client, auth_headers(admin), make_car().id, PNG_BYTES, 'image/png', 'a.png')
    assert response.status_code == 200
    assert response.json()['car_image'].endswith('.png')


def test_upload_webp_ok(client, seller, auth_headers, make_car, media_dir):
    response = upload(client, auth_headers(seller), make_car().id, WEBP_BYTES, 'image/webp', 'a.webp')
    assert response.status_code == 200
    assert response.json()['car_image'].endswith('.webp')


def test_upload_as_client_403(client, client_user, auth_headers, make_car, media_dir):
    assert upload(client, auth_headers(client_user), make_car().id).status_code == 403
    assert stored_files(media_dir) == []


def test_upload_without_token_401(client, make_car, media_dir):
    assert upload(client, {}, make_car().id).status_code == 401


def test_upload_to_deleted_car_404(client, seller, auth_headers, make_car, media_dir):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    assert upload(client, auth_headers(seller), car_db.id).status_code == 404


def test_upload_to_unknown_car_404(client, seller, auth_headers, media_dir):
    assert upload(client, auth_headers(seller), 9999).status_code == 404


def test_upload_wrong_content_type_400(client, seller, auth_headers, make_car, media_dir):
    response = upload(client, auth_headers(seller), make_car().id, JPEG_BYTES, 'text/plain', 'a.txt')
    assert response.status_code == 400
    assert stored_files(media_dir) == []


def test_upload_svg_400(client, seller, auth_headers, make_car, media_dir):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    response = upload(client, auth_headers(seller), make_car().id, svg, 'image/svg+xml', 'a.svg')
    assert response.status_code == 400
    assert stored_files(media_dir) == []


def test_upload_fake_jpeg_400(client, seller, auth_headers, make_car, media_dir):
    response = upload(client, auth_headers(seller), make_car().id, b'<html><script>1</script></html>')
    assert response.status_code == 400
    assert stored_files(media_dir) == []


def test_upload_type_signature_mismatch_400(client, seller, auth_headers, make_car, media_dir):
    response = upload(client, auth_headers(seller), make_car().id, PNG_BYTES, 'image/jpeg', 'a.jpg')
    assert response.status_code == 400
    assert stored_files(media_dir) == []


def test_upload_empty_file_400(client, seller, auth_headers, make_car, media_dir):
    assert upload(client, auth_headers(seller), make_car().id, b'').status_code == 400


def test_upload_too_large_413(client, seller, auth_headers, make_car, media_dir):
    content = JPEG_BYTES + b'\x01' * (5 * 1024 * 1024 + 1 - len(JPEG_BYTES))
    assert len(content) == 5 * 1024 * 1024 + 1
    response = upload(client, auth_headers(seller), make_car().id, content)
    assert response.status_code == 413
    assert stored_files(media_dir) == []


def test_upload_exactly_max_size_ok(client, seller, auth_headers, make_car, media_dir):
    content = JPEG_BYTES + b'\x01' * (5 * 1024 * 1024 - len(JPEG_BYTES))
    assert upload(client, auth_headers(seller), make_car().id, content).status_code == 200


def test_upload_path_traversal_filename_ignored(client, seller, auth_headers, make_car, media_dir):
    response = upload(client, auth_headers(seller), make_car().id, filename='../../evil.py')
    assert response.status_code == 200
    assert URL_RE.match(response.json()['car_image'])
    assert 'evil' not in response.json()['car_image']
    files = stored_files(media_dir)
    assert len(files) == 1
    assert files[0].suffix == '.jpg'
    assert not (media_dir.parent / 'evil.py').exists()
    assert not (media_dir / 'evil.py').exists()
    assert [path for path in media_dir.rglob('*') if path.is_file()] == files


def test_upload_limit_per_car_409(client, seller, auth_headers, make_car, media_dir, monkeypatch):
    monkeypatch.setattr('mysite.api.car_image.MAX_IMAGES_PER_CAR', 2)
    car_db = make_car()
    headers = auth_headers(seller)
    assert upload(client, headers, car_db.id).status_code == 200
    assert upload(client, headers, car_db.id).status_code == 200
    assert upload(client, headers, car_db.id).status_code == 409
    assert len(stored_files(media_dir)) == 2


def test_upload_negative_position_422(client, seller, auth_headers, make_car, media_dir):
    assert upload(client, auth_headers(seller), make_car().id, position=-1).status_code == 422


def test_upload_second_image_not_main(client, seller, auth_headers, make_car, media_dir):
    car_db = make_car()
    headers = auth_headers(seller)
    upload(client, headers, car_db.id)
    assert upload(client, headers, car_db.id).json()['is_main'] is False


def test_upload_is_main_resets_previous_main(client, seller, auth_headers, make_car, media_dir, db):
    car_db = make_car()
    headers = auth_headers(seller)
    first = upload(client, headers, car_db.id).json()
    second = upload(client, headers, car_db.id, is_main='true').json()
    assert second['is_main'] is True
    db.expire_all()
    assert db.get(CarImage, first['id']).is_main is False
    assert db.query(CarImage).filter(CarImage.car_id == car_db.id, CarImage.is_main.is_(True)).count() == 1


# ---------- list / detail ----------


def test_list_images_public_ok(client, make_car, db):
    car_db = make_car()
    add_image(db, car_db.id, 'a.jpg', position=0)
    main = add_image(db, car_db.id, 'b.jpg', is_main=True, position=9)
    third = add_image(db, car_db.id, 'c.jpg', position=1)
    response = client.get('/car-image/list', params={'car_id': car_db.id})
    assert response.status_code == 200
    assert [item['car_image'][-5:] for item in response.json()] == ['b.jpg', 'a.jpg', 'c.jpg']
    assert response.json()[0]['id'] == main.id
    assert third.id in [item['id'] for item in response.json()]


def test_list_images_deleted_car_404(client, make_car, db, seller, auth_headers):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    add_image(db, car_db.id, 'a.jpg')
    assert client.get('/car-image/list', params={'car_id': car_db.id}).status_code == 404
    response = client.get('/car-image/list', params={'car_id': car_db.id}, headers=auth_headers(seller))
    assert response.status_code == 404


def test_list_images_sold_car_public_404(client, make_car, db):
    car_db = make_car(status=CarStatus.sold)
    add_image(db, car_db.id, 'a.jpg')
    assert client.get('/car-image/list', params={'car_id': car_db.id}).status_code == 404


def test_list_images_sold_car_seller_ok(client, make_car, db, seller, auth_headers):
    car_db = make_car(status=CarStatus.sold)
    add_image(db, car_db.id, 'a.jpg')
    response = client.get('/car-image/list', params={'car_id': car_db.id}, headers=auth_headers(seller))
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_images_invalid_token_401(client, make_car):
    response = client.get(
        '/car-image/list', params={'car_id': make_car().id}, headers={'Authorization': 'Bearer garbage'}
    )
    assert response.status_code == 401


def test_detail_image_ok(client, make_car, db):
    car_db = make_car()
    image = add_image(db, car_db.id, 'a.jpg')
    response = client.get('/car-image/detail', params={'car_image_id': image.id})
    assert response.status_code == 200
    assert response.json()['car_id'] == car_db.id


def test_detail_image_not_found_404(client):
    assert client.get('/car-image/detail', params={'car_image_id': 9999}).status_code == 404


def test_detail_image_sold_car_public_404(client, make_car, db):
    image = add_image(db, make_car(status=CarStatus.sold).id, 'a.jpg')
    assert client.get('/car-image/detail', params={'car_image_id': image.id}).status_code == 404


def test_detail_image_deleted_car_404(client, make_car, db):
    image = add_image(db, make_car(deleted_at=datetime.now(timezone.utc)).id, 'a.jpg')
    assert client.get('/car-image/detail', params={'car_image_id': image.id}).status_code == 404


# ---------- update ----------


def test_update_image_set_main(client, seller, auth_headers, make_car, db):
    car_db = make_car()
    first = add_image(db, car_db.id, 'a.jpg', is_main=True)
    second = add_image(db, car_db.id, 'b.jpg')
    response = client.put(f'/car-image/update/{second.id}', json={'is_main': True}, headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['is_main'] is True
    db.refresh(first)
    assert first.is_main is False


def test_update_image_position_ok(client, seller, auth_headers, make_car, db):
    image = add_image(db, make_car().id, 'a.jpg')
    response = client.put(f'/car-image/update/{image.id}', json={'position': 3}, headers=auth_headers(seller))
    assert response.json()['position'] == 3


def test_update_image_position_negative_422(client, seller, auth_headers, make_car, db):
    image = add_image(db, make_car().id, 'a.jpg')
    response = client.put(f'/car-image/update/{image.id}', json={'position': -1}, headers=auth_headers(seller))
    assert response.status_code == 422


def test_update_image_null_is_main_400(client, seller, auth_headers, make_car, db):
    image = add_image(db, make_car().id, 'a.jpg')
    response = client.put(f'/car-image/update/{image.id}', json={'is_main': None}, headers=auth_headers(seller))
    assert response.status_code == 400


def test_update_image_not_found_404(client, seller, auth_headers):
    assert client.put('/car-image/update/9999', json={'position': 1}, headers=auth_headers(seller)).status_code == 404


def test_update_image_as_client_403(client, client_user, auth_headers, make_car, db):
    image = add_image(db, make_car().id, 'a.jpg')
    response = client.put(f'/car-image/update/{image.id}', json={'position': 1}, headers=auth_headers(client_user))
    assert response.status_code == 403


def test_update_image_without_token_401(client, make_car, db):
    image = add_image(db, make_car().id, 'a.jpg')
    assert client.put(f'/car-image/update/{image.id}', json={'position': 1}).status_code == 401


# ---------- delete ----------


def test_delete_image_ok(client, seller, auth_headers, make_car, media_dir, db):
    car_db = make_car()
    body = upload(client, auth_headers(seller), car_db.id).json()
    assert len(stored_files(media_dir)) == 1
    response = client.delete(f'/car-image/delete/{body["id"]}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert db.get(CarImage, body['id']) is None
    assert stored_files(media_dir) == []


def test_delete_main_image_promotes_next(client, seller, auth_headers, make_car, media_dir, db):
    car_db = make_car()
    headers = auth_headers(seller)
    main = upload(client, headers, car_db.id, position=0).json()
    late = upload(client, headers, car_db.id, position=5).json()
    early = upload(client, headers, car_db.id, position=1).json()
    client.delete(f'/car-image/delete/{main["id"]}', headers=headers)
    db.expire_all()
    assert db.get(CarImage, early['id']).is_main is True
    assert db.get(CarImage, late['id']).is_main is False


def test_delete_image_file_already_missing_ok(client, seller, auth_headers, make_car, media_dir, db):
    body = upload(client, auth_headers(seller), make_car().id).json()
    stored_files(media_dir)[0].unlink()
    response = client.delete(f'/car-image/delete/{body["id"]}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert db.get(CarImage, body['id']) is None


def test_delete_image_not_found_404(client, seller, auth_headers):
    assert client.delete('/car-image/delete/9999', headers=auth_headers(seller)).status_code == 404


def test_delete_image_as_client_403(client, client_user, auth_headers, make_car, db):
    image = add_image(db, make_car().id, 'a.jpg')
    assert client.delete(f'/car-image/delete/{image.id}', headers=auth_headers(client_user)).status_code == 403


def test_delete_image_without_token_401(client, make_car, db):
    image = add_image(db, make_car().id, 'a.jpg')
    assert client.delete(f'/car-image/delete/{image.id}').status_code == 401


@pytest.mark.parametrize('role_fixture', ['admin', 'seller'])
def test_delete_image_staff_ok(client, auth_headers, make_car, db, request, role_fixture):
    user = request.getfixturevalue(role_fixture)
    image = add_image(db, make_car().id, 'a.jpg')
    assert client.delete(f'/car-image/delete/{image.id}', headers=auth_headers(user)).status_code == 200
