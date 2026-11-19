from sqladmin import ModelView

from mysite.db.models import Brand, Car, CarModel, Lead, PriceHistory, SalonSettings, TestDrive, UserProfile


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
        UserProfile.is_active,
        UserProfile.discount_limit,
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
        SalonSettings.test_drive_minutes,
        SalonSettings.reservation_hours,
        SalonSettings.default_discount_limit,
    ]
    form_columns = [
        SalonSettings.salon_name,
        SalonSettings.address,
        SalonSettings.phone_number,
        SalonSettings.work_start,
        SalonSettings.work_end,
        SalonSettings.test_drive_minutes,
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


class TestDriveView(ModelView, model=TestDrive):
    column_list = [
        TestDrive.id,
        TestDrive.car_id,
        TestDrive.client_id,
        TestDrive.seller_id,
        TestDrive.start_time,
        TestDrive.end_time,
        TestDrive.status,
    ]
    can_create = False
    can_edit = False
    can_delete = False
