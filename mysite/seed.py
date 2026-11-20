import sys
from datetime import time
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from mysite.api.auth import get_password_hash
from mysite.config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_PHONE, ADMIN_USERNAME
from mysite.db.database import SessionLocal
from mysite.db.models import SalonSettings, UserProfile, UserRole
from mysite.db.schema import UserProfileCreateSchema


def create_admin(db: Session, username: str, email: str, phone_number: str, password: str) -> UserProfile:
    user_db = db.query(UserProfile).filter((UserProfile.username == username) | (UserProfile.email == email)).first()
    if user_db:
        if user_db.role != UserRole.admin:
            print('Пользователь с таким username или email уже существует и не является администратором')
            sys.exit(1)
        print('Администратор уже существует')
        return user_db

    user_db = UserProfile(
        username=username,
        email=email,
        phone_number=phone_number,
        password=get_password_hash(password),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(user_db)
    db.flush()
    print('Администратор создан')
    return user_db


def create_salon_settings(db: Session) -> SalonSettings:
    settings_db = db.query(SalonSettings).filter(SalonSettings.id == 1).first()
    if settings_db:
        print('Настройки салона уже существуют')
        return settings_db

    settings_db = SalonSettings(
        id=1,
        salon_name='Auto Salon',
        address='г. Бишкек',
        phone_number=ADMIN_PHONE,
        work_start=time(9, 0),
        work_end=time(18, 0),
        reservation_hours=48,
        default_discount_limit=Decimal('3'),
        # условия рассрочки по умолчанию (у авто могут быть свои)
        default_min_down_payment_percent=Decimal('30'),
        default_max_term_months=36,
        default_installment_rate_percent=Decimal('0'),
        min_term_months=6,
    )
    db.add(settings_db)
    db.flush()
    print('Настройки салона созданы')
    return settings_db


def main():
    if not all([ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PHONE, ADMIN_PASSWORD]):
        print('Заполните ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PHONE, ADMIN_PASSWORD в .env')
        sys.exit(1)

    try:
        admin_data = UserProfileCreateSchema(
            username=ADMIN_USERNAME, email=ADMIN_EMAIL, phone_number=ADMIN_PHONE, password=ADMIN_PASSWORD
        )
    except ValidationError as error:
        for item in error.errors():
            print(f'Некорректное значение {item["loc"][0]}: {item["msg"]}')
        sys.exit(1)

    db = SessionLocal()
    try:
        create_admin(db, admin_data.username, admin_data.email, admin_data.phone_number, admin_data.password)
        create_salon_settings(db)
        db.commit()
    finally:
        db.close()


if __name__ == '__main__':
    main()
