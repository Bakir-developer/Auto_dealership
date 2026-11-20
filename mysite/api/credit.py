from decimal import ROUND_HALF_UP, Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from mysite.api.car import build_car_detail, get_car_or_404, get_installment_defaults, get_installment_terms
from mysite.api.deal import CENT, create_audit_log
from mysite.api.dependencies import get_optional_user, require_role
from mysite.db.database import get_db
from mysite.db.models import Car, SalonSettings, UserProfile, UserRole
from mysite.db.schema import (
    CreditCalculateSchema,
    CreditCompareItemSchema,
    CreditCompareSchema,
    CreditResultSchema,
    InstallmentSettingsDetailSchema,
    InstallmentSettingsUpdateSchema,
    InstallmentTermsSchema,
)

credit_router = APIRouter(prefix='/credit', tags=['Credit'])

HUNDRED = Decimal('100')
DOWN_PAYMENT_ERROR = 'Первоначальный взнос должен быть меньше цены'


def format_number(value: Decimal) -> str:
    """Число для текста ошибки: 30.00 -> '30', 12.50 -> '12.5'."""
    text = f'{value:f}'
    return text.rstrip('0').rstrip('.') if '.' in text else text


def calc_monthly_payment(loan: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    """Аннуитетный платёж; всё в Decimal, округление до копеек half-up."""
    if loan == 0:
        return Decimal('0.00')
    if annual_rate == 0:
        return (loan / term_months).quantize(CENT, rounding=ROUND_HALF_UP)
    monthly_rate = annual_rate / Decimal('1200')
    factor = (1 + monthly_rate) ** term_months
    return (loan * monthly_rate * factor / (factor - 1)).quantize(CENT, rounding=ROUND_HALF_UP)


def build_credit_result(
    car_db: Car,
    terms: InstallmentTermsSchema,
    term_months: int,
    down_payment: Decimal | None = None,
    down_payment_percent: Decimal | None = None,
) -> CreditResultSchema:
    """Расчёт рассрочки строго по условиям авто (terms — итоговые условия с учётом значений по умолчанию)."""
    if down_payment is not None and down_payment_percent is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Укажите первый взнос либо суммой, либо в процентах'
        )
    if not terms.installment_available or terms.max_term_months < terms.min_term_months:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Для этого авто рассрочка недоступна')
    if not terms.min_term_months <= term_months <= terms.max_term_months:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f'Срок рассрочки для этого авто — от {terms.min_term_months} до {terms.max_term_months} мес.',
        )

    price = car_db.price.quantize(CENT, rounding=ROUND_HALF_UP)
    min_percent = terms.min_down_payment_percent
    min_down_payment_error = f'Минимальный первый взнос для этого авто — {format_number(min_percent)}%'
    if down_payment is None:
        if down_payment_percent is None:
            down_payment_percent = min_percent
        if down_payment_percent < min_percent:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=min_down_payment_error)
        down_payment = (price * down_payment_percent / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        down_payment = down_payment.quantize(CENT, rounding=ROUND_HALF_UP)
        if down_payment * HUNDRED < price * min_percent:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=min_down_payment_error)
        down_payment_percent = down_payment * HUNDRED / price

    if down_payment >= price:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=DOWN_PAYMENT_ERROR)

    annual_rate = terms.installment_rate_percent
    loan_amount = price - down_payment
    monthly_payment = calc_monthly_payment(loan_amount, annual_rate, term_months)
    # total_payment — только выплаты по рассрочке, без первого взноса;
    # последний платёж добирает копейки, поэтому итог не меньше суммы рассрочки (переплата >= 0)
    total_payment = max((monthly_payment * term_months).quantize(CENT), loan_amount)
    return CreditResultSchema(
        car_id=car_db.id,
        price=price,
        currency=car_db.currency,
        down_payment=down_payment,
        down_payment_percent=down_payment_percent.quantize(CENT, rounding=ROUND_HALF_UP),
        loan_amount=loan_amount,
        annual_rate=annual_rate,
        term_months=term_months,
        monthly_payment=monthly_payment,
        total_payment=total_payment,
        overpayment=total_payment - loan_amount,
        terms=terms,
    )


@credit_router.post('/calculate', response_model=CreditResultSchema)
async def calculate_credit(
    credit_data: CreditCalculateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile | None = Depends(get_optional_user),
):
    car_db = get_car_or_404(credit_data.car_id, db, current_user, only_visible=True)
    terms = get_installment_terms(car_db, get_installment_defaults(db))
    return build_credit_result(
        car_db, terms, credit_data.term_months, credit_data.down_payment, credit_data.down_payment_percent
    )


@credit_router.post('/compare', response_model=List[CreditCompareItemSchema])
async def compare_credit(
    credit_data: CreditCompareSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile | None = Depends(get_optional_user),
):
    if len(set(credit_data.car_ids)) != len(credit_data.car_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Автомобили в сравнении не должны повторяться'
        )
    if credit_data.down_payment_percent is not None and credit_data.term_months is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Укажите срок рассрочки')

    defaults = get_installment_defaults(db)
    items = []
    for car_id in credit_data.car_ids:
        car_db = get_car_or_404(car_id, db, current_user, only_visible=True)
        terms = get_installment_terms(car_db, defaults)
        credit_result, credit_error = None, None
        if credit_data.term_months is not None:
            # условия у авто разные — ошибка по одному авто не ломает всё сравнение
            try:
                credit_result = build_credit_result(
                    car_db, terms, credit_data.term_months, down_payment_percent=credit_data.down_payment_percent
                )
            except HTTPException as error:
                credit_error = error.detail
        items.append(
            CreditCompareItemSchema(
                car=build_car_detail(car_db, db, defaults), credit=credit_result, credit_error=credit_error
            )
        )
    return items


@credit_router.get('/settings', response_model=InstallmentSettingsDetailSchema)
async def settings_credit(db: Session = Depends(get_db)):
    return get_installment_defaults(db)


@credit_router.put('/settings/update', response_model=InstallmentSettingsDetailSchema)
async def update_settings_credit(
    settings_data: InstallmentSettingsUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin)),
):
    settings_db = db.query(SalonSettings).filter(SalonSettings.id == 1).first()
    if not settings_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Настройки салона не найдены')

    update_data = settings_data.model_dump(exclude_unset=True)
    if any(value is None for value in update_data.values()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    min_term_months = update_data.get('min_term_months', settings_db.min_term_months)
    max_term_months = update_data.get('default_max_term_months', settings_db.default_max_term_months)
    if max_term_months < min_term_months:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail='Максимальный срок по умолчанию не может быть меньше минимального срока рассрочки',
        )

    old_value = {
        key: getattr(settings_db, key) for key, value in update_data.items() if getattr(settings_db, key) != value
    }
    if old_value:
        new_value = {key: update_data[key] for key in old_value}
        for key, value in new_value.items():
            setattr(settings_db, key, value)
        create_audit_log(
            db, current_user.id, 'installment_settings_update', 'salon_settings', settings_db.id, old_value, new_value
        )
        db.commit()
    return get_installment_defaults(db)
