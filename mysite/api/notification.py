from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from mysite.api.dependencies import get_current_user
from mysite.db.database import get_db
from mysite.db.models import Notification, NotificationType, UserProfile, UserRole
from mysite.db.schema import NotificationDetailSchema, NotificationListSchema, NotificationUpdateSchema

notification_router = APIRouter(prefix='/notification', tags=['Notification'])


def create_notification(db: Session, user_id: int, notification_type: NotificationType, text: str):
    """Добавляет уведомление в сессию без commit — commit делает вызывающий роутер.
    Заблокированному получателю уведомление не создаётся."""
    is_active = db.query(UserProfile.is_active).filter(UserProfile.id == user_id).scalar()
    if not is_active:
        return
    db.add(Notification(user_id=user_id, notification_type=notification_type, text=text))


def notify_active_sellers(
    db: Session, notification_type: NotificationType, text: str, exclude_user_id: int | None = None
):
    sellers_db = db.query(UserProfile.id).filter(UserProfile.role == UserRole.seller, UserProfile.is_active.is_(True))
    for (seller_id,) in sellers_db.all():
        if seller_id != exclude_user_id:
            create_notification(db, seller_id, notification_type, text)


def get_notification_or_404(notification_id: int, db: Session, current_user: UserProfile) -> Notification:
    notification_db = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notification_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Уведомление не найдено')
    return notification_db


@notification_router.get('/list', response_model=List[NotificationListSchema])
async def list_notification(
    is_read: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)
    return query.order_by(Notification.created_at.desc(), Notification.id.desc()).offset(skip).limit(limit).all()


@notification_router.get('/detail', response_model=NotificationDetailSchema)
async def detail_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    return get_notification_or_404(notification_id, db, current_user)


@notification_router.get('/unread-count', response_model=dict)
async def unread_count_notification(
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    count = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .scalar()
    )
    return {'count': count}


@notification_router.put('/update/{notification_id}', response_model=NotificationDetailSchema)
async def update_notification(
    notification_id: int,
    notification_data: NotificationUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    notification_db = get_notification_or_404(notification_id, db, current_user)

    update_data = notification_data.model_dump(exclude_unset=True)
    if 'is_read' in update_data and update_data['is_read'] is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    for key, value in update_data.items():
        setattr(notification_db, key, value)

    db.commit()
    db.refresh(notification_db)
    return notification_db


@notification_router.post('/read-all', response_model=dict)
async def read_all_notification(
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .update({'is_read': True}, synchronize_session=False)
    )
    db.commit()
    return {'message': 'Уведомления прочитаны', 'count': count}


@notification_router.delete('/delete/{notification_id}', response_model=dict)
async def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    notification_db = get_notification_or_404(notification_id, db, current_user)
    db.delete(notification_db)
    db.commit()
    return {'message': 'Уведомление удалено'}
