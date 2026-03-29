# Файл: Pydantic-схемы для артериального давления.

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BloodPressureCreate(BaseModel):
    ts: datetime
    is_morning: bool = True
    systolic: int = Field(ge=0)
    diastolic: int = Field(ge=0)


class BloodPressureOut(BaseModel):
    id: uuid.UUID
    athlete_id: uuid.UUID
    ts: datetime
    is_morning: bool
    systolic: int | None
    diastolic: int | None

    class Config:
        from_attributes = True

