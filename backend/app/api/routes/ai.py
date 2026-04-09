# Файл: маршруты API для AI-оценки физической формы.

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.fitness_score import FitnessScore
from app.models.user import AppUser
from app.schemas.fitness_score import FitnessPredictionRequest, FitnessScoreOut
from app.services.fitness_ai_service import (
    AiServiceResponseError,
    AiServiceUnavailableError,
    predict_and_store_fitness_score,
    require_ai_service_url,
    resolve_target_athlete_id,
)

router = APIRouter(prefix="/ai", tags=["ai"])


def _resolve_request_athlete_id(
    db: Session,
    *,
    user: AppUser,
    requested_athlete_id: uuid.UUID | None,
) -> uuid.UUID:
    try:
        return resolve_target_athlete_id(
            db,
            requester_id=user.id,
            requester_role=user.role,
            requested_athlete_id=requested_athlete_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/predict", response_model=FitnessScoreOut, status_code=status.HTTP_201_CREATED)
def request_prediction(
    payload: FitnessPredictionRequest,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> FitnessScore:
    try:
        require_ai_service_url()
        athlete_id = _resolve_request_athlete_id(
            db,
            user=user,
            requested_athlete_id=payload.athlete_id,
        )
        return predict_and_store_fitness_score(
            db,
            athlete_id=athlete_id,
            date_from=payload.date_from,
            date_to=payload.date_to,
            history_limit=payload.history_limit,
        )
    except AiServiceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AiServiceResponseError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/last", response_model=FitnessScoreOut)
def get_last_prediction(
    athlete_id: uuid.UUID | None = Query(default=None),
    before_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> FitnessScore:
    target_athlete_id = _resolve_request_athlete_id(
        db,
        user=user,
        requested_athlete_id=athlete_id,
    )
    stmt = (
        select(FitnessScore)
        .where(FitnessScore.athlete_id == target_athlete_id)
        .order_by(FitnessScore.created_at.desc())
    )
    if before_date is not None:
        stmt = stmt.where(FitnessScore.date <= before_date)
    score = db.scalar(stmt)
    if score is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fitness score not found")
    return score
