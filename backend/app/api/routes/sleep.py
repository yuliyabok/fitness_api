# Файл: маршруты API для сна.

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.db.session import get_db
from app.models.sleep import SleepEntry
from app.models.user import AppUser
from app.schemas.sleep import SleepCreate, SleepOut

router = APIRouter(prefix="/sleep", tags=["sleep"])


@router.get("", response_model=list[SleepOut])
def list_sleep(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[SleepEntry]:
    stmt = (
        select(SleepEntry)
        .where(SleepEntry.athlete_id == user.id)
        .order_by(SleepEntry.end_ts.desc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "",
    response_model=SleepOut,
    status_code=status.HTTP_201_CREATED,
)
def create_sleep(
    payload: SleepCreate,
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
    return entry
