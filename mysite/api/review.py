from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.deal import create_audit_log, get_deal_or_404
from mysite.api.dependencies import get_current_user, require_role
from mysite.api.notification import create_notification
from mysite.db.database import get_db
from mysite.db.models import Deal, DealStatus, NotificationType, Review, UserProfile, UserRole
from mysite.db.schema import ReviewCreateSchema, ReviewDetailSchema, ReviewListSchema, ReviewUpdateSchema

review_router = APIRouter(prefix='/review', tags=['Review'])

REVIEW_EXISTS = 'Отзыв по этой сделке уже оставлен'


def visible_reviews_query(db: Session, current_user: UserProfile):
    """Отзывы по неудалённым сделкам: admin — все, client — свои, seller — о себе."""
    query = db.query(Review).join(Deal, Deal.id == Review.deal_id).filter(Deal.deleted_at.is_(None))
    if current_user.role == UserRole.client:
        query = query.filter(Review.client_id == current_user.id)
    elif current_user.role == UserRole.seller:
        query = query.filter(Review.seller_id == current_user.id)
    return query


def get_review_or_404(review_id: int, db: Session, current_user: UserProfile) -> Review:
    review_db = visible_reviews_query(db, current_user).filter(Review.id == review_id).first()
    if not review_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Отзыв не найден')
    return review_db


@review_router.post('/create', response_model=ReviewDetailSchema)
async def create_review(
    review_data: ReviewCreateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    deal_db = get_deal_or_404(review_data.deal_id, db, current_user)
    if deal_db.status != DealStatus.delivered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail='Отзыв можно оставить только после выдачи автомобиля'
        )

    deal_id = deal_db.id
    seller_id = deal_db.seller_id
    duplicate_db = db.query(Review.id).filter(Review.deal_id == deal_id).first()
    if duplicate_db:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=REVIEW_EXISTS)

    review_db = Review(**review_data.model_dump(), client_id=current_user.id, seller_id=seller_id)
    db.add(review_db)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=REVIEW_EXISTS)

    create_notification(
        db, seller_id, NotificationType.deal, f'Новый отзыв по сделке #{deal_id}: оценка {review_data.stars}/5'
    )
    db.commit()
    db.refresh(review_db)
    return review_db


@review_router.get('/list', response_model=List[ReviewListSchema])
async def list_review(
    seller_id: int | None = None,
    stars: int | None = Query(None, ge=1, le=5),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    query = visible_reviews_query(db, current_user)
    if current_user.role == UserRole.admin and seller_id is not None:
        query = query.filter(Review.seller_id == seller_id)
    if stars is not None:
        query = query.filter(Review.stars == stars)
    return query.order_by(Review.created_at.desc(), Review.id.desc()).offset(skip).limit(limit).all()


@review_router.get('/detail', response_model=ReviewDetailSchema)
async def detail_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    return get_review_or_404(review_id, db, current_user)


@review_router.put('/update/{review_id}', response_model=ReviewDetailSchema)
async def update_review(
    review_id: int,
    review_data: ReviewUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.client)),
):
    review_db = get_review_or_404(review_id, db, current_user)

    update_data = review_data.model_dump(exclude_unset=True)
    if 'stars' in update_data and update_data['stars'] is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    for key, value in update_data.items():
        setattr(review_db, key, value)

    db.commit()
    db.refresh(review_db)
    return review_db


@review_router.delete('/delete/{review_id}', response_model=dict)
async def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.client)),
):
    review_db = get_review_or_404(review_id, db, current_user)

    if current_user.role == UserRole.admin:
        create_audit_log(
            db,
            current_user.id,
            'review_delete',
            'review',
            review_id,
            {'deal_id': review_db.deal_id, 'stars': review_db.stars, 'comment': review_db.comment},
            None,
        )
    db.delete(review_db)
    db.commit()
    return {'message': 'Отзыв удалён'}
