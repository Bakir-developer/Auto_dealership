from datetime import datetime, timezone
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from mysite.api.car_image import ALLOWED_IMAGE_TYPES, IMAGE_TYPE_ERROR, MAX_IMAGE_SIZE, detect_image_extension
from mysite.api.deal import CENT, create_audit_log
from mysite.api.dependencies import get_current_user, require_role
from mysite.api.notification import create_notification, notify_active_sellers
from mysite.config import MEDIA_DIR
from mysite.db.database import get_db
from mysite.db.models import NotificationType, TradeIn, TradeInImage, TradeInStatus, UserProfile, UserRole
from mysite.db.schema import (
    TradeInAssignSchema,
    TradeInCreateSchema,
    TradeInDetailSchema,
    TradeInImageDetailSchema,
    TradeInImageListSchema,
    TradeInListSchema,
    TradeInOfferSchema,
    TradeInUpdateSchema,
)

trade_in_router = APIRouter(prefix='/trade-in', tags=['TradeIn'])
trade_in_image_router = APIRouter(prefix='/trade-in-image', tags=['TradeInImage'])

MAX_ACTIVE_TRADE_INS = 5
MAX_IMAGES_PER_TRADE_IN = 10
ACTIVE_TRADE_IN_STATUSES = (TradeInStatus.new, TradeInStatus.evaluating, TradeInStatus.offered)
CLOSED_TRADE_IN_STATUSES = (TradeInStatus.accepted, TradeInStatus.rejected)
IMAGE_EDITABLE_STATUSES = (TradeInStatus.new, TradeInStatus.evaluating)
TRADE_IN_TRANSITIONS = {
    TradeInStatus.new: (TradeInStatus.evaluating, TradeInStatus.rejected),
    TradeInStatus.evaluating: (TradeInStatus.offered, TradeInStatus.rejected),
    TradeInStatus.offered: (TradeInStatus.accepted, TradeInStatus.rejected),
}
# из каких статусов заявку может отклонить каждая роль
REJECT_FROM_STATUSES = {
    UserRole.client: (TradeInStatus.offered,),
    UserRole.seller: (TradeInStatus.evaluating,),
    UserRole.admin: ACTIVE_TRADE_IN_STATUSES,
}
TRADE_IN_NOT_FOUND = 'Заявка на trade-in не найдена'
IMAGE_NOT_FOUND = 'Фотография не найдена'
TRANSITION_ERROR = 'Недопустимый переход статуса trade-in'
EMPTY_FIELD_ERROR = 'Поле не может быть пустым'
YEAR_ERROR = 'Год выпуска не может быть больше следующего года'


# ---------- Хелперы ----------


def free_trade_in_condition():
    return and_(TradeIn.seller_id.is_(None), TradeIn.status == TradeInStatus.new)


def visible_trade_ins_query(db: Session, current_user: UserProfile):
    """Заявки, доступные пользователю: admin — все, client — свои, seller — свои и свободные."""
    query = db.query(TradeIn)
    if current_user.role == UserRole.client:
        query = query.filter(TradeIn.client_id == current_user.id)
    elif current_user.role == UserRole.seller:
        query = query.filter(or_(TradeIn.seller_id == current_user.id, free_trade_in_condition()))
    return query


def get_trade_in_or_404(trade_in_id: int, db: Session, current_user: UserProfile) -> TradeIn:
    trade_in_db = (
        visible_trade_ins_query(db, current_user)
        .options(selectinload(TradeIn.images))
        .filter(TradeIn.id == trade_in_id)
        .first()
    )
    if not trade_in_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TRADE_IN_NOT_FOUND)
    return trade_in_db


def get_own_trade_in_or_404(trade_in_id: int, db: Session, current_user: UserProfile) -> TradeIn:
    """Для действий над заявкой: admin — любая, seller — только своя (не свободная), client — только своя."""
    query = db.query(TradeIn).options(selectinload(TradeIn.images)).filter(TradeIn.id == trade_in_id)
    if current_user.role == UserRole.seller:
        query = query.filter(TradeIn.seller_id == current_user.id)
    elif current_user.role == UserRole.client:
        query = query.filter(TradeIn.client_id == current_user.id)
    trade_in_db = query.first()
    if not trade_in_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TRADE_IN_NOT_FOUND)
    return trade_in_db


