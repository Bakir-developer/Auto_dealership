from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, localcontext

import pytest

from mysite.db.models import AuditLog, CarStatus, Currency


def calculate(client, car_id, headers=None, **payload):
    data = {'car_id': car_id, 'term_months': 12}
    data.update(payload)
    return client.post('/credit/calculate', json=data, headers=headers or {})


def independent_monthly(loan, annual_rate, months):
    """Независимый расчёт аннуитета: P * r / (1 - (1 + r) ** -n), высокая точность Decimal."""
    with localcontext() as ctx:
        ctx.prec = 60
        rate = Decimal(annual_rate) / Decimal(1200)
        if rate == 0:
            value = Decimal(loan) / months
        else:
            value = Decimal(loan) * rate / (1 - (1 + rate) ** -months)
        return value.quantize(Decimal('0.01'), ROUND_HALF_UP)


@pytest.fixture
def installment_car(make_car):
    """Авто со своими условиями: взнос от 0%, до 120 мес., ставка 12%."""

    def _make(**overrides):
        data = dict(min_down_payment_percent=Decimal('0'), max_term_months=120, installment_rate_percent=Decimal('12'))
        data.update(overrides)
        return make_car(**data)

    return _make


# ---------- calculate: расчёт ----------


def test_calculate_known_annuity(client, installment_car):
    car = installment_car(price=Decimal('1000000.00'))
    response = calculate(client, car.id)
    assert response.status_code == 200
    body = response.json()
    assert body['monthly_payment'] == '88848.79'
    assert body['total_payment'] == '1066185.48'
    assert body['overpayment'] == '66185.48'
    assert body['loan_amount'] == '1000000.00'
    assert body['down_payment'] == '0.00'
    assert body['down_payment_percent'] == '0.00'
    assert body['price'] == '1000000.00'
    assert body['currency'] == 'KGS'
    assert body['car_id'] == car.id
    assert body['term_months'] == 12
    assert Decimal(body['annual_rate']) == Decimal('12')


def test_calculate_returns_car_terms(client, installment_car):
    car = installment_car(min_down_payment_percent=Decimal('20'), max_term_months=48)
    body = calculate(client, car.id, down_payment_percent='25').json()
    terms = body['terms']
    assert terms['installment_available'] is True
    assert Decimal(terms['min_down_payment_percent']) == Decimal('20')
    assert terms['max_term_months'] == 48
    assert terms['min_term_months'] == 6
    assert Decimal(terms['installment_rate_percent']) == Decimal('12')


@pytest.mark.parametrize(
    'price,rate,months',
    [('1350000', '10', 24), ('1000000', '5', 36), ('250000.50', '18.5', 60), ('999999.99', '0.5', 120)],
)
def test_calculate_matches_independent_formula(client, installment_car, price, rate, months):
    car = installment_car(price=Decimal(price), installment_rate_percent=Decimal(rate))
    body = calculate(client, car.id, term_months=months).json()
    expected_monthly = independent_monthly(price, rate, months)
    assert Decimal(body['monthly_payment']) == expected_monthly
    assert Decimal(body['total_payment']) == expected_monthly * months
    assert Decimal(body['overpayment']) == expected_monthly * months - Decimal(price)


def test_calculate_down_payment_amount(client, installment_car):
    car = installment_car(price=Decimal('1500000.00'), installment_rate_percent=Decimal('10'))
    body = calculate(client, car.id, down_payment='150000', term_months=24).json()
    assert body['down_payment'] == '150000.00'
    assert body['down_payment_percent'] == '10.00'
    assert body['loan_amount'] == '1350000.00'
    assert body['monthly_payment'] == '62295.65'
    assert body['total_payment'] == '1495095.60'
    assert body['overpayment'] == '145095.60'


