import uuid
from datetime import date

from pydantic import BaseModel, Field


class AnalysisCreate(BaseModel):
    date: date
    title: str = Field(min_length=1, max_length=255)
    value: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class AnalysisOut(BaseModel):
    id: uuid.UUID
    athlete_id: uuid.UUID
    date: date
    title: str
    value: str | None
    notes: str | None

    class Config:
        from_attributes = True

