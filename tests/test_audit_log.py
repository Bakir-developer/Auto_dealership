import json
from datetime import datetime, timezone
from decimal import Decimal

from mysite.api.deal import create_audit_log, to_audit_value
from mysite.db.models import AuditLog, CarStatus, DealStatus


def test_audit_values_json_serializable(db):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    create_audit_log(
        db,
        None,
        'test_action',
        'deal',
        1,
        {'price': Decimal('1500000.00'), 'at': now},
        {'status': DealStatus.paid, 'car': CarStatus.sold, 'n': 5, 'flag': True, 'none': None, 's': 'x'},
    )
    db.commit()
    log_db = db.query(AuditLog).filter(AuditLog.action == 'test_action').one()
    assert log_db.old_value['price'] == '1500000.00'
    assert log_db.old_value['at'].endswith('+00:00')
    assert log_db.new_value == {'status': 'paid', 'car': 'sold', 'n': 5, 'flag': True, 'none': None, 's': 'x'}
    json.dumps(log_db.old_value)
    json.dumps(log_db.new_value)


def test_to_audit_value_naive_datetime_treated_as_utc():
    assert to_audit_value(datetime(2026, 1, 1, 12, 0)) == '2026-01-01T12:00:00+00:00'


def test_to_audit_value_decimal_no_exponent():
    assert to_audit_value(Decimal('1E+3')) == '1000'
    assert to_audit_value(Decimal('0.50')) == '0.50'


def test_create_audit_log_none_values(db):
    create_audit_log(db, None, 'test_none', 'deal', 1)
    db.commit()
    log_db = db.query(AuditLog).filter(AuditLog.action == 'test_none').one()
    assert log_db.old_value is None
    assert log_db.new_value is None
    assert log_db.user_id is None


def test_audit_log_written_in_same_transaction(client, db, seller, make_car, make_deal, auth_headers):
    car_db = make_car(status=CarStatus.reserved)
    deal_db = make_deal(car=car_db, status=DealStatus.in_progress)
    response = client.post(f'/deal/reserve/{deal_db.id}', headers=auth_headers(seller))
    assert response.status_code == 409
    db.expire_all()
    assert db.query(AuditLog).filter(AuditLog.action == 'deal_reserve').count() == 0


def test_audit_log_full_deal_flow(client, db, seller, client_user, make_car, auth_headers):
    car_db = make_car()
    headers = auth_headers(seller)
    created = client.post('/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=headers)
    deal_id = created.json()['id']
    for action in ('start', 'reserve', 'pay', 'deliver'):
        assert client.post(f'/deal/{action}/{deal_id}', headers=headers).status_code == 200
    db.expire_all()
    logs = (
        db.query(AuditLog).filter(AuditLog.entity_id == deal_id, AuditLog.entity_name == 'deal').order_by(AuditLog.id)
    )
    logs = logs.all()
    assert [log.action for log in logs] == ['deal_create', 'deal_start', 'deal_reserve', 'deal_pay', 'deal_deliver']
    assert all(log.user_id == seller.id for log in logs)
    assert logs[0].old_value is None
    assert logs[0].new_value['status'] == 'new'
    assert logs[2].new_value['car_status'] == 'reserved'
    assert logs[2].new_value['reserved_until'].endswith('+00:00')
    assert logs[4].new_value['car_status'] == 'sold'


def test_audit_log_cancel_records_reason(client, db, seller, make_deal, auth_headers):
    deal_db = make_deal()
    client.post(f'/deal/cancel/{deal_db.id}', json={'cancel_reason': 'нет денег'}, headers=auth_headers(seller))
    db.expire_all()
    log_db = db.query(AuditLog).filter(AuditLog.action == 'deal_cancel', AuditLog.entity_id == deal_db.id).one()
    assert log_db.user_id == seller.id
    assert log_db.new_value['status'] == 'cancelled'
    assert log_db.new_value['cancel_reason'] == 'нет денег'


def test_audit_log_has_no_password(client, db, seller, client_user, make_car, auth_headers):
    car_db = make_car()
    client.post('/deal/create', json={'car_id': car_db.id, 'client_id': client_user.id}, headers=auth_headers(seller))
    db.expire_all()
    dump = ' '.join(f'{log.old_value} {log.new_value}' for log in db.query(AuditLog).all())
    assert 'password' not in dump