def test_calculate_down_payment_percent(client, installment_car):
    car = installment_car(price=Decimal('2000000.00'))
    body = calculate(client, car.id, down_payment_percent='25').json()
    assert body['down_payment'] == '500000.00'
    assert body['down_payment_percent'] == '25.00'
    assert body['loan_amount'] == '1500000.00'
    assert body['monthly_payment'] == str(independent_monthly('1500000', '12', 12))


def test_calculate_without_down_payment_uses_minimum(client, installment_car):
    car = installment_car(price=Decimal('1000000.00'), min_down_payment_percent=Decimal('30'))
    body = calculate(client, car.id).json()
    assert body['down_payment'] == '300000.00'
    assert body['down_payment_percent'] == '30.00'
    assert body['loan_amount'] == '700000.00'


def test_calculate_both_down_payment_forms_400(client, installment_car):
    car = installment_car()
    assert calculate(client, car.id, down_payment='1000', down_payment_percent='10').status_code == 400


def test_calculate_zero_rate(client, installment_car):
    car = installment_car(price=Decimal('1200000.00'), installment_rate_percent=Decimal('0'))
    body = calculate(client, car.id).json()
    assert body['monthly_payment'] == '100000.00'
    assert body['total_payment'] == '1200000.00'
    assert body['overpayment'] == '0.00'


@pytest.mark.parametrize('price,months', [('1000', 7), ('100', 120), ('1000.10', 9), ('999.99', 11)])
def test_calculate_zero_rate_overpayment_not_negative(client, installment_car, price, months):
    car = installment_car(price=Decimal(price), installment_rate_percent=Decimal('0'))
    body = calculate(client, car.id, term_months=months).json()
    assert Decimal(body['overpayment']) >= 0
    assert Decimal(body['total_payment']) >= Decimal(body['loan_amount'])


def test_calculate_rounding_half_up(client, installment_car):
    # 1000.10 / 4 = 250.025 -> half-up 250.03 (банковское округление дало бы 250.02)
    car = installment_car(price=Decimal('1000.10'), installment_rate_percent=Decimal('0'), max_term_months=12)
    response = calculate(client, car.id, term_months=6)
    assert response.json()['monthly_payment'] == str((Decimal('1000.10') / 6).quantize(Decimal('0.01'), ROUND_HALF_UP))


def test_calculate_usd_car(client, installment_car):
    car = installment_car(price=Decimal('25000.00'), currency=Currency.USD, installment_rate_percent=Decimal('0'))
    body = calculate(client, car.id, term_months=10).json()
    assert body['currency'] == 'USD'
    assert body['monthly_payment'] == '2500.00'


def test_calculate_no_float_artifacts(client, installment_car):
    car = installment_car(price=Decimal('777777.77'), installment_rate_percent=Decimal('13.37'))
    body = calculate(client, car.id, term_months=37, down_payment_percent='12.34').json()
    for field in (
        'price',
        'down_payment',
        'down_payment_percent',
        'loan_amount',
        'monthly_payment',
        'total_payment',
        'overpayment',
    ):
        assert isinstance(body[field], str)
        assert len(body[field].split('.')[1]) == 2, (field, body[field])


# ---------- calculate: условия авто ----------


def test_calculate_car_without_terms_uses_defaults(client, make_car, salon_settings):
    car = make_car(price=Decimal('1000000.00'))
    body = calculate(client, car.id, term_months=36).json()
    terms = body['terms']
    assert Decimal(terms['min_down_payment_percent']) == Decimal('30')
    assert terms['max_term_months'] == 36
    assert terms['min_term_months'] == 6
    assert Decimal(terms['installment_rate_percent']) == Decimal('0')
    assert body['down_payment'] == '300000.00'
    assert body['loan_amount'] == '700000.00'


