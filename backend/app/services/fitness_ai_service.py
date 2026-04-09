# Файл: сервис агрегации данных спортсмена и обращения к внешнему AI-сервису.

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.blood_pressure import BloodPressureEntry
from app.models.fitness_score import FitnessScore
from app.models.sleep import SleepEntry
from app.models.spo2 import Spo2Entry
from app.models.training import Training
from app.models.user import AthleteProfile, CoachAthleteLink
from app.services.ai_client import AIClient, AIClientResponseError, AIClientUnavailableError

logger = logging.getLogger(__name__)

AiServiceUnavailableError = AIClientUnavailableError
AiServiceResponseError = AIClientResponseError


def require_ai_service_url() -> str:
    service_url = (settings.ai_service_url or "").strip()
    if not service_url:
        raise AiServiceUnavailableError("AI_SERVICE_URL is not configured")
    return service_url


def resolve_target_athlete_id(
    db: Session,
    *,
    requester_id: uuid.UUID,
    requester_role: str,
    requested_athlete_id: uuid.UUID | None,
) -> uuid.UUID:
    if requester_role == "athlete":
        if requested_athlete_id is not None and requested_athlete_id != requester_id:
            raise PermissionError("Athlete can request AI score only for self")
        return requester_id

    if requested_athlete_id is None:
        raise ValueError("athlete_id is required for coach requests")

    link = db.scalar(
        select(CoachAthleteLink).where(
            CoachAthleteLink.coach_id == requester_id,
            CoachAthleteLink.athlete_id == requested_athlete_id,
        )
    )
    if link is None:
        raise PermissionError("Athlete not linked")
    return requested_athlete_id


def _serialize_trainings(entries: list[Training]) -> list[dict]:
    return [
        {
            "id": str(entry.id),
            "date": entry.date.isoformat(),
            "title": entry.title,
            "training_type": entry.training_type,
            "duration_minutes": entry.duration_minutes,
            "distance_km": entry.distance_km,
            "avg_hr": entry.avg_hr,
            "max_hr": entry.max_hr,
            "calories": entry.calories,
            "hr_zone": entry.hr_zone,
            "hr_zone_minutes": entry.hr_zone_minutes,
            "activity_types": entry.activity_types or [],
            "feeling_score": entry.feeling_score,
            "sport": entry.sport,
        }
        for entry in entries
    ]


def _serialize_sleep(entries: list[SleepEntry]) -> list[dict]:
    return [
        {
            "id": str(entry.id),
            "start_ts": entry.start_ts.isoformat(),
            "end_ts": entry.end_ts.isoformat(),
            "deep_minutes": entry.deep_minutes,
            "light_minutes": entry.light_minutes,
            "rem_minutes": entry.rem_minutes,
            "source": entry.source,
        }
        for entry in entries
    ]


def _serialize_blood_pressure(entries: list[BloodPressureEntry]) -> list[dict]:
    return [
        {
            "id": str(entry.id),
            "ts": entry.ts.isoformat(),
            "is_morning": entry.is_morning,
            "systolic": entry.systolic,
            "diastolic": entry.diastolic,
        }
        for entry in entries
    ]


def _serialize_spo2(entries: list[Spo2Entry]) -> list[dict]:
    return [
        {
            "id": str(entry.id),
            "ts": entry.ts.isoformat(),
            "percentage": entry.percentage,
            "source": entry.source,
        }
        for entry in entries
    ]


def _load_profile_context(db: Session, athlete_id: uuid.UUID) -> dict[str, object]:
    profile = db.get(AthleteProfile, athlete_id)
    if profile is None:
        return {}
    return {
        "age": profile.age,
        "gender": profile.gender,
        "weight_kg": profile.weight_kg,
        "height_cm": profile.height_cm,
        "sport": profile.sport,
    }


def _apply_date_range(statement, column, date_from: date | None, date_to: date | None):
    if date_from is not None:
        statement = statement.where(column >= date_from)
    if date_to is not None:
        statement = statement.where(column <= date_to)
    return statement


