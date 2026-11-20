from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from mysite.api.deal import (
    EDITABLE_DEAL_STATUSES,
    calc_final_price,
    create_audit_log,
    get_deal_or_404,
)
from mysite.api.dependencies import require_role
from mysite.api.notification import create_notification, notify_active_admins
from mysite.db.database import get_db
from mysite.db.models import Deal, DiscountRequest, DiscountStatus, NotificationType, UserProfile, UserRole
from mysite.db.schema import (
    DiscountRequestCreateSchema,
    DiscountRequestDecisionSchema,
    DiscountRequestDetailSchema,
    DiscountRequestListSchema,
)

discount_router = APIRouter(prefix='/discount', tags=['DiscountRequest'])


def get_discount_request_or_404(discount_request_id: int, db: Session, current_user: UserProfile) -> DiscountRequest:
    """admin — любой запрос, seller — только по своим сделкам; запросы по удалённым сделкам скрыты."""
    query = (
        db.query(DiscountRequest)
        .join(Deal, DiscountRequest.deal_id == Deal.id)
        .filter(DiscountRequest.id == discount_request_id, Deal.deleted_at.is_(None))
    )
    if current_user.role == UserRole.seller:
        query = query.filter(Deal.seller_id == current_user.id)
    discount_request_db = query.first()
    if not discount_request_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Запрос на скидку не найден')
    return discount_request_db