def build_trade_in_detail(trade_in_db: TradeIn) -> TradeInDetailSchema:
    trade_in_detail = TradeInDetailSchema.model_validate(trade_in_db, from_attributes=True)
    trade_in_detail.images.sort(key=lambda image: image.id)
    return trade_in_detail


def check_year(year: int):
    if year > datetime.now(timezone.utc).year + 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=YEAR_ERROR)


def change_trade_in_status(
    db: Session,
    trade_in_db: TradeIn,
    from_status: TradeInStatus,
    to_status: TradeInStatus,
    extra_filters: tuple = (),
    error_detail: str = TRANSITION_ERROR,
    **fields,
):
    """Атомарный условный UPDATE: сработает, только если статус ещё from_status (и выполнены extra_filters)."""
    if to_status not in TRADE_IN_TRANSITIONS.get(from_status, ()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=TRANSITION_ERROR)
    updated = (
        db.query(TradeIn)
        .filter(TradeIn.id == trade_in_db.id, TradeIn.status == from_status, *extra_filters)
        .update({'status': to_status, **fields}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_detail)
    db.refresh(trade_in_db)


def owner_filters(current_user: UserProfile) -> tuple:
    """Доп. условие условного UPDATE: продавец действует только над заявкой, которая всё ещё его."""
    if current_user.role == UserRole.seller:
        return (TradeIn.seller_id == current_user.id,)
    return ()


def get_trade_in_images_dir() -> Path:
    # MEDIA_DIR читается во время вызова, чтобы тесты могли его подменить
    return Path(MEDIA_DIR) / 'trade_in_images'


def get_image_file_path(trade_in_image: str) -> Path:
    # путь на диске — только имя файла из БД, без директорий
    return get_trade_in_images_dir() / Path(trade_in_image).name


def remove_image_files(file_paths: List[Path]):
    for file_path in file_paths:
        file_path.unlink(missing_ok=True)


# ---------- TradeIn ----------


@trade_in_router.post('/create', response_model=TradeInDetailSchema)
async def create_trade_in(
    trade_in_data: TradeInCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    check_year(trade_in_data.year)

    active_count = (
        db.query(TradeIn)
        .filter(TradeIn.client_id == current_user.id, TradeIn.status.in_(ACTIVE_TRADE_IN_STATUSES))
        .count()
    )
    if active_count >= MAX_ACTIVE_TRADE_INS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'У вас уже есть {MAX_ACTIVE_TRADE_INS} активных заявок на trade-in',
        )

    trade_in_db = TradeIn(
        **trade_in_data.model_dump(), client_id=current_user.id, status=TradeInStatus.new, seller_id=None
    )
    db.add(trade_in_db)
    db.flush()
    notify_active_sellers(db, NotificationType.lead, f'Новая заявка на trade-in #{trade_in_db.id}', current_user.id)
    db.commit()
    db.refresh(trade_in_db)
    return build_trade_in_detail(trade_in_db)


@trade_in_router.get('/list', response_model=List[TradeInListSchema])
async def list_trade_in(
    status_filter: TradeInStatus | None = Query(None, alias='status'),
    only_free: bool = False,
    seller_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    query = visible_trade_ins_query(db, current_user)
    if status_filter is not None:
        query = query.filter(TradeIn.status == status_filter)
    if current_user.role != UserRole.client and only_free:
        query = query.filter(free_trade_in_condition())
    if current_user.role == UserRole.admin and seller_id is not None:
        query = query.filter(TradeIn.seller_id == seller_id)
    return query.order_by(TradeIn.created_at.desc(), TradeIn.id.desc()).offset(skip).limit(limit).all()


@trade_in_router.get('/detail', response_model=TradeInDetailSchema)
async def detail_trade_in(
    trade_in_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    return build_trade_in_detail(get_trade_in_or_404(trade_in_id, db, current_user))


@trade_in_router.put('/update/{trade_in_id}', response_model=TradeInDetailSchema)
async def update_trade_in(
    trade_in_id: int,
    trade_in_data: TradeInUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    trade_in_db = get_own_trade_in_or_404(trade_in_id, db, current_user)
    if trade_in_db.status != TradeInStatus.new:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Заявку на trade-in в работе изменить нельзя')

    update_data = trade_in_data.model_dump(exclude_unset=True)
    for field in ('brand_name', 'model_name', 'year', 'mileage'):
        if field in update_data and update_data[field] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=EMPTY_FIELD_ERROR)
    if 'year' in update_data:
        check_year(update_data['year'])

    # атомарно: заявку могли взять в работу между проверкой и записью
    if update_data:
        updated = (
            db.query(TradeIn)
            .filter(
                TradeIn.id == trade_in_id,
                TradeIn.client_id == current_user.id,
                TradeIn.status == TradeInStatus.new,
            )
            .update(update_data, synchronize_session=False)
        )
        if updated == 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail='Заявку на trade-in в работе изменить нельзя'
            )
        db.commit()
    return build_trade_in_detail(get_own_trade_in_or_404(trade_in_id, db, current_user))


@trade_in_router.post('/take/{trade_in_id}', response_model=TradeInDetailSchema)
async def take_trade_in(
    trade_in_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.seller)),
):
    trade_in_db = get_trade_in_or_404(trade_in_id, db, current_user)

    # атомарно: SQLite без блокировки строк, второй продавец получит rowcount == 0
    client_id = trade_in_db.client_id
    change_trade_in_status(
        db,
        trade_in_db,
        TradeInStatus.new,
        TradeInStatus.evaluating,
        (TradeIn.seller_id.is_(None),),
        'Заявка на trade-in уже взята в работу',
        seller_id=current_user.id,
    )

    create_notification(db, client_id, NotificationType.lead, f'Ваша заявка на trade-in #{trade_in_id} взята в оценку')
    db.commit()
    db.refresh(trade_in_db)
    return build_trade_in_detail(trade_in_db)


