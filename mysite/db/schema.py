import re
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Annotated, List

from pydantic import AfterValidator, AwareDatetime, BaseModel, EmailStr, Field, StringConstraints

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


def to_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def mark_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


PhoneNumber = Annotated[str, AfterValidator(validate_phone)]
Password = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(validate_password)]
ManualCarStatus = Annotated[CarStatus, AfterValidator(validate_manual_car_status)]
Vin = Annotated[str, AfterValidator(validate_vin)]
Money = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
DownPayment = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
CreditTerm = Annotated[int, Field(ge=1, le=120)]
TermMonths = Annotated[int, Field(ge=1, le=120)]
DiscountPercent = Annotated[Decimal, Field(gt=0, lt=100, max_digits=5, decimal_places=2)]
Stars = Annotated[int, Field(ge=1, le=5)]
Year = Annotated[int, Field(ge=1900, le=2100)]
Mileage = Annotated[int, Field(ge=0)]
Name50 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Color = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Text2000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Text5000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(to_utc)]
UtcDatetimeOut = Annotated[datetime, AfterValidator(mark_utc)]


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


class UserProfileDiscountLimitSchema(BaseModel):
    discount_limit: Percent


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
    brand_name: Name50
    brand_logo: str | None = Field(default=None, max_length=500)


class BrandUpdateSchema(BaseModel):
    brand_name: Name50 | None = None
    brand_logo: str | None = Field(default=None, max_length=500)


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
    model_name: Name50


class CarModelUpdateSchema(BaseModel):
    brand_id: int | None = None
    model_name: Name50 | None = None


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
    position: int = Field(default=0, ge=0, le=1000)


class CarImageUpdateSchema(BaseModel):
    is_main: bool | None = None
    position: int | None = Field(default=None, ge=0, le=1000)


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
    color: Color
    engine_volume: Decimal | None = Field(default=None, gt=0, max_digits=3, decimal_places=1)
    fuel_type: FuelType
    transmission: Transmission
    drive_type: DriveType
    steering: Steering = Steering.left
    condition: CarCondition
    status: ManualCarStatus = CarStatus.available
    price: Money
    currency: Currency = Currency.KGS
    description: str | None = Field(default=None, max_length=5000)
    mileage: Mileage = 0
    owners_count: int | None = Field(default=None, ge=0)
    has_accidents: bool | None = None
    accident_notes: str | None = Field(default=None, max_length=5000)
    customs_cleared: bool = False
    registered_in_kr: bool = False


class CarUpdateSchema(BaseModel):
    year: Year | None = None
    body_type: BodyType | None = None
    color: Color | None = None
    engine_volume: Decimal | None = Field(default=None, gt=0, max_digits=3, decimal_places=1)
    fuel_type: FuelType | None = None
    transmission: Transmission | None = None
    drive_type: DriveType | None = None
    steering: Steering | None = None
    status: ManualCarStatus | None = None
    price: Money | None = None
    currency: Currency | None = None
    description: str | None = Field(default=None, max_length=5000)
    mileage: Mileage | None = None
    owners_count: int | None = Field(default=None, ge=0)
    has_accidents: bool | None = None
    accident_notes: str | None = Field(default=None, max_length=5000)
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


class InstallmentTermsSchema(BaseModel):
    installment_available: bool
    min_down_payment_percent: Decimal
    min_term_months: int
    max_term_months: int
    installment_rate_percent: Decimal


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
    # собственные условия рассрочки авто (null — значение по умолчанию салона)
    installment_available: bool
    min_down_payment_percent: Decimal | None
    max_term_months: int | None
    installment_rate_percent: Decimal | None
    # итоговые условия с учётом значений по умолчанию — заполняет сервер
    installment: InstallmentTermsSchema | None = None
    created_at: datetime
    updated_at: datetime
    images: List[CarImageListSchema] = []


# ---------- Рассрочка (условия задаются для каждого авто) ----------


class CarInstallmentUpdateSchema(BaseModel):
    # null в поле условия — сбросить к значению по умолчанию салона
    installment_available: bool | None = None
    min_down_payment_percent: Percent | None = None
    max_term_months: TermMonths | None = None
    installment_rate_percent: Percent | None = None


class InstallmentSettingsUpdateSchema(BaseModel):
    default_min_down_payment_percent: Percent | None = None
    default_max_term_months: TermMonths | None = None
    default_installment_rate_percent: Percent | None = None
    min_term_months: TermMonths | None = None


