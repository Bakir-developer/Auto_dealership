import re

import pytest

from mysite.api.car_image import MAX_IMAGE_SIZE
from mysite.db.models import TradeInImage, TradeInStatus
from tests.conftest import JPEG_BYTES, PNG_BYTES, WEBP_BYTES

URL_RE = re.compile(r'^/media/trade_in_images/[0-9a-f]{32}\.(jpg|png|webp)$')


def upload(client, headers, trade_in_id, content=JPEG_BYTES, content_type='image/jpeg', filename='photo.jpg'):
    return client.post(
        '/trade-in-image/create',
        data={'trade_in_id': str(trade_in_id)},
        files={'trade_in_image': (filename, content, content_type)},
        headers=headers,
    )


def stored_files(media_dir):
    return list((media_dir / 'trade_in_images').iterdir())


# ---------- upload ----------


def test_upload_jpeg_ok(client, client_user, auth_headers, make_trade_in, media_dir):
    trade_in = make_trade_in()
    response = upload(client, auth_headers(client_user), trade_in.id, filename='my holiday.jpg')
    assert response.status_code == 200
    body = response.json()
    assert body['trade_in_id'] == trade_in.id
    assert URL_RE.match(body['trade_in_image'])
    assert body['trade_in_image'].endswith('.jpg')
    assert 'holiday' not in body['trade_in_image']
    files = stored_files(media_dir)
    assert len(files) == 1
    assert files[0].name == body['trade_in_image'].rsplit('/', 1)[1]
    assert files[0].read_bytes() == JPEG_BYTES


def test_upload_png_ok(client, client_user, auth_headers, make_trade_in, media_dir):
    response = upload(client, auth_headers(client_user), make_trade_in().id, PNG_BYTES, 'image/png', 'a.png')
    assert response.status_code == 200
    assert response.json()['trade_in_image'].endswith('.png')


def test_upload_webp_ok(client, client_user, auth_headers, make_trade_in, media_dir):
    response = upload(client, auth_headers(client_user), make_trade_in().id, WEBP_BYTES, 'image/webp', 'a.webp')
    assert response.status_code == 200
    assert response.json()['trade_in_image'].endswith('.webp')


def test_upload_evaluating_ok(client, client_user, seller, auth_headers, make_trade_in, media_dir):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    assert upload(client, auth_headers(client_user), trade_in.id).status_code == 200


def test_upload_fake_content_type_400(client, client_user, auth_headers, make_trade_in, media_dir):
    response = upload(client, auth_headers(client_user), make_trade_in().id, b'not an image at all', 'image/jpeg')
    assert response.status_code == 400
    assert stored_files(media_dir) == []


def test_upload_content_type_mismatch_400(client, client_user, auth_headers, make_trade_in, media_dir):
    response = upload(client, auth_headers(client_user), make_trade_in().id, PNG_BYTES, 'image/jpeg')
    assert response.status_code == 400
    assert stored_files(media_dir) == []


def test_upload_empty_400(client, client_user, auth_headers, make_trade_in, media_dir):
    assert upload(client, auth_headers(client_user), make_trade_in().id, b'').status_code == 400


def test_upload_too_large_413(client, client_user, auth_headers, make_trade_in, media_dir):
    content = JPEG_BYTES + bytes(MAX_IMAGE_SIZE)
    response = upload(client, auth_headers(client_user), make_trade_in().id, content)
    assert response.status_code == 413
    assert stored_files(media_dir) == []


def test_upload_limit_409(client, client_user, auth_headers, make_trade_in, make_trade_in_image, media_dir):
    trade_in = make_trade_in()
    for index in range(10):
        make_trade_in_image(trade_in, f'{index}.jpg')
    response = upload(client, auth_headers(client_user), trade_in.id)
    assert response.status_code == 409
    assert stored_files(media_dir) == []


def test_upload_tenth_image_ok(client, client_user, auth_headers, make_trade_in, make_trade_in_image, media_dir):
    trade_in = make_trade_in()
    for index in range(9):
        make_trade_in_image(trade_in, f'{index}.jpg')
    assert upload(client, auth_headers(client_user), trade_in.id).status_code == 200


@pytest.mark.parametrize('current', [TradeInStatus.offered, TradeInStatus.accepted, TradeInStatus.rejected])
def test_upload_closed_status_409(client, client_user, auth_headers, make_trade_in, media_dir, current):
    trade_in = make_trade_in(status=current)
    assert upload(client, auth_headers(client_user), trade_in.id).status_code == 409
    assert stored_files(media_dir) == []


def test_upload_other_client_404(client, client2, auth_headers, make_trade_in, media_dir):
    trade_in = make_trade_in()
    assert upload(client, auth_headers(client2), trade_in.id).status_code == 404
    assert stored_files(media_dir) == []


def test_upload_unknown_trade_in_404(client, client_user, auth_headers, media_dir):
    assert upload(client, auth_headers(client_user), 9999).status_code == 404


def test_upload_as_seller_403(client, seller, auth_headers, make_trade_in, media_dir):
    assert upload(client, auth_headers(seller), make_trade_in().id).status_code == 403


def test_upload_as_admin_403(client, admin, auth_headers, make_trade_in, media_dir):
    assert upload(client, auth_headers(admin), make_trade_in().id).status_code == 403


def test_upload_without_token_401(client, make_trade_in, media_dir):
    assert upload(client, {}, make_trade_in().id).status_code == 401


