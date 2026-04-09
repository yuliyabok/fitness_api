# Файл: Pydantic-схемы для AI-оценки физической формы.

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class FitnessPredictionRequest(BaseModel):
    athlete_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    history_limit: int = Field(default=30, ge=1, le=180)


class FitnessScoreOut(BaseModel):
    id: uuid.UUID
    athlete_id: uuid.UUID
    date: date
    fitness_index: float
    recommendations: str
    created_at: datetime

    class Config:
        from_attributes = True
