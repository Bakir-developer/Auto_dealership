from datetime import datetime, time, timedelta, timezone

import pytest

from mysite.db.models import CarStatus, Notification, NotificationType, TestDrive, TestDriveStatus, UserRole


def ids(response):
    return [item['id'] for item in response.json()]


def parse_dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def post_create(client, user, auth_headers, car, start, **extra):
    return client.post(
        '/test-drive/create', json={'car_id': car.id, 'start_time': start, **extra}, headers=auth_headers(user)
    )


def notifications_of(db, user):
    db.expire_all()
    return db.query(Notification).filter(Notification.user_id == user.id).all()


@pytest.fixture
def car(make_car):
    return make_car()


@pytest.fixture
def utc_day():
    """Дата в UTC на два дня вперёд (гарантированно в будущем и в горизонте)."""
    return datetime.now(timezone.utc).date() + timedelta(days=2)


# ---------- create ----------


def test_create_test_drive_ok(client, db, salon_settings, client_user, auth_headers, car, future_slot):
    response = post_create(client, client_user, auth_headers, car, future_slot(1, 10, 0))
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'scheduled'
    assert data['seller_id'] is None
    assert data['client_id'] == client_user.id
    start, end = parse_dt(data['start_time']), parse_dt(data['end_time'])
    assert start.utcoffset() == timedelta(0)
    assert end - start == timedelta(minutes=60)
    assert start.hour == 4 and start.minute == 0  # 10:00 Asia/Bishkek (+06:00) = 04:00 UTC
    stored = db.get(TestDrive, data['id'])
    assert stored.start_time.replace(tzinfo=None).hour == 4


def test_create_ignores_end_time_client_id_status(
    client, salon_settings, client_user, seller, make_user, auth_headers, car, future_slot
):
    other = make_user('other', UserRole.client)
    response = post_create(
        client,
        client_user,
        auth_headers,
        car,
        future_slot(1, 10, 0),
        end_time=future_slot(1, 17, 0),
        client_id=other.id,
        seller_id=seller.id,
        status='confirmed',
    )
    assert response.status_code == 200
    data = response.json()
    assert data['client_id'] == client_user.id
    assert data['seller_id'] is None
    assert data['status'] == 'scheduled'
    assert parse_dt(data['end_time']) - parse_dt(data['start_time']) == timedelta(minutes=60)


def test_create_naive_datetime_422(client, salon_settings, client_user, auth_headers, car, slot_dt):
    naive = slot_dt(1, 10, 0).replace(tzinfo=None).isoformat()
    assert post_create(client, client_user, auth_headers, car, naive).status_code == 422


def test_create_utc_input_ok(client, salon_settings, client_user, auth_headers, car, utc_day):
    start = datetime.combine(utc_day, time(4, 0), tzinfo=timezone.utc)
    response = post_create(client, client_user, auth_headers, car, start.isoformat().replace('+00:00', 'Z'))
    assert response.status_code == 200
    assert parse_dt(response.json()['start_time']) == start


def test_create_as_seller_403(client, salon_settings, seller, auth_headers, car, future_slot):
    assert post_create(client, seller, auth_headers, car, future_slot()).status_code == 403


def test_create_as_admin_403(client, salon_settings, admin, auth_headers, car, future_slot):
    assert post_create(client, admin, auth_headers, car, future_slot()).status_code == 403


def test_create_without_token_401(client, salon_settings, car, future_slot):
    response = client.post('/test-drive/create', json={'car_id': car.id, 'start_time': future_slot()})
    assert response.status_code == 401


def test_create_invalid_start_time_422(client, salon_settings, client_user, auth_headers, car):
    assert post_create(client, client_user, auth_headers, car, 'not-a-date').status_code == 422


def test_create_notifies_active_sellers(
    client, db, salon_settings, client_user, seller, make_user, auth_headers, car, future_slot
):
    blocked = make_user('blockedseller', UserRole.seller, is_active=False)
    response = post_create(client, client_user, auth_headers, car, future_slot(1, 10, 0))
    assert response.status_code == 200
    items = notifications_of(db, seller)
    assert len(items) == 1
    assert items[0].notification_type == NotificationType.test_drive
    assert '10:00' in items[0].text  # время в часовом поясе салона
    assert notifications_of(db, blocked) == []
    assert notifications_of(db, client_user) == []