def apply_discount_to_deal(db: Session, deal_db: Deal, percent: Decimal) -> None:
    """Условный UPDATE цены сделки: срабатывает, только пока сделка не оплачена."""
    final_price = calc_final_price(deal_db.base_price, percent)
    if final_price <= 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Итоговая цена должна быть больше нуля')
    updated = (
        db.query(Deal)
        .filter(Deal.id == deal_db.id, Deal.status.in_(EDITABLE_DEAL_STATUSES), Deal.deleted_at.is_(None))
        .update({'discount_percent': percent, 'final_price': final_price}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Скидку можно изменить только до оплаты')


@discount_router.post('/create', response_model=DiscountRequestDetailSchema)
async def create_discount_request(
    discount_request_data: DiscountRequestCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    deal_db = get_deal_or_404(discount_request_data.deal_id, db, current_user)
    if deal_db.status not in EDITABLE_DEAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Скидку можно изменить только до оплаты')

    pending_db = (
        db.query(DiscountRequest.id)
        .filter(DiscountRequest.deal_id == deal_db.id, DiscountRequest.status == DiscountStatus.pending)
        .first()
    )
    if pending_db:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='По сделке уже есть запрос на скидку на рассмотрении'
        )

    percent = discount_request_data.requested_percent
    if percent == deal_db.discount_percent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Эта скидка уже применена')
    if calc_final_price(deal_db.base_price, percent) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Итоговая цена должна быть больше нуля')

    deal_id = deal_db.id
    old_value = {'discount_percent': deal_db.discount_percent, 'final_price': deal_db.final_price}
    discount_request_db = DiscountRequest(
        **discount_request_data.model_dump(), seller_id=deal_db.seller_id, status=DiscountStatus.pending
    )
    auto_approve = current_user.role == UserRole.admin or percent <= current_user.discount_limit

    if auto_approve:
        discount_request_db.status = DiscountStatus.approved
        discount_request_db.decided_by_id = current_user.id
        discount_request_db.decided_at = datetime.now(timezone.utc)
        db.add(discount_request_db)
        db.flush()
        apply_discount_to_deal(db, deal_db, percent)
        db.refresh(deal_db)
        create_audit_log(
            db,
            current_user.id,
            'discount_apply',
            'discount_request',
            discount_request_db.id,
            old_value,
            {'discount_percent': deal_db.discount_percent, 'final_price': deal_db.final_price, 'deal_id': deal_id},
        )
        create_notification(
            db,
            deal_db.client_id,
            NotificationType.deal,
            f'Цена по сделке #{deal_id} изменена: {deal_db.final_price} {deal_db.currency.value}',
        )
    else:
        db.add(discount_request_db)
        db.flush()
        create_audit_log(
            db,
            current_user.id,
            'discount_request',
            'discount_request',
            discount_request_db.id,
            None,
            {
                'deal_id': deal_id,
                'requested_percent': discount_request_db.requested_percent,
                'comment': discount_request_db.comment,
            },
        )
        notify_active_admins(
            db,
            NotificationType.discount,
            f'Запрос скидки {percent}% по сделке #{deal_id} (продавец {current_user.username})',
            current_user.id,
        )

    db.commit()
    db.refresh(discount_request_db)
    return discount_request_db


@discount_router.get('/list', response_model=List[DiscountRequestListSchema])
async def list_discount_request(
    status_filter: DiscountStatus | None = Query(None, alias='status'),
    deal_id: int | None = None,
    seller_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    query = db.query(DiscountRequest).join(Deal, DiscountRequest.deal_id == Deal.id).filter(Deal.deleted_at.is_(None))
    if current_user.role == UserRole.seller:
        query = query.filter(Deal.seller_id == current_user.id)
    if status_filter is not None:
        query = query.filter(DiscountRequest.status == status_filter)
    if deal_id is not None:
        query = query.filter(DiscountRequest.deal_id == deal_id)
    if current_user.role == UserRole.admin and seller_id is not None:
        query = query.filter(DiscountRequest.seller_id == seller_id)
    return query.order_by(DiscountRequest.id.desc()).offset(skip).limit(limit).all()


@discount_router.get('/detail', response_model=DiscountRequestDetailSchema)
async def detail_discount_request(
    discount_request_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    return get_discount_request_or_404(discount_request_id, db, current_user)


@discount_router.post('/approve/{discount_request_id}', response_model=DiscountRequestDetailSchema)
async def approve_discount_request(
    discount_request_id: int,
    discount_request_data: DiscountRequestDecisionSchema | None = None,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    discount_request_db = get_discount_request_or_404(discount_request_id, db, current_user)
    if discount_request_db.status != DiscountStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Запрос уже рассмотрен')

    deal_db = get_deal_or_404(discount_request_db.deal_id, db, current_user)
    if deal_db.status not in EDITABLE_DEAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Скидку можно изменить только до оплаты')

    comment = discount_request_data.comment if discount_request_data else None
    percent = discount_request_db.requested_percent
    deal_id = deal_db.id
    old_value = {
        'status': discount_request_db.status,
        'discount_percent': deal_db.discount_percent,
        'final_price': deal_db.final_price,
    }

    # атомарно: решение принимается один раз
    updated = (
        db.query(DiscountRequest)
        .filter(DiscountRequest.id == discount_request_id, DiscountRequest.status == DiscountStatus.pending)
        .update(
            {
                'status': DiscountStatus.approved,
                'decided_by_id': current_user.id,
                'decided_at': datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Запрос уже рассмотрен')

    apply_discount_to_deal(db, deal_db, percent)
    db.refresh(deal_db)
    create_audit_log(
        db,
        current_user.id,
        'discount_approve',
        'discount_request',
        discount_request_id,
        old_value,
        {
            'status': DiscountStatus.approved,
            'discount_percent': deal_db.discount_percent,
            'final_price': deal_db.final_price,
            'comment': comment,
        },
    )
    if discount_request_db.seller_id != current_user.id:
        create_notification(
            db,
            discount_request_db.seller_id,
            NotificationType.discount,
            f'Скидка {percent}% по сделке #{deal_id} одобрена',
        )
    create_notification(
        db,
        deal_db.client_id,
        NotificationType.deal,
        f'Цена по сделке #{deal_id} изменена: {deal_db.final_price} {deal_db.currency.value}',
    )
    db.commit()
    db.refresh(discount_request_db)
    return discount_request_db


@discount_router.post('/reject/{discount_request_id}', response_model=DiscountRequestDetailSchema)
async def reject_discount_request(
    discount_request_id: int,
    discount_request_data: DiscountRequestDecisionSchema | None = None,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    discount_request_db = get_discount_request_or_404(discount_request_id, db, current_user)
    if discount_request_db.status != DiscountStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Запрос уже рассмотрен')

    comment = discount_request_data.comment if discount_request_data else None
    percent = discount_request_db.requested_percent
    deal_id = discount_request_db.deal_id
    seller_id = discount_request_db.seller_id

    updated = (
        db.query(DiscountRequest)
        .filter(DiscountRequest.id == discount_request_id, DiscountRequest.status == DiscountStatus.pending)
        .update(
            {
                'status': DiscountStatus.rejected,
                'decided_by_id': current_user.id,
                'decided_at': datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Запрос уже рассмотрен')

    create_audit_log(
        db,
        current_user.id,
        'discount_reject',
        'discount_request',
        discount_request_id,
        {'status': DiscountStatus.pending},
        {'status': DiscountStatus.rejected, 'comment': comment},
    )
    text = f'Скидка {percent}% по сделке #{deal_id} отклонена'
    if comment:
        text = f'{text}: {comment}'
    if seller_id != current_user.id:
        create_notification(db, seller_id, NotificationType.discount, text)
    db.commit()
    db.refresh(discount_request_db)
    return discount_request_db


@discount_router.delete('/delete/{discount_request_id}', response_model=dict)
async def delete_discount_request(
    discount_request_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    discount_request_db = get_discount_request_or_404(discount_request_id, db, current_user)
    if current_user.role == UserRole.seller and discount_request_db.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Запрос на скидку не найден')
    if discount_request_db.status != DiscountStatus.pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Рассмотренный запрос удалить нельзя')

    old_value = {
        'deal_id': discount_request_db.deal_id,
        'requested_percent': discount_request_db.requested_percent,
        'status': discount_request_db.status,
    }
    create_audit_log(db, current_user.id, 'discount_withdraw', 'discount_request', discount_request_id, old_value, None)
    deleted = (
        db.query(DiscountRequest)
        .filter(DiscountRequest.id == discount_request_id, DiscountRequest.status == DiscountStatus.pending)
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Рассмотренный запрос удалить нельзя')
    db.expunge(discount_request_db)
    db.commit()
    return {'message': 'Запрос на скидку отозван'}
