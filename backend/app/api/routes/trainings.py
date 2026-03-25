import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_athlete
from app.db.session import get_db
from app.models.training import Training
from app.models.user import AppUser
from app.schemas.training import TrainingCreate, TrainingOut

router = APIRouter(prefix="/trainings", tags=["trainings"])


@router.get("", response_model=list[TrainingOut])
def list_trainings(
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> list[Training]:
    stmt = select(Training).where(Training.athlete_id == user.id).order_by(Training.date.desc())
    return list(db.scalars(stmt).all())


@router.post("", response_model=TrainingOut)
def create_training(
    payload: TrainingCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> Training:
    training = Training(
        athlete_id=user.id,
        title=payload.title,
        training_type=payload.training_type,
        date=payload.date,
        start_time=payload.start_time,
        duration_minutes=payload.duration_minutes,
        distance_km=payload.distance_km,
        elevation_m=payload.elevation_m,
        avg_hr=payload.avg_hr,
        max_hr=payload.max_hr,
        calories=payload.calories,
        notes=payload.notes,
        sport=payload.sport,
        hr_zone=payload.hr_zone,
        hr_zone_minutes=payload.hr_zone_minutes,
        activity_types=payload.activity_types,
        exercises=payload.exercises,
        feeling_score=payload.feeling_score,
    )
    db.add(training)
    db.commit()
    db.refresh(training)
    return training


@router.put("/{training_id}", response_model=TrainingOut)
def update_training(
    training_id: uuid.UUID,
    payload: TrainingCreate,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> Training:
    training = db.get(Training, training_id)
    if training is None or training.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training not found")

    training.title = payload.title
    training.training_type = payload.training_type
    training.date = payload.date
    training.start_time = payload.start_time
    training.duration_minutes = payload.duration_minutes
    training.distance_km = payload.distance_km
    training.elevation_m = payload.elevation_m
    training.avg_hr = payload.avg_hr
    training.max_hr = payload.max_hr
    training.calories = payload.calories
    training.notes = payload.notes
    training.sport = payload.sport
    training.hr_zone = payload.hr_zone
    training.hr_zone_minutes = payload.hr_zone_minutes
    training.activity_types = payload.activity_types
    training.exercises = payload.exercises
    training.feeling_score = payload.feeling_score
    db.commit()
    db.refresh(training)
    return training


@router.delete("/{training_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training(
    training_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_athlete),
) -> None:
    training = db.get(Training, training_id)
    if training is None or training.athlete_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training not found")
    db.delete(training)
    db.commit()


