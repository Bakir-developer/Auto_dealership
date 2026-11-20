import logging
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum as PyEnum
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mysite.api.car import get_car_or_404
from mysite.api.dependencies import get_current_user, require_role
from mysite.api.notification import create_notification
from mysite.db.database import get_db
from mysite.db.models import (
    AuditLog,
    Car,
    CarStatus,
    Deal,
    DealStatus,
    DiscountRequest,
    DiscountStatus,
    NotificationType,
    SalonSettings,
    UserProfile,
    UserRole,
)
from mysite.db.schema import DealCancelSchema, DealCreateSchema, DealDetailSchema, DealListSchema

deal_router = APIRouter(prefix='/deal', tags=['Deal'])

logger = logging.getLogger(__name__)

CENT = Decimal('0.01')
DEFAULT_RESERVATION_HOURS = 48
ACTIVE_DEAL_STATUSES = (DealStatus.new, DealStatus.in_progress, DealStatus.reserved, DealStatus.paid)
EDITABLE_DEAL_STATUSES = (DealStatus.new, DealStatus.in_progress, DealStatus.reserved)
DEAL_TRANSITIONS = {
    DealStatus.new: (DealStatus.in_progress, DealStatus.cancelled),
    DealStatus.in_progress: (DealStatus.reserved, DealStatus.cancelled),
    DealStatus.reserved: (DealStatus.paid, DealStatus.cancelled),
    DealStatus.paid: (DealStatus.delivered, DealStatus.cancelled),
}
EXPIRED_REASON = 'Срок брони истёк'
SOLD_REASON = 'Автомобиль продан'


# ---------- Хелперы ----------


def calc_final_price(base_price: Decimal, discount_percent: Decimal) -> Decimal:
    return (base_price * (Decimal('100') - discount_percent) / Decimal('100')).quantize(CENT, rounding=ROUND_HALF_UP)


def to_audit_value(value):
    """Приводит значение к JSON-совместимому виду: Decimal -> str, datetime -> ISO UTC, Enum -> value."""
    if isinstance(value, PyEnum):
        return value.value
    if isinstance(value, Decimal):
        return f'{value:f}'
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return value


def create_audit_log(
    db: Session,
    user_id: int | None,
    action: str,
    entity_name: str,
    entity_id: int | None,
    old_value: dict | None = None,
    new_value: dict | None = None,
):
    """Добавляет запись журнала в сессию без commit — запись живёт в транзакции действия."""
    audit_log_db = AuditLog(
        user_id=user_id,
        action=action,
        entity_name=entity_name,
        entity_id=entity_id,
        old_value={key: to_audit_value(value) for key, value in old_value.items()} if old_value is not None else None,
        new_value={key: to_audit_value(value) for key, value in new_value.items()} if new_value is not None else None,
    )
    db.add(audit_log_db)


def format_utc(value: datetime) -> str:
    return value.strftime('%d.%m.%Y %H:%M UTC')


def get_reservation_hours(db: Session) -> int:
    hours = db.query(SalonSettings.reservation_hours).filter(SalonSettings.id == 1).scalar()
    if hours is None or not 1 <= hours <= 720:
        return DEFAULT_RESERVATION_HOURS
    return hours


def visible_deals_query(db: Session, current_user: UserProfile):
    """Сделки, доступные пользователю: admin — все, seller — свои, client — свои (как покупатель)."""
    query = db.query(Deal).filter(Deal.deleted_at.is_(None))
    if current_user.role == UserRole.seller:
        query = query.filter(Deal.seller_id == current_user.id)
    elif current_user.role == UserRole.client:
        query = query.filter(Deal.client_id == current_user.id)
    return query


def get_deal_or_404(deal_id: int, db: Session, current_user: UserProfile) -> Deal:
    deal_db = visible_deals_query(db, current_user).filter(Deal.id == deal_id).first()
    if not deal_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Сделка не найдена')
    return deal_db


