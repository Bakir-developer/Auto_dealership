from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.dependencies import require_role
from mysite.db.database import get_db
from mysite.db.models import Brand, Car, CarModel, UserProfile, UserRole
from mysite.db.schema import BrandCreateSchema, BrandDetailSchema, BrandListSchema, BrandUpdateSchema

brand_router = APIRouter(prefix='/brand', tags=['Brand'])

DUPLICATE_DETAIL = 'Марка с таким названием уже существует'


def get_brand_or_404(brand_id: int, db: Session) -> Brand:
    brand_db = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')
    return brand_db


def check_brand_name_free(brand_name: str, db: Session, exclude_id: int | None = None):
    # casefold в Python: lower()/ilike в SQLite не работают для кириллицы
    name = brand_name.casefold()
    for brand_id, other_name in db.query(Brand.id, Brand.brand_name).all():
        if brand_id != exclude_id and other_name.casefold() == name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_DETAIL)


@brand_router.post('/create', response_model=BrandDetailSchema)
async def create_brand(
    brand_data: BrandCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    check_brand_name_free(brand_data.brand_name, db)

    brand_db = Brand(**brand_data.model_dump())
    db.add(brand_db)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_DETAIL)
    db.refresh(brand_db)
    return brand_db


@brand_router.get('/list', response_model=List[BrandListSchema])
async def list_brand(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return db.query(Brand).order_by(Brand.brand_name, Brand.id).offset(skip).limit(limit).all()


@brand_router.get('/detail', response_model=BrandDetailSchema)
async def detail_brand(brand_id: int, db: Session = Depends(get_db)):
    return get_brand_or_404(brand_id, db)


@brand_router.put('/update/{brand_id}', response_model=BrandDetailSchema)
async def update_brand(
    brand_id: int,
    brand_data: BrandUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    brand_db = get_brand_or_404(brand_id, db)

    update_data = brand_data.model_dump(exclude_unset=True)
    if 'brand_name' in update_data:
        if update_data['brand_name'] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')
        check_brand_name_free(update_data['brand_name'], db, exclude_id=brand_db.id)

    for key, value in update_data.items():
        setattr(brand_db, key, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_DETAIL)
    db.refresh(brand_db)
    return brand_db


@brand_router.delete('/delete/{brand_id}', response_model=dict)
async def delete_brand(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    brand_db = get_brand_or_404(brand_id, db)

    has_models = db.query(CarModel.id).filter(CarModel.brand_id == brand_id).first()
    has_cars = db.query(Car.id).filter(Car.brand_id == brand_id).first()
    if has_models or has_cars:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Нельзя удалить марку: к ней привязаны модели или автомобили',
        )

    db.delete(brand_db)
    db.commit()
    return {'message': 'Марка удалена'}
