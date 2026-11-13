from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from mysite.api.car import PUBLIC_CAR_STATUSES, get_car_or_404, is_staff
from mysite.api.dependencies import get_optional_user, require_role
from mysite.config import MEDIA_DIR
from mysite.db.database import get_db
from mysite.db.models import Car, CarImage, UserProfile, UserRole
from mysite.db.schema import CarImageDetailSchema, CarImageListSchema, CarImageUpdateSchema

car_image_router = APIRouter(prefix='/car-image', tags=['CarImage'])

MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_IMAGES_PER_CAR = 20
ALLOWED_IMAGE_TYPES = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}
IMAGE_TYPE_ERROR = 'Допустимы только изображения JPEG, PNG или WEBP'


def detect_image_extension(data: bytes) -> str | None:
    """Расширение по сигнатуре первых байт — content_type присылает клиент, ему не верим."""
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    return None


def get_images_dir() -> Path:
    # MEDIA_DIR читается во время вызова, чтобы тесты могли его подменить
    return Path(MEDIA_DIR) / 'car_images'


def sort_images(images: List[CarImage]) -> List[CarImage]:
    return sorted(images, key=lambda image: (not image.is_main, image.position, image.id))


def get_car_image_or_404(
    car_image_id: int, db: Session, current_user: UserProfile | None = None, only_visible: bool = False
) -> CarImage:
    query = (
        db.query(CarImage)
        .join(Car, Car.id == CarImage.car_id)
        .filter(CarImage.id == car_image_id, Car.deleted_at.is_(None))
    )
    if only_visible and not is_staff(current_user):
        query = query.filter(Car.status.in_(PUBLIC_CAR_STATUSES))
    car_image_db = query.first()
    if not car_image_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Фотография не найдена')
    return car_image_db


def reset_main_images(db: Session, car_id: int, except_id: int | None = None):
    for image in db.query(CarImage).filter(CarImage.car_id == car_id, CarImage.is_main.is_(True)).all():
        if image.id != except_id:
            image.is_main = False


@car_image_router.post('/create', response_model=CarImageDetailSchema)
async def create_car_image(
    car_id: int = Form(),
    is_main: bool = Form(False),
    position: int = Form(0, ge=0, le=1000),
    car_image: UploadFile = File(),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    get_car_or_404(car_id, db)

    data = await car_image.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail='Файл слишком большой (максимум 5 МБ)'
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой файл')

    extension = detect_image_extension(data)
    if ALLOWED_IMAGE_TYPES.get(car_image.content_type) != extension or extension is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=IMAGE_TYPE_ERROR)

    images_count = db.query(CarImage).filter(CarImage.car_id == car_id).count()
    if images_count >= MAX_IMAGES_PER_CAR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Достигнут лимит фотографий для автомобиля ({MAX_IMAGES_PER_CAR})',
        )

    # имя файла только серверное — UploadFile.filename не используется
    filename = f'{uuid4().hex}{extension}'
    file_path = get_images_dir() / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(file_path, 'wb') as file:
            file.write(data)
        if is_main:
            reset_main_images(db, car_id)
        car_image_db = CarImage(
            car_id=car_id,
            car_image=f'/media/car_images/{filename}',
            is_main=is_main or images_count == 0,
            position=position,
        )
        db.add(car_image_db)
        db.commit()
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise
    db.refresh(car_image_db)
    return car_image_db


@car_image_router.get('/list', response_model=List[CarImageListSchema])
async def list_car_image(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile | None = Depends(get_optional_user),
):
    get_car_or_404(car_id, db, current_user, only_visible=True)
    images = db.query(CarImage).filter(CarImage.car_id == car_id).all()
    return sort_images(images)


@car_image_router.get('/detail', response_model=CarImageDetailSchema)
async def detail_car_image(
    car_image_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile | None = Depends(get_optional_user),
):
    return get_car_image_or_404(car_image_id, db, current_user, only_visible=True)


@car_image_router.put('/update/{car_image_id}', response_model=CarImageDetailSchema)
async def update_car_image(
    car_image_id: int,
    car_image_data: CarImageUpdateSchema,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    car_image_db = get_car_image_or_404(car_image_id, db)

    update_data = car_image_data.model_dump(exclude_unset=True)
    for field in ('is_main', 'position'):
        if field in update_data and update_data[field] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Поле не может быть пустым')

    if update_data.get('is_main'):
        reset_main_images(db, car_image_db.car_id, except_id=car_image_db.id)

    for key, value in update_data.items():
        setattr(car_image_db, key, value)

    db.commit()
    db.refresh(car_image_db)
    return car_image_db


@car_image_router.delete('/delete/{car_image_id}', response_model=dict)
async def delete_car_image(
    car_image_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_role(UserRole.admin, UserRole.seller)),
):
    car_image_db = get_car_image_or_404(car_image_id, db)
    # путь на диске — только имя файла из БД, без директорий
    file_path = get_images_dir() / Path(car_image_db.car_image).name
    car_id = car_image_db.car_id
    was_main = car_image_db.is_main

    db.delete(car_image_db)
    db.flush()
    if was_main:
        remaining = db.query(CarImage).filter(CarImage.car_id == car_id).all()
        if remaining:
            next_main = min(remaining, key=lambda image: (image.position, image.id))
            next_main.is_main = True
    db.commit()

    file_path.unlink(missing_ok=True)
    return {'message': 'Фотография удалена'}
