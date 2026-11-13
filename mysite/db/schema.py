import re
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, List

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from .models import (
    BodyType,
    CarCondition,
    CarStatus,
    Currency,
    DealStatus,
    DiscountStatus,
    DriveType,
    FuelType,
    LeadStatus,
    LeadType,
    NotificationType,
    Steering,
    TestDriveStatus,
    TradeInStatus,
    Transmission,
    UserRole,
)

PHONE_RE = re.compile(r'^\+996\d{9}$')
VIN_RE = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')


def validate_phone(value: str) -> str:
    if not PHONE_RE.match(value):
        raise ValueError('Телефон должен быть в формате +996XXXXXXXXX')
    return value


def validate_vin(value: str) -> str:
    value = value.upper()
    if not VIN_RE.match(value):
        raise ValueError('VIN должен состоять из 17 символов (латиница и цифры, без I, O, Q)')
    return value


def validate_password(value: str) -> str:
    if len(value.encode('utf-8')) > 72:
        raise ValueError('Пароль слишком длинный (максимум 72 байта)')
    return value


def validate_manual_car_status(value: CarStatus | None) -> CarStatus | None:
    if value in (CarStatus.reserved, CarStatus.sold):
        raise ValueError('Статусы reserved и sold устанавливаются только через сделку')
    return value


PhoneNumber = Annotated[str, AfterValidator(validate_phone)]
Password = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(validate_password)]
ManualCarStatus = Annotated[CarStatus, AfterValidator(validate_manual_car_status)]
Vin = Annotated[str, AfterValidator(validate_vin)]
Money = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Stars = Annotated[int, Field(ge=1, le=5)]
Year = Annotated[int, Field(ge=1900, le=2100)]
Mileage = Annotated[int, Field(ge=0)]


# ---------- Auth ----------


class RegisterSchema(BaseModel):
    first_name: str | None = Field(default=None, max_length=50)
    last_name: str | None = Field(default=None, max_length=50)
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    phone_number: PhoneNumber
    password: Password


class LoginSchema(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=128)


class RefreshTokenSchema(BaseModel):
    refresh_token: str


class TokenSchema(BaseModel):
    access_token: str
    refresh_token: str
    user_id: int
    type: str = 'bearer'


# ---------- UserProfile ----------


class UserProfileCreateSchema(BaseModel):
    first_name: str | None = Field(default=None, max_length=50)
    last_name: str | None = Field(default=None, max_length=50)
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    phone_number: PhoneNumber
    password: Password
    discount_limit: Percent = Decimal('0')


class UserProfileUpdateSchema(BaseModel):
    first_name: str | None = Field(default=None, max_length=50)
    last_name: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    phone_number: PhoneNumber | None = None
    profile_image: str | None = None


class UserProfileListSchema(BaseModel):
    id: int
    username: str
    first_name: str | None
    last_name: str | None
    role: UserRole
    is_active: bool


class UserProfileDetailSchema(BaseModel):
    id: int
    first_name: str | None
    last_name: str | None
    username: str
    email: EmailStr
    phone_number: str
    profile_image: str | None
    role: UserRole
    is_active: bool
    discount_limit: Decimal
    created_at: datetime


# ---------- Brand ----------


class BrandCreateSchema(BaseModel):
    brand_name: str = Field(min_length=1, max_length=50)
    brand_logo: str | None = None


class BrandUpdateSchema(BaseModel):
    brand_name: str | None = Field(default=None, min_length=1, max_length=50)
    brand_logo: str | None = None


class BrandListSchema(BaseModel):
    id: int
    brand_name: str
    brand_logo: str | None


class BrandDetailSchema(BaseModel):
    id: int
    brand_name: str
    brand_logo: str | None


# ---------- CarModel ----------


class CarModelCreateSchema(BaseModel):
    brand_id: int
    model_name: str = Field(min_length=1, max_length=50)


class CarModelUpdateSchema(BaseModel):
    brand_id: int | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=50)


class CarModelListSchema(BaseModel):
    id: int
    brand_id: int
    model_name: str


class CarModelDetailSchema(BaseModel):
    id: int
    brand_id: int
    model_name: str


# ---------- CarImage ----------


class CarImageCreateSchema(BaseModel):
    car_id: int
    car_image: str
    is_main: bool = False
    position: int = Field(default=0, ge=0)


class CarImageUpdateSchema(BaseModel):
    is_main: bool | None = None
    position: int | None = Field(default=None, ge=0)


class CarImageListSchema(BaseModel):
    id: int
    car_image: str
    is_main: bool
    position: int


class CarImageDetailSchema(BaseModel):
    id: int
    car_id: int
    car_image: str
    is_main: bool
    position: int


# ---------- Car ----------


