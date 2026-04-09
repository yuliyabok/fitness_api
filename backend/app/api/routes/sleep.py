# Файл: маршруты API для сна.

import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.api.query_helpers import apply_datetime_date_range, apply_pagination
from app.db.session import get_db
from app.models.sleep import SleepEntry
from app.models.user import AppUser
from app.schemas.sleep import SleepCreate, SleepOut, SleepUpdate
from app.services.fitness_ai_service import enqueue_fitness_prediction

router = APIRouter(prefix="/sleep", tags=["sleep"])


@router.get("", response_model=list[SleepOut])
def list_sleep(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[SleepEntry]:
    stmt = (
        select(SleepEntry)
        .where(SleepEntry.athlete_id == user.id)
        .order_by(SleepEntry.end_ts.desc())
    )
    stmt = apply_datetime_date_range(stmt, SleepEntry.end_ts, date_from, date_to)
    stmt = apply_pagination(stmt, limit, offset)
    return list(db.scalars(stmt).all())


@router.get("/{entry_id}", response_model=SleepOut)
def get_sleep(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> SleepEntry:
    entry = db.get(SleepEntry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sleep entry not found")
    return entry


@router.post(
    "",
    response_model=SleepOut,
    status_code=status.HTTP_201_CREATED,
)
def create_sleep(
    payload: SleepCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> SleepEntry:
    entry = SleepEntry(
        athlete_id=user.id,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        deep_minutes=payload.deep_minutes,
        light_minutes=payload.light_minutes,
        rem_minutes=payload.rem_minutes,
        source=payload.source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    background_tasks.add_task(enqueue_fitness_prediction, user.id)
    return entry


@router.put("/{entry_id}", response_model=SleepOut)
def update_sleep(
    entry_id: uuid.UUID,
    payload: SleepUpdate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> SleepEntry:
    entry = db.get(SleepEntry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sleep entry not found")

    entry.start_ts = payload.start_ts
    entry.end_ts = payload.end_ts
    entry.deep_minutes = payload.deep_minutes
    entry.light_minutes = payload.light_minutes
    entry.rem_minutes = payload.rem_minutes
    entry.source = payload.source
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sleep(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> None:
    entry = db.get(SleepEntry, entry_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sleep entry not found")
    db.delete(entry)
    db.commit()
