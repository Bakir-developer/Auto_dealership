from fastapi import FastAPI
from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from mysite.api.auth import pwd_context, verify_password
from mysite.config import SECRET_KEY
from mysite.db.database import SessionLocal, engine
from mysite.db.models import UserProfile, UserRole

from .view import (
    AuditLogView,
    BrandView,
    CarModelView,
    CarView,
    DealView,
    DiscountRequestView,
    LeadView,
    PriceHistoryView,
    ReviewView,
    SalonSettingsView,
    TradeInView,
    UserProfileView,
)


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get('username', ''))
        password = str(form.get('password', ''))

        db = SessionLocal()
        try:
            user_db = db.query(UserProfile).filter(UserProfile.username == username).first()
            if not user_db:
                pwd_context.dummy_verify()
                return False
            if (
                not verify_password(password, user_db.password)
                or user_db.role != UserRole.admin
                or not user_db.is_active
            ):
                return False
            request.session.update({'user_id': user_db.id})
            return True
        finally:
            db.close()

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        user_id = request.session.get('user_id')
        if not user_id:
            return False

        db = SessionLocal()
        try:
            user_db = db.query(UserProfile).filter(UserProfile.id == user_id).first()
            return bool(user_db and user_db.role == UserRole.admin and user_db.is_active)
        finally:
            db.close()


def setup_admin(app: FastAPI):
    admin = Admin(app, engine=engine, authentication_backend=AdminAuth(secret_key=SECRET_KEY))
    admin.add_view(UserProfileView)
    admin.add_view(SalonSettingsView)
    admin.add_view(BrandView)
    admin.add_view(CarModelView)
    admin.add_view(CarView)
    admin.add_view(PriceHistoryView)
    admin.add_view(LeadView)
    admin.add_view(DealView)
    admin.add_view(DiscountRequestView)
    admin.add_view(TradeInView)
    admin.add_view(ReviewView)
    admin.add_view(AuditLogView)