# ---------- статусы авто ----------


@pytest.mark.parametrize('car_status', [CarStatus.reserved, CarStatus.in_transit])
def test_create_unavailable_car_409(
    client, salon_settings, client_user, auth_headers, make_car, future_slot, car_status
):
    car_db = make_car(status=car_status)
    assert post_create(client, client_user, auth_headers, car_db, future_slot()).status_code == 409


@pytest.mark.parametrize('car_status', [CarStatus.sold, CarStatus.withdrawn])
def test_create_sold_or_withdrawn_car_404(
    client, salon_settings, client_user, auth_headers, make_car, future_slot, car_status
):
    car_db = make_car(status=car_status)
    assert post_create(client, client_user, auth_headers, car_db, future_slot()).status_code == 404


def test_create_deleted_car_404(client, salon_settings, client_user, auth_headers, make_car, future_slot):
    car_db = make_car(deleted_at=datetime.now(timezone.utc))
    assert post_create(client, client_user, auth_headers, car_db, future_slot()).status_code == 404


def test_create_unknown_car_404(client, salon_settings, client_user, auth_headers, future_slot):
    response = client.post(
        '/test-drive/create',
        json={'car_id': 99999, 'start_time': future_slot()},
        headers=auth_headers(client_user),
    )
    assert response.status_code == 404


# ---------- время ----------


def test_create_in_past_400(client, salon_settings, client_user, auth_headers, car):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert post_create(client, client_user, auth_headers, car, past).status_code == 400


def test_create_now_400(client, salon_settings, client_user, auth_headers, car):
    now = datetime.now(timezone.utc).isoformat()
    assert post_create(client, client_user, auth_headers, car, now).status_code == 400


def test_create_beyond_30_days_400(client, salon_settings, client_user, auth_headers, car, future_slot):
    assert post_create(client, client_user, auth_headers, car, future_slot(31, 10, 0)).status_code == 400


def test_create_within_30_days_ok(client, salon_settings, client_user, auth_headers, car, future_slot):
    assert post_create(client, client_user, auth_headers, car, future_slot(29, 10, 0)).status_code == 200


def test_create_before_work_start_400(client, salon_settings, client_user, auth_headers, car, future_slot):
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 8, 59)).status_code == 400


def test_create_at_work_start_ok(client, salon_settings, client_user, auth_headers, car, future_slot):
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 9, 0)).status_code == 200


def test_create_ending_after_work_end_400(client, salon_settings, client_user, auth_headers, car, future_slot):
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 17, 30)).status_code == 400


def test_create_ending_exactly_work_end_ok(client, salon_settings, client_user, auth_headers, car, future_slot):
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 17, 0)).status_code == 200


def test_create_respects_salon_timezone(client, salon_settings, client_user, auth_headers, car, utc_day):
    # 09:00 UTC = 15:00 Бишкек — рабочее время
    ok = datetime.combine(utc_day, time(9, 0), tzinfo=timezone.utc).isoformat()
    assert post_create(client, client_user, auth_headers, car, ok).status_code == 200
    # 12:30 UTC = 18:30 Бишкек — после закрытия
    late = datetime.combine(utc_day, time(12, 30), tzinfo=timezone.utc).isoformat()
    assert post_create(client, client_user, auth_headers, car, late).status_code == 400
    # 02:00 UTC = 08:00 Бишкек — до открытия
    early = datetime.combine(utc_day, time(2, 0), tzinfo=timezone.utc).isoformat()
    assert post_create(client, client_user, auth_headers, car, early).status_code == 400
    # 18:00 UTC = 00:00 Бишкек следующего дня — нерабочее время, хотя в UTC «вечер»
    midnight = datetime.combine(utc_day, time(18, 0), tzinfo=timezone.utc).isoformat()
    assert post_create(client, client_user, auth_headers, car, midnight).status_code == 400