class InstallmentSettingsDetailSchema(BaseModel):
    default_min_down_payment_percent: Decimal
    default_max_term_months: int
    default_installment_rate_percent: Decimal
    min_term_months: int


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
    comment: Text2000 | None = None


class LeadUpdateSchema(BaseModel):
    status: LeadStatus | None = None
    comment: Text2000 | None = None


class LeadAssignSchema(BaseModel):
    seller_id: int


class LeadListSchema(BaseModel):
    id: int
    client_id: int
    car_id: int | None
    lead_type: LeadType
    status: LeadStatus
    seller_id: int | None
    created_at: UtcDatetimeOut


class LeadDetailSchema(BaseModel):
    id: int
    client_id: int
    car_id: int | None
    lead_type: LeadType
    status: LeadStatus
    seller_id: int | None
    comment: str | None
    created_at: UtcDatetimeOut


# ---------- LeadNote ----------


class LeadNoteCreateSchema(BaseModel):
    lead_id: int
    note: Text5000


class LeadNoteUpdateSchema(BaseModel):
    note: Text5000 | None = None


class LeadNoteListSchema(BaseModel):
    id: int
    seller_id: int
    note: str
    created_at: UtcDatetimeOut


class LeadNoteDetailSchema(BaseModel):
    id: int
    lead_id: int
    seller_id: int
    note: str
    created_at: UtcDatetimeOut


# ---------- Deal (base_price, final_price, discount_percent, currency, status — сервер) ----------


class DealCreateSchema(BaseModel):
    car_id: int
    client_id: int
    seller_id: int | None = None  # учитывается только у admin; у seller берётся из токена


class DealCancelSchema(BaseModel):
    cancel_reason: Text2000


class DealListSchema(BaseModel):
    id: int
    car_id: int
    client_id: int
    seller_id: int
    discount_percent: Decimal
    final_price: Decimal
    currency: Currency
    status: DealStatus
    created_at: UtcDatetimeOut


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
    reserved_until: UtcDatetimeOut | None
    paid_at: UtcDatetimeOut | None
    delivered_at: UtcDatetimeOut | None
    cancel_reason: str | None
    created_at: UtcDatetimeOut


# ---------- DiscountRequest (seller_id, status, decided_* — сервер) ----------


class DiscountRequestCreateSchema(BaseModel):
    deal_id: int
    requested_percent: DiscountPercent
    comment: Text2000 | None = None


class DiscountRequestDecisionSchema(BaseModel):
    comment: Text2000 | None = None


class DiscountRequestListSchema(BaseModel):
    id: int
    deal_id: int
    seller_id: int
    requested_percent: Decimal
    status: DiscountStatus
    decided_by_id: int | None


class DiscountRequestDetailSchema(BaseModel):
    id: int
    deal_id: int
    seller_id: int
    requested_percent: Decimal
    status: DiscountStatus
    decided_by_id: int | None
    decided_at: UtcDatetimeOut | None
    comment: str | None


# ---------- TradeIn (client_id, seller_id, status, estimated_price — сервер) ----------


class TradeInCreateSchema(BaseModel):
    brand_name: Name50
    model_name: Name50
    year: Year
    mileage: Mileage
    description: Text5000 | None = None


class TradeInUpdateSchema(BaseModel):
    brand_name: Name50 | None = None
    model_name: Name50 | None = None
    year: Year | None = None
    mileage: Mileage | None = None
    description: Text5000 | None = None


class TradeInOfferSchema(BaseModel):
    estimated_price: Money
    currency: Currency = Currency.KGS


class TradeInAssignSchema(BaseModel):
    seller_id: int


class TradeInImageListSchema(BaseModel):
    id: int
    trade_in_image: str


class TradeInImageDetailSchema(BaseModel):
    id: int
    trade_in_id: int
    trade_in_image: str


class TradeInListSchema(BaseModel):
    id: int
    client_id: int
    brand_name: str
    model_name: str
    year: int
    estimated_price: Decimal | None
    currency: Currency
    status: TradeInStatus
    seller_id: int | None
    created_at: UtcDatetimeOut


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
    created_at: UtcDatetimeOut
    images: List[TradeInImageListSchema] = []


# ---------- Favorite (user_id — сервер) ----------


class FavoriteCreateSchema(BaseModel):
    car_id: int


class FavoriteListSchema(BaseModel):
    id: int
    car_id: int
    car: CarListSchema


class FavoriteDetailSchema(BaseModel):
    id: int
    user_id: int
    car_id: int
    car: CarListSchema


# ---------- Review (client_id, seller_id — сервер) ----------


