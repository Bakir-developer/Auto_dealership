from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.config import ACCESS_EXPIRE_TOKEN, ALGORITHM, REFRESH_EXPIRE_TOKEN, SECRET_KEY
from mysite.db.database import get_db
from mysite.db.models import RefreshToken, UserProfile, UserRole
from mysite.db.schema import LoginSchema, RefreshTokenSchema, RegisterSchema, TokenSchema, UserProfileDetailSchema

if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY не задан')

auth_router = APIRouter(prefix='/auth', tags=['Authorization'])

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update(
        {
            'exp': datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE_TOKEN),
            'type': 'access',
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update(
        {
            'exp': datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_TOKEN),
            'type': 'refresh',
            'jti': uuid4().hex,
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Недействительный или просроченный токен',
            headers={'WWW-Authenticate': 'Bearer'},
        )


def issue_tokens(user_db: UserProfile, db: Session) -> dict:
    payload = {'sub': user_db.username, 'user_id': user_db.id}
    access_token = create_access_token(payload)
    refresh_token = create_refresh_token(payload)
    db.add(RefreshToken(user_id=user_db.id, token=refresh_token))
    db.commit()
    return {'access_token': access_token, 'refresh_token': refresh_token, 'user_id': user_db.id, 'type': 'bearer'}


def consume_refresh_token(token_db: RefreshToken, db: Session):
    deleted = db.query(RefreshToken).filter(RefreshToken.id == token_db.id).delete(synchronize_session=False)
    if deleted != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Недействительный refresh-токен')


def get_refresh_token_db(refresh_token: str, db: Session) -> RefreshToken:
    invalid_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Недействительный refresh-токен')
    try:
        payload = decode_token(refresh_token)
    except HTTPException:
        raise invalid_error
    if payload.get('type') != 'refresh':
        raise invalid_error
    token_db = db.query(RefreshToken).filter(RefreshToken.token == refresh_token).first()
    if not token_db:
        raise invalid_error
    return token_db


@auth_router.post('/register', response_model=UserProfileDetailSchema)
async def register(user_data: RegisterSchema, db: Session = Depends(get_db)):
    if db.query(UserProfile).filter(UserProfile.username == user_data.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь с таким username уже существует')
    if db.query(UserProfile).filter(UserProfile.email == user_data.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь с таким email уже существует')

    user_db = UserProfile(
        **user_data.model_dump(exclude={'password'}),
        password=get_password_hash(user_data.password),
        role=UserRole.client,
    )
    db.add(user_db)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Пользователь с такими данными уже существует')
    db.refresh(user_db)
    return user_db


@auth_router.post('/login', response_model=TokenSchema)
async def login(login_data: LoginSchema, db: Session = Depends(get_db)):
    user_db = db.query(UserProfile).filter(UserProfile.username == login_data.username).first()
    if not user_db:
        pwd_context.dummy_verify()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Неверный логин или пароль')
    if not verify_password(login_data.password, user_db.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Неверный логин или пароль')
    if not user_db.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Пользователь заблокирован')
    return issue_tokens(user_db, db)


@auth_router.post('/logout', response_model=dict)
async def logout(token_data: RefreshTokenSchema, db: Session = Depends(get_db)):
    token_db = get_refresh_token_db(token_data.refresh_token, db)
    consume_refresh_token(token_db, db)
    db.commit()
    return {'message': 'Вы вышли из системы'}


@auth_router.post('/access_generate', response_model=TokenSchema)
async def access_generate(token_data: RefreshTokenSchema, db: Session = Depends(get_db)):
    token_db = get_refresh_token_db(token_data.refresh_token, db)
    user_db = db.query(UserProfile).filter(UserProfile.id == token_db.user_id).first()
    if not user_db or not user_db.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Пользователь не найден или заблокирован')
    consume_refresh_token(token_db, db)
    return issue_tokens(user_db, db)
