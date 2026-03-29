# Файл: маршруты API для анализов.

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.db.session import get_db
from app.models.analysis import AnalysisEntry
from app.models.user import AppUser
from app.schemas.analysis import AnalysisCreate, AnalysisOut

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("", response_model=list[AnalysisOut])
def list_analyses(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[AnalysisEntry]:
    stmt = (
        select(AnalysisEntry)
        .where(AnalysisEntry.athlete_id == user.id)
        .order_by(AnalysisEntry.date.desc(), AnalysisEntry.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=AnalysisOut)
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