class CarCreateSchema(BaseModel):
    vin: Vin
    brand_id: int
    car_model_id: int
    year: Year
    body_type: BodyType
    color: str = Field(max_length=30)
    engine_volume: Decimal | None = Field(default=None, gt=0, max_digits=3, decimal_places=1)
    fuel_type: FuelType
    transmission: Transmission
    drive_type: DriveType
    steering: Steering = Steering.left
    condition: CarCondition
    status: ManualCarStatus = CarStatus.available
    price: Money
    currency: Currency = Currency.KGS
    description: str | None = None
    mileage: Mileage = 0
    owners_count: int | None = Field(default=None, ge=0)
    has_accidents: bool | None = None
    accident_notes: str | None = None
    customs_cleared: bool = False
    registered_in_kr: bool = False


class CarUpdateSchema(BaseModel):
    year: Year | None = None
    body_type: BodyType | None = None
    color: str | None = Field(default=None, max_length=30)
    engine_volume: Decimal | None = Field(default=None, gt=0, max_digits=3, decimal_places=1)
    fuel_type: FuelType | None = None
    transmission: Transmission | None = None
    drive_type: DriveType | None = None
    steering: Steering | None = None
    status: ManualCarStatus | None = None
    price: Money | None = None
    currency: Currency | None = None
    description: str | None = None
    mileage: Mileage | None = None
    owners_count: int | None = Field(default=None, ge=0)
    has_accidents: bool | None = None
    accident_notes: str | None = None
    customs_cleared: bool | None = None
    registered_in_kr: bool | None = None


class CarListSchema(BaseModel):
    id: int
    brand_id: int
    car_model_id: int
    year: int
    body_type: BodyType
    fuel_type: FuelType
    transmission: Transmission
    condition: CarCondition
    status: CarStatus
    price: Decimal
    currency: Currency
    mileage: int


class CarDetailSchema(BaseModel):
    id: int
    vin: str
    brand_id: int
    car_model_id: int
    year: int
    body_type: BodyType
    color: str
    engine_volume: Decimal | None
    fuel_type: FuelType
    transmission: Transmission
    drive_type: DriveType
    steering: Steering
    condition: CarCondition
    status: CarStatus
    price: Decimal
    currency: Currency
    description: str | None
    mileage: int
    owners_count: int | None
    has_accidents: bool | None
    accident_notes: str | None
    customs_cleared: bool
    registered_in_kr: bool
    created_at: datetime
    updated_at: datetime
    images: List[CarImageListSchema] = []


# ---------- PriceHistory (создаётся сервером при изменении цены) ----------


class PriceHistoryListSchema(BaseModel):
    id: int
    old_price: Decimal
    new_price: Decimal
    changed_at: datetime


class PriceHistoryDetailSchema(BaseModel):
    id: int
    car_id: int
    old_price: Decimal
    new_price: Decimal
    changed_by_id: int
    changed_at: datetime


# ---------- Lead ----------


class LeadCreateSchema(BaseModel):
    car_id: int | None = None
    lead_type: LeadType
    comment: str | None = None


class LeadUpdateSchema(BaseModel):
    status: LeadStatus | None = None
    comment: str | None = None


class LeadListSchema(BaseModel):
    id: int
    client_id: int
    car_id: int | None
    lead_type: LeadType
    status: LeadStatus
    seller_id: int | None
    created_at: datetime


class LeadDetailSchema(BaseModel):
    id: int
    client_id: int
    car_id: int | None
    lead_type: LeadType
    status: LeadStatus
    seller_id: int | None
    comment: str | None
    created_at: datetime


# ---------- LeadNote ----------


class LeadNoteCreateSchema(BaseModel):
    lead_id: int
    note: str = Field(min_length=1)


class LeadNoteUpdateSchema(BaseModel):
    note: str | None = Field(default=None, min_length=1)


class LeadNoteListSchema(BaseModel):
    id: int
    seller_id: int
    note: str
    created_at: datetime


class LeadNoteDetailSchema(BaseModel):
    id: int
    lead_id: int
    seller_id: int
    note: str
    created_at: datetime


# ---------- TestDrive (end_time считает сервер по test_drive_minutes) ----------


class TestDriveCreateSchema(BaseModel):
    car_id: int
    start_time: datetime


class TestDriveUpdateSchema(BaseModel):
    start_time: datetime | None = None
    status: TestDriveStatus | None = None


class TestDriveListSchema(BaseModel):
    id: int
    car_id: int
    client_id: int
    seller_id: int | None
    start_time: datetime
    end_time: datetime
    status: TestDriveStatus


class TestDriveDetailSchema(BaseModel):
    id: int
    car_id: int
    client_id: int
    seller_id: int | None
    start_time: datetime
    end_time: datetime
    status: TestDriveStatus
    created_at: datetime


# ---------- Deal (seller_id, base_price, final_price, currency, status — сервер) ----------


class DealCreateSchema(BaseModel):
    car_id: int
    client_id: int
    discount_percent: Percent = Decimal('0')


class DealUpdateSchema(BaseModel):
    discount_percent: Percent | None = None
    cancel_reason: str | None = None


