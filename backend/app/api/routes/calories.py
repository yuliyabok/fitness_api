# Файл: маршруты API для калорий.

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.db.session import get_db
from app.models.calorie import CalorieEntry
from app.models.user import AppUser
from app.schemas.calorie import CalorieCreate, CalorieOut

router = APIRouter(prefix="/calories", tags=["calories"])


@router.get("", response_model=list[CalorieOut])
def list_calories(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[CalorieEntry]:
    stmt = (
        select(CalorieEntry)
        .where(CalorieEntry.athlete_id == user.id)
        .order_by(CalorieEntry.date.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=CalorieOut)
def create_calorie(
    payload: CalorieCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> CalorieEntry:
    entry = CalorieEntry(
        athlete_id=user.id,
        date=payload.date,
        calories=payload.calories,
        notes=payload.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
