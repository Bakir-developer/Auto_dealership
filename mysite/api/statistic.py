from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from mysite.api.deal import CENT
from mysite.api.dependencies import require_role
from mysite.db.database import get_db
from mysite.db.models import (
    Car,
    CarStatus,
    Currency,
    Deal,
    DealStatus,
    DiscountRequest,
    DiscountStatus,
    Lead,
    LeadStatus,
    Review,
    TradeIn,
    TradeInStatus,
    UserProfile,
    UserRole,
)
from mysite.db.schema import StatisticGeneralSchema, StatisticSellerRowSchema, StatisticSellerSchema

statistic_router = APIRouter(prefix='/statistic', tags=['Statistic'])


# ---------- Хелперы ----------


def get_period_bounds(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """Границы периода: сутки UTC, date_to включительно -> правая граница строго меньше."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Дата начала позже даты окончания')
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from is not None else None
    end = None
    if date_to is not None and date_to != date.max:  # для date.max правой границы нет (иначе OverflowError)
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start, end


def period_filters(column, start: datetime | None, end: datetime | None) -> list:
    filters = []
    if start is not None:
        filters.append(column >= start)
    if end is not None:
        filters.append(column < end)
    return filters


def count_by_status(db: Session, status_column, status_enum, *filters) -> dict:
    """COUNT ... GROUP BY по статусу; в ответе все значения Enum (отсутствующие — 0)."""
    result = {member: 0 for member in status_enum}
    rows = db.query(status_column, func.count()).filter(*filters).group_by(status_column).all()
    for status_value, count in rows:
        result[status_value] = count
    return result


def sum_money_by_currency(rows) -> dict:
    """rows — пары (currency, сумма). Суммирование в Decimal: SUM() в SQLite вернул бы float."""
    result = {member: Decimal('0.00') for member in Currency}
    for currency, amount in rows:
        result[currency] += amount
    return {currency: total.quantize(CENT, rounding=ROUND_HALF_UP) for currency, total in result.items()}


def calc_avg_stars(stars_total: int, reviews_count: int) -> Decimal | None:
    if reviews_count == 0:
        return None
    return (Decimal(stars_total) / Decimal(reviews_count)).quantize(CENT, rounding=ROUND_HALF_UP)


def reviews_query_filters(start: datetime | None, end: datetime | None, seller_id: int | None = None) -> list:
    filters = [Deal.deleted_at.is_(None), *period_filters(Review.created_at, start, end)]
    if seller_id is not None:
        filters.append(Review.seller_id == seller_id)
    return filters


def avg_stars(db: Session, start: datetime | None, end: datetime | None, seller_id: int | None = None):
    """Возвращает (число отзывов, средняя оценка); SUM и COUNT — целые, деление в Decimal."""
    stars_total, reviews_count = (
        db.query(func.coalesce(func.sum(Review.stars), 0), func.count(Review.id))
        .join(Deal, Deal.id == Review.deal_id)
        .filter(*reviews_query_filters(start, end, seller_id))
        .one()
    )
    return reviews_count, calc_avg_stars(int(stars_total), reviews_count)


def delivered_deals_filters(start: datetime | None, end: datetime | None, seller_id: int | None = None) -> list:
    filters = [
        Deal.status == DealStatus.delivered,
        Deal.deleted_at.is_(None),
        *period_filters(Deal.delivered_at, start, end),
    ]
    if seller_id is not None:
        filters.append(Deal.seller_id == seller_id)
    return filters


def build_seller_statistic(
    db: Session,
    seller_db: UserProfile,
    start: datetime | None,
    end: datetime | None,
    date_from: date | None,
    date_to: date | None,
) -> StatisticSellerSchema:
    seller_id = seller_db.id
    delivered_rows = (
        db.query(Deal.currency, Deal.final_price).filter(*delivered_deals_filters(start, end, seller_id)).all()
    )
    reviews_count, average_stars = avg_stars(db, start, end, seller_id)
    return StatisticSellerSchema(
        seller_id=seller_id,
        username=seller_db.username,
        leads_by_status=count_by_status(
            db, Lead.status, LeadStatus, Lead.seller_id == seller_id, *period_filters(Lead.created_at, start, end)
        ),
        deals_by_status=count_by_status(
            db,
            Deal.status,
            DealStatus,
            Deal.seller_id == seller_id,
            Deal.deleted_at.is_(None),
            *period_filters(Deal.created_at, start, end),
        ),
        # у DiscountRequest нет created_at — период не применяется
        discounts_by_status=count_by_status(
            db, DiscountRequest.status, DiscountStatus, DiscountRequest.seller_id == seller_id
        ),
        trade_ins_by_status=count_by_status(
            db,
            TradeIn.status,
            TradeInStatus,
            TradeIn.seller_id == seller_id,
            *period_filters(TradeIn.created_at, start, end),
        ),
        revenue=sum_money_by_currency(delivered_rows),
        delivered_count=len(delivered_rows),
        reviews_count=reviews_count,
        avg_stars=average_stars,
        date_from=date_from,
        date_to=date_to,
    )


def get_seller_or_404(seller_id: int, db: Session) -> UserProfile:
    seller_db = db.query(UserProfile).filter(UserProfile.id == seller_id, UserProfile.role == UserRole.seller).first()
    if not seller_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Продавец не найден')
    return seller_db


def build_seller_rows(db: Session, start: datetime | None, end: datetime | None) -> list[StatisticSellerRowSchema]:
    """Строки по всем продавцам: по одной групповой выборке на метрику, без N+1."""
    sellers_db = db.query(UserProfile).filter(UserProfile.role == UserRole.seller).all()

    deals_counts = dict(
        db.query(Deal.seller_id, func.count())
        .filter(Deal.deleted_at.is_(None), *period_filters(Deal.created_at, start, end))
        .group_by(Deal.seller_id)
        .all()
    )
    delivered_rows = (
        db.query(Deal.seller_id, Deal.currency, Deal.final_price).filter(*delivered_deals_filters(start, end)).all()
    )
    delivered_by_seller: dict[int, list] = {}
    for seller_id, currency, final_price in delivered_rows:
        delivered_by_seller.setdefault(seller_id, []).append((currency, final_price))
    stars_rows = (
        db.query(Review.seller_id, func.sum(Review.stars), func.count(Review.id))
        .join(Deal, Deal.id == Review.deal_id)
        .filter(*reviews_query_filters(start, end))
        .group_by(Review.seller_id)
        .all()
    )
    stars_by_seller = {seller_id: (int(stars_total), count) for seller_id, stars_total, count in stars_rows}

    rows = []
    for seller_db in sellers_db:
        delivered = delivered_by_seller.get(seller_db.id, [])
        stars_total, reviews_count = stars_by_seller.get(seller_db.id, (0, 0))
        rows.append(
            StatisticSellerRowSchema(
                seller_id=seller_db.id,
                username=seller_db.username,
                is_active=seller_db.is_active,
                deals_count=deals_counts.get(seller_db.id, 0),
                delivered_count=len(delivered),
                revenue=sum_money_by_currency(delivered),
                avg_stars=calc_avg_stars(stars_total, reviews_count),
            )
        )
    rows.sort(key=lambda row: (-row.delivered_count, row.seller_id))
    return rows


# ---------- Statistic ----------


@statistic_router.get('/general', response_model=StatisticGeneralSchema)
async def general_statistic(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    start, end = get_period_bounds(date_from, date_to)

    delivered_rows = (
        db.query(Deal.currency, Deal.final_price, Deal.discount_percent)
        .filter(*delivered_deals_filters(start, end))
        .all()
    )
    avg_discount_percent = None
    if delivered_rows:
        discounts_total = sum((discount for _, _, discount in delivered_rows), Decimal('0'))
        avg_discount_percent = (discounts_total / len(delivered_rows)).quantize(CENT, rounding=ROUND_HALF_UP)

    reviews_count, average_stars = avg_stars(db, start, end)
    discounts_pending = db.query(DiscountRequest).filter(DiscountRequest.status == DiscountStatus.pending).count()
    clients_count = (
        db.query(UserProfile).filter(UserProfile.role == UserRole.client, UserProfile.is_active.is_(True)).count()
    )

    return StatisticGeneralSchema(
        cars_by_status=count_by_status(db, Car.status, CarStatus, Car.deleted_at.is_(None)),
        leads_by_status=count_by_status(db, Lead.status, LeadStatus, *period_filters(Lead.created_at, start, end)),
        deals_by_status=count_by_status(
            db, Deal.status, DealStatus, Deal.deleted_at.is_(None), *period_filters(Deal.created_at, start, end)
        ),
        trade_ins_by_status=count_by_status(
            db, TradeIn.status, TradeInStatus, *period_filters(TradeIn.created_at, start, end)
        ),
        discounts_pending=discounts_pending,
        revenue=sum_money_by_currency([(currency, price) for currency, price, _ in delivered_rows]),
        delivered_count=len(delivered_rows),
        avg_discount_percent=avg_discount_percent,
        clients_count=clients_count,
        reviews_count=reviews_count,
        avg_stars=average_stars,
        sellers=build_seller_rows(db, start, end),
        date_from=date_from,
        date_to=date_to,
    )


@statistic_router.get('/my', response_model=StatisticSellerSchema)
async def my_statistic(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.seller)),
):
    start, end = get_period_bounds(date_from, date_to)
    return build_seller_statistic(db, current_user, start, end, date_from, date_to)


@statistic_router.get('/seller/{seller_id}', response_model=StatisticSellerSchema)
async def seller_statistic(
    seller_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    seller_db = get_seller_or_404(seller_id, db)
    start, end = get_period_bounds(date_from, date_to)
    return build_seller_statistic(db, seller_db, start, end, date_from, date_to)