def test_calculate_uses_changed_salon_defaults(client, db, make_car, salon_settings):
    salon_settings.default_min_down_payment_percent = Decimal('40')
    salon_settings.default_max_term_months = 24
    salon_settings.default_installment_rate_percent = Decimal('15')
    db.commit()
    car = make_car(price=Decimal('1000000.00'))
    body = calculate(client, car.id, term_months=24).json()
    assert body['down_payment'] == '400000.00'
    assert Decimal(body['annual_rate']) == Decimal('15')
    assert body['monthly_payment'] == str(independent_monthly('600000', '15', 24))
    assert calculate(client, car.id, term_months=25).status_code == 422


def test_calculate_car_own_terms_override_defaults(client, make_car, salon_settings):
    car = make_car(min_down_payment_percent=Decimal('10'), max_term_months=60)
    body = calculate(client, car.id, term_months=60).json()
    assert Decimal(body['terms']['min_down_payment_percent']) == Decimal('10')
    assert body['terms']['max_term_months'] == 60


def test_calculate_without_salon_settings_uses_builtin_defaults(client, make_car):
    car = make_car()
    body = calculate(client, car.id, term_months=36).json()
    assert Decimal(body['terms']['min_down_payment_percent']) == Decimal('30')
    assert body['terms']['max_term_months'] == 36


def test_calculate_installment_unavailable_400(client, installment_car):
    car = installment_car(installment_available=False)
    response = calculate(client, car.id)
    assert response.status_code == 400
    assert response.json()['detail'] == 'Для этого авто рассрочка недоступна'


def test_calculate_down_payment_percent_below_minimum_422(client, installment_car):
    car = installment_car(min_down_payment_percent=Decimal('30'))
    response = calculate(client, car.id, down_payment_percent='29.99')
    assert response.status_code == 422
    assert response.json()['detail'] == 'Минимальный первый взнос для этого авто — 30%'


def test_calculate_down_payment_amount_below_minimum_422(client, installment_car):
    car = installment_car(price=Decimal('1000000.00'), min_down_payment_percent=Decimal('12.5'))
    response = calculate(client, car.id, down_payment='124999.99')
    assert response.status_code == 422
    assert response.json()['detail'] == 'Минимальный первый взнос для этого авто — 12.5%'
    assert calculate(client, car.id, down_payment='125000').status_code == 200


def test_calculate_term_above_maximum_422(client, installment_car):
    car = installment_car(max_term_months=24)
    response = calculate(client, car.id, term_months=25)
    assert response.status_code == 422
    assert response.json()['detail'] == 'Срок рассрочки для этого авто — от 6 до 24 мес.'
    assert calculate(client, car.id, term_months=24).status_code == 200


def test_calculate_term_below_minimum_422(client, installment_car):
    response = calculate(client, installment_car().id, term_months=5)
    assert response.status_code == 422
    assert 'от 6 до 120 мес.' in response.json()['detail']


@pytest.mark.parametrize('down_payment', ['1000000', '1000001'])
def test_calculate_down_payment_not_less_than_price_400(client, installment_car, down_payment):
    car = installment_car(price=Decimal('1000000.00'))
    assert calculate(client, car.id, down_payment=down_payment).status_code == 400


def test_calculate_down_payment_percent_100_400(client, installment_car):
    assert calculate(client, installment_car().id, down_payment_percent='100').status_code == 400


# ---------- calculate: доступ и валидация ----------


def test_calculate_anonymous_ok(client, installment_car):
    assert calculate(client, installment_car().id).status_code == 200


def test_calculate_as_client_ok(client, installment_car, client_user, auth_headers):
    assert calculate(client, installment_car().id, auth_headers(client_user)).status_code == 200


def test_calculate_sold_car_404(client, installment_car):
    assert calculate(client, installment_car(status=CarStatus.sold).id).status_code == 404


def test_calculate_deleted_car_404(client, installment_car):
    car = installment_car(deleted_at=datetime.now(timezone.utc))
    assert calculate(client, car.id).status_code == 404


def test_calculate_unknown_car_404(client):
    assert calculate(client, 9999).status_code == 404


