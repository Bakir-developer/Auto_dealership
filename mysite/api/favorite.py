from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager

from mysite.api.car import PUBLIC_CAR_STATUSES, get_car_or_404
from mysite.api.dependencies import require_role
from mysite.db.database import get_db
from mysite.db.models import Car, Favorite, UserProfile, UserRole
from mysite.db.schema import FavoriteCreateSchema, FavoriteDetailSchema, FavoriteListSchema

favorite_router = APIRouter(prefix='/favorite', tags=['Favorite'])

FAVORITE_NOT_FOUND = 'Запись избранного не найдена'
FAVORITE_EXISTS = 'Автомобиль уже в избранном'


def visible_favorites_query(db: Session, current_user: UserProfile):
    """Избранное клиента; проданные, снятые и удалённые авто скрыты (записи не удаляются)."""
    return (
        db.query(Favorite)
        .join(Car, Car.id == Favorite.car_id)
        .options(contains_eager(Favorite.car))
        .filter(
            Favorite.user_id == current_user.id,
            Car.deleted_at.is_(None),
            Car.status.in_(PUBLIC_CAR_STATUSES),
        )
    )


@favorite_router.post('/create', response_model=FavoriteDetailSchema)
async def create_favorite(
    favorite_data: FavoriteCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    car_db = get_car_or_404(favorite_data.car_id, db, current_user, only_visible=True)

    car_id = car_db.id
    duplicate_db = db.query(Favorite.id).filter(Favorite.user_id == current_user.id, Favorite.car_id == car_id).first()
    if duplicate_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=FAVORITE_EXISTS)

    favorite_db = Favorite(**favorite_data.model_dump(), user_id=current_user.id)
    db.add(favorite_db)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=FAVORITE_EXISTS)
    db.refresh(favorite_db)
    return favorite_db


@favorite_router.get('/list', response_model=List[FavoriteListSchema])
async def list_favorite(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    return visible_favorites_query(db, current_user).order_by(Favorite.id.desc()).offset(skip).limit(limit).all()


@favorite_router.get('/detail', response_model=FavoriteDetailSchema)
async def detail_favorite(
    favorite_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    favorite_db = visible_favorites_query(db, current_user).filter(Favorite.id == favorite_id).first()
    if not favorite_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FAVORITE_NOT_FOUND)
    return favorite_db


@favorite_router.delete('/delete/{favorite_id}', response_model=dict)
async def delete_favorite(
    favorite_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    # удалить можно и запись о скрытом авто — фильтр по авто не применяется
    favorite_db = db.query(Favorite).filter(Favorite.id == favorite_id, Favorite.user_id == current_user.id).first()
    if not favorite_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=FAVORITE_NOT_FOUND)

    db.delete(favorite_db)
    db.commit()
    return {'message': 'Автомобиль удалён из избранного'}
