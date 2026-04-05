# Файл: маршруты API для связей тренера со спортсменами.

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import require_coach
from app.api.query_helpers import apply_date_range, apply_datetime_date_range, apply_pagination
from app.db.session import get_db
from app.models.analysis import AnalysisEntry
from app.models.blood_pressure import BloodPressureEntry
from app.models.calorie import CalorieEntry
from app.models.sleep import SleepEntry
from app.models.spo2 import Spo2Entry
from app.models.training import Training
from app.models.user import AppUser, CoachAthleteLink
from app.schemas.coach import (
    CoachAthleteDetailOut,
    CoachLinkAthleteRequest,
    CoachLinkAthleteResponse,
    CoachLinkedAthleteOut,
)

router = APIRouter(prefix='/coach', tags=['coach'])


def _get_linked_athlete(db: Session, coach_id: uuid.UUID, athlete_id: uuid.UUID) -> AppUser:
    link = db.scalar(
        select(CoachAthleteLink).where(
            CoachAthleteLink.coach_id == coach_id,
            CoachAthleteLink.athlete_id == athlete_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Athlete not linked')

    athlete = db.get(AppUser, athlete_id)
    if athlete is None or athlete.role != 'athlete':
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Athlete not found')
    return athlete


@router.get('/athletes', response_model=list[CoachLinkedAthleteOut])
def list_linked_athletes(
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_coach),
) -> list[CoachLinkedAthleteOut]:
    stmt = (
        select(AppUser)
        .join(CoachAthleteLink, CoachAthleteLink.athlete_id == AppUser.id)
        .where(CoachAthleteLink.coach_id == user.id, AppUser.role == 'athlete')
        .order_by(AppUser.email.asc())
    )
    stmt = apply_pagination(stmt, limit, offset)
    athletes = list(db.scalars(stmt).all())
    result: list[CoachLinkedAthleteOut] = []
    for athlete in athletes:
        profile = athlete.athlete_profile
        if profile is None:
            continue
        result.append(
            CoachLinkedAthleteOut(
                athlete_id=athlete.id,
                first_name=profile.first_name,
                last_name=profile.last_name,
                email=athlete.email,
                age=profile.age,
                gender=profile.gender,
                weight_kg=profile.weight_kg,
                height_cm=profile.height_cm,
                sport=profile.sport,
            )
        )
    return result


@router.get('/athletes/{athlete_id}', response_model=CoachAthleteDetailOut)
def get_athlete_details(
    athlete_id: uuid.UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_coach),
) -> CoachAthleteDetailOut:
    athlete = _get_linked_athlete(db, user.id, athlete_id)
    profile = athlete.athlete_profile
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Athlete profile not found')

    trainings_stmt = (
        select(Training)
        .where(Training.athlete_id == athlete.id)
        .order_by(Training.date.desc())
    )
    trainings_stmt = apply_date_range(trainings_stmt, Training.date, date_from, date_to)
    trainings_stmt = apply_pagination(trainings_stmt, limit, offset)
    trainings = list(db.scalars(trainings_stmt).all())

    analyses_stmt = (
        select(AnalysisEntry)
        .where(AnalysisEntry.athlete_id == athlete.id)
        .order_by(AnalysisEntry.date.desc())
    )
    analyses_stmt = apply_date_range(analyses_stmt, AnalysisEntry.date, date_from, date_to)
    analyses_stmt = apply_pagination(analyses_stmt, limit, offset)
    analyses = list(db.scalars(analyses_stmt).all())

    calories_stmt = (
        select(CalorieEntry)
        .where(CalorieEntry.athlete_id == athlete.id)
        .order_by(CalorieEntry.date.desc())
    )
    calories_stmt = apply_date_range(calories_stmt, CalorieEntry.date, date_from, date_to)
    calories_stmt = apply_pagination(calories_stmt, limit, offset)
    calories = list(db.scalars(calories_stmt).all())

    blood_pressure_stmt = (
        select(BloodPressureEntry)
        .where(BloodPressureEntry.athlete_id == athlete.id)
        .order_by(BloodPressureEntry.ts.desc())
    )
    blood_pressure_stmt = apply_datetime_date_range(
        blood_pressure_stmt,
        BloodPressureEntry.ts,
        date_from,
        date_to,
    )
    blood_pressure_stmt = apply_pagination(blood_pressure_stmt, limit, offset)
    blood_pressures = list(db.scalars(blood_pressure_stmt).all())

    sleep_stmt = (
        select(SleepEntry)
        .where(SleepEntry.athlete_id == athlete.id)
        .order_by(SleepEntry.end_ts.desc())
    )
    sleep_stmt = apply_datetime_date_range(sleep_stmt, SleepEntry.end_ts, date_from, date_to)
    sleep_stmt = apply_pagination(sleep_stmt, limit, offset)
    sleep_entries = list(db.scalars(sleep_stmt).all())

    spo2_stmt = (
        select(Spo2Entry)
        .where(Spo2Entry.athlete_id == athlete.id)
        .order_by(Spo2Entry.ts.desc())
    )
    spo2_stmt = apply_datetime_date_range(spo2_stmt, Spo2Entry.ts, date_from, date_to)
    spo2_stmt = apply_pagination(spo2_stmt, limit, offset)
    spo2_entries = list(db.scalars(spo2_stmt).all())

    return CoachAthleteDetailOut(
        athlete_id=athlete.id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        email=athlete.email,
        age=profile.age,
        gender=profile.gender,
        weight_kg=profile.weight_kg,
        height_cm=profile.height_cm,
        sport=profile.sport,
        trainings=trainings,
        analyses=analyses,
        calories=calories,
        blood_pressures=blood_pressures,
        sleep_entries=sleep_entries,
        spo2_entries=spo2_entries,
    )


@router.post('/athletes', response_model=CoachLinkAthleteResponse)
def link_athlete(
    payload: CoachLinkAthleteRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_coach),
) -> CoachLinkAthleteResponse:
    athlete = db.scalar(select(AppUser).where(AppUser.email == payload.email.lower(), AppUser.role == 'athlete'))
    if athlete is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Athlete not found')

    existing = db.scalar(
        select(CoachAthleteLink).where(
            CoachAthleteLink.coach_id == user.id,
            CoachAthleteLink.athlete_id == athlete.id,
        )
    )
    if existing is None:
        existing = CoachAthleteLink(coach_id=user.id, athlete_id=athlete.id)
        db.add(existing)
        db.commit()
        db.refresh(existing)

    return CoachLinkAthleteResponse(athlete_id=athlete.id, linked_at=existing.created_at)


@router.delete('/athletes/{athlete_id}', status_code=status.HTTP_204_NO_CONTENT)
def unlink_athlete(
    athlete_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_coach),
) -> None:
    db.execute(
        delete(CoachAthleteLink).where(
            CoachAthleteLink.coach_id == user.id,
            CoachAthleteLink.athlete_id == athlete_id,
        )
    )
    db.commit()