class DealListSchema(BaseModel):
    id: int
    car_id: int
    client_id: int
    seller_id: int
    final_price: Decimal
    currency: Currency
    status: DealStatus
    created_at: datetime


class DealDetailSchema(BaseModel):
    id: int
    car_id: int
    client_id: int
    seller_id: int
    base_price: Decimal
    discount_percent: Decimal
    final_price: Decimal
    currency: Currency
    status: DealStatus
    reserved_until: datetime | None
    paid_at: datetime | None
    delivered_at: datetime | None
    cancel_reason: str | None
    created_at: datetime


# ---------- DiscountRequest ----------


class DiscountRequestCreateSchema(BaseModel):
    deal_id: int
    requested_percent: Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]
    comment: str | None = None


class DiscountRequestUpdateSchema(BaseModel):
    status: DiscountStatus | None = None
    comment: str | None = None


class DiscountRequestListSchema(BaseModel):
    id: int
    deal_id: int
    seller_id: int
    requested_percent: Decimal
    status: DiscountStatus


class DiscountRequestDetailSchema(BaseModel):
    id: int
    deal_id: int
    seller_id: int
    requested_percent: Decimal
    status: DiscountStatus
    decided_by_id: int | None
    decided_at: datetime | None
    comment: str | None


# ---------- TradeIn ----------


class TradeInCreateSchema(BaseModel):
    brand_name: str = Field(max_length=50)
    model_name: str = Field(max_length=50)
    year: Year
    mileage: Mileage
    description: str | None = None
    currency: Currency = Currency.KGS


class TradeInUpdateSchema(BaseModel):
    estimated_price: Money | None = None
    currency: Currency | None = None
    status: TradeInStatus | None = None
    description: str | None = None


class TradeInListSchema(BaseModel):
    id: int
    client_id: int
    brand_name: str
    model_name: str
    year: int
    status: TradeInStatus
    created_at: datetime


class TradeInDetailSchema(BaseModel):
    id: int
    client_id: int
    brand_name: str
    model_name: str
    year: int
    mileage: int
    description: str | None
    estimated_price: Decimal | None
    currency: Currency
    status: TradeInStatus
    seller_id: int | None
    created_at: datetime


# ---------- TradeInImage ----------


class TradeInImageCreateSchema(BaseModel):
    trade_in_id: int
    trade_in_image: str


class TradeInImageUpdateSchema(BaseModel):
    trade_in_image: str | None = None


class TradeInImageListSchema(BaseModel):
    id: int
    trade_in_image: str


class TradeInImageDetailSchema(BaseModel):
    id: int
    trade_in_id: int
    trade_in_image: str


# ---------- Favorite ----------


class FavoriteCreateSchema(BaseModel):
    car_id: int


class FavoriteListSchema(BaseModel):
    id: int
    car_id: int


class FavoriteDetailSchema(BaseModel):
    id: int
    user_id: int
    car_id: int


# ---------- Review (client_id, seller_id — сервер) ----------


class ReviewCreateSchema(BaseModel):
    deal_id: int
    stars: Stars
    comment: str | None = None


class ReviewUpdateSchema(BaseModel):
    stars: Stars | None = None
    comment: str | None = None


class ReviewListSchema(BaseModel):
    id: int
    client_id: int
    seller_id: int
    stars: int
    comment: str | None
    created_at: datetime


class ReviewDetailSchema(BaseModel):
    id: int
    client_id: int
    deal_id: int
    seller_id: int
    stars: int
    comment: str | None
    created_at: datetime


# ---------- Notification (создаётся сервером) ----------


class NotificationUpdateSchema(BaseModel):
    is_read: bool | None = None


class NotificationListSchema(BaseModel):
    id: int
    notification_type: NotificationType
    text: str
    is_read: bool
    created_at: datetime


class NotificationDetailSchema(BaseModel):
    id: int
    user_id: int
    notification_type: NotificationType
    text: str
    is_read: bool
    created_at: datetime


# ---------- AuditLog (создаётся сервером, только чтение) ----------


class AuditLogListSchema(BaseModel):
    id: int
    user_id: int | None
    action: str
    entity_name: str
    entity_id: int | None
    created_at: datetime


class AuditLogDetailSchema(BaseModel):
    id: int
    user_id: int | None
    action: str
    entity_name: str
    entity_id: int | None
    old_value: dict | None
    new_value: dict | None
    created_at: datetime


# ---------- SalonSettings (одна запись) ----------


class SalonSettingsUpdateSchema(BaseModel):
    salon_name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=200)
    phone_number: PhoneNumber | None = None
    work_start: time | None = None
    work_end: time | None = None
    test_drive_minutes: int | None = Field(default=None, ge=15, le=240)
    reservation_hours: int | None = Field(default=None, ge=1, le=720)
    default_discount_limit: Percent | None = None


class SalonSettingsDetailSchema(BaseModel):
    id: int
    salon_name: str
    address: str
    phone_number: str
    work_start: time
    work_end: time
    test_drive_minutes: int
    reservation_hours: int
    default_discount_limit: Decimal
