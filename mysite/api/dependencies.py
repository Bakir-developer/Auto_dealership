from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from mysite.api.auth import decode_token
from mysite.db.database import get_db
from mysite.db.models import UserProfile, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/login')
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl='auth/login', auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> UserProfile:
    payload = decode_token(token)
    if payload.get('type') != 'access':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Недействительный токен',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    user_id = payload.get('user_id')
    user_db = db.query(UserProfile).filter(UserProfile.id == user_id).first() if user_id else None
    if not user_db or not user_db.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Пользователь не найден или заблокирован',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return user_db


async def get_optional_user(
    token: str | None = Depends(oauth2_scheme_optional), db: Session = Depends(get_db)
) -> UserProfile | None:
    if token is None:
        return None
    return await get_current_user(token, db)


def require_role(*roles: UserRole):
    async def checker(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Недостаточно прав')
        return current_user

    return checker