@trade_in_router.post('/assign/{trade_in_id}', response_model=TradeInDetailSchema)
async def assign_trade_in(
    trade_in_id: int,
    trade_in_data: TradeInAssignSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    trade_in_db = get_trade_in_or_404(trade_in_id, db, current_user)
    seller_db = (
        db.query(UserProfile)
        .filter(
            UserProfile.id == trade_in_data.seller_id,
            UserProfile.role == UserRole.seller,
            UserProfile.is_active.is_(True),
        )
        .first()
    )
    if not seller_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Продавец не найден')
    if trade_in_db.status in CLOSED_TRADE_IN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Закрытую заявку на trade-in нельзя переназначить'
        )

    old_seller_id = trade_in_db.seller_id
    old_status = trade_in_db.status
    was_new = old_status == TradeInStatus.new
    client_id = trade_in_db.client_id
    assign_error = 'Заявка на trade-in уже изменена, повторите попытку'
    # атомарно: статус и прежний продавец должны остаться теми, что мы прочитали
    if was_new:
        change_trade_in_status(
            db,
            trade_in_db,
            TradeInStatus.new,
            TradeInStatus.evaluating,
            (TradeIn.seller_id.is_(None),),
            assign_error,
            seller_id=seller_db.id,
        )
    else:
        updated = (
            db.query(TradeIn)
            .filter(
                TradeIn.id == trade_in_id,
                TradeIn.status == old_status,
                TradeIn.seller_id.is_not_distinct_from(old_seller_id),
            )
            .update({'seller_id': seller_db.id}, synchronize_session=False)
        )
        if updated == 0:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=assign_error)

    if old_seller_id != seller_db.id:
        create_notification(db, seller_db.id, NotificationType.lead, f'Вам назначена заявка на trade-in #{trade_in_id}')
        if old_seller_id is not None:
            create_notification(
                db,
                old_seller_id,
                NotificationType.lead,
                f'Заявка на trade-in #{trade_in_id} передана другому продавцу',
            )
    if was_new:
        create_notification(
            db,
            client_id,
            NotificationType.lead,
            f'Ваша заявка на trade-in #{trade_in_id} взята в оценку',
        )

    db.commit()
    db.refresh(trade_in_db)
    return build_trade_in_detail(trade_in_db)


