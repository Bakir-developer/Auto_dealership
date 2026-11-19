from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from mysite.api.car import get_car_or_404
from mysite.api.dependencies import get_current_user, require_role
from mysite.api.notification import create_notification, notify_active_sellers
from mysite.db.database import get_db
from mysite.db.models import Lead, LeadNote, LeadStatus, LeadType, NotificationType, UserProfile, UserRole
from mysite.db.schema import (
    LeadAssignSchema,
    LeadCreateSchema,
    LeadDetailSchema,
    LeadListSchema,
    LeadNoteCreateSchema,
    LeadNoteDetailSchema,
    LeadNoteListSchema,
    LeadNoteUpdateSchema,
    LeadUpdateSchema,
)

lead_router = APIRouter(prefix='/lead', tags=['Lead'])
lead_note_router = APIRouter(prefix='/lead-note', tags=['LeadNote'])

ACTIVE_LEAD_STATUSES = (LeadStatus.new, LeadStatus.in_progress)
CLOSED_LEAD_STATUSES = (LeadStatus.closed, LeadStatus.rejected)
LEAD_TRANSITIONS = {
    LeadStatus.new: (LeadStatus.rejected,),
    LeadStatus.in_progress: (LeadStatus.closed, LeadStatus.rejected),
}
LEAD_TYPE_TEXT = {
    LeadType.purchase: 'покупка',
    LeadType.test_drive: 'тест-драйв',
    LeadType.trade_in: 'trade-in',
    LeadType.question: 'вопрос',
}
LEAD_STATUS_TEXT = {LeadStatus.closed: 'закрыта', LeadStatus.rejected: 'отклонена'}


def free_lead_condition():
    return and_(Lead.seller_id.is_(None), Lead.status == LeadStatus.new)


def visible_leads_query(db: Session, current_user: UserProfile):
    """Заявки, доступные пользователю: admin — все, client — свои, seller — свои и свободные."""
    query = db.query(Lead)
    if current_user.role == UserRole.client:
        query = query.filter(Lead.client_id == current_user.id)
    elif current_user.role == UserRole.seller:
        query = query.filter(or_(Lead.seller_id == current_user.id, free_lead_condition()))
    return query


def get_lead_or_404(lead_id: int, db: Session, current_user: UserProfile) -> Lead:
    lead_db = visible_leads_query(db, current_user).filter(Lead.id == lead_id).first()
    if not lead_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Заявка не найдена')
    return lead_db


def get_own_lead_for_notes_or_404(lead_id: int, db: Session, current_user: UserProfile) -> Lead:
    """Для заметок: admin — любая заявка, seller — только своя (не свободная)."""
    query = db.query(Lead).filter(Lead.id == lead_id)
    if current_user.role == UserRole.seller:
        query = query.filter(Lead.seller_id == current_user.id)
    lead_db = query.first()
    if not lead_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Заявка не найдена')
    return lead_db


@lead_router.post('/create', response_model=LeadDetailSchema)
async def create_lead(
    lead_data: LeadCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    if lead_data.car_id is not None:
        get_car_or_404(lead_data.car_id, db, current_user, only_visible=True)
    elif lead_data.lead_type == LeadType.test_drive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Для заявки на тест-драйв укажите автомобиль'
        )

    if lead_data.car_id is not None:
        duplicate_db = (
            db.query(Lead.id)
            .filter(
                Lead.client_id == current_user.id,
                Lead.car_id == lead_data.car_id,
                Lead.lead_type == lead_data.lead_type,
                Lead.status.in_(ACTIVE_LEAD_STATUSES),
            )
            .first()
        )
        if duplicate_db:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail='У вас уже есть активная заявка по этому автомобилю'
            )

    lead_db = Lead(**lead_data.model_dump(), client_id=current_user.id, status=LeadStatus.new, seller_id=None)
    db.add(lead_db)
    db.flush()
    notify_active_sellers(
        db, NotificationType.lead, f'Новая заявка #{lead_db.id} ({LEAD_TYPE_TEXT[lead_db.lead_type]})', current_user.id
    )
    db.commit()
    db.refresh(lead_db)
    return lead_db


