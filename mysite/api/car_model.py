from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.dependencies import require_role
from mysite.db.database import get_db
from mysite.db.models import Brand, Car, CarModel, UserProfile, UserRole
from mysite.db.schema import (
    CarModelCreateSchema,
    CarModelDetailSchema,
    CarModelListSchema,
    CarModelUpdateSchema,
)

car_model_router = APIRouter(prefix='/car-model', tags=['CarModel'])

DUPLICATE_DETAIL = 'Такая модель у этой марки уже существует'


def get_car_model_or_404(car_model_id: int, db: Session) -> CarModel:
    car_model_db = db.query(CarModel).filter(CarModel.id == car_model_id).first()
    if not car_model_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Модель не найдена')
    return car_model_db


def check_brand_exists(brand_id: int, db: Session):
    if not db.query(Brand.id).filter(Brand.id == brand_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')


def check_model_name_free(brand_id: int, model_name: str, db: Session, exclude_id: int | None = None):
    # casefold в Python: lower()/ilike в SQLite не работают для кириллицы
    name = model_name.casefold()
    for model_id, other_name in db.query(CarModel.id, CarModel.model_name).filter(CarModel.brand_id == brand_id).all():
        if model_id != exclude_id and other_name.casefold() == name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_DETAIL)


@car_model_router.post('/create', response_model=CarModelDetailSchema)
async def create_car_model(
    car_model_data: CarModelCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    check_brand_exists(car_model_data.brand_id, db)
    check_model_name_free(car_model_data.brand_id, car_model_data.model_name, db)

    car_model_db = CarModel(**car_model_data.model_dump())
    db.add(car_model_db)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_DETAIL)
    db.refresh(car_model_db)
    return car_model_db


@car_model_router.get('/list', response_model=List[CarModelListSchema])
async def list_car_model(
    brand_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(CarModel)
    if brand_id is not None:
        query = query.filter(CarModel.brand_id == brand_id)
    return query.order_by(CarModel.model_name, CarModel.id).offset(skip).limit(limit).all()


@car_model_router.get('/detail', response_model=CarModelDetailSchema)
async def detail_car_model(car_model_id: int, db: Session = Depends(get_db)):
    return get_car_model_or_404(car_model_id, db)


@car_model_router.put('/update/{car_model_id}', response_model=CarModelDetailSchema)
async def update_car_model(
    car_model_id: int,
    car_model_data: CarModelUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    car_model_db = get_car_model_or_404(car_model_id, db)

    update_data = car_model_data.model_dump(exclude_unset=True)
    for field in ('brand_id', 'model_name'):
        if field in update_data and update_data[field] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    new_brand_id = update_data.get('brand_id', car_model_db.brand_id)
    if new_brand_id != car_model_db.brand_id:
        check_brand_exists(new_brand_id, db)
        # учитываем и мягко удалённые авто: Car.brand_id должен совпадать с CarModel.brand_id
        if db.query(Car.id).filter(Car.car_model_id == car_model_db.id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail='Нельзя сменить марку: у модели есть автомобили'
            )
    check_model_name_free(new_brand_id, update_data.get('model_name', car_model_db.model_name), db, car_model_db.id)

    for key, value in update_data.items():
        setattr(car_model_db, key, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_DETAIL)
    db.refresh(car_model_db)
    return car_model_db


@car_model_router.delete('/delete/{car_model_id}', response_model=dict)
async def delete_car_model(
    car_model_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    car_model_db = get_car_model_or_404(car_model_id, db)

    if db.query(Car.id).filter(Car.car_model_id == car_model_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Нельзя удалить модель: к ней привязаны автомобили'
        )

    db.delete(car_model_db)
    db.commit()
    return {'message': 'Модель удалена'}
