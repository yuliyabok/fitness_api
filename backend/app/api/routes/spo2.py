# Файл: маршруты API для сатурации.

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.db.session import get_db
from app.models.spo2 import Spo2Entry
from app.models.user import AppUser
from app.schemas.spo2 import Spo2Create, Spo2Out

router = APIRouter(prefix="/spo2", tags=["spo2"])


@router.get("", response_model=list[Spo2Out])
def list_spo2(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[Spo2Entry]:
    stmt = (
        select(Spo2Entry)
        .where(Spo2Entry.athlete_id == user.id)
        .order_by(Spo2Entry.ts.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=Spo2Out)
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