def test_upload_path_traversal_filename_ignored(client, client_user, auth_headers, make_trade_in, media_dir):
    response = upload(client, auth_headers(client_user), make_trade_in().id, filename='../../x.jpg')
    assert response.status_code == 200
    assert URL_RE.match(response.json()['trade_in_image'])
    assert len(stored_files(media_dir)) == 1
    assert not (media_dir.parent / 'x.jpg').exists()
    assert not (media_dir / 'x.jpg').exists()


# ---------- list / detail ----------


def list_images(client, headers, trade_in_id):
    return client.get('/trade-in-image/list', params={'trade_in_id': trade_in_id}, headers=headers)


def test_list_images_client_owner_ok(client, client_user, auth_headers, make_trade_in, make_trade_in_image):
    trade_in = make_trade_in()
    first = make_trade_in_image(trade_in, 'a.jpg')
    second = make_trade_in_image(trade_in, 'b.jpg')
    response = list_images(client, auth_headers(client_user), trade_in.id)
    assert response.status_code == 200
    assert [item['id'] for item in response.json()] == [first.id, second.id]


def test_list_images_seller_owner_ok(client, seller, auth_headers, make_trade_in, make_trade_in_image):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    make_trade_in_image(trade_in)
    assert len(list_images(client, auth_headers(seller), trade_in.id).json()) == 1


def test_list_images_seller_free_ok(client, seller, auth_headers, make_trade_in, make_trade_in_image):
    trade_in = make_trade_in()
    make_trade_in_image(trade_in)
    assert list_images(client, auth_headers(seller), trade_in.id).status_code == 200


def test_list_images_other_seller_404(client, seller2, seller, auth_headers, make_trade_in):
    trade_in = make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    assert list_images(client, auth_headers(seller2), trade_in.id).status_code == 404


def test_list_images_other_client_404(client, client2, auth_headers, make_trade_in):
    trade_in = make_trade_in()
    assert list_images(client, auth_headers(client2), trade_in.id).status_code == 404


def test_list_images_without_token_401(client, make_trade_in):
    assert list_images(client, {}, make_trade_in().id).status_code == 401


def test_detail_image_ok(client, client_user, auth_headers, make_trade_in, make_trade_in_image):
    image = make_trade_in_image(make_trade_in())
    response = client.get(
        '/trade-in-image/detail', params={'trade_in_image_id': image.id}, headers=auth_headers(client_user)
    )
    assert response.status_code == 200
    assert response.json()['id'] == image.id


def test_detail_image_other_client_404(client, client2, auth_headers, make_trade_in, make_trade_in_image):
    image = make_trade_in_image(make_trade_in())
    response = client.get(
        '/trade-in-image/detail', params={'trade_in_image_id': image.id}, headers=auth_headers(client2)
    )
    assert response.status_code == 404


# ---------- delete ----------


def make_image_with_file(media_dir, make_trade_in_image, trade_in, name='a.jpg'):
    (media_dir / 'trade_in_images' / name).write_bytes(JPEG_BYTES)
    return make_trade_in_image(trade_in, name)


def test_delete_image_owner_ok(client, client_user, auth_headers, make_trade_in, make_trade_in_image, media_dir, db):
    image = make_image_with_file(media_dir, make_trade_in_image, make_trade_in())
    response = client.delete(f'/trade-in-image/delete/{image.id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json() == {'message': 'Фотография удалена'}
    assert db.query(TradeInImage).count() == 0
    assert stored_files(media_dir) == []


def test_delete_image_offered_409(client, client_user, auth_headers, make_trade_in, make_trade_in_image, media_dir):
    image = make_image_with_file(media_dir, make_trade_in_image, make_trade_in(status=TradeInStatus.offered))
    response = client.delete(f'/trade-in-image/delete/{image.id}', headers=auth_headers(client_user))
    assert response.status_code == 409
    assert len(stored_files(media_dir)) == 1


def test_delete_image_admin_ok(client, admin, auth_headers, make_trade_in, make_trade_in_image, media_dir):
    image = make_image_with_file(media_dir, make_trade_in_image, make_trade_in(status=TradeInStatus.offered))
    assert client.delete(f'/trade-in-image/delete/{image.id}', headers=auth_headers(admin)).status_code == 200
    assert stored_files(media_dir) == []


def test_delete_image_seller_403(client, seller, auth_headers, make_trade_in, make_trade_in_image):
    image = make_trade_in_image(make_trade_in())
    assert client.delete(f'/trade-in-image/delete/{image.id}', headers=auth_headers(seller)).status_code == 403


def test_delete_image_other_client_404(client, client2, auth_headers, make_trade_in, make_trade_in_image):
    image = make_trade_in_image(make_trade_in())
    assert client.delete(f'/trade-in-image/delete/{image.id}', headers=auth_headers(client2)).status_code == 404


def test_delete_image_does_not_touch_outside_dir(
    client, client_user, auth_headers, make_trade_in, make_trade_in_image, media_dir
):
    # в БД лежит путь с обходом каталога: удаляться должен только файл с именем из последнего сегмента
    outside = media_dir / 'secret.txt'
    outside.write_bytes(b'secret')
    image = make_trade_in_image(make_trade_in(), '../../secret.txt')
    response = client.delete(f'/trade-in-image/delete/{image.id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert outside.exists()


def test_delete_trade_in_removes_files(
    client, client_user, auth_headers, make_trade_in, make_trade_in_image, media_dir
):
    trade_in = make_trade_in()
    make_image_with_file(media_dir, make_trade_in_image, trade_in, 'a.jpg')
    make_image_with_file(media_dir, make_trade_in_image, trade_in, 'b.jpg')
    assert client.delete(f'/trade-in/delete/{trade_in.id}', headers=auth_headers(client_user)).status_code == 200
    assert stored_files(media_dir) == []
