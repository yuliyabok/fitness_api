import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import AppUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AppUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        uuid_user_id = uuid.UUID(user_id)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.get(AppUser, uuid_user_id)
    if user is None:
        raise credentials_exception
    return user


def require_athlete(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role != "athlete":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Athlete role required")
    return user


def require_coach(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role != "coach":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Coach role required")
    return user
