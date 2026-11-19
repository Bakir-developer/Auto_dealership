from sqladmin import ModelView

from mysite.db.models import (
    AuditLog,
    Brand,
    Car,
    CarModel,
    Deal,
    DiscountRequest,
    Lead,
    PriceHistory,
    SalonSettings,
    UserProfile,
)


class UserProfileView(ModelView, model=UserProfile):
    column_list = [
        UserProfile.id,
        UserProfile.username,
        UserProfile.email,
        UserProfile.role,
        UserProfile.is_active,
        UserProfile.discount_limit,
        UserProfile.created_at,
    ]
    column_details_exclude_list = [UserProfile.password]
    form_columns = [
        UserProfile.first_name,
        UserProfile.last_name,
        UserProfile.email,
        UserProfile.phone_number,
        UserProfile.role,
    ]
    can_create = False
    can_delete = False


class SalonSettingsView(ModelView, model=SalonSettings):
    column_list = [
        SalonSettings.id,
        SalonSettings.salon_name,
        SalonSettings.address,
        SalonSettings.phone_number,
        SalonSettings.work_start,
        SalonSettings.work_end,
        SalonSettings.reservation_hours,
        SalonSettings.default_discount_limit,
    ]
    form_columns = [
        SalonSettings.salon_name,
        SalonSettings.address,
        SalonSettings.phone_number,
        SalonSettings.work_start,
        SalonSettings.work_end,
        SalonSettings.reservation_hours,
        SalonSettings.default_discount_limit,
    ]
    can_create = False
    can_delete = False


class BrandView(ModelView, model=Brand):
    column_list = [Brand.id, Brand.brand_name, Brand.brand_logo]
    # только чтение: правка в панели обходит проверку дублей (casefold) и strip из API
    can_create = False
    can_edit = False
    can_delete = False


class CarModelView(ModelView, model=CarModel):
    column_list = [CarModel.id, CarModel.brand_id, CarModel.model_name]
    # только чтение: смена марки в панели нарушила бы Car.brand_id == CarModel.brand_id
    can_create = False
    can_edit = False
    can_delete = False


class CarView(ModelView, model=Car):
    column_list = [
        Car.id,
        Car.vin,
        Car.brand_id,
        Car.car_model_id,
        Car.year,
        Car.condition,
        Car.status,
        Car.price,
        Car.currency,
        Car.deleted_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class PriceHistoryView(ModelView, model=PriceHistory):
    column_list = [
        PriceHistory.id,
        PriceHistory.car_id,
        PriceHistory.old_price,
        PriceHistory.new_price,
        PriceHistory.changed_by_id,
        PriceHistory.changed_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class LeadView(ModelView, model=Lead):
    column_list = [
        Lead.id,
        Lead.client_id,
        Lead.car_id,
        Lead.lead_type,
        Lead.status,
        Lead.seller_id,
        Lead.created_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class DealView(ModelView, model=Deal):
    column_list = [
        Deal.id,
        Deal.car_id,
        Deal.client_id,
        Deal.seller_id,
        Deal.final_price,
        Deal.currency,
        Deal.status,
        Deal.reserved_until,
        Deal.created_at,
        Deal.deleted_at,
    ]
    # только чтение: правка в панели обошла бы машину состояний, бронь и расчёт цены
    can_create = False
    can_edit = False
    can_delete = False


class DiscountRequestView(ModelView, model=DiscountRequest):
    column_list = [
        DiscountRequest.id,
        DiscountRequest.deal_id,
        DiscountRequest.seller_id,
        DiscountRequest.requested_percent,
        DiscountRequest.status,
        DiscountRequest.decided_by_id,
        DiscountRequest.decided_at,
    ]
    can_create = False
    can_edit = False
    can_delete = False


class AuditLogView(ModelView, model=AuditLog):
    column_list = [
        AuditLog.id,
        AuditLog.user_id,
        AuditLog.action,
        AuditLog.entity_name,
        AuditLog.entity_id,
        AuditLog.created_at,
    ]
    column_default_sort = (AuditLog.id, True)
    can_create = False
    can_edit = False
    can_delete = False
