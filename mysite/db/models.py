from datetime import datetime, time
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, PyEnum):
    admin = 'admin'
    seller = 'seller'
    client = 'client'


class CarCondition(str, PyEnum):
    new = 'new'
    used = 'used'


class CarStatus(str, PyEnum):
    in_transit = 'in_transit'
    available = 'available'
    reserved = 'reserved'
    sold = 'sold'
    withdrawn = 'withdrawn'


class BodyType(str, PyEnum):
    sedan = 'sedan'
    hatchback = 'hatchback'
    suv = 'suv'
    crossover = 'crossover'
    coupe = 'coupe'
    minivan = 'minivan'
    pickup = 'pickup'
    wagon = 'wagon'
    other = 'other'


class FuelType(str, PyEnum):
    petrol = 'petrol'
    diesel = 'diesel'
    hybrid = 'hybrid'
    electric = 'electric'
    gas = 'gas'


class Transmission(str, PyEnum):
    manual = 'manual'
    automatic = 'automatic'
    robot = 'robot'
    cvt = 'cvt'


class DriveType(str, PyEnum):
    front = 'front'
    rear = 'rear'
    full = 'full'


class Steering(str, PyEnum):
    left = 'left'
    right = 'right'


class Currency(str, PyEnum):
    KGS = 'KGS'
    USD = 'USD'


class LeadType(str, PyEnum):
    purchase = 'purchase'
    trade_in = 'trade_in'
    question = 'question'


class LeadStatus(str, PyEnum):
    new = 'new'
    in_progress = 'in_progress'
    closed = 'closed'
    rejected = 'rejected'


class DealStatus(str, PyEnum):
    new = 'new'
    in_progress = 'in_progress'
    reserved = 'reserved'
    paid = 'paid'
    delivered = 'delivered'
    cancelled = 'cancelled'


class DiscountStatus(str, PyEnum):
    pending = 'pending'
    approved = 'approved'
    rejected = 'rejected'


class TradeInStatus(str, PyEnum):
    new = 'new'
    evaluating = 'evaluating'
    offered = 'offered'
    accepted = 'accepted'
    rejected = 'rejected'


class NotificationType(str, PyEnum):
    lead = 'lead'
    deal = 'deal'
    discount = 'discount'
    reservation = 'reservation'
    system = 'system'


class UserProfile(Base):
    __tablename__ = 'user_profile'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    phone_number: Mapped[str] = mapped_column(String(13), default='+996')
    profile_image: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.client)
    password: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    discount_limit: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    refresh_tokens: Mapped[List['RefreshToken']] = relationship(
        'RefreshToken', back_populates='user', cascade='all, delete-orphan'
    )
    created_cars: Mapped[List['Car']] = relationship('Car', back_populates='created_by')
    price_changes: Mapped[List['PriceHistory']] = relationship('PriceHistory', back_populates='changed_by')
    client_leads: Mapped[List['Lead']] = relationship('Lead', back_populates='client', foreign_keys='Lead.client_id')
    seller_leads: Mapped[List['Lead']] = relationship('Lead', back_populates='seller', foreign_keys='Lead.seller_id')
    lead_notes: Mapped[List['LeadNote']] = relationship('LeadNote', back_populates='seller')
    client_deals: Mapped[List['Deal']] = relationship('Deal', back_populates='client', foreign_keys='Deal.client_id')
    seller_deals: Mapped[List['Deal']] = relationship('Deal', back_populates='seller', foreign_keys='Deal.seller_id')
    discount_requests: Mapped[List['DiscountRequest']] = relationship(
        'DiscountRequest', back_populates='seller', foreign_keys='DiscountRequest.seller_id'
    )
    decided_discounts: Mapped[List['DiscountRequest']] = relationship(
        'DiscountRequest', back_populates='decided_by', foreign_keys='DiscountRequest.decided_by_id'
    )
    client_trade_ins: Mapped[List['TradeIn']] = relationship(
        'TradeIn', back_populates='client', foreign_keys='TradeIn.client_id'
    )
    seller_trade_ins: Mapped[List['TradeIn']] = relationship(
        'TradeIn', back_populates='seller', foreign_keys='TradeIn.seller_id'
    )
    favorites: Mapped[List['Favorite']] = relationship('Favorite', back_populates='user', cascade='all, delete-orphan')
    client_reviews: Mapped[List['Review']] = relationship(
        'Review', back_populates='client', foreign_keys='Review.client_id'
    )
    seller_reviews: Mapped[List['Review']] = relationship(
        'Review', back_populates='seller', foreign_keys='Review.seller_id'
    )
    notifications: Mapped[List['Notification']] = relationship(
        'Notification', back_populates='user', cascade='all, delete-orphan'
    )
    audit_logs: Mapped[List['AuditLog']] = relationship('AuditLog', back_populates='user')

    __table_args__ = (
        CheckConstraint('discount_limit >= 0 AND discount_limit <= 100', name='ck_user_discount_limit_range'),
    )


