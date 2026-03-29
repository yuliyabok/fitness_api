# Файл: Pydantic-схемы для калорий.

import uuid
from datetime import date

from pydantic import BaseModel, Field


class CalorieCreate(BaseModel):
    date: date
    calories: int = Field(ge=0)
    notes: str | None = None


class CalorieOut(BaseModel):
    id: uuid.UUID
    athlete_id: uuid.UUID
    date: date
    calories: int
    notes: str | None

    class Config:
        from_attributes = True