def test_create_custom_test_drive_minutes(client, db, salon_settings, client_user, auth_headers, car, future_slot):
    salon_settings.test_drive_minutes = 30
    db.commit()
    response = post_create(client, client_user, auth_headers, car, future_slot(1, 10, 0))
    assert response.status_code == 200
    data = response.json()
    assert parse_dt(data['end_time']) - parse_dt(data['start_time']) == timedelta(minutes=30)


def test_create_without_salon_settings_503(client, client_user, auth_headers, car, future_slot):
    assert post_create(client, client_user, auth_headers, car, future_slot()).status_code == 503


# ---------- пересечения ----------


def test_overlap_same_car_409(client, salon_settings, client_user, make_user, auth_headers, car, future_slot):
    other = make_user('other', UserRole.client)
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 10, 0)).status_code == 200
    assert post_create(client, other, auth_headers, car, future_slot(1, 10, 30)).status_code == 409


def test_overlap_identical_slot_same_car_409(
    client, salon_settings, client_user, make_user, auth_headers, car, future_slot
):
    other = make_user('other', UserRole.client)
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 10, 0)).status_code == 200
    assert post_create(client, other, auth_headers, car, future_slot(1, 10, 0)).status_code == 409


def test_adjacent_slots_same_car_ok(client, salon_settings, client_user, make_user, auth_headers, car, future_slot):
    other = make_user('other', UserRole.client)
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 10, 0)).status_code == 200
    assert post_create(client, other, auth_headers, car, future_slot(1, 11, 0)).status_code == 200
    assert post_create(client, other, auth_headers, car, future_slot(1, 9, 0)).status_code == 200


@pytest.mark.parametrize('old_status', [TestDriveStatus.cancelled, TestDriveStatus.completed])
def test_overlap_same_car_inactive_ignored_ok(
    client, salon_settings, client_user, make_user, auth_headers, car, make_test_drive, slot_dt, future_slot, old_status
):
    other = make_user('other', UserRole.client)
    make_test_drive(car, start=slot_dt(1, 10, 0), status=old_status)
    assert post_create(client, other, auth_headers, car, future_slot(1, 10, 0)).status_code == 200


def test_overlap_confirmed_same_car_409(
    client, salon_settings, client_user, make_user, auth_headers, car, make_test_drive, slot_dt, future_slot
):
    other = make_user('other', UserRole.client)
    make_test_drive(car, start=slot_dt(1, 10, 0), status=TestDriveStatus.confirmed)
    assert post_create(client, other, auth_headers, car, future_slot(1, 10, 30)).status_code == 409


def test_overlap_other_car_ok(client, salon_settings, client_user, make_user, auth_headers, car, make_car, future_slot):
    other = make_user('other', UserRole.client)
    car2 = make_car()
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 10, 0)).status_code == 200
    assert post_create(client, other, auth_headers, car2, future_slot(1, 10, 0)).status_code == 200


def test_overlap_same_client_other_car_409(
    client, salon_settings, client_user, auth_headers, car, make_car, future_slot
):
    car2 = make_car()
    assert post_create(client, client_user, auth_headers, car, future_slot(1, 10, 0)).status_code == 200
    assert post_create(client, client_user, auth_headers, car2, future_slot(1, 10, 30)).status_code == 409


def test_overlap_seller_on_confirm_409(
    client, salon_settings, client_user, make_user, seller, auth_headers, car, make_car, make_test_drive, slot_dt
):
    client2 = make_user('client2', UserRole.client)
    car2 = make_car()
    make_test_drive(car, start=slot_dt(1, 10, 0), status=TestDriveStatus.confirmed, seller_id=seller.id)
    second = make_test_drive(car2, start=slot_dt(1, 10, 30), client_id=client2.id)
    response = client.post(f'/test-drive/confirm/{second.id}', headers=auth_headers(seller))
    assert response.status_code == 409