def _apply_datetime_range(statement, column, date_from: date | None, date_to: date | None):
    if date_from is not None:
        statement = statement.where(column >= datetime.combine(date_from, time.min))
    if date_to is not None:
        statement = statement.where(column < datetime.combine(date_to + timedelta(days=1), time.min))
    return statement


def build_prediction_payload(
    db: Session,
    *,
    athlete_id: uuid.UUID,
    date_from: date | None,
    date_to: date | None,
    history_limit: int,
) -> dict[str, object]:
    trainings_stmt = (
        select(Training)
        .where(Training.athlete_id == athlete_id)
        .order_by(Training.date.desc())
        .limit(history_limit)
    )
    trainings_stmt = _apply_date_range(trainings_stmt, Training.date, date_from, date_to)
    trainings = list(db.scalars(trainings_stmt).all())

    sleep_stmt = (
        select(SleepEntry)
        .where(SleepEntry.athlete_id == athlete_id)
        .order_by(SleepEntry.end_ts.desc())
        .limit(history_limit)
    )
    sleep_stmt = _apply_datetime_range(sleep_stmt, SleepEntry.end_ts, date_from, date_to)
    sleep_entries = list(db.scalars(sleep_stmt).all())

    pressure_stmt = (
        select(BloodPressureEntry)
        .where(BloodPressureEntry.athlete_id == athlete_id)
        .order_by(BloodPressureEntry.ts.desc())
        .limit(history_limit)
    )
    pressure_stmt = _apply_datetime_range(pressure_stmt, BloodPressureEntry.ts, date_from, date_to)
    blood_pressures = list(db.scalars(pressure_stmt).all())

    spo2_stmt = (
        select(Spo2Entry)
        .where(Spo2Entry.athlete_id == athlete_id)
        .order_by(Spo2Entry.ts.desc())
        .limit(history_limit)
    )
    spo2_stmt = _apply_datetime_range(spo2_stmt, Spo2Entry.ts, date_from, date_to)
    spo2_entries = list(db.scalars(spo2_stmt).all())

    return {
        "athlete_id": str(athlete_id),
        "date_from": date_from.isoformat() if date_from is not None else None,
        "date_to": date_to.isoformat() if date_to is not None else None,
        "history_limit": history_limit,
        "profile": _load_profile_context(db, athlete_id),
        "trainings": _serialize_trainings(trainings),
        "sleep": _serialize_sleep(sleep_entries),
        "blood_pressure": _serialize_blood_pressure(blood_pressures),
        "spo2": _serialize_spo2(spo2_entries),
    }


def _call_ai_service(payload: dict[str, object]) -> tuple[float, str]:
    client = AIClient(
        service_url=require_ai_service_url(),
        target=settings.ai_model_target,
    )
    prediction = client.predict(payload)
    return prediction.fitness_index, prediction.recommendations


def predict_and_store_fitness_score(
    db: Session,
    *,
    athlete_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    history_limit: int = 30,
) -> FitnessScore:
    payload = build_prediction_payload(
        db,
        athlete_id=athlete_id,
        date_from=date_from,
        date_to=date_to,
        history_limit=history_limit,
    )
    fitness_index, recommendations = _call_ai_service(payload)
    score = FitnessScore(
        athlete_id=athlete_id,
        date=date_to or date.today(),
        fitness_index=fitness_index,
        recommendations=recommendations,
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def enqueue_fitness_prediction(
    athlete_id: uuid.UUID,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    history_limit: int = 30,
) -> None:
    if not (settings.ai_service_url or "").strip():
        return

    with SessionLocal() as db:
        try:
            predict_and_store_fitness_score(
                db,
                athlete_id=athlete_id,
                date_from=date_from,
                date_to=date_to,
                history_limit=history_limit,
            )
        except Exception:
            logger.exception("Failed to refresh AI fitness score in background", extra={"athlete_id": str(athlete_id)})
