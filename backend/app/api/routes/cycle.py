# Файл: маршруты API для цикла.

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.db.session import get_db
from app.models.cycle import CycleEvent, CycleSettings
from app.models.user import AppUser
from app.schemas.cycle import CycleEventsReplace, CycleSettingsOut, CycleSettingsUpsert

router = APIRouter(prefix="/cycle", tags=["cycle"])
_ALLOWED_KINDS = {"day", "excluded", "start", "end"}


@router.get("/settings", response_model=CycleSettingsOut)
def get_cycle_settings(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> CycleSettingsOut:
    settings = db.get(CycleSettings, user.id)
    if settings is None:
        return CycleSettingsOut(cycle_length_days=None, period_length_days=None)
    return CycleSettingsOut(
        cycle_length_days=settings.cycle_length_days,
        period_length_days=settings.period_length_days,
    )


@router.put("/settings", response_model=CycleSettingsOut)
def upsert_cycle_settings(
    payload: CycleSettingsUpsert,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> CycleSettingsOut:
    settings = db.get(CycleSettings, user.id)
    if settings is None:
        settings = CycleSettings(
            athlete_id=user.id,
            cycle_length_days=payload.cycle_length_days,
            period_length_days=payload.period_length_days,
        )
        db.add(settings)
    else:
        settings.cycle_length_days = payload.cycle_length_days
        settings.period_length_days = payload.period_length_days
    db.commit()
    return CycleSettingsOut(
        cycle_length_days=settings.cycle_length_days,
        period_length_days=settings.period_length_days,
    )


@router.get("/events", response_model=list[date])
def list_cycle_events(
    kind: str = Query(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[date]:
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported cycle event kind: {kind}",
        )
    stmt = (
        select(CycleEvent)
        .where(CycleEvent.athlete_id == user.id, CycleEvent.kind == kind)
        .order_by(CycleEvent.date.asc())
    )
    return [item.date for item in db.scalars(stmt).all()]


@router.put("/events", response_model=list[date])
def replace_cycle_events(
    payload: CycleEventsReplace,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[date]:
    if payload.kind not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported cycle event kind: {payload.kind}",
        )

    db.execute(
        delete(CycleEvent).where(
            CycleEvent.athlete_id == user.id,
            CycleEvent.kind == payload.kind,
        )
    )
    for d in payload.dates:
        db.add(CycleEvent(athlete_id=user.id, date=d, kind=payload.kind))
    db.commit()
    return sorted(payload.dates)