class RefreshToken(Base):
    __tablename__ = 'refresh_token'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'), index=True)
    token: Mapped[str] = mapped_column(String, unique=True)

    user: Mapped['UserProfile'] = relationship('UserProfile', back_populates='refresh_tokens')


class Brand(Base):
    __tablename__ = 'brand'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    brand_name: Mapped[str] = mapped_column(String(50), unique=True)
    brand_logo: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    car_models: Mapped[List['CarModel']] = relationship('CarModel', back_populates='brand')
    cars: Mapped[List['Car']] = relationship('Car', back_populates='brand')


class CarModel(Base):
    __tablename__ = 'car_model'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey('brand.id'))
    model_name: Mapped[str] = mapped_column(String(50))

    brand: Mapped['Brand'] = relationship('Brand', back_populates='car_models')
    cars: Mapped[List['Car']] = relationship('Car', back_populates='car_model')

    __table_args__ = (UniqueConstraint('brand_id', 'model_name', name='uq_brand_model_name'),)


class Car(Base):
    __tablename__ = 'car'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vin: Mapped[str] = mapped_column(String(17), unique=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey('brand.id'), index=True)
    car_model_id: Mapped[int] = mapped_column(ForeignKey('car_model.id'), index=True)
    year: Mapped[int] = mapped_column(SmallInteger, index=True)
    body_type: Mapped[BodyType] = mapped_column(Enum(BodyType))
    color: Mapped[str] = mapped_column(String(30))
    engine_volume: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 1), nullable=True)
    fuel_type: Mapped[FuelType] = mapped_column(Enum(FuelType))
    transmission: Mapped[Transmission] = mapped_column(Enum(Transmission))
    drive_type: Mapped[DriveType] = mapped_column(Enum(DriveType))
    steering: Mapped[Steering] = mapped_column(Enum(Steering), default=Steering.left)
    condition: Mapped[CarCondition] = mapped_column(Enum(CarCondition))
    status: Mapped[CarStatus] = mapped_column(Enum(CarStatus), default=CarStatus.available, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), index=True)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), default=Currency.KGS)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mileage: Mapped[int] = mapped_column(Integer, default=0)
    owners_count: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    has_accidents: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    accident_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customs_cleared: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_in_kr: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    brand: Mapped['Brand'] = relationship('Brand', back_populates='cars')
    car_model: Mapped['CarModel'] = relationship('CarModel', back_populates='cars')
    created_by: Mapped['UserProfile'] = relationship('UserProfile', back_populates='created_cars')
    images: Mapped[List['CarImage']] = relationship('CarImage', back_populates='car', cascade='all, delete-orphan')
    price_history: Mapped[List['PriceHistory']] = relationship('PriceHistory', back_populates='car')
    leads: Mapped[List['Lead']] = relationship('Lead', back_populates='car')
    deals: Mapped[List['Deal']] = relationship('Deal', back_populates='car')
    favorites: Mapped[List['Favorite']] = relationship('Favorite', back_populates='car', cascade='all, delete-orphan')

    __table_args__ = (
        CheckConstraint('price > 0', name='ck_car_price_positive'),
        CheckConstraint('length(vin) = 17', name='ck_car_vin_length'),
        CheckConstraint('mileage >= 0', name='ck_car_mileage_not_negative'),
        CheckConstraint('owners_count IS NULL OR owners_count >= 0', name='ck_car_owners_not_negative'),
        CheckConstraint('engine_volume IS NULL OR engine_volume > 0', name='ck_car_engine_volume_positive'),
    )


