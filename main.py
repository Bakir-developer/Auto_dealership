import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mysite.admin.setup import setup_admin
from mysite.api import auth, brand, car, car_image, car_model, user
from mysite.config import MEDIA_DIR

os.makedirs(os.path.join(MEDIA_DIR, 'car_images'), exist_ok=True)

auto_app = FastAPI(title='FastAPI Auto Salon')
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

# для локального запуска без nginx; в docker /media/ отдаёт nginx
auto_app.mount('/media', StaticFiles(directory=MEDIA_DIR), name='media')

setup_admin(auto_app)


@auto_app.get('/health', response_model=dict)
async def health():
    return {'status': 'ok'}
