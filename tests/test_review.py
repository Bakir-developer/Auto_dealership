from datetime import datetime, timezone

import pytest

from mysite.db.models import AuditLog, DealStatus, Notification, NotificationType, Review


def notifications_of(db, user, notification_type=None):
    db.expire_all()
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if notification_type is not None:
        query = query.filter(Notification.notification_type == notification_type)
    return query.all()


def create(client, headers, deal_id, stars=5, **extra):
    return client.post('/review/create', json={'deal_id': deal_id, 'stars': stars, **extra}, headers=headers)


def delivered_deal(make_deal, **overrides):
    return make_deal(status=DealStatus.delivered, **overrides)


# ---------- create ----------


def test_create_review_delivered_ok(client, client_user, seller, auth_headers, make_deal, db):
    deal = delivered_deal(make_deal)
    response = create(client, auth_headers(client_user), deal.id, 4, comment='Отличный сервис')
    assert response.status_code == 200
    body = response.json()
    assert body['deal_id'] == deal.id
    assert body['client_id'] == client_user.id
    assert body['seller_id'] == deal.seller_id == seller.id
    assert body['stars'] == 4
    assert body['comment'] == 'Отличный сервис'
    notes = notifications_of(db, seller, NotificationType.deal)
    assert len(notes) == 1
    assert str(deal.id) in notes[0].text


@pytest.mark.parametrize(
    'current',
    [DealStatus.new, DealStatus.in_progress, DealStatus.reserved, DealStatus.paid, DealStatus.cancelled],
)
def test_create_review_not_delivered_409(client, client_user, auth_headers, make_deal, db, current):
    deal = make_deal(status=current)
    assert create(client, auth_headers(client_user), deal.id).status_code == 409
    assert db.query(Review).count() == 0


def test_create_review_twice_409(client, client_user, auth_headers, make_deal, db):
    deal = delivered_deal(make_deal)
    assert create(client, auth_headers(client_user), deal.id).status_code == 200
    assert create(client, auth_headers(client_user), deal.id, 3).status_code == 409
    assert db.query(Review).count() == 1


def test_create_review_other_client_deal_404(client, client2, auth_headers, make_deal):
    deal = delivered_deal(make_deal)
    assert create(client, auth_headers(client2), deal.id).status_code == 404


def test_create_review_deleted_deal_404(client, client_user, auth_headers, make_deal):
    deal = delivered_deal(make_deal, deleted_at=datetime.now(timezone.utc))
    assert create(client, auth_headers(client_user), deal.id).status_code == 404


def test_create_review_unknown_deal_404(client, client_user, auth_headers):
    assert create(client, auth_headers(client_user), 9999).status_code == 404


def test_create_review_as_seller_403(client, seller, auth_headers, make_deal):
    assert create(client, auth_headers(seller), delivered_deal(make_deal).id).status_code == 403


def test_create_review_as_admin_403(client, admin, auth_headers, make_deal):
    assert create(client, auth_headers(admin), delivered_deal(make_deal).id).status_code == 403


def test_create_review_without_token_401(client, make_deal):
    assert create(client, {}, delivered_deal(make_deal).id).status_code == 401


@pytest.mark.parametrize('stars', [0, 6, -1])
def test_create_review_stars_out_of_range_422(client, client_user, auth_headers, make_deal, stars):
    assert create(client, auth_headers(client_user), delivered_deal(make_deal).id, stars).status_code == 422


def test_create_review_blank_comment_422(client, client_user, auth_headers, make_deal):
    response = create(client, auth_headers(client_user), delivered_deal(make_deal).id, comment='   ')
    assert response.status_code == 422


def test_create_review_ignores_seller_id(client, client_user, seller, seller2, auth_headers, make_deal):
    deal = delivered_deal(make_deal)
    response = create(client, auth_headers(client_user), deal.id, seller_id=seller2.id, client_id=seller2.id)
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller.id
    assert response.json()['client_id'] == client_user.id


# ---------- list / detail ----------


