# Файл: Pydantic-схемы для тренировок.

import uuid
from datetime import date, time
from typing import Any

from pydantic import BaseModel, Field


class TrainingCreate(BaseModel):
    title: str
    training_type: str
    date: date
    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    distance_km: float | None = Field(default=None, ge=0)
    elevation_m: int | None = Field(default=None, ge=0)
    avg_hr: int | None = Field(default=None, ge=0)
    max_hr: int | None = Field(default=None, ge=0)
    calories: int | None = Field(default=None, ge=0)
    notes: str | None = None
    sport: str | None = None
    hr_zone: str | None = None
    hr_zone_minutes: dict[str, int] | None = None
    activity_types: list[str] | None = None
    exercises: list[dict[str, Any]] | None = None
    feeling_score: int | None = Field(default=None, ge=0, le=10)


class TrainingOut(BaseModel):
    id: uuid.UUID
    athlete_id: uuid.UUID
    title: str
    training_type: str
    date: date
    start_time: time | None
    duration_minutes: int | None
    distance_km: float | None
    elevation_m: int | None
    avg_hr: int | None
    max_hr: int | None
    calories: int | None
    notes: str | None
    sport: str | None
    hr_zone: str | None
    hr_zone_minutes: dict[str, int] | None
    activity_types: list[str] | None
    exercises: list[dict[str, Any]] | None
    feeling_score: int | None

    class Config:
        from_attributes = True