def test_calculate_missing_car_id_422(client):
    assert client.post('/credit/calculate', json={'term_months': 12}).status_code == 422


@pytest.mark.parametrize('term', [0, 121, -3])
def test_calculate_term_out_of_schema_range_422(client, installment_car, term):
    assert calculate(client, installment_car().id, term_months=term).status_code == 422


@pytest.mark.parametrize(
    'payload', [{'down_payment': '-1'}, {'down_payment_percent': '-1'}, {'down_payment_percent': '101'}]
)
def test_calculate_invalid_down_payment_422(client, installment_car, payload):
    assert calculate(client, installment_car().id, **payload).status_code == 422


def test_calculate_client_rate_ignored(client, installment_car):
    car = installment_car(installment_rate_percent=Decimal('12'))
    body = calculate(client, car.id, annual_rate='0').json()
    assert Decimal(body['annual_rate']) == Decimal('12')


# ---------- compare ----------


def compare(client, car_ids, headers=None, **extra):
    return client.post('/credit/compare', json={'car_ids': car_ids, **extra}, headers=headers or {})


def test_compare_two_ok_with_terms(client, make_car):
    first, second = make_car(), make_car(max_term_months=60)
    response = compare(client, [first.id, second.id])
    assert response.status_code == 200
    body = response.json()
    assert [item['car']['id'] for item in body] == [first.id, second.id]
    assert [item['car']['installment']['max_term_months'] for item in body] == [36, 60]
    assert [item['credit'] for item in body] == [None, None]


def test_compare_four_ok_keeps_order(client, make_car):
    cars = [make_car() for _ in range(4)]
    ids = [cars[2].id, cars[0].id, cars[3].id, cars[1].id]
    response = compare(client, ids)
    assert response.status_code == 200
    assert [item['car']['id'] for item in response.json()] == ids


@pytest.mark.parametrize('count', [0, 1, 5])
def test_compare_wrong_count_422(client, make_car, count):
    assert compare(client, [make_car().id for _ in range(count)]).status_code == 422


def test_compare_duplicates_400(client, make_car):
    car = make_car()
    assert compare(client, [car.id, car.id]).status_code == 400


def test_compare_hidden_car_404(client, make_car):
    visible = make_car()
    assert compare(client, [visible.id, make_car(status=CarStatus.sold).id]).status_code == 404


def test_compare_unknown_car_404(client, make_car):
    assert compare(client, [make_car().id, 9999]).status_code == 404


def test_compare_with_credit_uses_each_car_terms(client, installment_car):
    cheap = installment_car(price=Decimal('1000000.00'), installment_rate_percent=Decimal('12'))
    expensive = installment_car(price=Decimal('2000000.00'), installment_rate_percent=Decimal('0'))
    response = compare(client, [cheap.id, expensive.id], term_months=12, down_payment_percent='10')
    assert response.status_code == 200
    first, second = (item['credit'] for item in response.json())
    assert first['down_payment'] == '100000.00'
    assert first['monthly_payment'] == str(independent_monthly('900000', '12', 12))
    assert second['down_payment'] == '200000.00'
    assert second['monthly_payment'] == '150000.00'


def test_compare_without_percent_uses_each_car_minimum(client, installment_car):
    first = installment_car(price=Decimal('1000000.00'), min_down_payment_percent=Decimal('10'))
    second = installment_car(price=Decimal('1000000.00'), min_down_payment_percent=Decimal('40'))
    credits = [item['credit'] for item in compare(client, [first.id, second.id], term_months=12).json()]
    assert [credit['down_payment'] for credit in credits] == ['100000.00', '400000.00']


