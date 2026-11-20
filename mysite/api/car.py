from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from mysite.api.dependencies import get_optional_user, require_role
from mysite.db.database import get_db
from mysite.db.models import (
    AuditLog,
    BodyType,
    Brand,
    Car,
    CarCondition,
    CarModel,
    CarStatus,
    Currency,
    DriveType,
    FuelType,
    PriceHistory,
    SalonSettings,
    Transmission,
    UserProfile,
    UserRole,
)
from mysite.db.schema import (
    CarCreateSchema,
    CarDetailSchema,
    CarInstallmentUpdateSchema,
    CarListSchema,
    CarUpdateSchema,
    InstallmentTermsSchema,
    PriceHistoryListSchema,
)

car_router = APIRouter(prefix='/car', tags=['Car'])

PUBLIC_CAR_STATUSES = (CarStatus.available, CarStatus.in_transit, CarStatus.reserved)
STAFF_ROLES = (UserRole.admin, UserRole.seller)
NOT_NULL_FIELDS = (
    'year',
    'body_type',
    'color',
    'fuel_type',
    'transmission',
    'drive_type',
    'steering',
    'status',
    'price',
    'currency',
    'mileage',
    'customs_cleared',
    'registered_in_kr',
)
INSTALLMENT_SETTING_FIELDS = (
    'default_min_down_payment_percent',
    'default_max_term_months',
    'default_installment_rate_percent',
    'min_term_months',
)
# если записи SalonSettings нет — те же значения, что default в модели
DEFAULT_INSTALLMENT_SETTINGS = {
    'default_min_down_payment_percent': Decimal('30.00'),
    'default_max_term_months': 36,
    'default_installment_rate_percent': Decimal('0.00'),
    'min_term_months': 6,
}


def is_staff(current_user: UserProfile | None) -> bool:
    return current_user is not None and current_user.role in STAFF_ROLES


def get_car_or_404(
    car_id: int, db: Session, current_user: UserProfile | None = None, only_visible: bool = False
) -> Car:
    """Не удалённое авто. only_visible=True — ещё и с учётом видимости статуса для публики."""
    query = db.query(Car).filter(Car.id == car_id, Car.deleted_at.is_(None))
    if only_visible and not is_staff(current_user):
        query = query.filter(Car.status.in_(PUBLIC_CAR_STATUSES))
    car_db = query.first()
    if not car_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Автомобиль не найден')
    return car_db


def check_car_condition_rules(state: dict):
    """Правила new/used на итоговом состоянии авто (ТЗ §5.9)."""
    if state['condition'] == CarCondition.new:
        if state['mileage'] != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail='У нового автомобиля пробег должен быть 0'
            )
        if (
            state['owners_count'] not in (None, 0)
            or state['has_accidents'] not in (None, False)
            or state['accident_notes']
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail='У нового автомобиля не может быть владельцев и ДТП'
            )
        return

    if state['mileage'] <= 0 or state['owners_count'] is None or state['owners_count'] < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Для автомобиля с пробегом обязательны: пробег, число владельцев, наличие ДТП',
        )
    if state['has_accidents'] is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Для автомобиля с пробегом обязательны: пробег, число владельцев, наличие ДТП',
        )
    if state['has_accidents'] and not (state['accident_notes'] or '').strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Укажите описание ДТП')


def car_state(car_db: Car, update_data: dict | None = None) -> dict:
    fields = ('condition', 'mileage', 'owners_count', 'has_accidents', 'accident_notes')
    update_data = update_data or {}
    return {field: update_data.get(field, getattr(car_db, field)) for field in fields}


def get_installment_defaults(db: Session) -> dict:
    settings_db = db.query(SalonSettings).filter(SalonSettings.id == 1).first()
    if not settings_db:
        return dict(DEFAULT_INSTALLMENT_SETTINGS)
    return {field: getattr(settings_db, field) for field in INSTALLMENT_SETTING_FIELDS}


