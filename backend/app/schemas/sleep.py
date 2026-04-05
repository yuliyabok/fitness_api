# Файл: Pydantic-схемы для сна.

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class SleepCreate(BaseModel):
    start_ts: datetime
    end_ts: datetime
    deep_minutes: int | None = Field(default=None, ge=0, le=1440)
    light_minutes: int | None = Field(default=None, ge=0, le=1440)
    rem_minutes: int | None = Field(default=None, ge=0, le=1440)
    source: str = "manual"

    @model_validator(mode="after")
    def validate_times(self) -> "SleepCreate":
        if self.end_ts <= self.start_ts:
            raise ValueError("end_ts must be after start_ts")
        return self


class SleepUpdate(SleepCreate):
    pass


class SleepOut(BaseModel):
    id: uuid.UUID
    athlete_id: uuid.UUID
    start_ts: datetime
    end_ts: datetime
    deep_minutes: int | None
    light_minutes: int | None
    rem_minutes: int | None
    source: str

    class Config:
        from_attributes = True
