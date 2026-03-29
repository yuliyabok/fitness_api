# Файл: Pydantic-схемы для цикла.

from datetime import date

from pydantic import BaseModel, Field


class CycleSettingsUpsert(BaseModel):
    cycle_length_days: int | None = Field(default=None, ge=0)
    period_length_days: int | None = Field(default=None, ge=0)


class CycleSettingsOut(BaseModel):
    cycle_length_days: int | None
    period_length_days: int | None


class CycleEventsReplace(BaseModel):
    kind: str
    dates: list[date]
