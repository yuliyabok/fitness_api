# Файл: маршруты API для анализов.

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.api.query_helpers import apply_date_range, apply_pagination
from app.db.session import get_db
from app.models.analysis import AnalysisEntry
from app.models.user import AppUser
from app.schemas.analysis import AnalysisCreate, AnalysisOut, AnalysisUpdate

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("", response_model=list[AnalysisOut])
def list_analyses(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[AnalysisEntry]:
    stmt = (
        select(AnalysisEntry)
        .where(AnalysisEntry.athlete_id == user.id)
        .order_by(AnalysisEntry.date.desc(), AnalysisEntry.created_at.desc())
    )
    stmt = apply_date_range(stmt, AnalysisEntry.date, date_from, date_to)
    stmt = apply_pagination(stmt, limit, offset)
    return list(db.scalars(stmt).all())


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> AnalysisEntry:
    entry = db.get(AnalysisEntry, analysis_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return entry


@router.post(
    "",
    response_model=AnalysisOut,
    status_code=status.HTTP_201_CREATED,
)
def create_analysis(
    payload: AnalysisCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> AnalysisEntry:
    entry = AnalysisEntry(
        athlete_id=user.id,
        date=payload.date,
        title=payload.title,
        value=payload.value,
        notes=payload.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{analysis_id}", response_model=AnalysisOut)
def update_analysis(
    analysis_id: uuid.UUID,
    payload: AnalysisUpdate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> AnalysisEntry:
    entry = db.get(AnalysisEntry, analysis_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    entry.date = payload.date
    entry.title = payload.title
    entry.value = payload.value
    entry.notes = payload.notes
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> None:
    entry = db.get(AnalysisEntry, analysis_id)
    if entry is None or entry.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    db.delete(entry)
    db.commit()
