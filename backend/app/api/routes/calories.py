# Файл: маршруты API для калорий.

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.api.query_helpers import apply_date_range, apply_pagination
from app.db.session import get_db
from app.models.calorie import CalorieEntry
from app.models.user import AppUser
from app.schemas.calorie import CalorieCreate, CalorieOut, CalorieUpdate

router = APIRouter(prefix="/calories", tags=["calories"])


@router.get("", response_model=list[CalorieOut])
def list_calories(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[CalorieEntry]:
    stmt = (
        select(CalorieEntry)
        .where(CalorieEntry.athlete_id == user.id)
        .order_by(CalorieEntry.date.desc())
    )
    stmt = apply_date_range(stmt, CalorieEntry.date, date_from, date_to)
    stmt = apply_pagination(stmt, limit, offset)
    return list(db.scalars(stmt).all())


@router.get("/{calorie_id}", response_model=CalorieOut)
def get_calorie(
    calorie_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> CalorieEntry:
    entry = db.get(CalorieEntry, calorie_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calorie entry not found")
    return entry


@router.post(
    "",
    response_model=CalorieOut,
    status_code=status.HTTP_201_CREATED,
)
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


@router.put("/{calorie_id}", response_model=CalorieOut)
def update_calorie(
    calorie_id: uuid.UUID,
    payload: CalorieUpdate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> CalorieEntry:
    entry = db.get(CalorieEntry, calorie_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calorie entry not found")

    entry.date = payload.date
    entry.calories = payload.calories
    entry.notes = payload.notes
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{calorie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calorie(
    calorie_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> None:
    entry = db.get(CalorieEntry, calorie_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calorie entry not found")
    db.delete(entry)
    db.commit()