@trade_in_router.post('/offer/{trade_in_id}', response_model=TradeInDetailSchema)
async def offer_trade_in(
    trade_in_id: int,
    trade_in_data: TradeInOfferSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    trade_in_db = get_own_trade_in_or_404(trade_in_id, db, current_user)

    client_id = trade_in_db.client_id
    estimated_price = trade_in_data.estimated_price.quantize(CENT)
    change_trade_in_status(
        db,
        trade_in_db,
        trade_in_db.status,
        TradeInStatus.offered,
        owner_filters(current_user),
        estimated_price=estimated_price,
        currency=trade_in_data.currency,
    )

    create_notification(
        db,
        client_id,
        NotificationType.lead,
        f'Предложение по trade-in #{trade_in_id}: {estimated_price:f} {trade_in_data.currency.value}',
    )
    create_audit_log(
        db,
        current_user.id,
        'trade_in_offer',
        'trade_in',
        trade_in_id,
        {'status': TradeInStatus.evaluating},
        {
            'status': TradeInStatus.offered,
            'estimated_price': estimated_price,
            'currency': trade_in_data.currency,
        },
    )
    db.commit()
    db.refresh(trade_in_db)
    return build_trade_in_detail(trade_in_db)


@trade_in_router.post('/accept/{trade_in_id}', response_model=TradeInDetailSchema)
async def accept_trade_in(
    trade_in_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    trade_in_db = get_own_trade_in_or_404(trade_in_id, db, current_user)

    seller_id = trade_in_db.seller_id
    change_trade_in_status(db, trade_in_db, trade_in_db.status, TradeInStatus.accepted)

    if seller_id is not None:
        create_notification(
            db, seller_id, NotificationType.lead, f'Клиент принял предложение по trade-in #{trade_in_id}'
        )
    create_audit_log(
        db,
        current_user.id,
        'trade_in_accept',
        'trade_in',
        trade_in_id,
        {'status': TradeInStatus.offered},
        {'status': TradeInStatus.accepted},
    )
    db.commit()
    db.refresh(trade_in_db)
    return build_trade_in_detail(trade_in_db)


@trade_in_router.post('/reject/{trade_in_id}', response_model=TradeInDetailSchema)
async def reject_trade_in(
    trade_in_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    trade_in_db = get_own_trade_in_or_404(trade_in_id, db, current_user)

    old_status = trade_in_db.status
    if old_status not in REJECT_FROM_STATUSES[current_user.role]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=TRANSITION_ERROR)

    client_id = trade_in_db.client_id
    seller_id = trade_in_db.seller_id
    change_trade_in_status(db, trade_in_db, old_status, TradeInStatus.rejected, owner_filters(current_user))

    text = f'Заявка на trade-in #{trade_in_id} отклонена'
    for user_id in {client_id, seller_id} - {None, current_user.id}:
        create_notification(db, user_id, NotificationType.lead, text)
    create_audit_log(
        db,
        current_user.id,
        'trade_in_reject',
        'trade_in',
        trade_in_id,
        {'status': old_status},
        {'status': TradeInStatus.rejected},
    )
    db.commit()
    db.refresh(trade_in_db)
    return build_trade_in_detail(trade_in_db)


@trade_in_router.delete('/delete/{trade_in_id}', response_model=dict)
async def delete_trade_in(
    trade_in_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.client)),
):
    trade_in_db = get_own_trade_in_or_404(trade_in_id, db, current_user)
    if current_user.role == UserRole.client and trade_in_db.status != TradeInStatus.new:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Удалить можно только новую заявку на trade-in'
        )

    # пути файлов собираем до удаления, с диска удаляем после commit
    file_paths = [get_image_file_path(image.trade_in_image) for image in trade_in_db.images]
    if current_user.role == UserRole.admin:
        create_audit_log(
            db,
            current_user.id,
            'trade_in_delete',
            'trade_in',
            trade_in_id,
            {'client_id': trade_in_db.client_id, 'status': trade_in_db.status},
            None,
        )

    if current_user.role == UserRole.client:
        # атомарно: заявку могли взять в работу между проверкой и удалением
        db.query(TradeInImage).filter(TradeInImage.trade_in_id == trade_in_id).delete(synchronize_session=False)
        deleted = (
            db.query(TradeIn)
            .filter(
                TradeIn.id == trade_in_id,
                TradeIn.client_id == current_user.id,
                TradeIn.status == TradeInStatus.new,
            )
            .delete(synchronize_session=False)
        )
        if deleted == 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail='Удалить можно только новую заявку на trade-in'
            )
    else:
        db.delete(trade_in_db)
    db.commit()
    remove_image_files(file_paths)
    return {'message': 'Заявка на trade-in удалена'}