def test_compare_car_errors_do_not_break_comparison(client, installment_car):
    ok = installment_car()
    unavailable = installment_car(installment_available=False)
    short = installment_car(max_term_months=12)
    response = compare(client, [ok.id, unavailable.id, short.id], term_months=24)
    assert response.status_code == 200
    first, second, third = response.json()
    assert first['credit'] is not None and first['credit_error'] is None
    assert second['credit'] is None and second['credit_error'] == 'Для этого авто рассрочка недоступна'
    assert third['credit'] is None and third['credit_error'] == 'Срок рассрочки для этого авто — от 6 до 12 мес.'


def test_compare_percent_without_term_400(client, make_car):
    assert compare(client, [make_car().id, make_car().id], down_payment_percent='30').status_code == 400


# ---------- PUT /car/installment ----------


def update_installment(client, car_id, headers, **payload):
    return client.put(f'/car/installment/{car_id}', json=payload, headers=headers)


@pytest.mark.parametrize('role', ['seller', 'admin'])
def test_installment_update_by_staff(client, db, make_car, auth_headers, salon_settings, role, request):
    user = request.getfixturevalue(role)
    car = make_car()
    response = update_installment(
        client,
        car.id,
        auth_headers(user),
        min_down_payment_percent='20',
        max_term_months=48,
        installment_rate_percent='9.5',
    )
    assert response.status_code == 200
    body = response.json()
    assert Decimal(body['min_down_payment_percent']) == Decimal('20')
    assert body['max_term_months'] == 48
    assert Decimal(body['installment_rate_percent']) == Decimal('9.5')
    assert body['installment']['max_term_months'] == 48
    db.refresh(car)
    assert car.max_term_months == 48


def test_installment_update_client_403(client, make_car, client_user, auth_headers):
    car = make_car()
    response = update_installment(client, car.id, auth_headers(client_user), max_term_months=48)
    assert response.status_code == 403


def test_installment_update_anonymous_401(client, make_car):
    assert client.put(f'/car/installment/{make_car().id}', json={'max_term_months': 48}).status_code == 401


def test_installment_update_disable(client, make_car, seller, auth_headers):
    car = make_car()
    response = update_installment(client, car.id, auth_headers(seller), installment_available=False)
    assert response.status_code == 200
    assert response.json()['installment']['installment_available'] is False
    assert calculate(client, car.id).status_code == 400


def test_installment_update_null_resets_to_default(client, make_car, seller, auth_headers, salon_settings):
    car = make_car(max_term_months=60)
    response = update_installment(client, car.id, auth_headers(seller), max_term_months=None)
    assert response.status_code == 200
    assert response.json()['max_term_months'] is None
    assert response.json()['installment']['max_term_months'] == 36


def test_installment_update_available_null_400(client, make_car, seller, auth_headers):
    response = update_installment(client, make_car().id, auth_headers(seller), installment_available=None)
    assert response.status_code == 400


@pytest.mark.parametrize(
    'payload',
    [
        {'min_down_payment_percent': '-1'},
        {'min_down_payment_percent': '100.01'},
        {'installment_rate_percent': '-0.5'},
        {'max_term_months': 0},
        {'max_term_months': 121},
    ],
)
def test_installment_update_invalid_values_422(client, make_car, seller, auth_headers, payload):
    assert update_installment(client, make_car().id, auth_headers(seller), **payload).status_code == 422


def test_installment_update_max_term_below_min_term_422(client, make_car, seller, auth_headers, salon_settings):
    response = update_installment(client, make_car().id, auth_headers(seller), max_term_months=5)
    assert response.status_code == 422
    assert response.json()['detail'] == 'Максимальный срок рассрочки не может быть меньше 6 мес.'


def test_installment_update_sold_car_409(client, make_car, seller, auth_headers):
    car = make_car(status=CarStatus.sold)
    assert update_installment(client, car.id, auth_headers(seller), max_term_months=24).status_code == 409


def test_installment_update_deleted_car_404(client, make_car, seller, auth_headers):
    car = make_car(deleted_at=datetime.now(timezone.utc))
    assert update_installment(client, car.id, auth_headers(seller), max_term_months=24).status_code == 404


