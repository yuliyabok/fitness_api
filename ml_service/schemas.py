from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TrendValue = Literal["up", "stable", "down"]


class AthleteProfileContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    age: int | None = None
    gender: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    sport: str | None = None


class TrainingRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    date: date
    title: str | None = None
    training_type: str | None = None
    duration_minutes: float | None = None
    distance_km: float | None = None
    calories: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    feeling_score: float | None = None
    sport: str | None = None


class SleepRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    start_ts: datetime
    end_ts: datetime
    deep_minutes: float | None = None
    light_minutes: float | None = None
    rem_minutes: float | None = None
    source: str | None = None


class BloodPressureRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    ts: datetime
    systolic: float
    diastolic: float
    is_morning: bool | None = None


class Spo2Record(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    ts: datetime
    percentage: float
    source: str | None = None


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    athlete_id: str | None = None
    history_limit: int = Field(default=30, ge=1, le=365)
    window_size: int | None = Field(default=None, ge=7, le=365)
    date_from: date | None = None
    date_to: date | None = None
    profile: AthleteProfileContext = Field(default_factory=AthleteProfileContext)
    trainings: list[TrainingRecord] = Field(default_factory=list)
    sleep: list[SleepRecord] = Field(default_factory=list)
    blood_pressure: list[BloodPressureRecord] = Field(default_factory=list)
    spo2: list[Spo2Record] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_date_range(self) -> "PredictionRequest":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        return self


class PredictionResponse(BaseModel):
    fitness_index: float
    fatigue_risk: float
    trend: TrendValue
    recommendations: list[str] = Field(default_factory=list)