class ReviewCreateSchema(BaseModel):
    deal_id: int
    stars: Stars
    comment: Text2000 | None = None


class ReviewUpdateSchema(BaseModel):
    stars: Stars | None = None
    comment: Text2000 | None = None


class ReviewListSchema(BaseModel):
    id: int
    client_id: int
    deal_id: int
    seller_id: int
    stars: int
    comment: str | None
    created_at: UtcDatetimeOut


class ReviewDetailSchema(BaseModel):
    id: int
    client_id: int
    deal_id: int
    seller_id: int
    stars: int
    comment: str | None
    created_at: UtcDatetimeOut


# ---------- Credit (все результаты считает сервер) ----------


class CreditCalculateSchema(BaseModel):
    car_id: int
    # первый взнос — суммой или в процентах (не оба); не указан — минимальный для авто
    down_payment: DownPayment | None = None
    down_payment_percent: Percent | None = None
    term_months: CreditTerm


class CreditResultSchema(BaseModel):
    car_id: int
    price: Decimal
    currency: Currency
    down_payment: Decimal
    down_payment_percent: Decimal
    loan_amount: Decimal
    annual_rate: Decimal
    term_months: int
    monthly_payment: Decimal
    total_payment: Decimal
    overpayment: Decimal
    terms: InstallmentTermsSchema


class CreditCompareSchema(BaseModel):
    car_ids: List[int] = Field(min_length=2, max_length=4)
    # срок указан — для каждого авто считается рассрочка по его условиям
    term_months: CreditTerm | None = None
    down_payment_percent: Percent | None = None


class CreditCompareItemSchema(BaseModel):
    car: CarDetailSchema
    credit: CreditResultSchema | None
    credit_error: str | None = None


# ---------- Statistic (только чтение) ----------


class StatisticSellerRowSchema(BaseModel):
    seller_id: int
    username: str
    is_active: bool
    deals_count: int
    delivered_count: int
    revenue: dict[Currency, Decimal]
    avg_stars: Decimal | None


class StatisticSellerSchema(BaseModel):
    seller_id: int
    username: str
    leads_by_status: dict[LeadStatus, int]
    deals_by_status: dict[DealStatus, int]
    discounts_by_status: dict[DiscountStatus, int]
    trade_ins_by_status: dict[TradeInStatus, int]
    revenue: dict[Currency, Decimal]
    delivered_count: int
    reviews_count: int
    avg_stars: Decimal | None
    date_from: date | None
    date_to: date | None


class StatisticGeneralSchema(BaseModel):
    cars_by_status: dict[CarStatus, int]
    leads_by_status: dict[LeadStatus, int]
    deals_by_status: dict[DealStatus, int]
    trade_ins_by_status: dict[TradeInStatus, int]
    discounts_pending: int
    revenue: dict[Currency, Decimal]
    delivered_count: int
    avg_discount_percent: Decimal | None
    clients_count: int
    reviews_count: int
    avg_stars: Decimal | None
    sellers: List[StatisticSellerRowSchema]
    date_from: date | None
    date_to: date | None


# ---------- Notification (создаётся сервером) ----------


class NotificationUpdateSchema(BaseModel):
    is_read: bool | None = None


class NotificationListSchema(BaseModel):
    id: int
    notification_type: NotificationType
    text: str
    is_read: bool
    created_at: UtcDatetimeOut


class NotificationDetailSchema(BaseModel):
    id: int
    user_id: int
    notification_type: NotificationType
    text: str
    is_read: bool
    created_at: UtcDatetimeOut


# ---------- AuditLog (создаётся сервером, только чтение) ----------


class AuditLogListSchema(BaseModel):
    id: int
    user_id: int | None
    action: str
    entity_name: str
    entity_id: int | None
    created_at: UtcDatetimeOut


class AuditLogDetailSchema(BaseModel):
    id: int
    user_id: int | None
    action: str
    entity_name: str
    entity_id: int | None
    old_value: dict | None
    new_value: dict | None
    created_at: UtcDatetimeOut


# ---------- SalonSettings (одна запись) ----------


class SalonSettingsUpdateSchema(BaseModel):
    salon_name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=200)
    phone_number: PhoneNumber | None = None
    work_start: time | None = None
    work_end: time | None = None
    reservation_hours: int | None = Field(default=None, ge=1, le=720)
    default_discount_limit: Percent | None = None


class SalonSettingsDetailSchema(BaseModel):
    id: int
    salon_name: str
    address: str
    phone_number: str
    work_start: time
    work_end: time
    reservation_hours: int
    default_discount_limit: Decimal