@lead_router.get('/list', response_model=List[LeadListSchema])
async def list_lead(
    status_filter: LeadStatus | None = Query(None, alias='status'),
    lead_type: LeadType | None = None,
    only_free: bool = False,
    seller_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    query = visible_leads_query(db, current_user)
    if status_filter is not None:
        query = query.filter(Lead.status == status_filter)
    if lead_type is not None:
        query = query.filter(Lead.lead_type == lead_type)
    if current_user.role != UserRole.client and only_free:
        query = query.filter(free_lead_condition())
    if current_user.role == UserRole.admin and seller_id is not None:
        query = query.filter(Lead.seller_id == seller_id)
    return query.order_by(Lead.created_at.desc(), Lead.id.desc()).offset(skip).limit(limit).all()


@lead_router.get('/detail', response_model=LeadDetailSchema)
async def detail_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    return get_lead_or_404(lead_id, db, current_user)


@lead_router.post('/take/{lead_id}', response_model=LeadDetailSchema)
async def take_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.seller)),
):
    lead_db = get_lead_or_404(lead_id, db, current_user)

    # атомарно: SQLite без блокировки строк, второй продавец получит rowcount == 0
    updated = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.seller_id.is_(None), Lead.status == LeadStatus.new)
        .update({'seller_id': current_user.id, 'status': LeadStatus.in_progress}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Заявка уже взята в работу')

    create_notification(db, lead_db.client_id, NotificationType.lead, f'Ваша заявка #{lead_id} взята в работу')
    db.commit()
    db.refresh(lead_db)
    return lead_db


@lead_router.post('/assign/{lead_id}', response_model=LeadDetailSchema)
async def assign_lead(
    lead_id: int,
    lead_data: LeadAssignSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    lead_db = get_lead_or_404(lead_id, db, current_user)
    seller_db = (
        db.query(UserProfile)
        .filter(
            UserProfile.id == lead_data.seller_id, UserProfile.role == UserRole.seller, UserProfile.is_active.is_(True)
        )
        .first()
    )
    if not seller_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Продавец не найден')
    if lead_db.status in CLOSED_LEAD_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Закрытую заявку нельзя переназначить')

    old_seller_id = lead_db.seller_id
    was_new = lead_db.status == LeadStatus.new
    lead_db.seller_id = seller_db.id
    if was_new:
        lead_db.status = LeadStatus.in_progress

    if old_seller_id != seller_db.id:
        create_notification(db, seller_db.id, NotificationType.lead, f'Вам назначена заявка #{lead_id}')
        if old_seller_id is not None:
            create_notification(
                db, old_seller_id, NotificationType.lead, f'Заявка #{lead_id} передана другому продавцу'
            )
    if was_new:
        create_notification(db, lead_db.client_id, NotificationType.lead, f'Ваша заявка #{lead_id} взята в работу')

    db.commit()
    db.refresh(lead_db)
    return lead_db


@lead_router.put('/update/{lead_id}', response_model=LeadDetailSchema)
async def update_lead(
    lead_id: int,
    lead_data: LeadUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    lead_db = get_lead_or_404(lead_id, db, current_user)
    if current_user.role == UserRole.seller and lead_db.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Заявка не найдена')

    update_data = lead_data.model_dump(exclude_unset=True)

    if current_user.role == UserRole.client and 'status' in update_data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Клиент не может менять статус заявки')
    if current_user.role == UserRole.seller and 'comment' in update_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Комментарий клиента менять нельзя — используйте заметки'
        )
    if 'status' in update_data and update_data['status'] is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    if current_user.role == UserRole.client and lead_db.status != LeadStatus.new:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Заявку в работе изменить нельзя')

    new_status = update_data.get('status')
    if new_status is not None:
        # new -> rejected разрешён только admin; seller работает с заявкой после take (in_progress)
        allowed = LEAD_TRANSITIONS.get(lead_db.status, ())
        if new_status not in allowed or (lead_db.status == LeadStatus.new and current_user.role != UserRole.admin):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Недопустимый переход статуса заявки')
        create_notification(
            db,
            lead_db.client_id,
            NotificationType.lead,
            f'Заявка #{lead_id}: {LEAD_STATUS_TEXT[new_status]}',
        )

    for key, value in update_data.items():
        setattr(lead_db, key, value)

    db.commit()
    db.refresh(lead_db)
    return lead_db


@lead_router.delete('/delete/{lead_id}', response_model=dict)
async def delete_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.client)),
):
    lead_db = get_lead_or_404(lead_id, db, current_user)
    if current_user.role == UserRole.client and lead_db.status != LeadStatus.new:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Удалить можно только новую заявку')

    db.delete(lead_db)
    db.commit()
    return {'message': 'Заявка удалена'}


# ---------- LeadNote ----------


def get_lead_note_or_404(lead_note_id: int, db: Session, current_user: UserProfile) -> LeadNote:
    query = db.query(LeadNote).join(Lead, LeadNote.lead_id == Lead.id).filter(LeadNote.id == lead_note_id)
    if current_user.role == UserRole.seller:
        query = query.filter(Lead.seller_id == current_user.id)
    lead_note_db = query.first()
    if not lead_note_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Заметка не найдена')
    return lead_note_db


def check_note_author(lead_note_db: LeadNote, current_user: UserProfile):
    if current_user.role != UserRole.admin and lead_note_db.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Можно изменять только свои заметки')


@lead_note_router.post('/create', response_model=LeadNoteDetailSchema)
async def create_lead_note(
    lead_note_data: LeadNoteCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    get_own_lead_for_notes_or_404(lead_note_data.lead_id, db, current_user)

    lead_note_db = LeadNote(**lead_note_data.model_dump(), seller_id=current_user.id)
    db.add(lead_note_db)
    db.commit()
    db.refresh(lead_note_db)
    return lead_note_db


@lead_note_router.get('/list', response_model=List[LeadNoteListSchema])
async def list_lead_note(
    lead_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    get_own_lead_for_notes_or_404(lead_id, db, current_user)
    return (
        db.query(LeadNote)
        .filter(LeadNote.lead_id == lead_id)
        .order_by(LeadNote.created_at.asc(), LeadNote.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@lead_note_router.get('/detail', response_model=LeadNoteDetailSchema)
async def detail_lead_note(
    lead_note_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    return get_lead_note_or_404(lead_note_id, db, current_user)


@lead_note_router.put('/update/{lead_note_id}', response_model=LeadNoteDetailSchema)
async def update_lead_note(
    lead_note_id: int,
    lead_note_data: LeadNoteUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    lead_note_db = get_lead_note_or_404(lead_note_id, db, current_user)
    check_note_author(lead_note_db, current_user)

    update_data = lead_note_data.model_dump(exclude_unset=True)
    if 'note' in update_data and update_data['note'] is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    for key, value in update_data.items():
        setattr(lead_note_db, key, value)

    db.commit()
    db.refresh(lead_note_db)
    return lead_note_db


@lead_note_router.delete('/delete/{lead_note_id}', response_model=dict)
async def delete_lead_note(
    lead_note_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    lead_note_db = get_lead_note_or_404(lead_note_id, db, current_user)
    check_note_author(lead_note_db, current_user)

    db.delete(lead_note_db)
    db.commit()
    return {'message': 'Заметка удалена'}
