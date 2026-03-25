from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.db.session import get_db
from app.models.blood_pressure import BloodPressureEntry
from app.models.user import AppUser
from app.schemas.blood_pressure import BloodPressureCreate, BloodPressureOut

router = APIRouter(prefix="/blood-pressure", tags=["blood-pressure"])


@router.get("", response_model=list[BloodPressureOut])
def list_blood_pressure(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[BloodPressureEntry]:
    stmt = (
        select(BloodPressureEntry)
        .where(BloodPressureEntry.athlete_id == user.id)
        .order_by(BloodPressureEntry.ts.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=BloodPressureOut)
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