def check_transition(deal_db: Deal, to_status: DealStatus):
    if to_status not in DEAL_TRANSITIONS.get(deal_db.status, ()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Недопустимый переход статуса сделки')


def update_deal_status(
    db: Session, deal_id: int, from_status: DealStatus, to_status: DealStatus, extra_filters: tuple = (), **fields
) -> int:
    """Атомарный условный UPDATE: сработает, только если статус сделки ещё from_status
    (и выполнены extra_filters)."""
    return (
        db.query(Deal)
        .filter(Deal.id == deal_id, Deal.status == from_status, Deal.deleted_at.is_(None), *extra_filters)
        .update({'status': to_status, **fields}, synchronize_session=False)
    )


def change_deal_status(
    db: Session, deal_db: Deal, from_status: DealStatus, to_status: DealStatus, extra_filters: tuple = (), **fields
):
    updated = update_deal_status(db, deal_db.id, from_status, to_status, extra_filters, **fields)
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Недопустимый переход статуса сделки')
    db.refresh(deal_db)


def release_car(db: Session, car_id: int) -> bool:
    """reserved -> available; если авто уже не reserved — ничего не делаем."""
    updated = (
        db.query(Car)
        .filter(Car.id == car_id, Car.status == CarStatus.reserved)
        .update({'status': CarStatus.available}, synchronize_session=False)
    )
    return updated > 0


def reject_pending_discounts(db: Session, deal_db: Deal, decided_by_id: int | None, reason: str, notify: bool = True):
    """Все pending-запросы скидки по сделке -> rejected (сделка отменена или удалена)."""
    now = datetime.now(timezone.utc)
    discounts_db = (
        db.query(DiscountRequest)
        .filter(DiscountRequest.deal_id == deal_db.id, DiscountRequest.status == DiscountStatus.pending)
        .all()
    )
    for discount_db in discounts_db:
        discount_db.status = DiscountStatus.rejected
        discount_db.decided_by_id = decided_by_id
        discount_db.decided_at = now
        if notify and discount_db.seller_id != decided_by_id:
            create_notification(
                db,
                discount_db.seller_id,
                NotificationType.discount,
                f'Скидка {discount_db.requested_percent}% по сделке #{deal_db.id} отклонена: {reason}',
            )


def cancel_deal_internal(db: Session, deal_db: Deal, cancel_reason: str, user_id: int | None):
    """Отмена сделки: статус, освобождение авто, отклонение pending-скидок. Без commit.
    Возвращает (старый статус, освобождено ли авто)."""
    old_status = deal_db.status
    car_id = deal_db.car_id
    change_deal_status(db, deal_db, old_status, DealStatus.cancelled, cancel_reason=cancel_reason)
    car_released = False
    if old_status in (DealStatus.reserved, DealStatus.paid):
        car_released = release_car(db, car_id)
    reject_pending_discounts(db, deal_db, user_id, 'сделка отменена')
    return old_status, car_released


def expire_deal(db: Session, deal_db: Deal) -> bool:
    """Отмена просроченной брони системой. Без commit; False — сделку уже перевели другим действием."""
    reserved_until = deal_db.reserved_until
    car_id = deal_db.car_id
    updated = update_deal_status(
        db, deal_db.id, DealStatus.reserved, DealStatus.cancelled, cancel_reason=EXPIRED_REASON
    )
    if updated == 0:
        return False
    car_released = release_car(db, car_id)
    reject_pending_discounts(db, deal_db, None, 'сделка отменена')
    text = f'Бронь по сделке #{deal_db.id} истекла, сделка отменена'
    create_notification(db, deal_db.seller_id, NotificationType.reservation, text)
    create_notification(db, deal_db.client_id, NotificationType.reservation, text)
    create_audit_log(
        db,
        None,
        'deal_expire',
        'deal',
        deal_db.id,
        {'status': DealStatus.reserved, 'reserved_until': reserved_until},
        {
            'status': DealStatus.cancelled,
            'cancel_reason': EXPIRED_REASON,
            **({'car_status': CarStatus.available} if car_released else {}),
        },
    )
    return True


def expire_reservations(db: Session) -> int:
    """Отменяет сделки с истёкшей бронью. Commit по одной сделке; сбой одной не блокирует остальные."""
    now = datetime.now(timezone.utc)
    deal_ids = [
        deal_id
        for (deal_id,) in db.query(Deal.id)
        .filter(Deal.status == DealStatus.reserved, Deal.deleted_at.is_(None), Deal.reserved_until <= now)
        .all()
    ]
    count = 0
    for deal_id in deal_ids:
        try:
            deal_db = db.query(Deal).filter(Deal.id == deal_id).first()
            if deal_db is not None and expire_deal(db, deal_db):
                db.commit()
                count += 1
            else:
                db.rollback()
        except Exception:
            db.rollback()
            logger.exception('Не удалось отменить просроченную бронь по сделке #%s', deal_id)
    return count


# ---------- Deal ----------


@deal_router.post('/create', response_model=DealDetailSchema)
async def create_deal(
    deal_data: DealCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    car_db = get_car_or_404(deal_data.car_id, db)
    client_db = (
        db.query(UserProfile)
        .filter(
            UserProfile.id == deal_data.client_id,
            UserProfile.role == UserRole.client,
            UserProfile.is_active.is_(True),
        )
        .first()
    )
    if not client_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Клиент не найден')

    if current_user.role == UserRole.admin:
        if deal_data.seller_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Укажите продавца')
        seller_db = (
            db.query(UserProfile)
            .filter(
                UserProfile.id == deal_data.seller_id,
                UserProfile.role == UserRole.seller,
                UserProfile.is_active.is_(True),
            )
            .first()
        )
        if not seller_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Продавец не найден')
        seller_id = seller_db.id
    else:
        seller_id = current_user.id

    if car_db.status not in (CarStatus.available, CarStatus.in_transit):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Автомобиль недоступен для сделки')

    duplicate_db = (
        db.query(Deal.id)
        .filter(
            Deal.car_id == car_db.id,
            Deal.client_id == client_db.id,
            Deal.status.in_(ACTIVE_DEAL_STATUSES),
            Deal.deleted_at.is_(None),
        )
        .first()
    )
    if duplicate_db:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='У клиента уже есть активная сделка по этому автомобилю'
        )

    deal_db = Deal(
        car_id=car_db.id,
        client_id=client_db.id,
        seller_id=seller_id,
        base_price=car_db.price,
        discount_percent=Decimal('0'),
        final_price=car_db.price,
        currency=car_db.currency,
        status=DealStatus.new,
    )
    db.add(deal_db)
    db.flush()

    create_notification(
        db, client_db.id, NotificationType.deal, f'Создана сделка #{deal_db.id} по автомобилю #{car_db.id}'
    )
    if seller_id != current_user.id:
        create_notification(db, seller_id, NotificationType.deal, f'Вам назначена сделка #{deal_db.id}')
    create_audit_log(
        db,
        current_user.id,
        'deal_create',
        'deal',
        deal_db.id,
        None,
        {
            'car_id': deal_db.car_id,
            'client_id': deal_db.client_id,
            'seller_id': deal_db.seller_id,
            'base_price': deal_db.base_price,
            'final_price': deal_db.final_price,
            'currency': deal_db.currency,
            'status': deal_db.status,
        },
    )
    db.commit()
    db.refresh(deal_db)
    return deal_db


@deal_router.get('/list', response_model=List[DealListSchema])
async def list_deal(
    status_filter: DealStatus | None = Query(None, alias='status'),
    car_id: int | None = None,
    client_id: int | None = None,
    seller_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    query = visible_deals_query(db, current_user)
    if status_filter is not None:
        query = query.filter(Deal.status == status_filter)
    if car_id is not None:
        query = query.filter(Deal.car_id == car_id)
    if current_user.role != UserRole.client and client_id is not None:
        query = query.filter(Deal.client_id == client_id)
    if current_user.role == UserRole.admin and seller_id is not None:
        query = query.filter(Deal.seller_id == seller_id)
    return query.order_by(Deal.created_at.desc(), Deal.id.desc()).offset(skip).limit(limit).all()


@deal_router.get('/detail', response_model=DealDetailSchema)
async def detail_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    return get_deal_or_404(deal_id, db, current_user)


@deal_router.post('/start/{deal_id}', response_model=DealDetailSchema)
async def start_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    deal_db = get_deal_or_404(deal_id, db, current_user)
    check_transition(deal_db, DealStatus.in_progress)

    change_deal_status(db, deal_db, DealStatus.new, DealStatus.in_progress)
    create_audit_log(
        db,
        current_user.id,
        'deal_start',
        'deal',
        deal_id,
        {'status': DealStatus.new},
        {'status': DealStatus.in_progress},
    )
    db.commit()
    db.refresh(deal_db)
    return deal_db


@deal_router.post('/reserve/{deal_id}', response_model=DealDetailSchema)
async def reserve_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    deal_db = get_deal_or_404(deal_id, db, current_user)
    check_transition(deal_db, DealStatus.reserved)

    car_id = deal_db.car_id
    client_id = deal_db.client_id
    reserved_until = datetime.now(timezone.utc) + timedelta(hours=get_reservation_hours(db))
    change_deal_status(db, deal_db, DealStatus.in_progress, DealStatus.reserved, reserved_until=reserved_until)

    # атомарно: SQLite без блокировки строк, второй покупатель получит rowcount == 0
    updated = (
        db.query(Car)
        .filter(Car.id == car_id, Car.status == CarStatus.available, Car.deleted_at.is_(None))
        .update({'status': CarStatus.reserved}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        car_status = db.query(Car.status).filter(Car.id == car_id, Car.deleted_at.is_(None)).scalar()
        if car_status == CarStatus.reserved:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Авто уже забронировано')
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Автомобиль недоступен для брони')

    create_notification(
        db,
        client_id,
        NotificationType.reservation,
        f'Автомобиль по сделке #{deal_id} забронирован до {format_utc(reserved_until)}',
    )
    create_audit_log(
        db,
        current_user.id,
        'deal_reserve',
        'deal',
        deal_id,
        {'status': DealStatus.in_progress, 'car_status': CarStatus.available},
        {'status': DealStatus.reserved, 'reserved_until': reserved_until, 'car_status': CarStatus.reserved},
    )
    db.commit()
    db.refresh(deal_db)
    return deal_db


@deal_router.post('/pay/{deal_id}', response_model=DealDetailSchema)
async def pay_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    deal_db = get_deal_or_404(deal_id, db, current_user)
    check_transition(deal_db, DealStatus.paid)

    now = datetime.now(timezone.utc)
    reserved_until = deal_db.reserved_until
    if reserved_until is not None:
        if reserved_until.tzinfo is None:
            reserved_until = reserved_until.replace(tzinfo=timezone.utc)
        if reserved_until <= now:
            if expire_deal(db, deal_db):
                db.commit()
            else:
                db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Срок брони истёк')

    pending_db = (
        db.query(DiscountRequest.id)
        .filter(DiscountRequest.deal_id == deal_id, DiscountRequest.status == DiscountStatus.pending)
        .first()
    )
    if pending_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Есть нерассмотренный запрос на скидку')

    change_deal_status(db, deal_db, DealStatus.reserved, DealStatus.paid, (Deal.reserved_until > now,), paid_at=now)
    create_notification(db, deal_db.client_id, NotificationType.deal, f'Оплата по сделке #{deal_id} получена')
    create_audit_log(
        db,
        current_user.id,
        'deal_pay',
        'deal',
        deal_id,
        {'status': DealStatus.reserved},
        {'status': DealStatus.paid, 'paid_at': now, 'car_status': CarStatus.reserved},
    )
    db.commit()
    db.refresh(deal_db)
    return deal_db


@deal_router.post('/deliver/{deal_id}', response_model=DealDetailSchema)
async def deliver_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    deal_db = get_deal_or_404(deal_id, db, current_user)
    check_transition(deal_db, DealStatus.delivered)

    car_id = deal_db.car_id
    now = datetime.now(timezone.utc)
    change_deal_status(db, deal_db, DealStatus.paid, DealStatus.delivered, delivered_at=now)

    updated = (
        db.query(Car)
        .filter(Car.id == car_id, Car.status == CarStatus.reserved)
        .update({'status': CarStatus.sold}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Некорректный статус автомобиля')

    create_notification(db, deal_db.client_id, NotificationType.deal, f'Сделка #{deal_id} завершена, автомобиль выдан')
    create_audit_log(
        db,
        current_user.id,
        'deal_deliver',
        'deal',
        deal_id,
        {'status': DealStatus.paid},
        {'status': DealStatus.delivered, 'delivered_at': now, 'car_status': CarStatus.sold},
    )

    other_deals_db = (
        db.query(Deal)
        .filter(
            Deal.car_id == car_id,
            Deal.id != deal_id,
            Deal.status.in_((DealStatus.new, DealStatus.in_progress)),
            Deal.deleted_at.is_(None),
        )
        .all()
    )
    for other_deal_db in other_deals_db:
        old_status = other_deal_db.status
        other_deal_id = other_deal_db.id
        # условный UPDATE: если сделку уже перевели другим действием — пропускаем, выдачу это не ломает
        if update_deal_status(db, other_deal_id, old_status, DealStatus.cancelled, cancel_reason=SOLD_REASON) == 0:
            continue
        reject_pending_discounts(db, other_deal_db, current_user.id, 'сделка отменена')
        text = f'Сделка #{other_deal_db.id} отменена: автомобиль продан'
        create_notification(db, other_deal_db.client_id, NotificationType.deal, text)
        if other_deal_db.seller_id != current_user.id:
            create_notification(db, other_deal_db.seller_id, NotificationType.deal, text)
        create_audit_log(
            db,
            current_user.id,
            'deal_cancel',
            'deal',
            other_deal_db.id,
            {'status': old_status},
            {'status': DealStatus.cancelled, 'cancel_reason': SOLD_REASON},
        )

    db.commit()
    db.refresh(deal_db)
    return deal_db


@deal_router.post('/cancel/{deal_id}', response_model=DealDetailSchema)
async def cancel_deal(
    deal_id: int,
    deal_data: DealCancelSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    deal_db = get_deal_or_404(deal_id, db, current_user)
    check_transition(deal_db, DealStatus.cancelled)
    if current_user.role == UserRole.seller and deal_db.status == DealStatus.paid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Отменить оплаченную сделку может только администратор'
        )

    old_status, car_released = cancel_deal_internal(db, deal_db, deal_data.cancel_reason, current_user.id)

    old_value = {'status': old_status}
    new_value = {'status': DealStatus.cancelled, 'cancel_reason': deal_data.cancel_reason}
    if car_released:
        old_value['car_status'] = CarStatus.reserved
        new_value['car_status'] = CarStatus.available
    create_audit_log(db, current_user.id, 'deal_cancel', 'deal', deal_id, old_value, new_value)

    text = f'Сделка #{deal_id} отменена: {deal_data.cancel_reason}'
    for user_id in {deal_db.client_id, deal_db.seller_id}:
        if user_id != current_user.id:
            create_notification(db, user_id, NotificationType.deal, text)

    db.commit()
    db.refresh(deal_db)
    return deal_db


@deal_router.delete('/delete/{deal_id}', response_model=dict)
async def delete_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    deal_db = get_deal_or_404(deal_id, db, current_user)
    if deal_db.status not in (DealStatus.new, DealStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Удалить можно только новую или отменённую сделку'
        )

    now = datetime.now(timezone.utc)
    updated = (
        db.query(Deal)
        .filter(
            Deal.id == deal_id,
            Deal.status.in_((DealStatus.new, DealStatus.cancelled)),
            Deal.deleted_at.is_(None),
        )
        .update({'deleted_at': now}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Удалить можно только новую или отменённую сделку'
        )

    reject_pending_discounts(db, deal_db, current_user.id, 'сделка удалена', notify=False)
    create_audit_log(db, current_user.id, 'deal_delete', 'deal', deal_id, {'deleted_at': None}, {'deleted_at': now})
    db.commit()
    return {'message': 'Сделка удалена'}
