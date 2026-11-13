---
name: my-style
description: Применяй при написании ЛЮБОГО Python-кода в этом проекте (модели, схемы, роутеры, main.py, config, admin) — краткая выжимка стиля автора с примерами. Полная версия — docs/STYLE_GUIDE.md.
---

# Стиль автора — выжимка

Полный эталон: `docs/STYLE_GUIDE.md`. При сомнениях — он главнее.

## Нельзя
services/ repositories/ utils/ слои · разбивать models.py/schema.py · async SQLAlchemy ·
`.dict()` · копировать `get_db` в роутеры · ошибки на английском · `Float` для денег.

## Модель (mysite/db/models.py — всё в одном файле)
```python
class CarStatus(str, PyEnum):
    available = 'available'
    sold = 'sold'


class Car(Base):
    __tablename__ = 'car'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vin: Mapped[str] = mapped_column(String(17), unique=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey('brand.id'))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[CarStatus] = mapped_column(Enum(CarStatus), default=CarStatus.available)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    brand: Mapped['Brand'] = relationship('Brand', back_populates='cars')
    images: Mapped[List['CarImage']] = relationship('CarImage', back_populates='car', cascade='all, delete-orphan')
```

## Схемы (mysite/db/schema.py — всё в одном файле)
```python
class CarCreateSchema(BaseModel):
    vin: str
    brand_id: int
    price: Decimal


class CarUpdateSchema(BaseModel):
    price: Decimal | None = None
    description: str | None = None


class CarListSchema(BaseModel):
    id: int
    price: Decimal
    status: CarStatus


class CarDetailSchema(BaseModel):
    id: int
    vin: str
    price: Decimal
    status: CarStatus
    created_at: datetime
```

## Роутер (mysite/api/car.py)
```python
car_router = APIRouter(prefix='/car', tags=['Car'])


@car_router.post('/create', response_model=CarDetailSchema)
async def create_car(car_data: CarCreateSchema, db: Session = Depends(get_db)):
    car_db = Car(**car_data.model_dump())
    db.add(car_db)
    db.commit()
    db.refresh(car_db)
    return car_db


@car_router.get('/detail', response_model=CarDetailSchema)
async def detail_car(car_id: int, db: Session = Depends(get_db)):
    car_db = db.query(Car).filter(Car.id == car_id, Car.deleted_at.is_(None)).first()
    if not car_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Автомобиль не найден')
    return car_db
```
update: `for key, value in car_data.model_dump(exclude_unset=True).items(): setattr(car_db, key, value)`.

## main.py
```python
auto_app = FastAPI(title='FastAPI Auto Salon')
auto_app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000'], allow_credentials=True,
                        allow_methods=['*'], allow_headers=['*'])

auto_app.include_router(auth.auth_router)
auto_app.include_router(car.car_router)

setup_admin(auto_app)
```

## config.py / database.py
```python
load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY')
ACCESS_EXPIRE_TOKEN = int(os.getenv('ACCESS_EXPIRE_TOKEN', 30))
```
```python
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## Мелочи
одинарные кавычки · black line-length 120 · isort profile black · `datetime.now(timezone.utc)` ·
`<entity>_db` / `<entity>_data` · `response_model` всегда · 404/403/409/400 с текстом на русском.