def test_installment_update_writes_audit_log(client, db, make_car, seller, auth_headers):
    car = make_car(min_down_payment_percent=Decimal('30'))
    update_installment(client, car.id, auth_headers(seller), min_down_payment_percent='20', installment_available=True)
    log_db = db.query(AuditLog).filter(AuditLog.action == 'car_installment_update').one()
    assert log_db.user_id == seller.id
    assert log_db.entity_name == 'car'
    assert log_db.entity_id == car.id
    # installment_available не менялся — в журнал попадает только изменённое поле
    assert log_db.old_value == {'min_down_payment_percent': '30.00'}
    assert log_db.new_value == {'min_down_payment_percent': '20'}


def test_installment_update_without_changes_no_audit_log(client, db, make_car, seller, auth_headers):
    car = make_car(max_term_months=24)
    assert update_installment(client, car.id, auth_headers(seller), max_term_months=24).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action == 'car_installment_update').count() == 0


def test_car_detail_shows_installment_terms(client, make_car, salon_settings):
    car = make_car(installment_rate_percent=Decimal('7'))
    body = client.get('/car/detail', params={'car_id': car.id}).json()
    assert body['installment_available'] is True
    assert body['min_down_payment_percent'] is None
    assert Decimal(body['installment_rate_percent']) == Decimal('7')
    assert body['installment'] == {
        'installment_available': True,
        'min_down_payment_percent': '30.00',
        'min_term_months': 6,
        'max_term_months': 36,
        'installment_rate_percent': '7.00',
    }


def test_car_create_and_update_ignore_installment_fields(client, make_car, seller, auth_headers):
    car = make_car()
    response = client.put(
        f'/car/update/{car.id}', json={'color': 'White', 'max_term_months': 99}, headers=auth_headers(seller)
    )
    assert response.status_code == 200
    assert response.json()['max_term_months'] is None


# ---------- значения по умолчанию салона ----------


def test_settings_public(client, salon_settings):
    response = client.get('/credit/settings')
    assert response.status_code == 200
    assert response.json() == {
        'default_min_down_payment_percent': '30.00',
        'default_max_term_months': 36,
        'default_installment_rate_percent': '0.00',
        'min_term_months': 6,
    }


def test_settings_update_by_admin_with_audit(client, db, admin, auth_headers, salon_settings):
    response = client.put(
        '/credit/settings/update',
        json={'default_min_down_payment_percent': '25', 'default_installment_rate_percent': '14'},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    assert response.json()['default_min_down_payment_percent'] == '25.00'
    log_db = db.query(AuditLog).filter(AuditLog.action == 'installment_settings_update').one()
    assert log_db.user_id == admin.id
    assert log_db.old_value == {'default_min_down_payment_percent': '30.00', 'default_installment_rate_percent': '0.00'}
    assert log_db.new_value == {'default_min_down_payment_percent': '25', 'default_installment_rate_percent': '14'}


@pytest.mark.parametrize('role', ['seller', 'client_user'])
def test_settings_update_not_admin_403(client, auth_headers, salon_settings, role, request):
    user = request.getfixturevalue(role)
    response = client.put('/credit/settings/update', json={'min_term_months': 3}, headers=auth_headers(user))
    assert response.status_code == 403


def test_settings_update_max_below_min_422(client, admin, auth_headers, salon_settings):
    response = client.put('/credit/settings/update', json={'min_term_months': 40}, headers=auth_headers(admin))
    assert response.status_code == 422


def test_settings_update_null_400(client, admin, auth_headers, salon_settings):
    response = client.put('/credit/settings/update', json={'min_term_months': None}, headers=auth_headers(admin))
    assert response.status_code == 400


def test_settings_update_without_settings_404(client, admin, auth_headers):
    response = client.put('/credit/settings/update', json={'min_term_months': 3}, headers=auth_headers(admin))
    assert response.status_code == 404