# ---------- TradeInImage ----------


def get_trade_in_image_or_404(trade_in_image_id: int, db: Session, current_user: UserProfile) -> TradeInImage:
    """Фото видно, если видна родительская заявка."""
    visible_ids = visible_trade_ins_query(db, current_user).with_entities(TradeIn.id).scalar_subquery()
    trade_in_image_db = (
        db.query(TradeInImage)
        .filter(TradeInImage.id == trade_in_image_id, TradeInImage.trade_in_id.in_(visible_ids))
        .first()
    )
    if not trade_in_image_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=IMAGE_NOT_FOUND)
    return trade_in_image_db


@trade_in_image_router.post('/create', response_model=TradeInImageDetailSchema)
async def create_trade_in_image(
    trade_in_id: int = Form(),
    trade_in_image: UploadFile = File(),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    trade_in_db = get_own_trade_in_or_404(trade_in_id, db, current_user)
    if trade_in_db.status not in IMAGE_EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Фото можно добавлять только к новой заявке или заявке на оценке',
        )

    data = await trade_in_image.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail='Файл слишком большой (максимум 5 МБ)'
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой файл')

    extension = detect_image_extension(data)
    if ALLOWED_IMAGE_TYPES.get(trade_in_image.content_type) != extension or extension is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=IMAGE_TYPE_ERROR)

    images_count = db.query(TradeInImage).filter(TradeInImage.trade_in_id == trade_in_id).count()
    if images_count >= MAX_IMAGES_PER_TRADE_IN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Достигнут лимит фотографий для заявки ({MAX_IMAGES_PER_TRADE_IN})',
        )

    # имя файла только серверное — UploadFile.filename не используется
    filename = f'{uuid4().hex}{extension}'
    file_path = get_trade_in_images_dir() / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(file_path, 'wb') as file:
            file.write(data)
        trade_in_image_db = TradeInImage(trade_in_id=trade_in_id, trade_in_image=f'/media/trade_in_images/{filename}')
        db.add(trade_in_image_db)
        db.commit()
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise
    db.refresh(trade_in_image_db)
    return trade_in_image_db


@trade_in_image_router.get('/list', response_model=List[TradeInImageListSchema])
async def list_trade_in_image(
    trade_in_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    get_trade_in_or_404(trade_in_id, db, current_user)
    return db.query(TradeInImage).filter(TradeInImage.trade_in_id == trade_in_id).order_by(TradeInImage.id).all()


@trade_in_image_router.get('/detail', response_model=TradeInImageDetailSchema)
async def detail_trade_in_image(
    trade_in_image_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    return get_trade_in_image_or_404(trade_in_image_id, db, current_user)


@trade_in_image_router.delete('/delete/{trade_in_image_id}', response_model=dict)
async def delete_trade_in_image(
    trade_in_image_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.client)),
):
    trade_in_image_db = get_trade_in_image_or_404(trade_in_image_id, db, current_user)
    if current_user.role == UserRole.client:
        status_db = db.query(TradeIn.status).filter(TradeIn.id == trade_in_image_db.trade_in_id).scalar()
        if status_db not in IMAGE_EDITABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Удалять фото можно только у новой заявки или заявки на оценке',
            )

    file_path = get_image_file_path(trade_in_image_db.trade_in_image)
    db.delete(trade_in_image_db)
    db.commit()

    remove_image_files([file_path])
    return {'message': 'Фотография удалена'}
