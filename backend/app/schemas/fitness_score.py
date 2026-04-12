# Файл: Pydantic-схемы для AI-оценки физической формы.

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TrendValue = Literal["up", "stable", "down"]


class FitnessPredictionRequest(BaseModel):
    athlete_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    history_limit: int = Field(default=30, ge=1, le=180)


class FitnessScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    athlete_id: uuid.UUID
    fitness_index: float
    fatigue_risk: float
    trend: TrendValue
    recommendations: list[str]
    created_at: datetime