class CarImage(Base):
    __tablename__ = 'car_image'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(ForeignKey('car.id'), index=True)
    car_image: Mapped[str] = mapped_column(String)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)

    car: Mapped['Car'] = relationship('Car', back_populates='images')

    __table_args__ = (CheckConstraint('position >= 0', name='ck_car_image_position_not_negative'),)


class PriceHistory(Base):
    __tablename__ = 'price_history'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(ForeignKey('car.id'), index=True)
    old_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    new_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    changed_by_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    car: Mapped['Car'] = relationship('Car', back_populates='price_history')
    changed_by: Mapped['UserProfile'] = relationship('UserProfile', back_populates='price_changes')


class Lead(Base):
    __tablename__ = 'lead'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'), index=True)
    car_id: Mapped[Optional[int]] = mapped_column(ForeignKey('car.id'), nullable=True)
    lead_type: Mapped[LeadType] = mapped_column(Enum(LeadType))
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.new)
    seller_id: Mapped[Optional[int]] = mapped_column(ForeignKey('user_profile.id'), nullable=True, index=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped['UserProfile'] = relationship('UserProfile', back_populates='client_leads', foreign_keys=[client_id])
    seller: Mapped[Optional['UserProfile']] = relationship(
        'UserProfile', back_populates='seller_leads', foreign_keys=[seller_id]
    )
    car: Mapped[Optional['Car']] = relationship('Car', back_populates='leads')
    notes: Mapped[List['LeadNote']] = relationship('LeadNote', back_populates='lead', cascade='all, delete-orphan')


class LeadNote(Base):
    __tablename__ = 'lead_note'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey('lead.id'), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped['Lead'] = relationship('Lead', back_populates='notes')
    seller: Mapped['UserProfile'] = relationship('UserProfile', back_populates='lead_notes')


class Deal(Base):
    __tablename__ = 'deal'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(ForeignKey('car.id'), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'), index=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    final_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[Currency] = mapped_column(Enum(Currency), default=Currency.KGS)
    status: Mapped[DealStatus] = mapped_column(Enum(DealStatus), default=DealStatus.new, index=True)
    reserved_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    car: Mapped['Car'] = relationship('Car', back_populates='deals')
    client: Mapped['UserProfile'] = relationship('UserProfile', back_populates='client_deals', foreign_keys=[client_id])
    seller: Mapped['UserProfile'] = relationship('UserProfile', back_populates='seller_deals', foreign_keys=[seller_id])
    discount_requests: Mapped[List['DiscountRequest']] = relationship('DiscountRequest', back_populates='deal')
    review: Mapped[Optional['Review']] = relationship('Review', back_populates='deal', uselist=False)

    __table_args__ = (
        CheckConstraint('base_price > 0', name='ck_deal_base_price_positive'),
        CheckConstraint('final_price > 0', name='ck_deal_final_price_positive'),
        CheckConstraint('discount_percent >= 0 AND discount_percent <= 100', name='ck_deal_discount_range'),
        CheckConstraint('final_price <= base_price', name='ck_deal_final_not_above_base'),
    )


class DiscountRequest(Base):
    __tablename__ = 'discount_request'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey('deal.id'), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    requested_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    status: Mapped[DiscountStatus] = mapped_column(Enum(DiscountStatus), default=DiscountStatus.pending)
    decided_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey('user_profile.id'), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    deal: Mapped['Deal'] = relationship('Deal', back_populates='discount_requests')
    seller: Mapped['UserProfile'] = relationship(
        'UserProfile', back_populates='discount_requests', foreign_keys=[seller_id]
    )
    decided_by: Mapped[Optional['UserProfile']] = relationship(
        'UserProfile', back_populates='decided_discounts', foreign_keys=[decided_by_id]
    )

    __table_args__ = (
        CheckConstraint('requested_percent > 0 AND requested_percent <= 100', name='ck_discount_request_range'),
    )


class TradeIn(Base):
    __tablename__ = 'trade_in'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'), index=True)
    brand_name: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(50))
    year: Mapped[int] = mapped_column(SmallInteger)
    mileage: Mapped[int] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), default=Currency.KGS)
    status: Mapped[TradeInStatus] = mapped_column(Enum(TradeInStatus), default=TradeInStatus.new)
    seller_id: Mapped[Optional[int]] = mapped_column(ForeignKey('user_profile.id'), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped['UserProfile'] = relationship(
        'UserProfile', back_populates='client_trade_ins', foreign_keys=[client_id]
    )
    seller: Mapped[Optional['UserProfile']] = relationship(
        'UserProfile', back_populates='seller_trade_ins', foreign_keys=[seller_id]
    )
    images: Mapped[List['TradeInImage']] = relationship(
        'TradeInImage', back_populates='trade_in', cascade='all, delete-orphan'
    )

    __table_args__ = (
        CheckConstraint('mileage >= 0', name='ck_trade_in_mileage_not_negative'),
        CheckConstraint('estimated_price IS NULL OR estimated_price > 0', name='ck_trade_in_price_positive'),
    )


class TradeInImage(Base):
    __tablename__ = 'trade_in_image'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_in_id: Mapped[int] = mapped_column(ForeignKey('trade_in.id'), index=True)
    trade_in_image: Mapped[str] = mapped_column(String)

    trade_in: Mapped['TradeIn'] = relationship('TradeIn', back_populates='images')


class Favorite(Base):
    __tablename__ = 'favorite'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    car_id: Mapped[int] = mapped_column(ForeignKey('car.id'))

    user: Mapped['UserProfile'] = relationship('UserProfile', back_populates='favorites')
    car: Mapped['Car'] = relationship('Car', back_populates='favorites')

    __table_args__ = (UniqueConstraint('user_id', 'car_id', name='uq_favorite_user_car'),)


class Review(Base):
    __tablename__ = 'review'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    deal_id: Mapped[int] = mapped_column(ForeignKey('deal.id'), unique=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'), index=True)
    stars: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped['UserProfile'] = relationship(
        'UserProfile', back_populates='client_reviews', foreign_keys=[client_id]
    )
    seller: Mapped['UserProfile'] = relationship(
        'UserProfile', back_populates='seller_reviews', foreign_keys=[seller_id]
    )
    deal: Mapped['Deal'] = relationship('Deal', back_populates='review')

    __table_args__ = (CheckConstraint('stars BETWEEN 1 AND 5', name='ck_review_stars_range'),)


class Notification(Base):
    __tablename__ = 'notification'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'), index=True)
    notification_type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    text: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped['UserProfile'] = relationship('UserProfile', back_populates='notifications')


class AuditLog(Base):
    __tablename__ = 'audit_log'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('user_profile.id'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50))
    entity_name: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[Optional['UserProfile']] = relationship('UserProfile', back_populates='audit_logs')


class SalonSettings(Base):
    __tablename__ = 'salon_settings'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    salon_name: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(200))
    phone_number: Mapped[str] = mapped_column(String(13))
    work_start: Mapped[time] = mapped_column(Time)
    work_end: Mapped[time] = mapped_column(Time)
    reservation_hours: Mapped[int] = mapped_column(SmallInteger, default=48)
    default_discount_limit: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=3)

    __table_args__ = (
        CheckConstraint('id = 1', name='ck_salon_settings_single_row'),
        CheckConstraint('work_end > work_start', name='ck_salon_work_hours'),
        CheckConstraint(
            'default_discount_limit >= 0 AND default_discount_limit <= 100', name='ck_salon_discount_limit_range'
        ),
    )