def test_overlap_seller_on_assign_409(
    client, salon_settings, admin, make_user, seller, auth_headers, car, make_car, make_test_drive, slot_dt
):
    client2 = make_user('client2', UserRole.client)
    car2 = make_car()
    make_test_drive(car, start=slot_dt(1, 10, 0), status=TestDriveStatus.confirmed, seller_id=seller.id)
    second = make_test_drive(car2, start=slot_dt(1, 10, 30), client_id=client2.id)
    response = client.post(
        f'/test-drive/assign/{second.id}', json={'seller_id': seller.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 409


# ---------- list / detail / видимость ----------


def test_list_without_token_401(client):
    assert client.get('/test-drive/list').status_code == 401


def test_list_client_sees_only_own(
    client, client_user, make_user, auth_headers, car, make_car, make_test_drive, slot_dt
):
    other = make_user('other', UserRole.client)
    mine = make_test_drive(car, start=slot_dt(1, 10, 0))
    make_test_drive(make_car(), start=slot_dt(1, 10, 0), client_id=other.id)
    response = client.get('/test-drive/list', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert ids(response) == [mine.id]


def test_list_seller_own_and_free(client, seller, make_user, auth_headers, car, make_car, make_test_drive, slot_dt):
    seller2 = make_user('seller2', UserRole.seller)
    own = make_test_drive(car, start=slot_dt(1, 10, 0), seller_id=seller.id, status=TestDriveStatus.confirmed)
    free = make_test_drive(make_car(), start=slot_dt(1, 12, 0))
    foreign = make_test_drive(
        make_car(), start=slot_dt(1, 14, 0), seller_id=seller2.id, status=TestDriveStatus.confirmed
    )
    response = client.get('/test-drive/list', headers=auth_headers(seller))
    assert set(ids(response)) == {own.id, free.id}
    assert foreign.id not in ids(response)
    only_free = client.get('/test-drive/list', params={'only_free': True}, headers=auth_headers(seller))
    assert ids(only_free) == [free.id]


def test_list_admin_sees_all_ordered_by_start(
    client, admin, seller, auth_headers, car, make_car, make_test_drive, slot_dt
):
    late = make_test_drive(car, start=slot_dt(2, 10, 0))
    early = make_test_drive(make_car(), start=slot_dt(1, 10, 0), seller_id=seller.id)
    response = client.get('/test-drive/list', headers=auth_headers(admin))
    assert ids(response) == [early.id, late.id]


def test_list_filters_status_and_car(client, admin, auth_headers, car, make_car, make_test_drive, slot_dt):
    car2 = make_car()
    a = make_test_drive(car, start=slot_dt(1, 10, 0))
    make_test_drive(car2, start=slot_dt(1, 12, 0), status=TestDriveStatus.cancelled)
    assert ids(client.get('/test-drive/list', params={'status': 'scheduled'}, headers=auth_headers(admin))) == [a.id]
    assert ids(client.get('/test-drive/list', params={'car_id': car.id}, headers=auth_headers(admin))) == [a.id]


def test_list_filter_date_range(client, admin, auth_headers, car, make_test_drive, slot_dt):
    first = make_test_drive(car, start=slot_dt(1, 10, 0))
    second = make_test_drive(car, start=slot_dt(3, 10, 0))
    response = client.get(
        '/test-drive/list',
        params={'date_from': slot_dt(2, 0, 0).isoformat(), 'date_to': slot_dt(4, 0, 0).isoformat()},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    assert ids(response) == [second.id]
    exact = client.get(
        '/test-drive/list',
        params={'date_from': slot_dt(1, 10, 0).isoformat(), 'date_to': slot_dt(1, 10, 0).isoformat()},
        headers=auth_headers(admin),
    )
    assert ids(exact) == [first.id]  # смещение +06:00 корректно приводится к UTC


def test_list_invalid_date_range_400(client, admin, auth_headers, slot_dt):
    response = client.get(
        '/test-drive/list',
        params={'date_from': slot_dt(3, 0, 0).isoformat(), 'date_to': slot_dt(1, 0, 0).isoformat()},
        headers=auth_headers(admin),
    )
    assert response.status_code == 400


def test_list_naive_date_from_422(client, admin, auth_headers):
    response = client.get('/test-drive/list', params={'date_from': '2030-01-01T10:00:00'}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_list_invalid_limit_422(client, admin, auth_headers):
    assert client.get('/test-drive/list', params={'limit': 101}, headers=auth_headers(admin)).status_code == 422


def test_detail_own_ok(client, client_user, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    response = client.get('/test-drive/detail', params={'test_drive_id': td.id}, headers=auth_headers(client_user))
    assert response.status_code == 200
    assert parse_dt(response.json()['start_time']).utcoffset() == timedelta(0)


def test_detail_other_client_404(client, make_user, auth_headers, car, make_test_drive):
    other = make_user('other', UserRole.client)
    td = make_test_drive(car)
    assert (
        client.get('/test-drive/detail', params={'test_drive_id': td.id}, headers=auth_headers(other)).status_code
        == 404
    )


def test_detail_other_seller_404(client, make_user, auth_headers, car, make_test_drive):
    seller1 = make_user('s1', UserRole.seller)
    seller2 = make_user('s2', UserRole.seller)
    td = make_test_drive(car, seller_id=seller1.id, status=TestDriveStatus.confirmed)
    assert (
        client.get('/test-drive/detail', params={'test_drive_id': td.id}, headers=auth_headers(seller2)).status_code
        == 404
    )


def test_detail_free_seller_ok_and_admin_ok(client, seller, admin, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    for user in (seller, admin):
        response = client.get('/test-drive/detail', params={'test_drive_id': td.id}, headers=auth_headers(user))
        assert response.status_code == 200


def test_detail_not_found_404(client, admin, auth_headers):
    assert (
        client.get('/test-drive/detail', params={'test_drive_id': 9999}, headers=auth_headers(admin)).status_code == 404
    )


# ---------- confirm / complete / cancel ----------


def test_confirm_free_by_seller_assigns_self(
    client, db, salon_settings, seller, client_user, auth_headers, car, make_test_drive
):
    td = make_test_drive(car)
    response = client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['status'] == 'confirmed'
    assert response.json()['seller_id'] == seller.id
    items = notifications_of(db, client_user)
    assert len(items) == 1
    assert items[0].notification_type == NotificationType.test_drive


def test_confirm_other_seller_404(client, salon_settings, make_user, auth_headers, car, make_test_drive):
    seller1 = make_user('s1', UserRole.seller)
    seller2 = make_user('s2', UserRole.seller)
    td = make_test_drive(car, seller_id=seller1.id)
    assert client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(seller2)).status_code == 404


def test_confirm_as_client_403(client, client_user, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    assert client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(client_user)).status_code == 403


def test_confirm_admin_without_seller_409(client, salon_settings, admin, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    assert client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(admin)).status_code == 409


def test_confirm_admin_with_seller_ok(client, salon_settings, admin, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car, seller_id=seller.id)
    response = client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['status'] == 'confirmed'


def test_confirm_twice_409(client, salon_settings, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    assert client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(seller)).status_code == 200
    assert client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(seller)).status_code == 409


def test_confirm_past_400(client, salon_settings, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car, start=datetime.now(timezone.utc) - timedelta(hours=3))
    assert client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(seller)).status_code == 400


def test_confirm_car_withdrawn_409(client, db, salon_settings, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    car.status = CarStatus.withdrawn
    db.commit()
    assert client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(seller)).status_code == 409


def test_complete_confirmed_after_start_ok(client, seller, auth_headers, car, make_test_drive):
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    td = make_test_drive(car, start=start, seller_id=seller.id, status=TestDriveStatus.confirmed)
    response = client.post(f'/test-drive/complete/{td.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert response.json()['status'] == 'completed'


def test_complete_before_start_409(client, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car, seller_id=seller.id, status=TestDriveStatus.confirmed)
    assert client.post(f'/test-drive/complete/{td.id}', headers=auth_headers(seller)).status_code == 409


def test_complete_scheduled_409(client, seller, auth_headers, car, make_test_drive):
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    td = make_test_drive(car, start=start, seller_id=seller.id)
    assert client.post(f'/test-drive/complete/{td.id}', headers=auth_headers(seller)).status_code == 409


def test_complete_as_client_403(client, client_user, auth_headers, car, make_test_drive):
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    td = make_test_drive(car, start=start, status=TestDriveStatus.confirmed)
    assert client.post(f'/test-drive/complete/{td.id}', headers=auth_headers(client_user)).status_code == 403


def test_complete_other_seller_404(client, make_user, auth_headers, car, make_test_drive):
    seller1 = make_user('s1', UserRole.seller)
    seller2 = make_user('s2', UserRole.seller)
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    td = make_test_drive(car, start=start, seller_id=seller1.id, status=TestDriveStatus.confirmed)
    assert client.post(f'/test-drive/complete/{td.id}', headers=auth_headers(seller2)).status_code == 404


def test_cancel_by_client_ok(client, db, seller, client_user, auth_headers, car, make_test_drive):
    td = make_test_drive(car, seller_id=seller.id, status=TestDriveStatus.confirmed)
    response = client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(client_user))
    assert response.status_code == 200
    assert response.json()['status'] == 'cancelled'
    assert len(notifications_of(db, seller)) == 1
    assert notifications_of(db, client_user) == []


def test_cancel_by_client_without_seller_ok(client, client_user, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    assert client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(client_user)).status_code == 200


def test_cancel_by_seller_ok(client, db, seller, client_user, auth_headers, car, make_test_drive):
    td = make_test_drive(car, seller_id=seller.id, status=TestDriveStatus.confirmed)
    response = client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(seller))
    assert response.status_code == 200
    assert len(notifications_of(db, client_user)) == 1


def test_cancel_by_admin_ok(client, admin, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    assert client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(admin)).status_code == 200


def test_cancel_free_by_seller_404(client, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    assert client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(seller)).status_code == 404


@pytest.mark.parametrize('final', [TestDriveStatus.completed, TestDriveStatus.cancelled])
def test_cancel_final_status_409(client, client_user, auth_headers, car, make_test_drive, final):
    td = make_test_drive(car, status=final)
    assert client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(client_user)).status_code == 409


def test_cancel_other_client_404(client, make_user, auth_headers, car, make_test_drive):
    other = make_user('other', UserRole.client)
    td = make_test_drive(car)
    assert client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(other)).status_code == 404


def test_cancel_without_token_401(client, car, make_test_drive):
    td = make_test_drive(car)
    assert client.post(f'/test-drive/cancel/{td.id}').status_code == 401


# ---------- update (перенос) ----------


def test_update_reschedule_ok(
    client, db, salon_settings, client_user, seller, auth_headers, car, make_test_drive, slot_dt, future_slot
):
    td = make_test_drive(car, start=slot_dt(1, 10, 0), seller_id=seller.id, status=TestDriveStatus.confirmed)
    response = client.put(
        f'/test-drive/update/{td.id}', json={'start_time': future_slot(2, 14, 0)}, headers=auth_headers(client_user)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'scheduled'
    assert data['seller_id'] == seller.id
    start, end = parse_dt(data['start_time']), parse_dt(data['end_time'])
    assert end - start == timedelta(minutes=60)
    assert start == slot_dt(2, 14, 0)
    assert len(notifications_of(db, seller)) == 1


def test_update_reschedule_by_seller_notifies_client(
    client, db, salon_settings, client_user, seller, auth_headers, car, make_test_drive, future_slot
):
    td = make_test_drive(car, seller_id=seller.id, status=TestDriveStatus.confirmed)
    response = client.put(
        f'/test-drive/update/{td.id}', json={'start_time': future_slot(2, 14, 0)}, headers=auth_headers(seller)
    )
    assert response.status_code == 200
    assert len(notifications_of(db, client_user)) == 1


def test_update_reschedule_overlap_self_ok(
    client, salon_settings, client_user, seller, auth_headers, car, make_test_drive, slot_dt, future_slot
):
    td = make_test_drive(car, start=slot_dt(1, 10, 0), seller_id=seller.id)
    response = client.put(
        f'/test-drive/update/{td.id}', json={'start_time': future_slot(1, 10, 30)}, headers=auth_headers(client_user)
    )
    assert response.status_code == 200


def test_update_reschedule_overlap_other_409(
    client, salon_settings, client_user, make_user, auth_headers, car, make_test_drive, slot_dt, future_slot
):
    other = make_user('other', UserRole.client)
    mine = make_test_drive(car, start=slot_dt(1, 10, 0))
    make_test_drive(car, start=slot_dt(1, 14, 0), client_id=other.id)
    response = client.put(
        f'/test-drive/update/{mine.id}', json={'start_time': future_slot(1, 14, 30)}, headers=auth_headers(client_user)
    )
    assert response.status_code == 409


def test_update_reschedule_past_400(client, salon_settings, client_user, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    response = client.put(f'/test-drive/update/{td.id}', json={'start_time': past}, headers=auth_headers(client_user))
    assert response.status_code == 400


def test_update_reschedule_naive_422(client, salon_settings, client_user, auth_headers, car, make_test_drive, slot_dt):
    td = make_test_drive(car)
    naive = slot_dt(2, 10, 0).replace(tzinfo=None).isoformat()
    response = client.put(f'/test-drive/update/{td.id}', json={'start_time': naive}, headers=auth_headers(client_user))
    assert response.status_code == 422


@pytest.mark.parametrize('body', [{}, {'start_time': None}])
def test_update_no_start_time_400(client, salon_settings, client_user, auth_headers, car, make_test_drive, body):
    td = make_test_drive(car)
    assert client.put(f'/test-drive/update/{td.id}', json=body, headers=auth_headers(client_user)).status_code == 400


@pytest.mark.parametrize('final', [TestDriveStatus.completed, TestDriveStatus.cancelled])
def test_update_final_status_409(
    client, salon_settings, client_user, auth_headers, car, make_test_drive, future_slot, final
):
    td = make_test_drive(car, status=final)
    response = client.put(
        f'/test-drive/update/{td.id}', json={'start_time': future_slot(2, 10, 0)}, headers=auth_headers(client_user)
    )
    assert response.status_code == 409


def test_update_other_client_404(client, salon_settings, make_user, auth_headers, car, make_test_drive, future_slot):
    other = make_user('other', UserRole.client)
    td = make_test_drive(car)
    response = client.put(
        f'/test-drive/update/{td.id}', json={'start_time': future_slot(2, 10, 0)}, headers=auth_headers(other)
    )
    assert response.status_code == 404


def test_update_status_field_ignored(
    client, salon_settings, client_user, auth_headers, car, make_test_drive, future_slot
):
    td = make_test_drive(car)
    response = client.put(
        f'/test-drive/update/{td.id}',
        json={'start_time': future_slot(2, 10, 0), 'status': 'completed'},
        headers=auth_headers(client_user),
    )
    assert response.status_code == 200
    assert response.json()['status'] == 'scheduled'


# ---------- assign / delete ----------


def test_assign_ok_and_notifies(client, db, salon_settings, admin, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    response = client.post(f'/test-drive/assign/{td.id}', json={'seller_id': seller.id}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller.id
    assert len(notifications_of(db, seller)) == 1


def test_reassign_notifies_old_seller(client, db, admin, seller, make_user, auth_headers, car, make_test_drive):
    seller2 = make_user('seller2', UserRole.seller)
    td = make_test_drive(car, seller_id=seller.id)
    response = client.post(f'/test-drive/assign/{td.id}', json={'seller_id': seller2.id}, headers=auth_headers(admin))
    assert response.status_code == 200
    assert len(notifications_of(db, seller2)) == 1
    assert len(notifications_of(db, seller)) == 1


def test_assign_as_seller_403(client, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    response = client.post(f'/test-drive/assign/{td.id}', json={'seller_id': seller.id}, headers=auth_headers(seller))
    assert response.status_code == 403


def test_assign_to_client_404(client, admin, client_user, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    response = client.post(
        f'/test-drive/assign/{td.id}', json={'seller_id': client_user.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 404


def test_assign_completed_409(client, admin, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car, status=TestDriveStatus.completed)
    response = client.post(f'/test-drive/assign/{td.id}', json={'seller_id': seller.id}, headers=auth_headers(admin))
    assert response.status_code == 409


def test_delete_as_admin_ok(client, db, admin, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    td_id = td.id
    assert client.delete(f'/test-drive/delete/{td_id}', headers=auth_headers(admin)).status_code == 200
    db.expire_all()
    assert db.get(TestDrive, td_id) is None


def test_delete_as_seller_403(client, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    assert client.delete(f'/test-drive/delete/{td.id}', headers=auth_headers(seller)).status_code == 403


def test_delete_as_client_403(client, client_user, auth_headers, car, make_test_drive):
    td = make_test_drive(car)
    assert client.delete(f'/test-drive/delete/{td.id}', headers=auth_headers(client_user)).status_code == 403


def test_delete_without_token_401(client, car, make_test_drive):
    td = make_test_drive(car)
    assert client.delete(f'/test-drive/delete/{td.id}').status_code == 401


# ---------- уведомления: admin, заблокированные, assign в прошлом ----------


def test_cancel_by_admin_notifies_client_and_seller(
    client, db, admin, seller, client_user, auth_headers, car, make_test_drive
):
    td = make_test_drive(car, seller_id=seller.id, status=TestDriveStatus.confirmed)
    assert client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(admin)).status_code == 200
    assert len(notifications_of(db, client_user)) == 1
    assert len(notifications_of(db, seller)) == 1
    assert notifications_of(db, admin) == []


def test_update_reschedule_by_admin_notifies_client_and_seller(
    client, db, salon_settings, admin, seller, client_user, auth_headers, car, make_test_drive, future_slot
):
    td = make_test_drive(car, seller_id=seller.id)
    response = client.put(
        f'/test-drive/update/{td.id}', json={'start_time': future_slot(2, 14, 0)}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert len(notifications_of(db, client_user)) == 1
    assert len(notifications_of(db, seller)) == 1


def test_cancel_by_admin_without_seller_notifies_only_client(
    client, db, admin, seller, client_user, auth_headers, car, make_test_drive
):
    td = make_test_drive(car)
    assert client.post(f'/test-drive/cancel/{td.id}', headers=auth_headers(admin)).status_code == 200
    assert len(notifications_of(db, client_user)) == 1
    assert notifications_of(db, seller) == []


def test_reassign_blocked_old_seller_not_notified(client, db, admin, make_user, auth_headers, car, make_test_drive):
    old_seller = make_user('oldseller', UserRole.seller, is_active=False)
    new_seller = make_user('newseller', UserRole.seller)
    td = make_test_drive(car, seller_id=old_seller.id)
    response = client.post(
        f'/test-drive/assign/{td.id}', json={'seller_id': new_seller.id}, headers=auth_headers(admin)
    )
    assert response.status_code == 200
    assert len(notifications_of(db, new_seller)) == 1
    assert notifications_of(db, old_seller) == []


def test_confirm_blocked_client_not_notified(client, db, seller, make_user, auth_headers, car, make_test_drive):
    blocked_client = make_user('blockedclient', UserRole.client, is_active=False)
    td = make_test_drive(car, client_id=blocked_client.id)
    assert client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(seller)).status_code == 200
    assert notifications_of(db, blocked_client) == []


def test_assign_in_past_400(client, admin, seller, auth_headers, car, make_test_drive):
    start = datetime.now(timezone.utc) - timedelta(hours=3)
    td = make_test_drive(car, start=start)
    response = client.post(f'/test-drive/assign/{td.id}', json={'seller_id': seller.id}, headers=auth_headers(admin))
    assert response.status_code == 400


def test_confirm_by_admin_keeps_assigned_seller(client, admin, seller, auth_headers, car, make_test_drive):
    td = make_test_drive(car, seller_id=seller.id)
    response = client.post(f'/test-drive/confirm/{td.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()['seller_id'] == seller.id
    assert response.json()['status'] == 'confirmed'
