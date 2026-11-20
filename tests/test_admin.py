import pytest

from mysite.db.models import UserRole

PASSWORD = 'pass12345'


def admin_login(client, username, password=PASSWORD):
    return client.post('/admin/login', data={'username': username, 'password': password}, follow_redirects=False)


def is_redirect_into_panel(response):
    return response.status_code in (302, 303) and not response.headers['location'].endswith('/admin/login')


def assert_panel_denied(client):
    response = client.get('/admin/', follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers['location'].endswith('/admin/login')


def test_admin_panel_without_login_redirects(client, admin_session_local):
    assert_panel_denied(client)


def test_admin_login_page_available(client, admin_session_local):
    assert client.get('/admin/login').status_code == 200


def test_admin_login_as_admin_ok(client, admin_session_local, admin):
    response = admin_login(client, admin.username)
    assert is_redirect_into_panel(response)
    assert client.get('/admin/', follow_redirects=False).status_code == 200


def test_admin_user_list_has_no_password(client, admin_session_local, admin):
    admin_login(client, admin.username)
    response = client.get('/admin/user-profile/list', follow_redirects=False)
    assert response.status_code == 200
    assert admin.username in response.text
    assert admin.password not in response.text


@pytest.mark.parametrize('role', [UserRole.seller, UserRole.client])
def test_admin_login_non_admin_denied(client, admin_session_local, make_user, role):
    user_db = make_user('someone', role)
    assert not is_redirect_into_panel(admin_login(client, user_db.username))
    assert_panel_denied(client)


def test_admin_login_wrong_password_denied(client, admin_session_local, admin):
    assert not is_redirect_into_panel(admin_login(client, admin.username, 'wrong-password'))
    assert_panel_denied(client)


def test_admin_login_unknown_user_denied(client, admin_session_local):
    assert not is_redirect_into_panel(admin_login(client, 'nobody'))
    assert_panel_denied(client)


def test_admin_login_blocked_admin_denied(client, admin_session_local, make_user):
    blocked = make_user('blockedadmin', UserRole.admin, is_active=False)
    assert not is_redirect_into_panel(admin_login(client, blocked.username))
    assert_panel_denied(client)


def test_admin_session_revoked_after_block(client, admin_session_local, db, admin):
    admin_login(client, admin.username)
    assert client.get('/admin/', follow_redirects=False).status_code == 200
    admin.is_active = False
    db.commit()
    assert_panel_denied(client)


def test_admin_session_revoked_after_role_change(client, admin_session_local, db, admin):
    admin_login(client, admin.username)
    admin.role = UserRole.seller
    db.commit()
    assert_panel_denied(client)


def test_admin_logout_clears_session(client, admin_session_local, admin):
    admin_login(client, admin.username)
    client.get('/admin/logout', follow_redirects=False)
    assert_panel_denied(client)


def test_admin_brand_list_ok(client, admin_session_local, admin, brand):
    admin_login(client, admin.username)
    response = client.get('/admin/brand/list', follow_redirects=False)
    assert response.status_code == 200
    assert brand.brand_name in response.text


def test_admin_car_list_ok(client, admin_session_local, admin, make_car):
    car_db = make_car()
    admin_login(client, admin.username)
    response = client.get('/admin/car/list', follow_redirects=False)
    assert response.status_code == 200
    assert car_db.vin in response.text


@pytest.mark.parametrize('path', ['car', 'price-history'])
def test_admin_readonly_views_forbid_create_and_edit(client, admin_session_local, admin, make_car, path):
    car_db = make_car()
    admin_login(client, admin.username)
    assert client.get(f'/admin/{path}/list', follow_redirects=False).status_code == 200
    assert client.get(f'/admin/{path}/create', follow_redirects=False).status_code == 403
    assert client.get(f'/admin/{path}/edit/{car_db.id}', follow_redirects=False).status_code == 403
    assert client.delete(f'/admin/{path}/delete?pks={car_db.id}', follow_redirects=False).status_code == 403


def test_admin_brand_delete_forbidden(client, admin_session_local, admin, brand):
    admin_login(client, admin.username)
    assert client.delete(f'/admin/brand/delete?pks={brand.id}', follow_redirects=False).status_code == 403


def test_admin_brand_list_without_login_redirects(client, admin_session_local, brand):
    response = client.get('/admin/brand/list', follow_redirects=False)
    assert response.status_code in (302, 303, 307)


def test_admin_lead_list_ok(client, admin_session_local, admin, make_lead):
    lead_db = make_lead(comment='admin-visible-comment')
    admin_login(client, admin.username)
    response = client.get('/admin/lead/list', follow_redirects=False)
    assert response.status_code == 200
    assert str(lead_db.id) in response.text


@pytest.mark.parametrize('path', ['lead'])
def test_admin_crm_views_readonly(client, admin_session_local, admin, make_lead, path):
    obj = make_lead()
    admin_login(client, admin.username)
    assert client.get(f'/admin/{path}/create', follow_redirects=False).status_code == 403
    assert client.get(f'/admin/{path}/edit/{obj.id}', follow_redirects=False).status_code == 403
    assert client.delete(f'/admin/{path}/delete?pks={obj.id}', follow_redirects=False).status_code == 403


@pytest.mark.parametrize('path', ['lead'])
def test_admin_crm_list_without_login_redirects(client, admin_session_local, path):
    assert client.get(f'/admin/{path}/list', follow_redirects=False).status_code in (302, 303, 307)


def test_admin_deal_list_ok(client, admin_session_local, admin, make_deal):
    deal_db = make_deal()
    admin_login(client, admin.username)
    response = client.get('/admin/deal/list', follow_redirects=False)
    assert response.status_code == 200
    assert str(deal_db.id) in response.text


def test_admin_discount_request_list_ok(client, admin_session_local, admin, make_discount_request):
    obj = make_discount_request()
    admin_login(client, admin.username)
    response = client.get('/admin/discount-request/list', follow_redirects=False)
    assert response.status_code == 200
    assert str(obj.id) in response.text


def test_admin_audit_log_list_ok(client, admin_session_local, admin, db):
    from mysite.api.deal import create_audit_log

    create_audit_log(db, admin.id, 'test_admin_view_action', 'deal', 1)
    db.commit()
    admin_login(client, admin.username)
    response = client.get('/admin/audit-log/list', follow_redirects=False)
    assert response.status_code == 200
    assert 'test_admin_view_action' in response.text


@pytest.mark.parametrize('path', ['deal', 'discount-request', 'audit-log'])
def test_admin_sales_views_readonly(client, admin_session_local, admin, make_deal, db, path):
    from mysite.api.deal import create_audit_log
    from mysite.db.models import AuditLog

    make_discount = path == 'discount-request'
    if make_discount:
        from mysite.db.models import DiscountRequest

        obj = DiscountRequest(deal_id=make_deal().id, seller_id=admin.id, requested_percent=5)
        db.add(obj)
        db.commit()
    elif path == 'deal':
        obj = make_deal()
    else:
        create_audit_log(db, admin.id, 'x', 'deal', 1)
        db.commit()
        obj = db.query(AuditLog).first()
    admin_login(client, admin.username)
    assert client.get(f'/admin/{path}/list', follow_redirects=False).status_code == 200
    assert client.get(f'/admin/{path}/create', follow_redirects=False).status_code == 403
    assert client.get(f'/admin/{path}/edit/{obj.id}', follow_redirects=False).status_code == 403
    assert client.delete(f'/admin/{path}/delete?pks={obj.id}', follow_redirects=False).status_code == 403


@pytest.mark.parametrize('path', ['deal', 'discount-request', 'audit-log'])
def test_admin_sales_views_without_login_redirect(client, admin_session_local, path):
    assert client.get(f'/admin/{path}/list', follow_redirects=False).status_code in (302, 303, 307)


@pytest.mark.parametrize('path', ['trade-in', 'review'])
def test_admin_trade_in_review_views_readonly(client, admin_session_local, admin, make_trade_in, make_review, path):
    obj = make_trade_in() if path == 'trade-in' else make_review()
    admin_login(client, admin.username)
    response = client.get(f'/admin/{path}/list', follow_redirects=False)
    assert response.status_code == 200
    assert str(obj.id) in response.text
    assert client.get(f'/admin/{path}/create', follow_redirects=False).status_code == 403
    assert client.get(f'/admin/{path}/edit/{obj.id}', follow_redirects=False).status_code == 403
    assert client.delete(f'/admin/{path}/delete?pks={obj.id}', follow_redirects=False).status_code == 403


@pytest.mark.parametrize('path', ['trade-in', 'review'])
def test_admin_trade_in_review_views_without_login_redirect(client, admin_session_local, path):
    assert client.get(f'/admin/{path}/list', follow_redirects=False).status_code in (302, 303, 307)
