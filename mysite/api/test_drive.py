from datetime import datetime, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from mysite.api.car import get_car_or_404
from mysite.api.dependencies import get_current_user, require_role
from mysite.api.notification import create_notification, notify_active_sellers
from mysite.config import SALON_TIMEZONE
from mysite.db.database import get_db
from mysite.db.models import (
    Car,
    CarStatus,
    NotificationType,
    SalonSettings,
    TestDrive,
    TestDriveStatus,
    UserProfile,
    UserRole,
)
from mysite.db.schema import (
    TestDriveAssignSchema,
    TestDriveCreateSchema,
    TestDriveDetailSchema,
    TestDriveListSchema,
    TestDriveUpdateSchema,
    UtcDatetime,
)

test_drive_router = APIRouter(prefix='/test-drive', tags=['TestDrive'])

MAX_DAYS_AHEAD = 30
ACTIVE_TEST_DRIVE_STATUSES = (TestDriveStatus.scheduled, TestDriveStatus.confirmed)
TEST_DRIVE_TRANSITIONS = {
    TestDriveStatus.scheduled: (TestDriveStatus.confirmed, TestDriveStatus.cancelled),
    TestDriveStatus.confirmed: (TestDriveStatus.completed, TestDriveStatus.cancelled),
}


def as_utc(value: datetime) -> datetime:
    """SQLite возвращает naive datetime — считаем его UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_local(value: datetime) -> str:
    return as_utc(value).astimezone(ZoneInfo(SALON_TIMEZONE)).strftime('%d.%m.%Y %H:%M')


def get_salon_settings_or_503(db: Session) -> SalonSettings:
    settings_db = db.query(SalonSettings).filter(SalonSettings.id == 1).first()
    if not settings_db:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Настройки салона не заданы, обратитесь к администратору',
        )
    return settings_db


def check_car_available(car_db: Car | None):
    if not car_db or car_db.deleted_at is not None or car_db.status != CarStatus.available:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Тест-драйв для этого автомобиля недоступен')


def check_start_time(settings_db: SalonSettings, start: datetime) -> datetime:
    """Проверки времени (не в прошлом, горизонт, рабочие часы). Возвращает end_time."""
    now = datetime.now(timezone.utc)
    end = start + timedelta(minutes=settings_db.test_drive_minutes)

    if start <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нельзя записаться на тест-драйв в прошлом')
    if start > now + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Запись возможна не более чем на {MAX_DAYS_AHEAD} дней вперёд',
        )

    salon_tz = ZoneInfo(SALON_TIMEZONE)
    local_start = start.astimezone(salon_tz)
    local_end = end.astimezone(salon_tz)
    if (
        local_start.date() != local_end.date()
        or local_start.time() < settings_db.work_start
        or local_end.time() > settings_db.work_end
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                'Тест-драйв возможен только в рабочие часы салона '
                f'({settings_db.work_start:%H:%M}–{settings_db.work_end:%H:%M})'
            ),
        )
    return end


def check_slot(
    db: Session,
    start: datetime,
    end: datetime,
    car_id: int | None = None,
    client_id: int | None = None,
    seller_id: int | None = None,
    exclude_id: int | None = None,
):
    """Пересечения активных тест-драйвов (интервалы полуоткрытые). Время — только UTC."""
    checks = (
        (TestDrive.car_id, car_id, 'Автомобиль уже занят на это время'),
        (TestDrive.client_id, client_id, 'У вас уже есть тест-драйв на это время'),
        (TestDrive.seller_id, seller_id, 'У продавца уже есть тест-драйв на это время'),
    )
    for column, value, message in checks:
        if value is None:
            continue
        query = db.query(TestDrive.id).filter(
            column == value,
            TestDrive.status.in_(ACTIVE_TEST_DRIVE_STATUSES),
            TestDrive.start_time < end,
            TestDrive.end_time > start,
        )
        if exclude_id is not None:
            query = query.filter(TestDrive.id != exclude_id)
        if query.first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def free_test_drive_condition():
    return and_(TestDrive.seller_id.is_(None), TestDrive.status == TestDriveStatus.scheduled)


def visible_test_drives_query(db: Session, current_user: UserProfile):
    """Тест-драйвы, доступные пользователю: admin — все, client — свои, seller — свои и свободные."""
    query = db.query(TestDrive)
    if current_user.role == UserRole.client:
        query = query.filter(TestDrive.client_id == current_user.id)
    elif current_user.role == UserRole.seller:
        query = query.filter(or_(TestDrive.seller_id == current_user.id, free_test_drive_condition()))
    return query


def get_test_drive_or_404(test_drive_id: int, db: Session, current_user: UserProfile) -> TestDrive:
    test_drive_db = visible_test_drives_query(db, current_user).filter(TestDrive.id == test_drive_id).first()
    if not test_drive_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Тест-драйв не найден')
    return test_drive_db


def get_own_test_drive_or_404(test_drive_id: int, db: Session, current_user: UserProfile) -> TestDrive:
    """Для действий seller: только назначенный на него (свободный даёт 404)."""
    test_drive_db = get_test_drive_or_404(test_drive_id, db, current_user)
    if current_user.role == UserRole.seller and test_drive_db.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Тест-драйв не найден')
    return test_drive_db


def check_transition(test_drive_db: TestDrive, new_status: TestDriveStatus):
    if new_status not in TEST_DRIVE_TRANSITIONS.get(test_drive_db.status, ()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Недопустимый переход статуса тест-драйва')


def get_active_seller_or_404(seller_id: int, db: Session) -> UserProfile:
    seller_db = (
        db.query(UserProfile)
        .filter(UserProfile.id == seller_id, UserProfile.role == UserRole.seller, UserProfile.is_active.is_(True))
        .first()
    )
    if not seller_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Продавец не найден')
    return seller_db


def notify_other_side(db: Session, test_drive_db: TestDrive, current_user: UserProfile, text: str):
    """Клиент действовал: уведомить назначенного продавца; продавец: клиента; admin: обоих."""
    if current_user.role != UserRole.client:
        create_notification(db, test_drive_db.client_id, NotificationType.test_drive, text)
    if current_user.role != UserRole.seller and test_drive_db.seller_id is not None:
        create_notification(db, test_drive_db.seller_id, NotificationType.test_drive, text)


@test_drive_router.post('/create', response_model=TestDriveDetailSchema)
async def create_test_drive(
    test_drive_data: TestDriveCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    settings_db = get_salon_settings_or_503(db)
    car_db = get_car_or_404(test_drive_data.car_id, db, current_user, only_visible=True)
    check_car_available(car_db)

    start = test_drive_data.start_time
    end = check_start_time(settings_db, start)
    check_slot(db, start, end, car_id=car_db.id, client_id=current_user.id)

    test_drive_db = TestDrive(
        car_id=car_db.id,
        client_id=current_user.id,
        seller_id=None,
        start_time=start,
        end_time=end,
        status=TestDriveStatus.scheduled,
    )
    db.add(test_drive_db)
    db.flush()
    notify_active_sellers(
        db,
        NotificationType.test_drive,
        f'Новая запись на тест-драйв #{test_drive_db.id} на {format_local(start)}',
    )
    db.commit()
    db.refresh(test_drive_db)
    return test_drive_db


@test_drive_router.get('/list', response_model=List[TestDriveListSchema])
async def list_test_drive(
    status_filter: TestDriveStatus | None = Query(None, alias='status'),
    car_id: int | None = None,
    date_from: UtcDatetime | None = None,
    date_to: UtcDatetime | None = None,
    only_free: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Некорректный диапазон фильтра')

    query = visible_test_drives_query(db, current_user)
    if status_filter is not None:
        query = query.filter(TestDrive.status == status_filter)
    if car_id is not None:
        query = query.filter(TestDrive.car_id == car_id)
    if date_from is not None:
        query = query.filter(TestDrive.start_time >= date_from)
    if date_to is not None:
        query = query.filter(TestDrive.start_time <= date_to)
    if current_user.role != UserRole.client and only_free:
        query = query.filter(free_test_drive_condition())
    return query.order_by(TestDrive.start_time.asc(), TestDrive.id.asc()).offset(skip).limit(limit).all()


@test_drive_router.get('/detail', response_model=TestDriveDetailSchema)
async def detail_test_drive(
    test_drive_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    return get_test_drive_or_404(test_drive_id, db, current_user)


@test_drive_router.put('/update/{test_drive_id}', response_model=TestDriveDetailSchema)
async def update_test_drive(
    test_drive_id: int,
    test_drive_data: TestDriveUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    test_drive_db = get_own_test_drive_or_404(test_drive_id, db, current_user)

    start = test_drive_data.start_time
    if start is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Укажите новое время')
    if test_drive_db.status not in ACTIVE_TEST_DRIVE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Перенести можно только запланированный тест-драйв'
        )

    settings_db = get_salon_settings_or_503(db)
    # авто грузим напрямую, а не через get_car_or_404: удалённое или недоступное авто здесь — 409, а не 404
    car_db = db.query(Car).filter(Car.id == test_drive_db.car_id).first()
    check_car_available(car_db)

    end = check_start_time(settings_db, start)
    check_slot(
        db,
        start,
        end,
        car_id=test_drive_db.car_id,
        client_id=test_drive_db.client_id,
        seller_id=test_drive_db.seller_id,
        exclude_id=test_drive_db.id,
    )

    test_drive_db.start_time = start
    test_drive_db.end_time = end
    test_drive_db.status = TestDriveStatus.scheduled
    notify_other_side(
        db,
        test_drive_db,
        current_user,
        f'Тест-драйв #{test_drive_db.id} перенесён на {format_local(start)}',
    )
    db.commit()
    db.refresh(test_drive_db)
    return test_drive_db


@test_drive_router.post('/assign/{test_drive_id}', response_model=TestDriveDetailSchema)
async def assign_test_drive(
    test_drive_id: int,
    test_drive_data: TestDriveAssignSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    test_drive_db = get_test_drive_or_404(test_drive_id, db, current_user)
    seller_db = get_active_seller_or_404(test_drive_data.seller_id, db)
    if test_drive_db.status not in ACTIVE_TEST_DRIVE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Назначить продавца можно только на активный тест-драйв'
        )

    if as_utc(test_drive_db.start_time) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Время тест-драйва уже прошло')

    check_slot(
        db,
        as_utc(test_drive_db.start_time),
        as_utc(test_drive_db.end_time),
        seller_id=seller_db.id,
        exclude_id=test_drive_db.id,
    )

    old_seller_id = test_drive_db.seller_id
    test_drive_db.seller_id = seller_db.id
    if old_seller_id != seller_db.id:
        create_notification(
            db,
            seller_db.id,
            NotificationType.test_drive,
            f'Вам назначен тест-драйв #{test_drive_id} на {format_local(test_drive_db.start_time)}',
        )
        if old_seller_id is not None:
            create_notification(
                db,
                old_seller_id,
                NotificationType.test_drive,
                f'Тест-драйв #{test_drive_id} передан другому продавцу',
            )
    db.commit()
    db.refresh(test_drive_db)
    return test_drive_db


@test_drive_router.post('/confirm/{test_drive_id}', response_model=TestDriveDetailSchema)
async def confirm_test_drive(
    test_drive_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    test_drive_db = get_test_drive_or_404(test_drive_id, db, current_user)
    check_transition(test_drive_db, TestDriveStatus.confirmed)

    if current_user.role == UserRole.seller:
        seller_id = current_user.id
        seller_condition = or_(TestDrive.seller_id.is_(None), TestDrive.seller_id == current_user.id)
    elif test_drive_db.seller_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Сначала назначьте продавца')
    else:
        seller_id = test_drive_db.seller_id
        seller_condition = TestDrive.seller_id == seller_id

    start = as_utc(test_drive_db.start_time)
    if start <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Время тест-драйва уже прошло')

    # авто грузим напрямую, а не через get_car_or_404: удалённое или недоступное авто здесь — 409, а не 404
    car_db = db.query(Car).filter(Car.id == test_drive_db.car_id).first()
    check_car_available(car_db)
    check_slot(
        db,
        start,
        as_utc(test_drive_db.end_time),
        car_id=test_drive_db.car_id,
        client_id=test_drive_db.client_id,
        seller_id=seller_id,
        exclude_id=test_drive_db.id,
    )

    # атомарно: SQLite без блокировки строк, проигравший получит rowcount == 0
    updated = (
        db.query(TestDrive)
        .filter(TestDrive.id == test_drive_id, TestDrive.status == TestDriveStatus.scheduled, seller_condition)
        .update({'seller_id': seller_id, 'status': TestDriveStatus.confirmed}, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Тест-драйв уже взят другим продавцом')

    create_notification(
        db,
        test_drive_db.client_id,
        NotificationType.test_drive,
        f'Тест-драйв #{test_drive_id} на {format_local(start)} подтверждён',
    )
    db.commit()
    db.refresh(test_drive_db)
    return test_drive_db


@test_drive_router.post('/complete/{test_drive_id}', response_model=TestDriveDetailSchema)
async def complete_test_drive(
    test_drive_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    test_drive_db = get_own_test_drive_or_404(test_drive_id, db, current_user)
    check_transition(test_drive_db, TestDriveStatus.completed)
    if as_utc(test_drive_db.start_time) > datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Тест-драйв ещё не начался')

    test_drive_db.status = TestDriveStatus.completed
    db.commit()
    db.refresh(test_drive_db)
    return test_drive_db


@test_drive_router.post('/cancel/{test_drive_id}', response_model=TestDriveDetailSchema)
async def cancel_test_drive(
    test_drive_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    test_drive_db = get_own_test_drive_or_404(test_drive_id, db, current_user)
    check_transition(test_drive_db, TestDriveStatus.cancelled)

    test_drive_db.status = TestDriveStatus.cancelled
    notify_other_side(
        db,
        test_drive_db,
        current_user,
        f'Тест-драйв #{test_drive_id} на {format_local(test_drive_db.start_time)} отменён',
    )
    db.commit()
    db.refresh(test_drive_db)
    return test_drive_db


@test_drive_router.delete('/delete/{test_drive_id}', response_model=dict)
async def delete_test_drive(
    test_drive_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    test_drive_db = get_test_drive_or_404(test_drive_id, db, current_user)
    db.delete(test_drive_db)
    db.commit()
    return {'message': 'Тест-драйв удалён'}
