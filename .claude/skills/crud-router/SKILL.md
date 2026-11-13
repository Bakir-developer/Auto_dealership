---
name: crud-router
description: Применяй, когда нужно создать CRUD-роутер mysite/api/<entity>.py (create/list/detail/update/delete) в стиле автора и подключить его в main.py. Используется командой /crud.
---

# CRUD-роутер в стиле автора

## 0. Проверки перед началом
1. Сущность входит в **текущий этап** `docs/ROADMAP.md`? Нет → стоп, сообщи автору.
2. Модель есть в `mysite/db/models.py`? Нет → это задача db-specialist (модель + миграция).
3. Какие роли и права по `docs/PROJECT_SPEC.md` раздел 3?

## 1. Схемы — в `mysite/db/schema.py` (дописать, не новый файл)
`<Entity>CreateSchema`, `<Entity>UpdateSchema` (все поля `X | None = None`),
`<Entity>ListSchema`, `<Entity>DetailSchema`.
Не включай во входные схемы поля, которые задаёт сервер (`id`, `created_at`, `created_by_id`,
`client_id`, `seller_id`, `final_price`, `status` где его меняют только действия).
Не включай `password`/токены в ответы.

## 2. Файл `mysite/api/<entity>.py`
Имена: файл `car_model.py` → `car_model_router`, `prefix='/car-model'`, `tags=['CarModel']`,
переменные `car_model_db`, `car_model_data`, параметр `car_model_id`.

```python
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from mysite.api.dependencies import get_current_user, require_role
from mysite.db.database import get_db
from mysite.db.models import Brand, UserProfile, UserRole
from mysite.db.schema import (BrandCreateSchema, BrandDetailSchema, BrandListSchema,
                              BrandUpdateSchema)

brand_router = APIRouter(prefix='/brand', tags=['Brand'])


@brand_router.post('/create', response_model=BrandDetailSchema)
async def create_brand(brand_data: BrandCreateSchema, db: Session = Depends(get_db),
                       current_user: UserProfile = Depends(require_role(UserRole.admin))):
    brand_db = Brand(**brand_data.model_dump())
    db.add(brand_db)
    db.commit()
    db.refresh(brand_db)
    return brand_db


@brand_router.get('/list', response_model=List[BrandListSchema])
async def list_brand(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(Brand).offset(skip).limit(limit).all()


@brand_router.get('/detail', response_model=BrandDetailSchema)
async def detail_brand(brand_id: int, db: Session = Depends(get_db)):
    brand_db = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')
    return brand_db


@brand_router.put('/update/{brand_id}', response_model=BrandDetailSchema)
async def update_brand(brand_id: int, brand_data: BrandUpdateSchema, db: Session = Depends(get_db),
                       current_user: UserProfile = Depends(require_role(UserRole.admin))):
    brand_db = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')

    for key, value in brand_data.model_dump(exclude_unset=True).items():
        setattr(brand_db, key, value)

    db.commit()
    db.refresh(brand_db)
    return brand_db


@brand_router.delete('/delete/{brand_id}', response_model=dict)
async def delete_brand(brand_id: int, db: Session = Depends(get_db),
                       current_user: UserProfile = Depends(require_role(UserRole.admin))):
    brand_db = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Марка не найдена')
    db.delete(brand_db)
    db.commit()
    return {'message': 'Марка удалена'}
```

## 3. Варианты
- **Объекты клиента** (Lead, Deal, Favorite, ...): в list/detail/update/delete фильтр
  `Model.client_id == current_user.id` для роли client; чужой → **404**. В create
  `client_id=current_user.id` выставляет сервер: `Lead(**lead_data.model_dump(), client_id=current_user.id)`.
- **Объекты продавца:** для seller — фильтр `Model.seller_id == current_user.id`.
- **Мягкое удаление** (Car, Deal): delete → `x_db.deleted_at = datetime.now(timezone.utc)`; все запросы
  с `Model.deleted_at.is_(None)`.
- **Уникальность:** перед create проверь дубль → 409 `'... уже существует'` (или поймай `IntegrityError`
  → `db.rollback()` → 409).
- **N+1:** если ListSchema содержит вложенные объекты → `options(selectinload(...))`.

## 4. Подключение в `main.py`
Импорт модуля в общий `from mysite.api import ...` и отдельная строка:
```python
auto_app.include_router(brand.brand_router)
```

## 5. Проверка
- `python -c "import main"` — импорт без ошибок.
- flake8 чисто (хук проверит автоматически).
- Тесты — через агента tester / skill `testing`.
