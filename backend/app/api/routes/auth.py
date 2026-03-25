from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    ensure_bcrypt_password_limit,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import AppUser, AthleteProfile, CoachProfile
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        ensure_bcrypt_password_limit(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    existing = db.scalar(select(AppUser).where(AppUser.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = AppUser(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == "athlete":
        db.add(
            AthleteProfile(
                user_id=user.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
                age=payload.age,
                gender=payload.gender,
                weight_kg=payload.weight_kg,
                height_cm=payload.height_cm,
                sport=payload.sport,
            )
        )
    else:
        db.add(
            CoachProfile(
                user_id=user.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
            )
        )

    db.commit()
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(AppUser).where(AppUser.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)