def get_installment_terms(car_db: Car, defaults: dict) -> InstallmentTermsSchema:
    """Итоговые условия рассрочки авто: своё значение, а если его нет — значение по умолчанию салона."""
    return InstallmentTermsSchema(
        installment_available=car_db.installment_available,
        min_down_payment_percent=(
            car_db.min_down_payment_percent
            if car_db.min_down_payment_percent is not None
            else defaults['default_min_down_payment_percent']
        ),
        min_term_months=defaults['min_term_months'],
        max_term_months=(
            car_db.max_term_months if car_db.max_term_months is not None else defaults['default_max_term_months']
        ),
        installment_rate_percent=(
            car_db.installment_rate_percent
            if car_db.installment_rate_percent is not None
            else defaults['default_installment_rate_percent']
        ),
    )


def build_car_detail(car_db: Car, db: Session, defaults: dict | None = None) -> CarDetailSchema:
    car_detail = CarDetailSchema.model_validate(car_db, from_attributes=True)
    car_detail.images.sort(key=lambda image: (not image.is_main, image.position, image.id))
    car_detail.installment = get_installment_terms(car_db, defaults or get_installment_defaults(db))
    return car_detail


@car_router.post('/create', response_model=CarDetailSchema)
async def create_car(
    car_data: CarCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    if not db.query(Brand.id).filter(Brand.id == car_data.brand_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')
    car_model_db = db.query(CarModel).filter(CarModel.id == car_data.car_model_id).first()
    if not car_model_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Модель не найдена')
    if car_model_db.brand_id != car_data.brand_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Модель не принадлежит выбранной марке')

    if car_data.year > datetime.now(timezone.utc).year + 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Год выпуска не может быть больше следующего года'
        )

    check_car_condition_rules(car_data.model_dump())

    # VIN уникален и среди мягко удалённых авто — фильтр по deleted_at не нужен
    if db.query(Car.id).filter(Car.vin == car_data.vin).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Автомобиль с таким VIN уже существует')

    car_db = Car(**car_data.model_dump(), created_by_id=current_user.id)
    db.add(car_db)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Автомобиль с таким VIN уже существует')
    db.refresh(car_db)
    return build_car_detail(car_db, db)


@car_router.get('/list', response_model=List[CarListSchema])
async def list_car(
    brand_id: int | None = None,
    car_model_id: int | None = None,
    year_min: int | None = Query(None, ge=1900, le=2100),
    year_max: int | None = Query(None, ge=1900, le=2100),
    price_min: Decimal | None = Query(None, gt=0),
    price_max: Decimal | None = Query(None, gt=0),
    currency: Currency | None = None,
    condition: CarCondition | None = None,
    body_type: BodyType | None = None,
    fuel_type: FuelType | None = None,
    transmission: Transmission | None = None,
    drive_type: DriveType | None = None,
    status_filter: CarStatus | None = Query(None, alias='status'),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile | None = Depends(get_optional_user),
):
    if (year_min is not None and year_max is not None and year_min > year_max) or (
        price_min is not None and price_max is not None and price_min > price_max
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Некорректный диапазон фильтра')

    query = db.query(Car).filter(Car.deleted_at.is_(None))
    if not is_staff(current_user):
        query = query.filter(Car.status.in_(PUBLIC_CAR_STATUSES))

    if brand_id is not None:
        query = query.filter(Car.brand_id == brand_id)
    if car_model_id is not None:
        query = query.filter(Car.car_model_id == car_model_id)
    if year_min is not None:
        query = query.filter(Car.year >= year_min)
    if year_max is not None:
        query = query.filter(Car.year <= year_max)
    if price_min is not None:
        query = query.filter(Car.price >= price_min)
    if price_max is not None:
        query = query.filter(Car.price <= price_max)
    if currency is not None:
        query = query.filter(Car.currency == currency)
    if condition is not None:
        query = query.filter(Car.condition == condition)
    if body_type is not None:
        query = query.filter(Car.body_type == body_type)
    if fuel_type is not None:
        query = query.filter(Car.fuel_type == fuel_type)
    if transmission is not None:
        query = query.filter(Car.transmission == transmission)
    if drive_type is not None:
        query = query.filter(Car.drive_type == drive_type)
    if status_filter is not None:
        query = query.filter(Car.status == status_filter)

    return query.order_by(Car.created_at.desc(), Car.id.desc()).offset(skip).limit(limit).all()


@car_router.get('/detail', response_model=CarDetailSchema)
async def detail_car(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile | None = Depends(get_optional_user),
):
    query = db.query(Car).options(selectinload(Car.images)).filter(Car.id == car_id, Car.deleted_at.is_(None))
    if not is_staff(current_user):
        query = query.filter(Car.status.in_(PUBLIC_CAR_STATUSES))
    car_db = query.first()
    if not car_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Автомобиль не найден')
    return build_car_detail(car_db, db)


@car_router.put('/update/{car_id}', response_model=CarDetailSchema)
async def update_car(
    car_id: int,
    car_data: CarUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    car_db = get_car_or_404(car_id, db)

    update_data = car_data.model_dump(exclude_unset=True)
    for field in NOT_NULL_FIELDS:
        if field in update_data and update_data[field] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    if car_db.status == CarStatus.sold:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Проданный автомобиль нельзя изменить')
    if 'status' in update_data and car_db.status == CarStatus.reserved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Статус забронированного автомобиля меняется только через сделку',
        )

    check_car_condition_rules(car_state(car_db, update_data))

    if 'year' in update_data and update_data['year'] > datetime.now(timezone.utc).year + 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Год выпуска не может быть больше следующего года'
        )

    if 'price' in update_data and update_data['price'] != car_db.price:
        db.add(
            PriceHistory(
                car_id=car_db.id,
                old_price=car_db.price,
                new_price=update_data['price'],
                changed_by_id=current_user.id,
            )
        )

    for key, value in update_data.items():
        setattr(car_db, key, value)

    db.commit()
    db.refresh(car_db)
    return build_car_detail(car_db, db)


@car_router.put('/installment/{car_id}', response_model=CarDetailSchema)
async def installment_car(
    car_id: int,
    installment_data: CarInstallmentUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    car_db = get_car_or_404(car_id, db)
    if car_db.status == CarStatus.sold:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Проданный автомобиль нельзя изменить')

    update_data = installment_data.model_dump(exclude_unset=True)
    if 'installment_available' in update_data and update_data['installment_available'] is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    defaults = get_installment_defaults(db)
    max_term_months = update_data.get('max_term_months')
    if max_term_months is not None and max_term_months < defaults['min_term_months']:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f'Максимальный срок рассрочки не может быть меньше {defaults["min_term_months"]} мес.',
        )

    old_value = {key: getattr(car_db, key) for key, value in update_data.items() if getattr(car_db, key) != value}
    if old_value:
        new_value = {key: update_data[key] for key in old_value}
        for key, value in new_value.items():
            setattr(car_db, key, value)
        # create_audit_log из deal.py импортировать нельзя (deal.py импортирует car.py) — запись создаётся здесь
        db.add(
            AuditLog(
                user_id=current_user.id,
                action='car_installment_update',
                entity_name='car',
                entity_id=car_db.id,
                old_value={
                    key: f'{value:f}' if isinstance(value, Decimal) else value for key, value in old_value.items()
                },
                new_value={
                    key: f'{value:f}' if isinstance(value, Decimal) else value for key, value in new_value.items()
                },
            )
        )
        db.commit()
        db.refresh(car_db)
    return build_car_detail(car_db, db, defaults)


@car_router.delete('/delete/{car_id}', response_model=dict)
async def delete_car(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    car_db = get_car_or_404(car_id, db)
    if car_db.status == CarStatus.reserved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Нельзя удалить забронированный автомобиль')

    car_db.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {'message': 'Автомобиль удалён'}


@car_router.get('/price-history/{car_id}', response_model=List[PriceHistoryListSchema])
async def price_history_car(
    car_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    get_car_or_404(car_id, db)
    return (
        db.query(PriceHistory)
        .filter(PriceHistory.car_id == car_id)
        .order_by(PriceHistory.changed_at.desc(), PriceHistory.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
