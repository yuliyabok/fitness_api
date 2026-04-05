# Файл: маршруты API для профиля пользователя.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import AppUser
from app.schemas.profile import AthleteProfileOut, AthleteProfileUpdate, CoachProfileOut

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=AthleteProfileOut | CoachProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
):
    db.refresh(user)
    if user.role == "athlete":
        profile = user.athlete_profile
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Athlete profile not found")
        return AthleteProfileOut(
            role="athlete",
            first_name=profile.first_name,
            last_name=profile.last_name,
            email=user.email,
            age=profile.age,
            gender=profile.gender,
            weight_kg=profile.weight_kg,
            height_cm=profile.height_cm,
            sport=profile.sport,
            created_at=user.created_at,
        )

    profile = user.coach_profile
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coach profile not found")
    return CoachProfileOut(
        role="coach",
        first_name=profile.first_name,
        last_name=profile.last_name,
        email=user.email,
        created_at=user.created_at,
    )


@router.put("/me", response_model=AthleteProfileOut)
def update_my_athlete_profile(
    payload: AthleteProfileUpdate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> AthleteProfileOut:
    if user.role != "athlete" or user.athlete_profile is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Athlete profile required")

    profile = user.athlete_profile
    profile.first_name = payload.first_name
    profile.last_name = payload.last_name
    profile.age = payload.age
    profile.gender = payload.gender
    profile.weight_kg = payload.weight_kg
    profile.height_cm = payload.height_cm
    profile.sport = payload.sport
    db.commit()
    db.refresh(user)
    return AthleteProfileOut(
        role="athlete",
        first_name=profile.first_name,
        last_name=profile.last_name,
        email=user.email,
        age=profile.age,
        gender=profile.gender,
        weight_kg=profile.weight_kg,
        height_cm=profile.height_cm,
        sport=profile.sport,
        created_at=user.created_at,
    )
