# Файл: маршруты API для артериального давления.

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.api.query_helpers import apply_datetime_date_range, apply_pagination
from app.db.session import get_db
from app.models.blood_pressure import BloodPressureEntry
from app.models.user import AppUser
from app.schemas.blood_pressure import BloodPressureCreate, BloodPressureOut, BloodPressureUpdate

router = APIRouter(prefix="/blood-pressure", tags=["blood-pressure"])


@router.get("", response_model=list[BloodPressureOut])
def list_blood_pressure(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[BloodPressureEntry]:
    stmt = (
        select(BloodPressureEntry)
        .where(BloodPressureEntry.athlete_id == user.id)
        .order_by(BloodPressureEntry.ts.desc())
    )
    stmt = apply_datetime_date_range(stmt, BloodPressureEntry.ts, date_from, date_to)
    stmt = apply_pagination(stmt, limit, offset)
    return list(db.scalars(stmt).all())


@router.get("/{entry_id}", response_model=BloodPressureOut)
def get_blood_pressure(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> BloodPressureEntry:
    entry = db.get(BloodPressureEntry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood pressure entry not found")
    return entry


@router.post(
    "",
    response_model=BloodPressureOut,
    status_code=status.HTTP_201_CREATED,
)
def create_blood_pressure(
    payload: BloodPressureCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> BloodPressureEntry:
    entry = BloodPressureEntry(
        athlete_id=user.id,
        ts=payload.ts,
        is_morning=payload.is_morning,
        systolic=payload.systolic,
        diastolic=payload.diastolic,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=BloodPressureOut)
def update_blood_pressure(
    entry_id: uuid.UUID,
    payload: BloodPressureUpdate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> BloodPressureEntry:
    entry = db.get(BloodPressureEntry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood pressure entry not found")

    entry.ts = payload.ts
    entry.is_morning = payload.is_morning
    entry.systolic = payload.systolic
    entry.diastolic = payload.diastolic
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_blood_pressure(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> None:
    entry = db.get(BloodPressureEntry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood pressure entry not found")
    db.delete(entry)
    db.commit()
