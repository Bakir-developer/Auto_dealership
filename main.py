import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mysite.admin.setup import setup_admin
from mysite.api import auth, brand, car, car_image, car_model, deal, discount, lead, notification, user
from mysite.api.deal import expire_reservations
from mysite.config import MEDIA_DIR, RESERVATION_CHECK_SECONDS, RESERVATION_SCHEDULER_ENABLED
from mysite.db.database import SessionLocal

logger = logging.getLogger(__name__)

os.makedirs(os.path.join(MEDIA_DIR, 'car_images'), exist_ok=True)


async def reservation_scheduler():
    while True:
        db = SessionLocal()
        try:
            expire_reservations(db)
        except Exception:
            logger.exception('Ошибка фоновой задачи истечения брони')
        finally:
            db.close()
        await asyncio.sleep(RESERVATION_CHECK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(reservation_scheduler()) if RESERVATION_SCHEDULER_ENABLED else None
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


auto_app = FastAPI(title='FastAPI Auto Salon', lifespan=lifespan)
auto_app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

auto_app.include_router(auth.auth_router)
auto_app.include_router(user.user_router)
auto_app.include_router(brand.brand_router)
auto_app.include_router(car_model.car_model_router)
auto_app.include_router(car.car_router)
auto_app.include_router(car_image.car_image_router)
auto_app.include_router(lead.lead_router)
auto_app.include_router(lead.lead_note_router)
auto_app.include_router(deal.deal_router)
auto_app.include_router(discount.discount_router)
auto_app.include_router(notification.notification_router)

# для локального запуска без nginx; в docker /media/ отдаёт nginx
auto_app.mount('/media', StaticFiles(directory=MEDIA_DIR), name='media')

setup_admin(auto_app)


@auto_app.get('/health', response_model=dict)
async def health():
    return {'status': 'ok'}
