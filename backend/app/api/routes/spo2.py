# Файл: маршруты API для сатурации.

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.api.query_helpers import apply_datetime_date_range, apply_pagination
from app.db.session import get_db
from app.models.spo2 import Spo2Entry
from app.models.user import AppUser
from app.schemas.spo2 import Spo2Create, Spo2Out, Spo2Update

router = APIRouter(prefix="/spo2", tags=["spo2"])


@router.get("", response_model=list[Spo2Out])
def list_spo2(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[Spo2Entry]:
    stmt = (
        select(Spo2Entry)
        .where(Spo2Entry.athlete_id == user.id)
        .order_by(Spo2Entry.ts.desc())
    )
    stmt = apply_datetime_date_range(stmt, Spo2Entry.ts, date_from, date_to)
    stmt = apply_pagination(stmt, limit, offset)
    return list(db.scalars(stmt).all())


@router.get("/{entry_id}", response_model=Spo2Out)
def get_spo2(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> Spo2Entry:
    entry = db.get(Spo2Entry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SpO2 entry not found")
    return entry


@router.post(
    "",
    response_model=Spo2Out,
    status_code=status.HTTP_201_CREATED,
)
def create_spo2(
    payload: Spo2Create,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> Spo2Entry:
    entry = Spo2Entry(
        athlete_id=user.id,
        ts=payload.ts,
        percentage=payload.percentage,
        source=payload.source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=Spo2Out)
def update_spo2(
    entry_id: uuid.UUID,
    payload: Spo2Update,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> Spo2Entry:
    entry = db.get(Spo2Entry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SpO2 entry not found")

    entry.ts = payload.ts
    entry.percentage = payload.percentage
    entry.source = payload.source
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_spo2(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> None:
    entry = db.get(Spo2Entry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SpO2 entry not found")
    db.delete(entry)
    db.commit()
