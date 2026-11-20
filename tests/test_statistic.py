from datetime import datetime, timezone
from decimal import Decimal

from mysite.db.models import (
    CarStatus,
    Currency,
    DealStatus,
    DiscountStatus,
    LeadStatus,
    TradeInStatus,
    UserRole,
)

ENUM_SECTIONS = {
    'cars_by_status': CarStatus,
    'leads_by_status': LeadStatus,
    'deals_by_status': DealStatus,
    'trade_ins_by_status': TradeInStatus,
}


def utc(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def general(client, headers, **params):
    return client.get('/statistic/general', params=params, headers=headers)


def delivered(make_deal, make_car, price, currency=Currency.KGS, delivered_at=None, **overrides):
    car = make_car(price=Decimal(price), currency=currency)
    return make_deal(
        car=car,
        status=DealStatus.delivered,
        delivered_at=delivered_at or utc(2025, 1, 15, 12),
        **overrides,
    )


def test_general_date_to_max_not_500(client, admin, auth_headers):
    response = general(client, auth_headers(admin), date_to='9999-12-31')
    assert response.status_code == 200


# ---------- general: доступ и форма ----------


def test_general_as_admin_ok(client, admin, auth_headers):
    response = general(client, auth_headers(admin))
    assert response.status_code == 200
    body = response.json()
    for section, enum in ENUM_SECTIONS.items():
        assert set(body[section]) == {member.value for member in enum}
        assert all(value == 0 for value in body[section].values())
    assert set(body['revenue']) == {'KGS', 'USD'}
    assert body['revenue'] == {'KGS': '0.00', 'USD': '0.00'}
    assert body['delivered_count'] == 0
    assert body['discounts_pending'] == 0
    assert body['reviews_count'] == 0
    assert body['avg_stars'] is None
    assert body['avg_discount_percent'] is None
    assert body['date_from'] is None and body['date_to'] is None
    assert 'password' not in response.text


def test_general_as_seller_403(client, seller, auth_headers):
    assert general(client, auth_headers(seller)).status_code == 403


def test_general_as_client_403(client, client_user, auth_headers):
    assert general(client, auth_headers(client_user)).status_code == 403


def test_general_without_token_401(client):
    assert general(client, {}).status_code == 401


# ---------- general: значения ----------


def test_general_revenue_decimal_sum(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.10')
    delivered(make_deal, make_car, '200000.20')
    body = general(client, auth_headers(admin)).json()
    assert body['revenue']['KGS'] == '300000.30'
    assert body['delivered_count'] == 2


def test_general_revenue_split_by_currency(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '1000000.00', Currency.KGS)
    delivered(make_deal, make_car, '12000.50', Currency.USD)
    delivered(make_deal, make_car, '3000.25', Currency.USD)
    body = general(client, auth_headers(admin)).json()
    assert body['revenue'] == {'KGS': '1000000.00', 'USD': '15000.75'}


def test_general_revenue_uses_final_price(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.00', base_price=Decimal('100000.00'), final_price=Decimal('95000.00'))
    body = general(client, auth_headers(admin)).json()
    assert body['revenue']['KGS'] == '95000.00'


def test_general_revenue_only_delivered(client, admin, auth_headers, make_deal, make_car):
    make_deal(status=DealStatus.paid)
    make_deal(status=DealStatus.cancelled)
    body = general(client, auth_headers(admin)).json()
    assert body['revenue']['KGS'] == '0.00'
    assert body['delivered_count'] == 0
    assert body['deals_by_status']['paid'] == 1
    assert body['deals_by_status']['cancelled'] == 1


def test_general_excludes_deleted_deals_and_cars(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.00', deleted_at=utc(2025, 2, 1))
    make_deal(status=DealStatus.new, deleted_at=utc(2025, 2, 1))
    make_car(deleted_at=utc(2025, 2, 1))
    visible_car = make_car()
    body = general(client, auth_headers(admin)).json()
    assert body['revenue']['KGS'] == '0.00'
    assert body['delivered_count'] == 0
    assert body['deals_by_status']['new'] == 0
    # неудалённые авто: по одному у двух сделок и visible_car; удалённое не считается
    assert body['cars_by_status']['available'] == 3
    assert visible_car.id is not None


def test_general_cars_by_status_skips_deleted(client, admin, auth_headers, make_car):
    make_car()
    make_car(status=CarStatus.sold)
    make_car(deleted_at=utc(2025, 2, 1))
    body = general(client, auth_headers(admin)).json()
    assert body['cars_by_status']['available'] == 1
    assert body['cars_by_status']['sold'] == 1
    assert sum(body['cars_by_status'].values()) == 2


def test_general_avg_stars(client, admin, auth_headers, make_deal, make_review):
    make_review(make_deal(status=DealStatus.delivered), stars=4)
    make_review(make_deal(status=DealStatus.delivered), stars=5)
    body = general(client, auth_headers(admin)).json()
    assert body['reviews_count'] == 2
    assert body['avg_stars'] == '4.50'


def test_general_avg_stars_rounds_half_up(client, admin, auth_headers, make_deal, make_review):
    for stars in (5, 5, 4):
        make_review(make_deal(status=DealStatus.delivered), stars=stars)
    # 14 / 3 = 4.666... -> 4.67
    assert general(client, auth_headers(admin)).json()['avg_stars'] == '4.67'


def test_general_no_reviews_null(client, admin, auth_headers, make_deal):
    make_deal(status=DealStatus.delivered)
    assert general(client, auth_headers(admin)).json()['avg_stars'] is None


def test_general_reviews_of_deleted_deal_excluded(client, admin, auth_headers, make_deal, make_review):
    make_review(make_deal(status=DealStatus.delivered, deleted_at=utc(2025, 2, 1)), stars=1)
    body = general(client, auth_headers(admin)).json()
    assert body['reviews_count'] == 0
    assert body['avg_stars'] is None


def test_general_avg_discount_percent(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.00', discount_percent=Decimal('2.00'), final_price=Decimal('98000.00'))
    delivered(make_deal, make_car, '100000.00', discount_percent=Decimal('3.00'), final_price=Decimal('97000.00'))
    assert general(client, auth_headers(admin)).json()['avg_discount_percent'] == '2.50'


def test_general_discounts_pending_and_clients(
    client, admin, client_user, client2, make_user, auth_headers, make_discount_request
):
    make_user('blockedclient', UserRole.client, is_active=False)
    make_discount_request()
    make_discount_request(status=DiscountStatus.approved)
    body = general(client, auth_headers(admin)).json()
    assert body['discounts_pending'] == 1
    assert body['clients_count'] == 2


def test_general_trade_ins_and_leads_counted(client, admin, auth_headers, make_trade_in, make_lead):
    make_trade_in()
    make_trade_in(status=TradeInStatus.offered)
    make_lead()
    body = general(client, auth_headers(admin)).json()
    assert body['trade_ins_by_status']['new'] == 1
    assert body['trade_ins_by_status']['offered'] == 1
    assert body['leads_by_status']['new'] == 1


def test_general_sellers_rows(
    client, admin, seller, seller2, make_user, auth_headers, make_deal, make_car, make_review
):
    blocked = make_user('blockedseller', UserRole.seller, is_active=False)
    delivered(make_deal, make_car, '100000.00', seller_id=seller2.id)
    deal2 = delivered(make_deal, make_car, '50000.00', seller_id=seller2.id)
    make_review(deal2, stars=4)
    delivered(make_deal, make_car, '70000.00', seller_id=seller.id)
    make_deal(status=DealStatus.new, seller_id=seller.id)
    body = general(client, auth_headers(admin)).json()
    rows = body['sellers']
    assert [row['seller_id'] for row in rows] == [seller2.id, seller.id, blocked.id]
    by_id = {row['seller_id']: row for row in rows}
    assert by_id[seller2.id]['delivered_count'] == 2
    assert by_id[seller2.id]['deals_count'] == 2
    assert by_id[seller2.id]['revenue'] == {'KGS': '150000.00', 'USD': '0.00'}
    assert by_id[seller2.id]['avg_stars'] == '4.00'
    assert by_id[seller.id]['deals_count'] == 2
    assert by_id[seller.id]['delivered_count'] == 1
    assert by_id[seller.id]['avg_stars'] is None
    assert by_id[blocked.id]['is_active'] is False
    assert by_id[blocked.id]['delivered_count'] == 0
    assert admin.id not in by_id


# ---------- период ----------


def test_period_filters_delivered_at(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.00', delivered_at=utc(2025, 1, 10, 12))
    delivered(make_deal, make_car, '200000.00', delivered_at=utc(2025, 2, 10, 12))
    body = general(client, auth_headers(admin), date_from='2025-01-01', date_to='2025-01-31').json()
    assert body['revenue']['KGS'] == '100000.00'
    assert body['delivered_count'] == 1
    assert body['date_from'] == '2025-01-01'
    assert body['date_to'] == '2025-01-31'


def test_period_only_date_from(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.00', delivered_at=utc(2025, 1, 10))
    delivered(make_deal, make_car, '200000.00', delivered_at=utc(2025, 2, 10))
    body = general(client, auth_headers(admin), date_from='2025-02-01').json()
    assert body['revenue']['KGS'] == '200000.00'


def test_period_inclusive_date_to(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.00', delivered_at=utc(2025, 1, 31, 23, 59, 59))
    delivered(make_deal, make_car, '200000.00', delivered_at=utc(2025, 2, 1, 0, 0, 0))
    body = general(client, auth_headers(admin), date_from='2025-01-31', date_to='2025-01-31').json()
    assert body['revenue']['KGS'] == '100000.00'
    assert body['delivered_count'] == 1


def test_period_single_day_from_boundary(client, admin, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.00', delivered_at=utc(2025, 3, 5, 0, 0, 0))
    delivered(make_deal, make_car, '200000.00', delivered_at=utc(2025, 3, 4, 23, 59, 59))
    body = general(client, auth_headers(admin), date_from='2025-03-05', date_to='2025-03-05').json()
    assert body['revenue']['KGS'] == '100000.00'


def test_period_invalid_400(client, admin, auth_headers):
    response = general(client, auth_headers(admin), date_from='2025-02-01', date_to='2025-01-01')
    assert response.status_code == 400


def test_period_bad_date_format_422(client, admin, auth_headers):
    assert general(client, auth_headers(admin), date_from='not-a-date').status_code == 422


def test_period_filters_reviews_by_created_at(client, admin, auth_headers, make_deal, make_review):
    make_review(make_deal(status=DealStatus.delivered), stars=5, created_at=utc(2025, 1, 10))
    make_review(make_deal(status=DealStatus.delivered), stars=1, created_at=utc(2025, 3, 10))
    body = general(client, auth_headers(admin), date_from='2025-01-01', date_to='2025-01-31').json()
    assert body['reviews_count'] == 1
    assert body['avg_stars'] == '5.00'


# ---------- /my ----------


def test_my_as_seller_only_own(client, seller, seller2, auth_headers, make_deal, make_car, make_review, make_trade_in):
    mine = delivered(make_deal, make_car, '100000.50', seller_id=seller.id)
    delivered(make_deal, make_car, '999999.00', seller_id=seller2.id)
    make_deal(status=DealStatus.paid, seller_id=seller2.id)
    make_review(mine, stars=3)
    make_trade_in(seller_id=seller.id, status=TradeInStatus.evaluating)
    make_trade_in(seller_id=seller2.id, status=TradeInStatus.evaluating)
    response = client.get('/statistic/my', headers=auth_headers(seller))
    assert response.status_code == 200
    body = response.json()
    assert body['seller_id'] == seller.id
    assert body['username'] == seller.username
    assert body['revenue'] == {'KGS': '100000.50', 'USD': '0.00'}
    assert body['delivered_count'] == 1
    assert body['deals_by_status']['delivered'] == 1
    assert body['deals_by_status']['paid'] == 0
    assert body['reviews_count'] == 1
    assert body['avg_stars'] == '3.00'
    assert body['trade_ins_by_status']['evaluating'] == 1
    for section in ('leads_by_status', 'deals_by_status', 'discounts_by_status', 'trade_ins_by_status'):
        assert section in body


def test_my_discounts_counted_for_own_seller(client, seller, seller2, auth_headers, make_discount_request):
    make_discount_request(seller_id=seller.id)
    make_discount_request(seller_id=seller2.id)
    body = client.get('/statistic/my', headers=auth_headers(seller)).json()
    assert body['discounts_by_status']['pending'] == 1


def test_my_period_filter(client, seller, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '100000.00', delivered_at=utc(2025, 1, 10))
    delivered(make_deal, make_car, '300000.00', delivered_at=utc(2025, 6, 10))
    response = client.get(
        '/statistic/my', params={'date_from': '2025-06-01', 'date_to': '2025-06-30'}, headers=auth_headers(seller)
    )
    assert response.json()['revenue']['KGS'] == '300000.00'


def test_my_invalid_period_400(client, seller, auth_headers):
    response = client.get(
        '/statistic/my', params={'date_from': '2025-02-01', 'date_to': '2025-01-01'}, headers=auth_headers(seller)
    )
    assert response.status_code == 400


def test_my_as_admin_403(client, admin, auth_headers):
    assert client.get('/statistic/my', headers=auth_headers(admin)).status_code == 403


def test_my_as_client_403(client, client_user, auth_headers):
    assert client.get('/statistic/my', headers=auth_headers(client_user)).status_code == 403


def test_my_without_token_401(client):
    assert client.get('/statistic/my').status_code == 401


# ---------- /seller/{id} ----------


def test_seller_stat_admin_ok(client, admin, seller, seller2, auth_headers, make_deal, make_car):
    delivered(make_deal, make_car, '250000.00', seller_id=seller2.id)
    delivered(make_deal, make_car, '1.00', seller_id=seller.id)
    response = client.get(f'/statistic/seller/{seller2.id}', headers=auth_headers(admin))
    assert response.status_code == 200
    body = response.json()
    assert body['seller_id'] == seller2.id
    assert body['revenue']['KGS'] == '250000.00'
    assert body['delivered_count'] == 1


def test_seller_stat_not_seller_404(client, admin, client_user, auth_headers):
    assert client.get(f'/statistic/seller/{client_user.id}', headers=auth_headers(admin)).status_code == 404


def test_seller_stat_unknown_404(client, admin, auth_headers):
    assert client.get('/statistic/seller/9999', headers=auth_headers(admin)).status_code == 404


def test_seller_stat_as_seller_403(client, seller, seller2, auth_headers):
    assert client.get(f'/statistic/seller/{seller2.id}', headers=auth_headers(seller)).status_code == 403


def test_seller_stat_as_client_403(client, client_user, seller, auth_headers):
    assert client.get(f'/statistic/seller/{seller.id}', headers=auth_headers(client_user)).status_code == 403


def test_seller_stat_without_token_401(client, seller):
    assert client.get(f'/statistic/seller/{seller.id}').status_code == 401