def test_list_review_client_own(client, client_user, client2, auth_headers, make_deal, make_review):
    own = make_review(delivered_deal(make_deal))
    make_review(delivered_deal(make_deal, client_id=client2.id))
    response = client.get('/review/list', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert [item['id'] for item in response.json()] == [own.id]


def test_list_review_seller_about_self(client, seller, seller2, auth_headers, make_deal, make_review):
    about_me = make_review(delivered_deal(make_deal))
    make_review(delivered_deal(make_deal, seller_id=seller2.id))
    response = client.get('/review/list', headers=auth_headers(seller))
    assert [item['id'] for item in response.json()] == [about_me.id]


def test_list_review_admin_all(client, admin, seller2, auth_headers, make_deal, make_review):
    ids = {make_review(delivered_deal(make_deal)).id, make_review(delivered_deal(make_deal, seller_id=seller2.id)).id}
    response = client.get('/review/list', headers=auth_headers(admin))
    assert {item['id'] for item in response.json()} == ids


def test_list_review_admin_filter_seller(client, admin, seller2, auth_headers, make_deal, make_review):
    make_review(delivered_deal(make_deal))
    target = make_review(delivered_deal(make_deal, seller_id=seller2.id))
    response = client.get('/review/list', params={'seller_id': seller2.id}, headers=auth_headers(admin))
    assert [item['id'] for item in response.json()] == [target.id]


def test_list_review_seller_cannot_use_seller_id_filter(client, seller, seller2, auth_headers, make_deal, make_review):
    make_review(delivered_deal(make_deal, seller_id=seller2.id))
    response = client.get('/review/list', params={'seller_id': seller2.id}, headers=auth_headers(seller))
    assert response.json() == []


def test_list_review_filter_stars(client, admin, auth_headers, make_deal, make_review):
    make_review(delivered_deal(make_deal), stars=2)
    five = make_review(delivered_deal(make_deal), stars=5)
    response = client.get('/review/list', params={'stars': 5}, headers=auth_headers(admin))
    assert [item['id'] for item in response.json()] == [five.id]


def test_list_review_hides_deleted_deal(client, admin, auth_headers, make_deal, make_review):
    make_review(delivered_deal(make_deal, deleted_at=datetime.now(timezone.utc)))
    assert client.get('/review/list', headers=auth_headers(admin)).json() == []


def test_list_review_limit_101_422(client, admin, auth_headers):
    assert client.get('/review/list', params={'limit': 101}, headers=auth_headers(admin)).status_code == 422


def test_list_review_without_token_401(client):
    assert client.get('/review/list').status_code == 401


def test_detail_review_ok(client, client_user, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal))
    response = client.get('/review/detail', params={'review_id': review.id}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['id'] == review.id


def test_detail_review_other_client_404(client, client2, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal))
    response = client.get('/review/detail', params={'review_id': review.id}, headers=auth_headers(client2))
    assert response.status_code == 404


def test_detail_review_other_seller_404(client, seller2, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal))
    response = client.get('/review/detail', params={'review_id': review.id}, headers=auth_headers(seller2))
    assert response.status_code == 404


# ---------- update ----------


def test_update_review_author_ok(client, client_user, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal), stars=5, comment='old')
    response = client.put(
        f'/review/update/{review.id}', json={'stars': 3, 'comment': 'new'}, headers=auth_headers(client_user)
    )
    assert response.status_code == 200
    assert response.json()['stars'] == 3
    assert response.json()['comment'] == 'new'


def test_update_review_partial_keeps_stars(client, client_user, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal), stars=4)
    response = client.put(f'/review/update/{review.id}', json={'comment': 'only'}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['stars'] == 4


def test_update_review_other_client_404(client, client2, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal))
    response = client.put(f'/review/update/{review.id}', json={'stars': 1}, headers=auth_headers(client2))
    assert response.status_code == 404


def test_update_review_seller_403(client, seller, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal))
    assert client.put(f'/review/update/{review.id}', json={'stars': 1}, headers=auth_headers(seller)).status_code == 403


def test_update_review_null_stars_400(client, client_user, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal))
    response = client.put(f'/review/update/{review.id}', json={'stars': None}, headers=auth_headers(client_user))
    assert response.status_code == 400


def test_update_review_stars_out_of_range_422(client, client_user, auth_headers, make_deal, make_review):
    review = make_review(delivered_deal(make_deal))
    response = client.put(f'/review/update/{review.id}', json={'stars': 6}, headers=auth_headers(client_user))
    assert response.status_code == 422


# ---------- delete ----------


def test_delete_review_author_ok(client, client_user, auth_headers, make_deal, make_review, db):
    deal = delivered_deal(make_deal)
    review = make_review(deal)
    response = client.delete(f'/review/delete/{review.id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json() == {'message': 'Отзыв удалён'}
    assert db.query(Review).count() == 0
    assert db.query(AuditLog).filter(AuditLog.action == 'review_delete').count() == 0
    # после удаления можно оставить отзыв заново
    assert create(client, auth_headers(client_user), deal.id, 2).status_code == 200


def test_delete_review_admin_ok(client, admin, auth_headers, make_deal, make_review, db):
    review = make_review(delivered_deal(make_deal), stars=2, comment='плохо')
    response = client.delete(f'/review/delete/{review.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert db.query(Review).count() == 0
    logs = db.query(AuditLog).filter(AuditLog.action == 'review_delete', AuditLog.entity_id == review.id).all()
    assert len(logs) == 1
    assert logs[0].user_id == admin.id
    assert logs[0].old_value['stars'] == 2
    assert logs[0].old_value['comment'] == 'плохо'


def test_delete_review_seller_403(client, seller, auth_headers, make_deal, make_review, db):
    review = make_review(delivered_deal(make_deal))
    assert client.delete(f'/review/delete/{review.id}', headers=auth_headers(seller)).status_code == 403
    assert db.query(Review).count() == 1


def test_delete_review_other_client_404(client, client2, auth_headers, make_deal, make_review, db):
    review = make_review(delivered_deal(make_deal))
    assert client.delete(f'/review/delete/{review.id}', headers=auth_headers(client2)).status_code == 404
    assert db.query(Review).count() == 1
