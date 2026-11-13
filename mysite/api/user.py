from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.auth import get_password_hash
from mysite.api.dependencies import get_current_user, require_role
from mysite.db.database import get_db
from mysite.db.models import RefreshToken, SalonSettings, UserProfile, UserRole
from mysite.db.schema import (
    UserProfileCreateSchema,
    UserProfileDetailSchema,
    UserProfileDiscountLimitSchema,
    UserProfileListSchema,
    UserProfileUpdateSchema,
)

user_router = APIRouter(prefix='/user', tags=['UserProfile'])


def get_user_or_404(user_id: int, db: Session) -> UserProfile:
    user_db = db.query(UserProfile).filter(UserProfile.id == user_id).first()
    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Пользователь не найден')
    return user_db


@user_router.get('/profile', response_model=UserProfileDetailSchema)
async def detail_profile(current_user: UserProfile = Depends(get_current_user)):
    return current_user


@user_router.put('/profile', response_model=UserProfileDetailSchema)
async def update_profile(
    user_data: UserProfileUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    update_data = user_data.model_dump(exclude_unset=True)
    for field in ('email', 'phone_number'):
        if field in update_data and update_data[field] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    email = update_data.get('email')
    if email and email != current_user.email:
        email_taken = (
            db.query(UserProfile).filter(UserProfile.email == email, UserProfile.id != current_user.id).first()
        )
        if email_taken:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail='Пользователь с таким email уже существует'
            )

    for key, value in update_data.items():
        setattr(current_user, key, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь с таким email уже существует')
    db.refresh(current_user)
    return current_user


@user_router.post('/create', response_model=UserProfileDetailSchema)
async def create_user(
    user_data: UserProfileCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    if db.query(UserProfile).filter(UserProfile.username == user_data.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь с таким username уже существует')
    if db.query(UserProfile).filter(UserProfile.email == user_data.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь с таким email уже существует')

    user_dict = user_data.model_dump(exclude={'password'})
    if 'discount_limit' not in user_data.model_fields_set:
        settings_db = db.query(SalonSettings).first()
        user_dict['discount_limit'] = settings_db.default_discount_limit if settings_db else 0

    user_db = UserProfile(**user_dict, password=get_password_hash(user_data.password), role=UserRole.seller)
    db.add(user_db)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь с такими данными уже существует')
    db.refresh(user_db)
    return user_db


@user_router.get('/list', response_model=List[UserProfileListSchema])
async def list_user(
    role: UserRole | None = None,
    is_active: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    query = db.query(UserProfile)
    if role is not None:
        query = query.filter(UserProfile.role == role)
    if is_active is not None:
        query = query.filter(UserProfile.is_active == is_active)
    return query.order_by(UserProfile.id).offset(skip).limit(limit).all()


@user_router.get('/detail', response_model=UserProfileDetailSchema)
async def detail_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    return get_user_or_404(user_id, db)


@user_router.post('/block/{user_id}', response_model=UserProfileDetailSchema)
async def block_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    user_db = get_user_or_404(user_id, db)
    if user_db.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нельзя заблокировать самого себя')
    if user_db.role == UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Нельзя заблокировать администратора')
    if not user_db.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь уже заблокирован')

    user_db.is_active = False
    db.query(RefreshToken).filter(RefreshToken.user_id == user_db.id).delete()
    db.commit()
    db.refresh(user_db)
    return user_db


@user_router.post('/unblock/{user_id}', response_model=UserProfileDetailSchema)
async def unblock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    user_db = get_user_or_404(user_id, db)
    if user_db.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь не заблокирован')

    user_db.is_active = True
    db.commit()
    db.refresh(user_db)
    return user_db


@user_router.put('/discount-limit/{user_id}', response_model=UserProfileDetailSchema)
async def update_discount_limit(
    user_id: int,
    user_data: UserProfileDiscountLimitSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    user_db = get_user_or_404(user_id, db)
    if user_db.role != UserRole.seller:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Лимит скидки задаётся только продавцу')

    user_db.discount_limit = user_data.discount_limit
    db.commit()
    db.refresh(user_db)
    return user_db
